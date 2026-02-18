from pathlib import Path
import logging
from typing import Protocol
import typing

import abd.command as cmd
from abd.config import Config
from abd.context import App
from abd.project import ExitCode
log = logging.getLogger(__name__)


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
        c = f"docker images --format '{{{{.Repository}}}}' {filter_str}"
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

    @classmethod
    def stop(cls, filter: str = "all") -> ExitCode:
        filter_str = ""
        if filter and filter != "all":
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

    @classmethod
    def list_networks(cls) -> typing.List[str]:
        c = "docker network ls --format '{{.Name}}'"
        output = cmd.run_throws(c)
        return output.strip().splitlines()

    @classmethod
    def create_network(cls, net_name: str) -> ExitCode:
        if net_name in cls.list_networks():
            log.info(f"Network {net_name} already exists.")
            return 0
        c = f"docker network create {net_name}"
        return cmd.run_print(c)


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

    def get_image_name(self) -> str:
        ...

    def get_container_name(self, index: int = 0) -> str:
        ...

    def build_image(self, is_cached: bool) -> ExitCode:
        log.debug(f"{self.get_image_name()} - Nothing to build.")
        return 0

    def run_container(self, index: int = 0) -> ExitCode:
        ...
