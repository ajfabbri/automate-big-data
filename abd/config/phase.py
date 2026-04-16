
from typing import override
from abd.config.raw import Loader
from abd.context import App
from abd.core.task.phases import Task, TaskId, PhaseType


class ConfigTask(Task):
    task_id = TaskId("config", PhaseType.CONFIGURE)

    def __init__(self):
        self.config = None

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        # for now, just ensure we can load config
        if not arg.try_get_config():
            arg.config = Loader().ensure_exists()
        self.config = arg.get_config()
