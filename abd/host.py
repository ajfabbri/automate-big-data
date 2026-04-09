from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator, Protocol, override
from logging import getLogger

import abd.command as cmd
from abd.project import CmdResult, ExitCode

log = getLogger(__name__)


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

    def run_throws(self, command, quiet_failure=False, is_dryrun=False) -> str:
        (err, out) = self.run_command(command, quiet_failure=quiet_failure, is_dryrun=is_dryrun)
        if err != 0:
            e = f"Command '{command}' failed with exit code {err}"
            log.error(f"{e}, output: {out}")
            raise RuntimeError(e)
        return out

    def put_file(self, local_path: Path, chown: str | None, host_path: Path | None = None,
                 is_dryrun=False) -> ExitCode:
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
        # backslash-escape any single quotes
        cmd = cmd.replace("'", r"\'")
        docker_cmd = f"docker exec {self.name} bash {opt}-lc $'{cmd}'"
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

    @override
    def put_file(self, local_path: Path, chown: str | None, host_path: Path | None = None,
                 is_dryrun=False) -> ExitCode:
        if not host_path:
            host_path = local_path
        docker_cmd = f"docker cp {local_path} {self.name}:{host_path}"
        (err, out) = cmd.run(docker_cmd, is_dryrun=is_dryrun)
        if err != 0:
            e = f"Failed to copy file to container {self.name}"
            log.error(f"{e}: {out}")
        elif chown:
            (err, out) = self.run_command(f"sudo chown {chown} {host_path}",
                                          is_dryrun=is_dryrun)
            if err != 0:
                e = f"Failed to chown file in container {self.name}"
                log.error(f"{e}: {out}")
        return err
