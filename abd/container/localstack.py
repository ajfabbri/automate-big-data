import logging
from typing import override
from abd.config import Config
import abd.command as cmd
from abd.container.container import ContainerBuild, Containers
from abd.context import App
from abd.project import ExitCode

log = logging.getLogger(__name__)


class LocalstackBuild(ContainerBuild):
    """ Support for building a container to build hadoop in. """

    @override
    def __init__(self, app: App, cfg: Config):
        super().__init__(app, cfg)
        # TODO

    @override
    def get_image_name(self) -> str:
        return "localstack/localstack"

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        if index != 0:
            log.warning("localstack container is single-instance; ignoring index.")

        run_cmd = f"""
        docker run --rm -dit
              -p 127.0.0.1:4566:4566
              -p 127.0.0.1:4510-4559:4510-4559
              -v /var/run/docker.sock:/var/run/docker.sock
              {self.get_image_name()}
        """

        if self.get_image_name() in Containers.list():
            log.info(f"Container {self.get_image_name()} already running.")
            return 0
        else:
            return cmd.run_with_status(self.app, run_cmd)
