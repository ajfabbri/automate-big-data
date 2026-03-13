
from dataclasses import dataclass
from enum import auto, StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, Set

from abd.context import App
from abd.project import Project


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
