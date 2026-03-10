import logging
from typing import Self
from abd.config.phase import ConfigTask
from abd.job.phases import PhaseType, Task, TaskId

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

    def to_dot_graph(self) -> str:

        color_map = {
            PhaseType.CONFIGURE: "lightblue",
            PhaseType.BUILD: "lightgreen",
            PhaseType.DEPLOY: "lightyellow",
            PhaseType.EXECUTE: "lightcoral",
        }
        header = "digraph G {\n"
        edges = ""
        nodes = ""
        for task_id, task in self.tasks.items():
            nodes += f'  "{task_id}" [style=filled, fillcolor={color_map[task_id.phase_type]}];\n'
            for dep in task.dependencies():
                edges += f'  "{dep}" -> "{task_id}";\n'
        trailer = "}\n"
        return header + nodes + edges + trailer
