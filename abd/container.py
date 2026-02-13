from pathlib import Path
import logging
from typing import Protocol, override
import typing

import abd.command as cmd
from abd.config import Config
from abd.context import App
from abd.project import ExitCode, Project
log = logging.getLogger(__name__)

HADOOP_BASE_DOCKERFILE = Path("Dockerfile_ubuntu_24")
HADOOP_BASE_DOCKERFILE_ARM = Path("Dockerfile_ubuntu_24_aarch64")
HADOOP_BUILD_CONTAINER = "hadoop-build"


class Containers:
    def __init__(self, app: App, cfg: Config):
        self.app = app
        self.cfg = cfg

    @classmethod
    def list(cls, name_filter: str | None = None) -> list[str]:
        filter_str = f" --filter {name_filter}" if name_filter else ""
        c = f"docker ps --format '{{{{.Names}}}}'{filter_str}"
        output = cmd.run_throws(c)
        return output.strip().splitlines()

    @classmethod
    def list_images(cls, name_filter: str | None = None) -> typing.List[str]:  # pyright quirk
        filter_str = f" --filter reference={name_filter}" if name_filter else ""
        c = f"docker images --format '{{{{.Repository}}}}:{{{{.Tag}}}}' {filter_str}"
        output = cmd.run_throws(c)
        return output.strip().splitlines()

    def attach(self, container_name: str) -> ExitCode:
        (ret, output) = cmd.run("which docker")
        if ret != 0:
            log.error("Docker not found, cannot attach to container.")
            return ret
        docker_path = output.strip()
        c = [docker_path,  "exec", "-it", container_name, "bash"]
        return cmd.run_raw(c)

    # def _start(self, image_name: str, container_name: str, extra_args: str = "") -> ExitCode:
    #     c = f"docker run -d --rm --name {container_name} {extra_args} {image_name}
    #         tail -f /dev/null"
    #     return cmd.run_throws(c)

    def run_all(self, is_cached: bool) -> ExitCode:
        # Initial stab:
        # 1. start hadoop build container
        if not self.cfg.hadoop:
            log.error("Hadoop not enabled in config, cannot run containers.")
            return 1

        hbuild = HadoopBuild(self.app, self.cfg)
        # local_cloudstore = Path(self.cfg.hadoop.cloudstore_git_path)

        # From hadoop.git:
        # By mapping the .m2 directory you can do an mvn install from
        # within the container and use the result on your normal
        # system.  And this also is a significant speedup in subsequent
        # builds because the dependencies are downloaded only once.
        if not is_cached:
            ret = hbuild.run_container()
            if ret != 0:
                return ret

            # 2. run build script in container
            ret = hbuild.build_in_container()
            if ret != 0:
                return ret

        # XXX TODO skip on cached if exists
        nbuild = ClusterNodeBuild(self.app, self.cfg)
        for i in range(self.cfg.hadoop.num_nodes):
            ret = nbuild.run_container(i)
            if ret != 0:
                return ret

        # 3. start hadoop node containers

        # 4. Deploy build(s) to node containers
        jars = hbuild.find_hadoop_jars()
        if not jars:
            log.error("No hadoop jars found after build.")
            return 1
        jar = jars[0]
        log.info(f"Using hadoop jar: {jar}")
        # 5. Run tests in node containers
        return 0

    def stop(self, filter: str = "all") -> ExitCode:
        filter_str = ""
        if filter != all and filter != "":
            filter_str = f"--filter name={filter}"
        log.info(f"Stopping containers with filter: '{filter}'")
        c = f"docker ps -q {filter_str}"
        try:
            output = cmd.run_throws(c)
            container_ids = output.strip().splitlines()
            for cid in container_ids:
                cmd.run_throws(f"docker stop {cid}")
        except Exception as e:
            log.error(f"Failed to stop containers: {e}")
            return 1
        return 0


class ContainerBuild(Protocol):
    """ Common interface for container image build and run classes. """
    cfg: Config
    app: App
    user: str
    uid: int
    gid: int
    docker_home_dir: str
    local_home: Path

    def __init__(self, app: App, cfg: Config):
        self.cfg = cfg
        self.app = app
        self.user = app.sysinfo.get_user()
        self.uid = app.sysinfo.get_uid()
        self.gid = app.sysinfo.get_gid()
        self.docker_home_dir = f"/home/{self.user}"
        self.local_home = app.sysinfo.get_user_home()

    def get_build_image_name(self) -> str:
        ...

    def build_image(self) -> ExitCode:
        ...

    def run_container(self, index: int = 0) -> ExitCode:
        ...


