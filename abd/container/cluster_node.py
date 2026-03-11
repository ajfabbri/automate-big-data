import logging
from pathlib import Path
from typing import Set, override

from abd.builder.image import ImageBuilder
import abd.command as cmd
from abd.config.raw import BuildType
from abd.container.container import ContainerBuild, Containers
from abd.container.net import NetworkTask
from abd.context import App
from abd.host import Container
from abd.job.phases import Task, TaskId, PhaseType
from abd.project import ExitCode, Project

log = logging.getLogger(__name__)


class ClusterNodeBuild(ContainerBuild):
    CONTAINER_USERNAME = "hadoop"

    @override
    def __init__(self, app: App):
        super().__init__(app)
        cfg = app.get_config()
        self.docker_home_dir = f"/home/{self.CONTAINER_USERNAME}"
        self.deploy_cfg = cfg.get_deploy_cfg("cluster-node")
        self.hadoop_cfg = cfg.get_build_cfg(BuildType.HADOOP)
        self.cloudstore_cfg = cfg.get_build_cfg(BuildType.CLOUDSTORE)

    @override
    def get_image_name(self) -> str:
        return f"cluster-node-{self.user}"

    # TODO separate container image building from instance info
    @override
    @classmethod
    def get_container_name(cls, index: int = 0) -> str:
        return f"cluster-node-{index}"

    @override
    def build_image(self, is_cached: bool, is_dryrun: bool) -> ExitCode:
        if is_cached:
            images = Containers.list_images()
            if self.get_image_name() in images:
                log.info(f"cached: Image {self.get_image_name()} exists, skipping build.")
                return 0
        root = Project.get_project_root()
        dockerfile = root / "Dockerfile.cluster-node"
        ibuild = ImageBuilder(self.get_image_name(), root)
        return ibuild.build_dockerfile(dockerfile, is_dryrun,
                                       [f"USERNAME={self.CONTAINER_USERNAME}"])

    @override
    def run_container(self, is_dryrun: bool, index: int = 0) -> ExitCode:
        container_name = self.get_container_name(index)
        run_cmd = f"""
        docker run --rm=true
            --network {self.app.container_network}
            --name "{container_name}"
            --hostname "{container_name}"
            -dit
            {self.get_image_name()}
        """
        ret = 0
        if container_name in Containers.list():
            log.info(f"Container {container_name} already running.")
        else:
            ret = cmd.run_print(run_cmd, cwd=Project.get_project_root())
        if ret == 0:
            # TODO return running host instead of mutating app context directly?
            self.app.hosts.add(Container(container_name))
        return ret

    def _resolve_container_path(self, path: str | None = None) -> str:
        dest_path = path if path else self.docker_home_dir
        # substitute $HOME for container's home dir
        return dest_path.replace("$HOME", self.docker_home_dir)

    # TODO move to Host.put_file()
    def copy_to_containers(self, local_path: Path, container_path: str | None = None,
                           is_dryrun=False) -> ExitCode:
        ret = 0
        dest_path = self._resolve_container_path(container_path)
        for i in range(self.deploy_cfg.num_nodes):  # type: ignore
            container_name = f"cluster-node-{i}"
            c = f"docker cp {local_path} {container_name}:{dest_path}"
            (ret, output) = cmd.run(c, is_dryrun=is_dryrun)
            if ret != 0:
                log.error(f"Failed to copy {local_path} to {container_name}: {output}")
                return ret
            c = f"docker exec {container_name} bash -c 'sudo chown -R {self.CONTAINER_USERNAME}:" \
                f"{self.CONTAINER_USERNAME} {dest_path}'"
            (ret, output) = cmd.run(c, is_dryrun=is_dryrun)
            if ret != 0:
                log.error(f"Failed to set ownership of {dest_path} in {container_name}: {output}")
                return ret
        return 0

    def find_in_containers(self, glob: str, container_path: str | None = None) -> str | None:
        """ Find the first path matching 'glob' and return it if same for all containers. """
        dest_path = self._resolve_container_path(container_path)
        found: str | None = None
        for i in range(self.deploy_cfg.num_nodes):  # type: ignore
            container_name = f"cluster-node-{i}"
            c = f"docker exec {container_name} bash -c 'ls -t1 {dest_path}/{glob} | tail -1'"
            (ret, output) = cmd.run(c)
            if ret == 0:
                host_path = output.strip()
                # must be same path on all hosts
                if not found:
                    found = host_path
                elif host_path != found:
                    e = f"{dest_path} not found (one host had {found} "
                    e += f"but {container_name} has {host_path})"
                    log.info(e)
                    return None
            else:
                log.info(f"Failed to find {dest_path} in {container_name}: {output}")
                return None
        return found

    # TODO move to hadoop module
    def check_hadoop_install(self) -> bool:
        any_missing = False
        for i in range(self.deploy_cfg.num_nodes):  # type: ignore
            host = self.get_container_name(i)
            c = f"""
            docker exec {host} bash -c
            'if [ ! -f /opt/hadoop/bin/hadoop ]; then exit 1; fi'
            """
            (ret, _) = cmd.run(c)
            if ret != 0:
                any_missing = True
                log.debug(f"check_hadoop_install({host}) -> False")
        return not any_missing

    def install_hadoop(self, local_path: Path, is_dryrun: bool):
        ret = self.copy_to_containers(local_path)

        for i in range(self.deploy_cfg.num_nodes):  # type: ignore
            host = self.get_container_name(i)
            c = f"""
            docker exec {host} bash -c
            'cd {self.docker_home_dir} &&
             tar -xzf {local_path.name} --strip-components=1 -C /opt/hadoop'
            """
            (ret, output) = cmd.run(c, is_dryrun=is_dryrun)
            if ret != 0:
                log.error(f"Failed to extract hadoop in {host}: {output}")
                return ret
            log.info(f"✅ Extracted {local_path.name} to {host}")
        return 0

    def check_cloudstore_jar(self) -> bool:
        any_missing = False
        for i in range(self.deploy_cfg.num_nodes):  # type: ignore
            host = self.get_container_name(i)
            c = f"""
            docker exec {host} bash -c
            'if ! ls {self.docker_home_dir}/cloudstore-*.jar > /dev/null 2>&1; then exit 1; fi'
            """
            (ret, _) = cmd.run(c)
            if ret != 0:
                any_missing = True
                log.debug(f"check_cloudstore_jar({host}) -> False")
        return not any_missing


class NodeBuildTask(Task):
    phase_id = TaskId("cluster-node", PhaseType.BUILD)

    @override
    def dependencies(self) -> Set[TaskId]:
        # XXX TODO? return {HadoopBuild.HadoopBuildTask.phase_id}
        return set()

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        nbuild = ClusterNodeBuild(arg)
        err = nbuild.build_image(is_cached, is_dryrun)
        # TODO make up mind on where exceptions versus error codes live
        if err != 0:
            raise RuntimeError("Failed to build cluster node image.")


class NodeDeployTask(Task):
    phase_id = TaskId("start-cluster-nodes", PhaseType.DEPLOY)

    @override
    def dependencies(self) -> Set[TaskId]:
        return {NodeBuildTask.phase_id, NetworkTask.phase_id}

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        nbuild = ClusterNodeBuild(arg)
        self.node_deploy = arg.get_config().get_deploy_cfg("cluster-node")
        for i in range(self.node_deploy.num_nodes):
            ret = nbuild.run_container(is_dryrun, i)
            if ret != 0:
                raise RuntimeError("Failed to run cluster node container.")
