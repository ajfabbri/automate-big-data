
from dataclasses import dataclass
from enum import auto, StrEnum
from typing import ClassVar, Protocol, Set

from abd.context import App


class PhaseType(StrEnum):
    CONFIGURE = auto()
    BUILD = auto()
    DEPLOY = auto()
    EXECUTE = auto()


@dataclass(frozen=True)
class TaskId:
    name: str
    phase_type: PhaseType


class Task[T: App](Protocol):
    """ Interface for phase of a job.
        R is type of the output of the phase, if any.
        T is type of input argument, if any. (For now we always use context.App.)
        """
    phase_id: ClassVar[TaskId]

    def dependencies(self) -> Set[TaskId]:
        """ Return list of phases this depends on. Default: no dependencies """
        return set()

    def run(self, arg: T, is_cached: bool):
        """ Run this phase, skipping generating existing assets when `is_cached` is set.
            Throws on failure.
        """
        ...

    def __str__(self):
        return f"{self.phase_id.phase_type}:{self.phase_id.name}"
