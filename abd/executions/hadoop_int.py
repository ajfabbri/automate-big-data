import logging
from typing import override

from abd.builder.hadoop import BuildHadoopRelease, HadoopBuild
from abd.host import Container
from abd.job.phases import PhaseType, Task, TaskId

log = logging.getLogger(__name__)


class HadoopS3aIntegration(Task):
    """Run some upstream unit/integration tests"""
    phase_id = TaskId("hadoop-integration", PhaseType.EXECUTE)

    @override
    def dependencies(self):
        return {BuildHadoopRelease.phase_id}

    def run(self, arg, is_cached: bool, is_dryrun: bool):
        host = Container(HadoopBuild.get_container_name())
        cmd = "cd $HOME/hadoop/hadoop-tools/hadoop-aws && mvn -Dparallel-tests clean verify"
        err = host.run_print(cmd, is_dryrun)
        if err != 0:
            e = f"Hadoop unit tests failed with error code {err}"
            log.error(e)
            raise RuntimeError(e)
        else:
            log.info("✅ Hadoop unit tests passed!")
