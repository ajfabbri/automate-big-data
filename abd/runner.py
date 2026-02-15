
from pathlib import Path
import tempfile
import logging

from abd.config import Config
from abd.container.cluster_node import ClusterNodeBuild
from abd.container.hadoop_build import HadoopBuild
from abd.container.localstack import LocalstackBuild
from abd.context import App
from abd.project import ExitCode

log = logging.getLogger(__name__)


class Runner:
    """ Running tasks on cluster nodes. """
    def __init__(self, app: App, cfg: Config):
        self.app = app
        self.cfg = cfg

    def run_all(self, is_cached: bool) -> ExitCode:
        # Initial stab:
        # 1. start hadoop build container
        if not self.cfg.hadoop:
            log.error("Hadoop not enabled in config, cannot run containers.")
            return 1

        hbuild = HadoopBuild(self.app, self.cfg)
        # local_cloudstore = Path(self.cfg.hadoop.cloudstore_git_path)

        if not is_cached:
            ret = hbuild.run_container()
            if ret != 0:
                return ret

            # 2. run build script in container
            ret = hbuild.build_in_container()
            if ret != 0:
                return ret

        # 3. start hadoop node containers
        nbuild = ClusterNodeBuild(self.app, self.cfg)
        for i in range(self.cfg.hadoop.num_nodes):
            ret = nbuild.run_container(i)
            if ret != 0:
                return ret

        # 4. Deploy build(s) to node containers
        with tempfile.TemporaryDirectory() as tmpdir:
            (err, path) = hbuild.fetch_hadoop_build(Path(tmpdir))
            if err != 0:
                return err
            if not path:
                return 1

            ret = nbuild.copy_to_containers(path)
            if ret != 0:
                return ret

        # Start localstack
        ls_build = LocalstackBuild(self.app, self.cfg)
        ls_build.run_container()

        # Run tests in node containers
        return 0
