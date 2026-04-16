import logging
from typing import override

from abd.container.cluster_node import NodeDeployTask
from abd.container.localstack import LocalstackTask
from abd.core.context import App
from abd.core.task.phases import PhaseType, Task, TaskId

log = logging.getLogger(__name__)


class ClusterTask(Task):
    """ Top-level cluster deploy task. """
    task_id = TaskId("cluster", PhaseType.DEPLOY)

    @override
    def dependencies(self):
        # all nodes must be deployed before cluster is ready
        return {NodeDeployTask.task_id, LocalstackTask.task_id}

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        log.info("Cluster is ready!")
