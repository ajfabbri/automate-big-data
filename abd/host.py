from dataclasses import dataclass
from enum import Enum
from typing import Protocol, override

import abd.command as cmd
from abd.project import CmdResult


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

    def run_command(self, command: str, quiet_failure=False, is_dryrun=False) -> CmdResult:
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
    def run_command(self, command: str, quiet_failure=False, is_dryrun=False) -> CmdResult:
        # use -l for login shell to pick up PATH etc.
        opt = "" if quiet_failure else "-e -o pipefail "
        docker_cmd = f"docker exec {self.name} bash {opt}-lc '{command}'"
        return cmd.run(docker_cmd, quiet=quiet_failure, is_dryrun=is_dryrun)
