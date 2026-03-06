import logging
from typing import Self
from abd.config.phase import ConfigTask
from abd.job.phases import Task, TaskId, PhaseType

log = logging.getLogger(__name__)


class Job:

    _instance: Self | None = None

    # Sigleton instance. Not thread safe (until needed).
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.init_once()
        return cls._instance

    def init_once(self):
        # always add implicit config phase
        self.tasks: dict[TaskId, Task] = {}
        self.register_phase(ConfigTask())

    def register_phase(self, task: Task):
        self.tasks[task.phase_id] = task

    def get_tasks(self) -> dict[TaskId, Task]:
        return self.tasks
