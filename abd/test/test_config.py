import unittest

from abd.config import Loader, Config


class TestConfigLoader(unittest.TestCase):

    def test_load_nonexistent(self):
        loader = Loader()
        config = loader.load("nonexistent.toml")
        self.assertIsNone(config)

    def test_load_valid(self):
        loader = Loader()
        config: Config | None = loader.load("abd.toml.example")
        if config is None:
            self.fail("Expected config to be loaded, got None")
        hadoop_config = config.hadoop
        if hadoop_config is None:
            self.fail("Expected hadoop_config to be loaded, got None")
        self.assertEqual(hadoop_config.hadoop_git_path, "../hadoop")
        self.assertEqual(hadoop_config.cloudstore_git_path, "../cloudstore")
        self.assertTrue(hadoop_config.test_s3a)