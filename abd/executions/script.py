
from dataclasses import dataclass
import logging
from typing import Dict, Iterable, List, Protocol, Tuple

from abd.host import Host
from abd.project import ExitCode, camel_to_snake

log = logging.getLogger(__name__)


@dataclass
class ScriptResult:
    """Result of executing a script."""
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


class Script(Protocol):
    """Interface for one or more commands that can be executed."""

    def get_name(self):
        """Get the name of the script."""
        return camel_to_snake(self.__class__.__name__)

    def quiet_failure(self) -> bool:
        """Override this to be quiet on failures."""
        return False

    def get_commands(self) -> List[str]:
        ...

    def run(self, hosts: Iterable[Host], is_dryrun: bool) -> Dict[str, ExitCode]:
        """Run the script."""

        results = {c.get_name(): 0 for c in hosts}
        for command in self.get_commands():
            for host in hosts:
                if is_dryrun:
                    log.info(f"[DRY RUN] {host.get_name()}: {command}")
                    continue
                ret = host.run_command(command,  quiet_failure=self.quiet_failure())
                if ret != 0:
                    results[host.get_name()] = ret
                    return results
        return results

    def run_result(self, hosts: Iterable[Host], is_dryrun: bool) -> ExitCode:
        """Run script on containers, returning the first non-zero exit code, if any."""
        results = self.run(hosts, is_dryrun)
        fail = ScriptResult.first_failure(results)
        if not fail:
            return 0
        else:
            (_, ret) = fail
            return ret
