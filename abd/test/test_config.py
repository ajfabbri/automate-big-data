import logging
import unittest

from abd.config.raw import BuildType, Loader, Config
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)


class TestConfigLoader(unittest.TestCase):

    def test_load_nonexistent(self):
        loader = Loader()
        config = loader.load(Path("nonexistent.toml"))
        self.assertIsNone(config)

    def test_load_valid(self):
        loader = Loader()
        config: Config | None = loader.load(Path("abd", "abd.toml.example"))
        if config is None:
            self.fail("Expected config to be loaded, got None")
        hadoop_config = config.get_build_cfg(BuildType.HADOOP)
        if hadoop_config is None:
            self.fail("Expected hadoop_config to be loaded, got None")
        self.assertEqual(hadoop_config.git_path, "build/hadoop")
        cloudstore_config = config.get_build_cfg(BuildType.CLOUDSTORE)
        if cloudstore_config is None:
            self.fail("Expected cloudstore_config to be loaded, got None")
        self.assertEqual(cloudstore_config.git_path, "build/cloudstore")
