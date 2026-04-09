import logging
from pathlib import Path
from typing import Set, override
from abd.builder.hadoop import InstallHadoop
from abd.config.raw import BuildCfg, BuildType
from abd.container.container import ContainerBuild
from abd.context import App
from abd.download import URI, Downloader
from abd.host import Host
from abd.job.phases import PhaseType, Task, TaskId
from abd.project import Project

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
        return {InstallHadoop.task_id}

    def _install_host(self, host: Host, tar_path: Path, is_cached: bool, is_dryrun: bool):
        if not is_cached:
            host.run_throws(f"if [ -d {SPARK_HOME} ]; then sudo rm -rf {SPARK_HOME}; fi",
                            is_dryrun=is_dryrun)
        cmd = f"""
        if [ ! -d {SPARK_HOME} ]; then
            sudo mkdir -p {SPARK_HOME}
            sudo chown -R hadoop:hadoop {SPARK_HOME}
        fi
        """
        host.run_throws(cmd, is_dryrun=is_dryrun)
        err = host.put_file(tar_path, chown="hadoop:hadoop", is_dryrun=is_dryrun)
        if err != 0:
            raise RuntimeError(f"Failed to copy Spark tar to host {host.get_name()}")

        host.run_throws(f"tar -xzf {tar_path} -C {SPARK_HOME} --strip-components=1",
                        is_dryrun=is_dryrun)

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        build_cfg = arg.get_config().get_build_cfg(BuildType.SPARK)
        if not build_cfg:
            raise RuntimeError("Spark build config not found")

        build = BuildSpark(build_cfg)
        tar_path = build.fetch()
        deploy_cfg = arg.get_config().get_deploy_cfg("spark")
        for host in ContainerBuild.get_deploy_hosts(deploy_cfg):
            self._install_host(host, tar_path, is_cached, is_dryrun)
