
from typing import List, override
from abd.tasks.task import Task


HADOOP_HOME = "/opt/hadoop"


class HadoopSanity(Task):
    """Sanity check for Hadoop cluster."""

    @override
    def get_commands(self) -> List[str]:
        # Run local mapreduce example (PI)
        mapred_example_jar = f"{HADOOP_HOME}/share/hadoop/mapreduce/hadoop-mapreduce-examples-*.jar"
        return [
            f"hadoop jar {mapred_example_jar} pi 10 1000"
        ]
