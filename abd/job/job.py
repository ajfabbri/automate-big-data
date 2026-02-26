import logging
from typing import Self
from abd.config.phase import ConfigTask
from abd.job.phases import Task, TaskId, PhaseType

logging.basicConfig(level=logging.INFO)
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
        self.phases: dict[TaskId, Task] = {}
        self.register_phase(ConfigTask())

    def register_phase(self, phase: Task):
        log.info(f"registering phase:  {phase}")
        self.phases[phase.phase_id] = phase

    def run(self, goal: TaskId, cache_images: bool, cache_releases: bool):
        """ Run the job, executing given phases and any that it depends on. """
        pass

    def get_tasks(self) -> dict[TaskId, Task]:
        return self.phases

    # TODO: use "phase of tasks" terminology?
    def get_phase_targets(self, phase_type: PhaseType) -> set[TaskId]:
        return {p_id for p_id, phase in self.phases.items() if
                phase.phase_id.phase_type == phase_type}
