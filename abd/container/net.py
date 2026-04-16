import logging
from typing import override
from abd.container.container import Containers
from abd.context import App
from abd.core.task.phases import PhaseType, Task, TaskId

log = logging.getLogger(__name__)


class NetworkTask(Task):
    task_id = TaskId("network", PhaseType.DEPLOY)

    # no dependencies, yet.

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        net_name = arg.container_network
        if is_cached:
            if net_name in Containers.list_networks():
                log.info(f"[cache hit] existing container network {net_name}.")
                return

        ret = Containers.create_network(net_name, is_dryrun)
        if ret != 0:
            e = f"Failed to create container network {net_name}."
            log.error(e)
            raise RuntimeError(e)
