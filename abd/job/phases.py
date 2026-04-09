
from dataclasses import dataclass
from enum import auto, StrEnum
from logging import Logger
from pathlib import Path
from typing import ClassVar, Protocol, Set

from abd.context import App
from abd.host import Host
from abd.project import CmdResult, Project


class PhaseType(StrEnum):
    CONFIGURE = auto()
    BUILD = auto()
    DEPLOY = auto()
    EXECUTE = auto()


@dataclass(frozen=True, eq=True)
class TaskId:
    name: str
    phase_type: PhaseType

    def __str__(self):
        return f"{self.phase_type}:{self.name}"


class Task[T: App](Protocol):
    """ Interface for phase of a job.
        R is type of the output of the phase, if any.
        T is type of input argument, if any. (For now we always use context.App.)
        """
    task_id: ClassVar[TaskId]

    def dependencies(self) -> Set[TaskId]:
        """ Return list of phases this depends on. Default: no dependencies """
        return set()

    # TODO remove is_cached, is_dryrun?
    def run(self, arg: T, is_cached: bool, is_dryrun: bool):
        """ Run this phase, skipping generating existing assets when `is_cached` is set.
            Throws on failure.
        """
        ...

    def get_output_dir(self) -> Path:
        return Project.get_build_dir() / f"{self.task_id}"

    def __str__(self):
        return f"{self.task_id.phase_type}:{self.task_id.name}"

    # helper functions
    def _check_err(self, log: Logger, err: int, msg: str):
        if err != 0:
            log.error(msg)
            raise RuntimeError(msg)

    def _check_result(self, log: Logger, res: CmdResult, msg: str):
        (err, output) = res
        if err != 0:
            e = f"{msg}: {output}"
            log.error(e)
            raise RuntimeError(e)

    def _md5_sum(self, log: Logger, host: Host, path: Path, is_dryrun=False) -> str:
        cmd = f"md5sum {path}"
        (err, out) = host.run_command(cmd, is_dryrun)
        self._check_err(log, err, f"Failed to compute md5 of {path} on {host.get_name()}: {cmd}")
        return out.strip().split()[0]
