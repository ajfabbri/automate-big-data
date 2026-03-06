import logging
from typing import List, override

from abd.builder.hadoop import InstallHadoop
from abd.container.cluster_node import NodeDeployTask
from abd.context import App
from abd.executions.script import Script
from abd.job.phases import PhaseType, Task, TaskId

HADOOP_HOME = "/opt/hadoop"
log = logging.getLogger(__name__)


class HadoopSanity(Script):
    """Sanity check for Hadoop cluster."""
    phase_id = TaskId("hadoop-sanity", PhaseType.EXECUTE)

    @override
    def get_commands(self) -> List[str]:
        # Run local mapreduce example (PI)
        mapred_example_jar = f"{HADOOP_HOME}/share/hadoop/mapreduce/hadoop-mapreduce-examples-*.jar"
        return [
            f"hadoop jar {mapred_example_jar} pi 10 1000"
        ]


class HadoopSanityTask(Task):
    phase_id = TaskId("hadoop-sanity", PhaseType.EXECUTE)

    @override
    def dependencies(self):
        return {InstallHadoop.phase_id}

    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        ret = HadoopSanity().run_result(arg.hosts, is_dryrun)
        if ret != 0:
            log.error("⛔️ Hadoop sanity check failed.")
            raise RuntimeError("Hadoop sanity check failed.")
        else:
            log.debug("👍 Hadoop sanity check passed.")
