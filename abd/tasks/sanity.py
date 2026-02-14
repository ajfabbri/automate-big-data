import logging
from typing import override
from abd.tasks.task import Task

log = logging.getLogger(__name__)


class FailingTask(Task):
    """Example of a failing task used to test error code propagation."""

    @override
    def quiet_failure(self) -> bool:
        return True

    @override
    def get_commands(self):
        log.debug("Running FailingTask, which will return exit code 1")
        return ["exit 1"]
