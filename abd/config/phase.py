
from types import NoneType
from typing import override
from abd.config.raw import Loader
from abd.job.phases import Task, TaskId, PhaseType


class ConfigTask(Task):
    phase_id = TaskId("config", PhaseType.CONFIGURE)

    def __init__(self):
        self.config = None

    @override
    def run(self, arg: NoneType, is_cached: bool):  # pyright: ignore[reportUnusedParameter]
        # for now, just ensure we can load config
        self.config = Loader().ensure_exists()
