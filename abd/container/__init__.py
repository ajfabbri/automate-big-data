from abd.container.localstack import LocalstackPhase
from abd.job.job import Job


job = Job()
job.register_phase(LocalstackPhase())
