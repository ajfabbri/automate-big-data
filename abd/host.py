from dataclasses import dataclass
from enum import Enum
from typing import Iterator, Protocol, override

import abd.command as cmd
from abd.project import CmdResult, ExitCode


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

    def run_print(self, command: str, quiet_failure=False, is_dryrun=False) -> ExitCode:
        ...

    def run_streaming(self, command: str, filter_re=".*", quiet_failure=False,
                      is_dryrun=False) -> Iterator[str | ExitCode]:
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

    def _make_cmd(self, cmd: str, quiet_failure: bool) -> str:
        # use -l for login shell to pick up PATH etc.
        opt = "" if quiet_failure else "-e -o pipefail "
        docker_cmd = f"docker exec {self.name} bash {opt}-lc '{cmd}'"
        return docker_cmd

    @override
    def run_command(self, command: str, quiet_failure=False, is_dryrun=False) -> CmdResult:
        docker_cmd = self._make_cmd(command, quiet_failure)
        return cmd.run(docker_cmd, quiet=quiet_failure, is_dryrun=is_dryrun)

    @override
    def run_print(self, command: str, quiet_failure=False, is_dryrun=False) -> ExitCode:
        docker_cmd = self._make_cmd(command, quiet_failure)
        return cmd.run_print(docker_cmd, is_dryrun=is_dryrun)

    @override
    def run_streaming(self, command: str, filter_re=".*", quiet_failure=False,
                      is_dryrun=False) -> Iterator[str | ExitCode]:
        docker_cmd = self._make_cmd(command, quiet_failure)
        return cmd.run_streaming(docker_cmd, filter_re=filter_re,
                                 quiet=quiet_failure, is_dryrun=is_dryrun)
