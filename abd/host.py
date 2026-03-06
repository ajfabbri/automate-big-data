from dataclasses import dataclass
from enum import Enum
from typing import Protocol, override

import abd.command as cmd
from abd.project import ExitCode


class HostType(Enum):
    """Host types for executing scripts."""
    LOCAL = "local"
    CONTAINER = "container"
    SSH = "ssh"


class Host(Protocol):
    """ Common interface for a local or remote host or container. """
    def get_type(self) -> HostType:
        ...

    def get_name(self) -> str:
        ...

    def run_command(self, command: str, quiet_failure: bool = False) -> ExitCode:
        ...


@dataclass(eq=True, frozen=True)
class Container(Host):
    """Container info for executing scripts."""
    name: str

    @override
    def get_type(self) -> HostType:
        return HostType.CONTAINER

    @override
    def get_name(self) -> str:
        return self.name

    @override
    def run_command(self, command: str, quiet_failure: bool = False) -> ExitCode:
        # use -l for login shell to pick up PATH etc.
        docker_cmd = f"docker exec {self.name} bash -lc '{command}'"
        return cmd.run_print(docker_cmd, log_prefix=self.name,
                             quiet_failure=quiet_failure)
