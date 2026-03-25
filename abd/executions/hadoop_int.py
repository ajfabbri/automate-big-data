import logging
import re
from typing import override

from abd.builder.hadoop import BuildHadoopRelease, HadoopBuild
from abd.container.localstack import LocalstackTask
from abd.host import Container
from abd.job.phases import PhaseType, Task, TaskId
from abd.project import ExitCode

log = logging.getLogger(__name__)

ERROR_STR = "[ERROR]"
ERROR_RE = re.escape(ERROR_STR)


class HadoopS3aIntegration(Task):
    """Run some upstream unit/integration tests"""
    task_id = TaskId("hadoop-integration", PhaseType.EXECUTE)

    @override
    def dependencies(self):
        return {BuildHadoopRelease.task_id, LocalstackTask.task_id}

    def run(self, arg, is_cached: bool, is_dryrun: bool):
        host = Container(HadoopBuild.get_container_name())
        cmd = "cd $HOME/hadoop/hadoop-tools/hadoop-aws && mvn -Dparallel-tests verify"
        filter_re = f'{ERROR_RE}|Tests run:'
        failure_re = re.compile(ERROR_RE)
        failures = []
        err = 0
        for result in host.run_streaming(cmd, filter_re, False, is_dryrun):
            match result:
                case str(s):
                    if failure_re.search(s):
                        print(f"❌ {s}")
                        failures.append(s)
                    else:
                        print(s)
                case ExitCode(error):
                    err = error
        err = err or len(failures)
        if err != 0:
            e = f"Hadoop unit tests failed ({err})"
            log.error(e)
            raise RuntimeError(e)
        else:
            log.info("✅ Hadoop unit tests passed!")
