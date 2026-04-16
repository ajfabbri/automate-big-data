import logging
from pathlib import Path
from typing import Set, override
import re

from abd.core.infra.image import ImageBuilder
import abd.core.command as cmd
from abd.config.raw import BuildType
from abd.core.infra.container import ContainerBuild, Containers
from abd.core.infra.net import NetworkTask
from abd.core.context import App
from abd.core.infra.host import Container, Host
from abd.core.task.phases import Task, TaskId, PhaseType
from abd.core.project import ExitCode, Project

log = logging.getLogger(__name__)


class ClusterNodeBuild(ContainerBuild):
    CONTAINER_USERNAME = "hadoop"
    SHARED_VOL = "cluster-node-shared"
    PORT_SPARK_UI = 4040  # Ensure Dockerfile.cluster-node matches
    PORT_SPARK_MASTER = 8088

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
        err = Containers.ensure_volume(self.SHARED_VOL) if not is_dryrun else 0
        if err != 0:
            log.error(f"Failed to create shared volume {self.SHARED_VOL}.")
            return err
        ports = ""
        if index == 0:
            # master node
            ports += f" -p 127.0.0.1:{self.PORT_SPARK_UI}:8080"
            ports += f" -p 127.0.0.1:{self.PORT_SPARK_MASTER}:7077"

        run_cmd = f"""
        docker run --rm=true
            -v {self.SHARED_VOL}:{self.docker_home_dir}/shared
            --network {self.app.container_network}
            --name "{container_name}"
            --hostname "{container_name}" {ports}
            -dit
            {self.get_image_name()}
        """
        ret = 0
        if container_name in Containers.list():
            log.info(f"Container {container_name} already running.")
        else:
            ret = cmd.run_print(run_cmd, cwd=Project.get_project_root(), is_dryrun=is_dryrun)
        if ret == 0:
            # TODO return running host instead of mutating app context directly?
            self.app.hosts.add(Container(container_name))
        return ret

    def _resolve_container_path(self, path: str | None = None) -> Path:
        dest_path = path if path else self.docker_home_dir
        # substitute $HOME for container's home dir
        return Path(dest_path.replace("$HOME", self.docker_home_dir))

    # TODO move to Host.put_file()
    def copy_to_containers(self, local_path: Path, container_path: str | None = None,
                           is_dryrun=False) -> ExitCode:
        err = 0
        dest_path = self._resolve_container_path(container_path)
        for host in self.get_deploy_hosts(self.deploy_cfg):
            err = host.put_file(local_path, chown=self.CONTAINER_USERNAME,
                                host_dir=dest_path, is_dryrun=is_dryrun)
            if err != 0:
                log.error(f"Failed to copy {local_path} to {host.get_name()}:{dest_path}")
                break
        return err

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
    def check_hadoop_install(self, required_version: str | None = None) -> bool:
        any_missing = False
        for host in self.get_deploy_hosts(self.deploy_cfg):
            (err, output) = host.run_command(r"hadoop version | head -1 | awk '{ print $2}'")
            if err != 0:
                any_missing = True
                log.debug(f"check_hadoop_install({host}) -> False")
                continue
            installed = output.strip()
            if required_version and installed != required_version:
                any_missing = True
                log.debug(f"check_hadoop_install({host}) -> version mismatch: "
                          + f"{installed} != {required_version})")
        return not any_missing

    def _validate_aws_vers(self, version: str) -> ExitCode:
        pat = r"^\d+\.\d+\.\d+$"
        if not re.match(pat, version):
            log.error(f"Invalid AWS SDK version {version} (expected format X.Y.Z)")
            return 1
        return 0

    def _set_optional_tools(self, val="hadoop-aws,hadoop-azure", is_dryrun=False) -> ExitCode:
        script = Project.get_project_root() / "abd/scripts/ensure-line-in-file.sh"
        for host in self.get_deploy_hosts(self.deploy_cfg):
            err = host.put_file(script, chown=self.CONTAINER_USERNAME, chmod="750",
                                host_dir=Path(self.docker_home_dir), is_dryrun=is_dryrun)
            if err != 0:
                return err
            henv_path = "/opt/hadoop/etc/hadoop/hadoop-env.sh"
            line = f"export HADOOP_OPTIONAL_TOOLS=\"{val}\""
            cmd = f"{self.docker_home_dir}/ensure-line-in-file.sh {henv_path} '{line}'"
            (err, out) = host.run_command(cmd, is_dryrun=is_dryrun)
            if err != 0:
                log.error(f"Failed to set HADOOP_OPTIONAL_TOOLS in {host.get_name()}: {out}")
                return err
        return 0

    def install_hadoop_aws(self, is_dryrun=False) -> ExitCode:
        """ Hadoop releases no longer include AWS SDK depencency; it is too huge.
        This function derives the required version and installs it. """

        some_host = self.get_deploy_hosts(self.deploy_cfg).pop()
        # 1. figure out which versions of jars we need
        ver_cmd = "hadoop version | head -1 | awk '{print $2}'"
        (err, output) = some_host.run_command(ver_cmd)
        if err != 0:
            log.error(f"Failed to get hadoop version on {some_host.get_name()}: {output}")
            return err
        vers = output.strip()

        sdk_ver_cmd = "grep awssdk.bundle /opt/hadoop/LICENSE-binary | cut -d ':' -f 3"
        (err, sdk_vers) = some_host.run_command(sdk_ver_cmd)
        if err != 0:
            log.error(f"Failed to get AWS SDK version {some_host.get_name()}: {sdk_vers}")
            return err
        err = self._validate_aws_vers(sdk_vers)
        if err != 0:
            return err
        log.info(f"ℹ️ Found hadoop {vers}, aws-java-sdk-bundle {sdk_vers}")

        is_first = True
        for host in self.get_deploy_hosts(self.deploy_cfg):
            if is_first:
                mvn_cmd = f"mvn dependency:get -Dartifact=software.amazon.awssdk:bundle:{sdk_vers}"
                (err, _) = host.run_command(mvn_cmd, is_dryrun=is_dryrun)
                if err != 0:
                    log.error(f"Failed to download AWS SDK bundle in {host.get_name()}: {sdk_vers}")
                    return err
                cmd = f"find {self.docker_home_dir}/.m2/repository/software/amazon/awssdk/bundle"
                cmd += f"/{sdk_vers} -name bundle-{sdk_vers}.jar"
                (err, out) = host.run_command(cmd, is_dryrun=is_dryrun)
                if err != 0:
                    log.error(f"Failed to find AWS SDK bundle jar in {host.get_name()}: {sdk_vers}")
                    return err
                jar_path = out.split("\n")[0]
                cmd = f"cp {jar_path} {self.docker_home_dir}/shared/"
                (err, out) = host.run_command(cmd, is_dryrun=is_dryrun)
                if err != 0:
                    log.error(f"Fail copying AWS SDK jar to shared/ {host.get_name()}: {out}")
                    return err
                is_first = False

            cmd = f"cp {self.docker_home_dir}/shared/bundle-{sdk_vers}.jar"
            cmd += " /opt/hadoop/share/hadoop/common/lib"
            (err, out) = host.run_command(cmd, is_dryrun=is_dryrun)
            if err != 0:
                log.error(f"Fail copying AWS SDK jar from shared/ {host.get_name()}: {out}")
                return err
            err = self._set_optional_tools()
            if err != 0:
                return err
        return 0

    def install_hadoop(self, local_tar: Path, is_dryrun: bool) -> ExitCode:
        ret = self.copy_to_containers(local_tar, is_dryrun=is_dryrun)

        for i in range(self.deploy_cfg.num_nodes):  # type: ignore
            host = self.get_container_name(i)
            # move any existing /opt/hadoop
            c = f"""
            docker exec {host} bash -c
            'if [ -d /opt/hadoop ]; then
              if [ -d /opt/hadoop-prev ]; then
                sudo rm -rf /opt/hadoop-prev;
              fi;
              sudo mv /opt/hadoop /opt/hadoop-prev;
              sudo mkdir -p /opt/hadoop;
              sudo chown {self.CONTAINER_USERNAME}:{self.CONTAINER_USERNAME} /opt/hadoop; fi'
            """
            (ret, output) = cmd.run(c, is_dryrun=is_dryrun)
            if ret != 0:
                log.error(f"Failed to move existing hadoop {host}: {output}")
                return ret
            c = f"""
            docker exec {host} bash -c
            'cd {self.docker_home_dir} &&
             tar -xzf {local_tar.name} --strip-components=1 -C /opt/hadoop'
            """
            (ret, output) = cmd.run(c, is_dryrun=is_dryrun)
            if ret != 0:
                log.error(f"Failed to extract hadoop in {host}: {output}")
                return ret
            log.info(f"✅ Extracted {local_tar.name} to {host}")

        # Note: this could be a separate task
        # TODO add optional `staging_repo` to build.hadoop config
        return self.install_hadoop_aws(is_dryrun)

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
    task_id = TaskId("cluster-node", PhaseType.BUILD)

    @override
    def dependencies(self) -> Set[TaskId]:
        # XXX TODO? return {HadoopBuild.HadoopBuildTask.task_id}
        return set()

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        nbuild = ClusterNodeBuild(arg)
        err = nbuild.build_image(is_cached, is_dryrun)
        # TODO make up mind on where exceptions versus error codes live
        if err != 0:
            raise RuntimeError("Failed to build cluster node image.")


