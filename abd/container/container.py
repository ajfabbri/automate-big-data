from pathlib import Path
import logging
import tempfile
from typing import Protocol, override
import typing

import abd.command as cmd
from abd.config import Config
from abd.container.hadoop_build import HadoopBuild
from abd.context import App
from abd.project import ExitCode, Project
log = logging.getLogger(__name__)

HADOOP_BASE_DOCKERFILE = Path("Dockerfile_ubuntu_24")
HADOOP_BASE_DOCKERFILE_ARM = Path("Dockerfile_ubuntu_24_aarch64")
HADOOP_BUILD_CONTAINER = "hadoop-build"


class Containers:
    """ Utility methods for finding and managing containers. """
    def __init__(self, app: App, cfg: Config):
        self.app = app
        self.cfg = cfg

    @classmethod
    def list(cls, name_filter: str | None = None) -> list[str]:
        filter_str = f' --filter "name={name_filter}"' if name_filter else ""
        c = f"docker ps --format '{{{{.Names}}}}'{filter_str}"
        output = cmd.run_throws(c)
        return output.strip().splitlines()

    @classmethod
    def list_images(cls, name_filter: str | None = None) -> typing.List[str]:  # pyright quirk
        filter_str = f" --filter reference={name_filter}" if name_filter else ""
        c = f"docker images --format '{{{{.Repository}}}}:{{{{.Tag}}}}' {filter_str}"
        output = cmd.run_throws(c)
        return output.strip().splitlines()

    @classmethod
    def attach(cls, container_name: str) -> ExitCode:
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

        if not is_cached:
            ret = hbuild.run_container()
            if ret != 0:
                return ret

            # 2. run build script in container
            ret = hbuild.build_in_container()
            if ret != 0:
                return ret

        # 3. start hadoop node containers
        nbuild = ClusterNodeBuild(self.app, self.cfg)
        for i in range(self.cfg.hadoop.num_nodes):
            ret = nbuild.run_container(i)
            if ret != 0:
                return ret

        # 4. Deploy build(s) to node containers
        with tempfile.TemporaryDirectory() as tmpdir:
            (err, path) = hbuild.fetch_hadoop_build(Path(tmpdir))
            if err != 0:
                return err
            if not path:
                return 1

            ret = nbuild.copy_to_containers(path)
            if ret != 0:
                return ret

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


class ClusterNodeBuild(ContainerBuild):
    CONTAINER_USERNAME = "hadoop"

    @override
    def __init__(self, app: App, cfg: Config):
        super().__init__(app, cfg)
        self.docker_home_dir = f"/home/{self.CONTAINER_USERNAME}"

    @override
    def get_build_image_name(self) -> str:
        return f"cluster-node-{self.user}"

    @override
    def build_image(self) -> ExitCode:
        root = Project.get_project_root()
        dockerfile = root / "Dockerfile.cluster-node"
        img_builder = ImageBuilder(self.get_build_image_name(), root)
        return img_builder.build_dockerfile(dockerfile,
                                            [f"USERNAME={self.CONTAINER_USERNAME}"])

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        container_name = f"cluster-node-{index}"
        run_cmd = f"""
        docker run --rm=true
            --name "{container_name}"
            -dit
            {self.get_build_image_name()}
        """
        if container_name in Containers.list():
            log.info(f"Container {container_name} already running.")
            return 0
        else:
            return cmd.run_with_status(self.app, run_cmd, cwd=Project.get_project_root())

    def copy_to_containers(self, local_path: Path) -> ExitCode:
        ret = 0
        for i in range(self.cfg.hadoop.num_nodes):  # type: ignore
            container_name = f"cluster-node-{i}"
            c = f"docker cp {local_path} {container_name}:{self.docker_home_dir}"
            (ret, output) = cmd.run(c)
            if ret != 0:
                log.error(f"Failed to copy {local_path} to {container_name}: {output}")
                return ret
            c = f"""
            docker exec {container_name} bash -c
            'cd {self.docker_home_dir} &&
             tar -xzf {local_path.name} --strip-components=1 -C /opt/hadoop'
            """
            (ret, output) = cmd.run(c)
            if ret != 0:
                log.error(f"Failed to extract hadoop in {container_name}: {output}")
                return ret
            log.info(f"✅ Extracted {local_path.name} to {container_name}")
        return 0


class ImageBuilder:
    def __init__(self, image_name: str, build_path: Path):
        self.image_name = image_name
        self.build_path = build_path.resolve(strict=True)

    def build_dockerfile(self, dockerfile: Path, build_args: list[str] = []) -> ExitCode:
        log.info(f"Building image {self.image_name} from {dockerfile}...")
        args_str = " ".join(f"--build-arg {arg}" for arg in build_args)
        command = f"docker build -t {self.image_name} -f {dockerfile} {args_str} ."
        (exit_code, output) = cmd.run(command, cwd=self.build_path)
        log.debug(f"Build output: {output}")
        return exit_code

    def build_input(self, input: str) -> ExitCode:
        log.info(f"Building image {self.image_name} from input...")
        log.debug(f"Input: {input}")
        command = f"docker build -t {self.image_name} -"
        (exit_code, _) = cmd.run(command, cwd=self.build_path, input=input)
        return exit_code

    def clean_image(self) -> ExitCode:
        return self.clean_image_by_name(self.image_name)

    @classmethod
    def clean_image_by_name(cls, image_name: str) -> ExitCode:
        command = f"docker rmi {image_name}"
        (err, _) = cmd.run(command)
        return err
