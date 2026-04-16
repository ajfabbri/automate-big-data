import logging
from pathlib import Path
from typing import List, override

from abd.builder.hadoop import HADOOP_HOME, InstallHadoop
import abd.command as cmd
from abd.config.raw import DeployCfg
from abd.container.cluster_node import ClusterNodeBuild
from abd.context import App
from abd.executions.script import Script
from abd.core.task.phases import PhaseType, Task, TaskId

log = logging.getLogger(__name__)


class HadoopSanity(Script):
    """Sanity check for Hadoop cluster."""
    task_id = TaskId("hadoop-sanity", PhaseType.EXECUTE)

    @override
    def get_commands(self) -> List[str]:
        # Run local mapreduce example (PI)
        mapred_example_jar = f"{HADOOP_HOME}/share/hadoop/mapreduce/hadoop-mapreduce-examples-*.jar"
        return [
            f"hadoop jar {mapred_example_jar} pi 10 1000"
        ]


class HadoopSanityTask(Task):
    task_id = TaskId("hadoop-sanity", PhaseType.EXECUTE)

    @override
    def dependencies(self):
        return {InstallHadoop.task_id}

    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        ret = HadoopSanity().run_result(arg.hosts, is_dryrun)
        if ret != 0:
            log.error("⛔️ Hadoop sanity check failed.")
            raise RuntimeError("Hadoop sanity check failed.")
        else:
            log.debug("👍 Hadoop sanity check passed.")


class S3ARoundTrip(Task):
    task_id = TaskId("s3a-roundtrip", PhaseType.EXECUTE)
    fsize_mb = 10
    fname = "testfile-abd-s3a-roundtrip"

    @override
    def dependencies(self):
        return {InstallHadoop.task_id}

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        deploy = arg.get_config().get_deploy_cfg("cluster-node")
        nodes = ClusterNodeBuild.get_deploy_hosts(deploy)
        node_iter = iter(nodes)
        source_node = next(node_iter)
        dest_node = next(node_iter)
        put_cmd = f"hadoop fs -put -f /tmp/{self.fname} s3a://abd-bucket/{self.fname}"
        make_file_cmd = f"dd if=/dev/urandom of=/tmp/{self.fname} bs=1M count={self.fsize_mb}"

        res = source_node.run_command(make_file_cmd, is_dryrun)
        self._check_result(log, res, f"Failed create test file on {source_node}: {make_file_cmd}")

        res = source_node.run_command(put_cmd, is_dryrun)
        self._check_result(log, res, f"Failed put file to s3a from {source_node}: {put_cmd}")

        get_cmd = f"hadoop fs -get -f s3a://abd-bucket/{self.fname} /tmp/{self.fname}.downloaded"
        res = dest_node.run_command(get_cmd, is_dryrun)
        self._check_result(log, res, f"Failed get file from s3a on {dest_node}: {get_cmd}")

        src_hash = self._md5_sum(log, source_node, Path(f"/tmp/{self.fname}"), is_dryrun)
        dest_hash = self._md5_sum(log, dest_node, Path(f"/tmp/{self.fname}.downloaded"), is_dryrun)

        if not src_hash:
            e = f"⛔️ Failed to compute source file hash on {source_node}."
            log.error(e)
            raise RuntimeError(e)
        elif src_hash != dest_hash:
            e = f"⛔️ S3A source and dest file hash mismatch: {src_hash} != {dest_hash}."
            log.error(e)
            raise RuntimeError(e)
        else:
            log.info(f"👍 S3A round trip successful: {src_hash} == {dest_hash}.")


class S3ALargeFile(Task):
    task_id = TaskId("s3a-largefile", PhaseType.EXECUTE)

    @override
    def dependencies(self):
        # TODO validate cloudstore is in install config, or (better) separate it from
        # hadoop task and add a dependency
        return {InstallHadoop.task_id}

    def _find_cloudstore_jar(self, deploy: DeployCfg) -> Path:
        for i in range(deploy.num_nodes):
            # TODO we should probably cache the path from earlier tasks
            host = ClusterNodeBuild.get_container_name(i)
            c = f"docker exec {host} bash -lc 'ls -t1 cloudstore-*.jar| head -1'"
            (ret, output) = cmd.run(c)
            if ret != 0:
                log.error(f"Failed to find cloudstore jar in {host}: {output}")
                raise RuntimeError(f"Failed to find cloudstore jar in {host}: {output}")
            output = output.strip()
            if output:
                return Path(output)
        raise RuntimeError("Failed to find cloudstore jar.")

    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        deploy = arg.get_config().get_deploy_cfg("cluster-node")
        nodes = ClusterNodeBuild.get_deploy_hosts(deploy)
        node_iter = iter(nodes)
        source_node = next(node_iter)
        dest_node = next(node_iter)
        # TODO use dependency task's output
        path = self._find_cloudstore_jar(deploy)
        cs_cmd = f"hadoop jar {path} "
        put_cmd = cs_cmd + "put /tmp/testfile s3a://abd-bucket/testfile"
        make_file_cmd = "dd if=/dev/urandom of=/tmp/testfile bs=1M count=10"

        res = source_node.run_command(make_file_cmd, is_dryrun=is_dryrun)
        self._check_result(log, res, f"Failed create test file on {source_node}: {make_file_cmd}")

        res = source_node.run_command(put_cmd, is_dryrun=is_dryrun)
        self._check_result(log, res, f"Failed put file to s3a from {source_node}: {put_cmd}")

        get_cmd = "hadoop fs -get -f s3a://abd-bucket/testfile /tmp/testfile.downloaded"
        res = dest_node.run_command(get_cmd, is_dryrun=is_dryrun)
        self._check_result(log, res, f"Failed get file from s3a on {dest_node}: {get_cmd}")

        src_hash = self._md5_sum(log, source_node, Path("/tmp/testfile"), is_dryrun)
        dest_hash = self._md5_sum(log, dest_node, Path("/tmp/testfile.downloaded"), is_dryrun)

        if not src_hash:
            e = f"⛔️ Failed to compute source file hash on {source_node}."
            log.error(e)
            raise RuntimeError(e)
        elif src_hash != dest_hash:
            e = f"⛔️ S3A source and dest file hash mismatch: {src_hash} != {dest_hash}."
            log.error(e)
            raise RuntimeError(e)
        else:
            log.info(f"👍 S3A round trip successful: {src_hash} == {dest_hash}.")
