
from abd.builder.hadoop import DeployHadoopBuildContainer, HadoopBuildImagePhase
from abd.job.job import Job


job = Job()
job.register_phase(HadoopBuildImagePhase())
job.register_phase(DeployHadoopBuildContainer())
