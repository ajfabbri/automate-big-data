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
        self.tasks[task.task_id] = task

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


class TaskIdSet:
    """ Given a set of TaskId-matching strings and a Job, create a set of all
    the Job's TaskIds that match. """

    @classmethod
    def _task_str_matches(cls, task_str: str, id: TaskId) -> bool:
        if ":" in task_str:
            parts = task_str.split(":")
            if parts[1] == "":
                # phase: match
                return str(id.phase_type) == parts[0]
            else:
                # phase:name match
                return parts[0] == str(id.phase_type) and parts[1] == id.name
        else:
            # name match
            return task_str == id.name

    @classmethod
    def _is_valid_task_str(cls, task_str: str) -> bool:
        return len(task_str.split(":")) in [1, 2]

    def __init__(self, job: Job, task_strs: set[str]):
        self.task_ids: set[TaskId] = set()
        for task_str in task_strs:
            if not self._is_valid_task_str(task_str):
                log.warning(f"Bad task {task_str}: should be 'phase:', 'name', or 'phase:name'")
                continue
            if task_str == "all":
                self.task_ids.update(job.get_tasks().keys())
                log.debug("Task 'all': matching all tasks")
                break
            else:
                found = False
                for task_id in job.get_tasks().keys():
                    if self._task_str_matches(task_str, task_id):
                        self.task_ids.add(task_id)
                        log.debug(f"Task '{task_str}': matching {task_id}")
                        found = True
                if not found:
                    log.warning(f"Task '{task_str}' did not match any tasks in the job.")

    def __contains__(self, item: TaskId) -> bool:
        return item in self.task_ids

    def __iter__(self):
        return iter(self.task_ids)

    def get(self) -> set[TaskId]:
        return self.task_ids