class NodeDeployTask(Task):
    task_id = TaskId("start-cluster-nodes", PhaseType.DEPLOY)

    @override
    def dependencies(self) -> Set[TaskId]:
        return {NodeBuildTask.task_id, NetworkTask.task_id}

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        nbuild = ClusterNodeBuild(arg)
        self.node_deploy = arg.get_config().get_deploy_cfg("cluster-node")
        for i in range(self.node_deploy.num_nodes):
            ret = nbuild.run_container(is_dryrun, i)
            if ret != 0:
                raise RuntimeError("Failed to run cluster node container.")


class SharedSsh(Task):
    task_id = TaskId("shared-ssh", PhaseType.DEPLOY)

    @override
    def dependencies(self) -> Set[TaskId]:
        return {NodeDeployTask.task_id}

    def _is_ssh_key_setup(self, host: Host) -> bool:
        c = "ls .ssh/id_rsa.pub"
        (err, _) = host.run_command(c)
        return err == 0

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        node_deploy = arg.get_config().get_deploy_cfg("cluster-node")
        is_first = True
        for host in ClusterNodeBuild.get_deploy_hosts(node_deploy):
            if is_cached and self._is_ssh_key_setup(host):
                log.info(f"[skipped] SSH key already set up in {host.get_name()}.")
                is_first = False
            elif is_first:
                (err, out) = host.run_command("ssh-keygen -t rsa -f ~/.ssh/id_rsa -q -N ''",
                                              is_dryrun=is_dryrun)
                if err != 0:
                    e = f"Failed to generate ssh key in {host.get_name()}: {out}"
                    log.error(e)
                    raise RuntimeError(e)

                (err, out) = host.run_command("cp ~/.ssh/id_rsa* ~/shared/",
                                              is_dryrun=is_dryrun)
                if err != 0:
                    e = f"Failed to copy ssh keys to shared/ in {host.get_name()}: {out}"
                    log.error(e)
                    raise RuntimeError(e)
                (err, out) = host.run_command("cat ~/.ssh/id_rsa.pub >> "
                                              + "~/shared/authorized_keys")
                if err != 0:
                    e = f"Failed to set up authorized_keys in {host.get_name()}: {out}"
                    log.error(e)
                    raise RuntimeError(e)

                (err, out) = host.run_command("cp ~/shared/authorized_keys ~/.ssh/")
                if err != 0:
                    e = f"Failed to copy authorized_keys in {host.get_name()}: {out}"
                    log.error(e)
                    raise RuntimeError(e)
                is_first = False
            else:
                (err, out) = host.run_command("mkdir -p ~/.ssh/")
                if err != 0:
                    e = f"Failed to create .ssh directory in {host.get_name()}: {out}"
                    log.error(e)
                    raise RuntimeError(e)

                (err, out) = host.run_command("cp ~/shared/id_rsa* ~/.ssh/",
                                              is_dryrun=is_dryrun)
                if err != 0:
                    e = f"Failed to copy ssh keys from shared/ in {host.get_name()}: {out}"
                    log.error(e)
                    raise RuntimeError(e)

                (err, out) = host.run_command("cp ~/shared/authorized_keys ~/.ssh/")
                if err != 0:
                    e = f"Failed to copy authorized_keys from shared/ in {host.get_name()}: {out}"
                    log.error(e)
                    raise RuntimeError(e)
            (err, _) = host.run_command("sudo service ssh start")
            if err != 0:
                e = f"Failed to start ssh service in {host.get_name()}"
                log.error(e)
                raise RuntimeError(e)
