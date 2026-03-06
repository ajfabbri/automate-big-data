import logging
from typing import override
from abd.executions.script import Script

log = logging.getLogger(__name__)


class FailingTask(Script):
    """Example of a failing task used to test error code propagation."""

    @override
    def quiet_failure(self) -> bool:
        return True

    @override
    def get_commands(self):
        log.debug("Running FailingTask, which will return exit code 1")
        return ["exit 1"]