class HadoopBuild(ContainerBuild):
    """ Support for building a container to build hadoop in. """

    @override
    def __init__(self, app: App, cfg: Config):
        super().__init__(app, cfg)
        if cfg.hadoop:
            self.h_cfg = cfg.hadoop
        else:
            raise Exception("Hadoop config is required for HadoopBuild.")
        self.local_hadoop = Path(self.h_cfg.hadoop_git_path).resolve(strict=True)

    @override
    def get_build_image_name(self) -> str:
        # just throw on error; should be unlikely at this point
        return f"hadoop-build-{self.user}"

    @override
    def build_image(self) -> ExitCode:
        # Use upstream hadoop container definition for a build machine

        # Build base image
        hadoop_path = Path(self.h_cfg.hadoop_git_path)
        if self.app.sysinfo.get_cpu_arch() in ["arm64", "aarch64"]:
            docker_file = HADOOP_BASE_DOCKERFILE_ARM
        else:
            docker_file = HADOOP_BASE_DOCKERFILE
        base_dockerfile = hadoop_path / "dev-support" / "docker" / docker_file
        base_builder = ImageBuilder("hadoop-build", base_dockerfile.parent)
        result = base_builder.build_dockerfile(docker_file)
        if result != 0:
            log.error(f"Failed to build base image from {base_dockerfile}")
            return result

        # build user-specific image
        docker_input = f"""
        FROM hadoop-build
        RUN rm -f /var/log/faillog /var/log/lastlog
        RUN userdel -r $(getent passwd {self.uid} | cut -d: -f1) 2>/dev/null || :
        RUN groupadd --non-unique -g {self.gid} {self.user}
        RUN useradd -g {self.gid} -u {self.uid} -k /root -m {self.user} -d "/home/{self.user}"
        RUN echo "{self.user} ALL=NOPASSWD: ALL" > "/etc/sudoers.d/hadoop-build-{self.uid}"
        ENV HOME="/home/{self.user}"
        """
        u_builder = ImageBuilder(self.get_build_image_name(), base_dockerfile.parent)
        return u_builder.build_input(docker_input)

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        if index != 0:
            log.warning("Hadoop build container is single-instance; ignoring index.")

        build_image = self.get_build_image_name()
        # local_cloudstore = Path(self.h_cfg.hadoop.cloudstore_git_path)

        # From hadoop.git:
        # By mapping the .m2 directory you can do an mvn install from
        # within the container and use the result on your normal
        # system.  And this also is a significant speedup in subsequent
        # builds because the dependencies are downloaded only once.

        run_cmd = f"""
        docker run --rm=true
                -v "{self.local_hadoop}:{self.docker_home_dir}/hadoop"
                -w "{self.docker_home_dir}/hadoop"
                -v "{self.local_home}/.m2:{self.docker_home_dir}/.m2"
                -v "{self.local_home}/.gnupg:{self.docker_home_dir}/.gnupg"
                -u "{self.uid}"
                --name "{HADOOP_BUILD_CONTAINER}"
                -dit
                {build_image}
        """
        if HADOOP_BUILD_CONTAINER in Containers.list():
            log.info(f"Container {HADOOP_BUILD_CONTAINER} already running.")
            return 0
        else:
            return cmd.run_with_status(self.app, run_cmd, cwd=self.local_hadoop)

    def build_in_container(self) -> ExitCode:
        build_cmd = f"""
        docker exec hadoop-build bash -c
        "cd {self.docker_home_dir}/hadoop && mvn package -Pdist,native -DskipTests -Dtar"
        """
        return cmd.run_with_status(self.app, build_cmd)

    def find_hadoop_jars(self) -> list[Path]:
        dist_dir = Path(self.docker_home_dir) / "hadoop" / "hadoop-dist" / "target"
        list_cmd = f"docker exec hadoop-build bash -c 'find {dist_dir} -name hadoop-common-*.jar'"
        (exit_code, output) = cmd.run(list_cmd)
        if exit_code != 0:
            log.error(f"Failed to list hadoop jars in container: {output}")
            return []

        return [Path(line.strip()) for line in output.splitlines() if line.strip()]


class ClusterNodeBuild(ContainerBuild):

    @override
    def get_build_image_name(self) -> str:
        return f"cluster-node-{self.user}"

    @override
    def build_image(self) -> ExitCode:
        root = Project.get_project_root()
        dockerfile = root / "Dockerfile.cluster-node"
        img_builder = ImageBuilder(self.get_build_image_name(), root)
        return img_builder.build_dockerfile(dockerfile)

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        container_name = f"cluster-node-{index}"
        run_cmd = f"""
        docker run --rm=true -u "{self.uid}"
            --name "{container_name}"
            -dit
            {self.get_build_image_name()}
        """
        if container_name in Containers.list():
            log.info(f"Container {container_name} already running.")
            return 0
        else:
            return cmd.run_with_status(self.app, run_cmd, cwd=Project.get_project_root())


class ImageBuilder:
    def __init__(self, image_name: str, build_path: Path):
        self.image_name = image_name
        self.build_path = build_path.resolve(strict=True)

    def build_dockerfile(self, dockerfile: Path) -> ExitCode:
        log.info(f"Building image {self.image_name} from {dockerfile}...")
        command = f"docker build -t {self.image_name} -f {dockerfile} ."
        (exit_code, output) = cmd.run(command, cwd=self.build_path)
        log.debug(f"Build output: {output}")
        return exit_code

    def build_input(self, input: str) -> ExitCode:
        log.info(f"Building image {self.image_name} from input...")
        log.debug(f"Input: {input}")
        command = f"docker build -t {self.image_name} -"
        (exit_code, _) = cmd.run(command, cwd=self.build_path, input=input)
        return exit_code
