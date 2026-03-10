from abd.builder.hadoop import BuildHadoopRelease, DeployHadoopBuildContainer, \
    GitHadoop, HadoopBuildImageTask, InstallHadoop
from abd.container.cluster import ClusterTask
from abd.container.cluster_node import NodeBuildTask, NodeDeployTask
from abd.container.localstack import LocalstackTask
from abd.container.net import NetworkTask
from abd.executions.hadoop import HadoopSanityTask, S3ARoundTrip
from abd.executions.hadoop_int import HadoopS3aIntegration
from abd.job.job import Job
from abd.job.phases import Task


# All tasks are registered here.
# `abd tasks` will lst them.
# `abd tasks --graph` will show dependencies. (TODO)

tasks: list[Task] = [
    #             __ _
    #  ___  ___  / _| |___      ____ _ _ __ ___
    # / __|/ _ \| |_| __\ \ /\ / / _` | '__/ _ \
    # \__ \ (_) |  _| |_ \ V  V / (_| | | |  __/
    # |___/\___/|_|  \__| \_/\_/ \__,_|_|  \___|
    #
    GitHadoop(),
    HadoopBuildImageTask(),
    DeployHadoopBuildContainer(),
    BuildHadoopRelease(),
    InstallHadoop(),

    #  _        __
    # (_)_ __  / _|_ __ __ _
    # | | '_ \| |_| '__/ _` |
    # | | | | |  _| | | (_| |
    # |_|_| |_|_| |_|  \__,_|
    #
    NetworkTask(),
    LocalstackTask(),
    NodeBuildTask(),
    NodeDeployTask(),
    ClusterTask(),

    #                           _   _
    #   _____  _____  ___ _   _| |_(_) ___  _ __  ___
    #  / _ \ \/ / _ \/ __| | | | __| |/ _ \| '_ \/ __|
    # |  __/>  <  __/ (__| |_| | |_| | (_) | | | \__ \
    #  \___/_/\_\___|\___|\__,_|\__|_|\___/|_| |_|___/
    #
    HadoopSanityTask(),
    S3ARoundTrip(),
    HadoopS3aIntegration()
]


def init() -> Job:
    job = Job()
    for task in tasks:
        job.register_phase(task)
    return job
