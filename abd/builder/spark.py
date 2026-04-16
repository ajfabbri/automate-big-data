import logging
from pathlib import Path
from typing import Set, override
from abd.builder.hadoop import HADOOP_HOME, InstallHadoop
from abd.config.raw import BuildCfg, BuildType
from abd.container.cluster_node import ClusterNodeBuild, SharedSsh
from abd.core.context import App
from abd.core.download import URI, Downloader
from abd.core.infra.host import Host
from abd.core.task.phases import PhaseType, Task, TaskId
from abd.core.project import Project
from abd.core.util import unwrap

SPARK_HOME = Path("/opt/spark")
log = logging.getLogger(__name__)


class BuildSpark:
    # TODO support for task inputs / outputs plumbed through dependency graph
    # then make this a separate task
    def __init__(self, cfg: BuildCfg):
        self.build_cfg = cfg.get_tar_build()

    def fetch(self) -> Path:
        """ Download configured spark build, returning a local path for the tar file. """
        dl = Downloader(URI(self.build_cfg.tar_path), Project.get_build_dir())
        return dl.fetch()


class InstallSpark(Task):
    task_id = TaskId("spark", PhaseType.DEPLOY)

    @override
    def dependencies(self) -> Set[TaskId]:
        return {InstallHadoop.task_id, SharedSsh.task_id}

    def _build_dir(self) -> Path:
        return Project.get_build_dir() / "spark"

    def _install_host(self, host: Host, tar_path: Path, install_dir: Path,
                      is_cached: bool, is_dryrun: bool):

        if not is_cached:
            host.run_throws(f"if [ -d {SPARK_HOME} ]; then sudo rm -rf {SPARK_HOME}; fi",
                            is_dryrun=is_dryrun)
        cmd = f"""
        if [ ! -d {SPARK_HOME} ]; then
            sudo mkdir -p {SPARK_HOME};
            sudo chown -R hadoop:hadoop {SPARK_HOME};
        fi
        """
        host.run_throws(cmd, is_dryrun=is_dryrun)
        err = host.put_file(tar_path, host_dir=install_dir,
                            chown="hadoop:hadoop", is_dryrun=is_dryrun)
        if err != 0:
            raise RuntimeError(f"Failed to copy Spark tar to host {host.get_name()}")

        host_tar_path = install_dir / tar_path.name
        host.run_throws(f"tar -xzf {host_tar_path} -C {SPARK_HOME} --strip-components=1",
                        is_dryrun=is_dryrun)

        host.put_file(self._build_dir() / "workers", chown="hadoop:hadoop",
                      chmod="644", host_dir=SPARK_HOME / "conf", is_dryrun=is_dryrun)
        host.put_file(self._build_dir() / "spark-env.sh", chown="hadoop:hadoop",
                      chmod="755", host_dir=SPARK_HOME / "conf", is_dryrun=is_dryrun)

    def _create_workers_file(self, path: Path, workers: list[Host]):
        with open(path, "w") as f:
            for w in workers:
                f.write(w.get_name() + "\n")

    def _create_env_file(self, path: Path):
        contents = f"""export SPARK_HOME={SPARK_HOME}
export PATH=$PATH:$SPARK_HOME/bin:$SPARK_HOME/sbin
export HADOOP_CONF_DIR={HADOOP_HOME}/etc/hadoop
export SPARK_DIST_CLASSPATH=$(hadoop classpath)
"""
        with open(path, "w") as f:
            f.write(contents)

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        build_cfg = arg.get_config().get_build_cfg(BuildType.SPARK)
        if not build_cfg:
            raise RuntimeError("Spark build config not found")

        # fetch build
        build = BuildSpark(build_cfg)
        tar_path = build.fetch()

        # Get sorted list of hosts, first one is master
        deploy_cfg = arg.get_config().get_deploy_cfg("cluster-node")
        install_path = unwrap(deploy_cfg.get_install(BuildType.SPARK)).path
        hosts = list(ClusterNodeBuild.get_deploy_hosts(deploy_cfg))
        hosts.sort(key=lambda h: h.get_name())

        # create spark conf files
        self._build_dir().mkdir(parents=True, exist_ok=True)
        self._create_workers_file(self._build_dir() / "workers", hosts)
        self._create_env_file(self._build_dir() / "spark-env.sh")

        # install on hosts
        for host in hosts:
            self._install_host(host, tar_path, Path(install_path), is_cached, is_dryrun)

        master = hosts[0]
        master.run_throws(f"{SPARK_HOME}/sbin/stop-all.sh", is_dryrun=is_dryrun)
        master.run_throws(f"{SPARK_HOME}/sbin/start-all.sh", is_dryrun=is_dryrun)
        log.info("✅ Spark installed successfully. Master UI at " +
                 f"http://127.0.0.1:{ClusterNodeBuild.PORT_SPARK_UI}")
