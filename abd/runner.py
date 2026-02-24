
from pathlib import Path
import tempfile
import logging

from abd.builder.hadoop import HadoopBuild
from abd.container.localstack import LocalstackBuild
from abd.config import Config, BuildType
from abd.container.cluster_node import ClusterNodeBuild
from abd.container.container import Containers
from abd.context import App
from abd.project import ExitCode, Project

log = logging.getLogger(__name__)


class Runner:
    """ Running tasks on cluster nodes. """
    def __init__(self, app: App, cfg: Config):
        self.app = app
        self.cfg = cfg
        h_cfg = self.cfg.get_build_cfg(BuildType.HADOOP)
        if h_cfg:
            self.h_cfg = h_cfg
        else:
            raise RuntimeError("Hadoop not enabled in config, cannot run containers.")
        self.c_cfg = self.cfg.get_build_cfg(BuildType.CLOUDSTORE)
        node_deploy = cfg.get_deploy_cfg("cluster-node")
        if node_deploy:
            self.node_deploy = node_deploy
        else:
            raise RuntimeError("cluster-node deploy config not found, cannot run containers.")

    def run_all(self, is_cached: bool) -> ExitCode:
        # Start hadoop build container
        # create network for containers
        ret = Containers.create_network(self.app.container_network)
        if ret != 0:
            log.error("Failed to create container network.")
            return ret

        hbuild = HadoopBuild(self.app, self.cfg)

        ret = hbuild.run_container()
        if ret != 0:
            return ret

        if not is_cached:
            # 2. run build script in container
            ret = hbuild.build_in_container()
            if ret != 0:
                return ret

        # 3. start hadoop node containers
        nbuild = ClusterNodeBuild(self.app, self.cfg)
        for i in range(self.node_deploy.num_nodes):
            ret = nbuild.run_container(i)
            if ret != 0:
                return ret

        # 4. Deploy build(s) to node containers
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (err, path) = hbuild.fetch_hadoop_build(tmpdir_path)
            if err != 0:
                return err
            if not path:
                return 1
            ret = nbuild.install_hadoop(path)
            if ret != 0:
                return ret

            (err, path) = hbuild.fetch_cloudstore_build(tmpdir_path)
            if err != 0:
                return err
            if not path:
                return 1
            err = nbuild.copy_to_containers(path)
            if err != 0:
                return err

        # Copy auth-keys.yml config for s3 (localstack) etc.
        config_path = Project.get_project_root() / "config" / "auth-keys.xml"
        dest_path = "$HOME"
        ret = nbuild.copy_to_containers(config_path, dest_path)
        if ret != 0:
            return ret

        # Start localstack, create s3 bucket
        ls_build = LocalstackBuild(self.app, self.cfg)
        ls_build.run_container()
        ls_build.ensure_s3_bucket("abd-bucket")

        # Run tests in node containers
        return 0
