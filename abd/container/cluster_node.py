import logging
from pathlib import Path
from typing import override

import abd.command as cmd
from abd.config import Config
from abd.container.builder import ImageBuilder
from abd.container.container import ContainerBuild, Containers
from abd.context import App
from abd.project import ExitCode, Project

log = logging.getLogger(__name__)


class ClusterNodeBuild(ContainerBuild):
    CONTAINER_USERNAME = "hadoop"

    @override
    def __init__(self, app: App, cfg: Config):
        super().__init__(app, cfg)
        self.docker_home_dir = f"/home/{self.CONTAINER_USERNAME}"

    @override
    def get_image_name(self) -> str:
        return f"cluster-node-{self.user}"

    @override
    def build_image(self, is_cached: bool) -> ExitCode:
        if is_cached:
            images = Containers.list_images()
            if self.get_image_name() in images:
                log.info(f"cached: Image {self.get_image_name()} exists, skipping build.")
                return 0
        root = Project.get_project_root()
        dockerfile = root / "Dockerfile.cluster-node"
        img_builder = ImageBuilder(self.get_image_name(), root)
        return img_builder.build_dockerfile(dockerfile,
                                            [f"USERNAME={self.CONTAINER_USERNAME}"])

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        container_name = f"cluster-node-{index}"
        run_cmd = f"""
        docker run --rm=true
            --network {self.app.container_network}
            --name "{container_name}"
            -dit
            {self.get_image_name()}
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

