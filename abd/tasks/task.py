
from dataclasses import dataclass
import logging
from typing import Dict, List, Protocol, Set, Tuple

from abd.project import ExitCode, camel_to_snake
import abd.command as cmd

log = logging.getLogger(__name__)


@dataclass(eq=True, frozen=True)
class Container:
    """Container info for executing tasks."""
    name: str


@dataclass
class TaskResult:
    """Result of executing a task."""
    exit_code: ExitCode
    output: str

    @staticmethod
    def first_failure(results: Dict[str, ExitCode]) -> Tuple[str, ExitCode] | None:
        """Get the first failure result from a dict of results, or return None."""
        for container, ret in results.items():
            if ret != 0:
                log.error(f"Task failed on container {container} with exit code {ret}")
                return (container, ret)
        return None


class Task(Protocol):
    """Interface for a task that can be executed."""

    def get_name(self):
        """Get the name of the task."""
        return camel_to_snake(self.__class__.__name__)

    def quiet_failure(self) -> bool:
        """Override this to be quiet on failures."""
        return False

    def get_commands(self) -> List[str]:
        ...

    def run(self, containers: Set[Container]) -> Dict[str, ExitCode]:
        """Run the task."""

        results = {c.name: 0 for c in containers}
        for command in self.get_commands():
            for container in containers:
                # use -il for interactive login shell to pick up PATH etc.
                docker_cmd = f"docker exec {container.name} bash -ilc '{command}'"
                ret = cmd.run_print(docker_cmd, log_prefix=container.name,
                                    quiet_failure=self.quiet_failure())
                if ret != 0:
                    results[container.name] = ret
                    return results
        return results

    def run_result(self, containers: Set[Container]) -> ExitCode:
        """Run task on containers, returning the first non-zero exit code, if any."""
        results = self.run(containers)
        fail = TaskResult.first_failure(results)
        if not fail:
            return 0
        else:
            (_, ret) = fail
            return ret
