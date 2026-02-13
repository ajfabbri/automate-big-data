from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import tomllib
import tomli_w
import logging
from abd.project import Project
from abd.ui import prompt_bool, prompt_int, prompt_str

log = logging.getLogger(__name__)

DEFAULT_ENABLE_HADOOP = True
DEFAULT_NUM_NODES = 3
DEFAULT_HADOOP_PATH = "build/hadoop"
DEFAULT_CLOUDSTORE_PATH = "build/cloudstore"
DEFAULT_TEST_S3A = True

CLOUDSTORE_GIT_URI = "git@github.com:steveloughran/cloudstore.git"
CLOUSTORE_GIT_REF = "main"
HADOOP_GIT_URI = "git@github.com:apache/hadoop.git"
HADOOP_GIT_REF = "trunk"


@dataclass
class HadoopConfig:
    num_nodes: int = DEFAULT_NUM_NODES
    hadoop_git_path: str = DEFAULT_HADOOP_PATH
    cloudstore_git_path: str = DEFAULT_CLOUDSTORE_PATH
    test_s3a: bool = DEFAULT_TEST_S3A


@dataclass
class Config:
    # hadoop is enabled when hadoop is not None
    hadoop: Optional[HadoopConfig] = None


class Loader:
    CONF_FILENAME = Path("abd.toml")
    CONF_TEMPLATE = Path("abd", "abd.toml.example")

    def load(self, config_filename: Optional[Path] = None) -> Optional[Config]:
        """Load configuration from file and return it, if it exists."""

        _filename = config_filename or self.CONF_FILENAME
        config_path: Path = Project.get_project_root() / _filename
        if not config_path.exists():
            return None
        with open(config_path, 'rb') as f:
            data = tomllib.load(f)

        log.debug(f"Loaded config data: {data}")

        hadoop = None
        if 'hadoop' in data:
            h = data['hadoop']
            hadoop = HadoopConfig(
                num_nodes=h.get('num_nodes', DEFAULT_NUM_NODES),
                hadoop_git_path=h.get('hadoop_git_path', ''),
                cloudstore_git_path=h.get('cloudstore_git_path', ''),
                test_s3a=h.get('test_s3a', False)
            )
        return Config(hadoop=hadoop)

    def load_template_or_throw(self) -> Config:
        config = self.load(self.CONF_TEMPLATE)
        if not config:
            raise FileNotFoundError(f"Config template not found: {self.CONF_TEMPLATE}")
        return config

    def create_interactive(self) -> Config:
        """Edit or create a new configuration, interactively."""

        # check for existing config
        existing_config = self.load()
        if existing_config:
            print("Existing configuration found:")
            print(existing_config)
            if not prompt_bool("Do you want to edit existing config?", False):
                return existing_config
        else:
            existing_config = self.load_template_or_throw()

        existing_hadoop = existing_config.hadoop is not None
        enable_hadoop = prompt_bool("Enable Hadoop?", existing_hadoop)
        hadoop = None
        if enable_hadoop:
            h_defaults = existing_config.hadoop or HadoopConfig()
            num_nodes = prompt_int("Number of Hadoop nodes", h_defaults.num_nodes)
            hadoop_git_path = prompt_str("Hadoop git path (empty to fetch latest)",
                                         h_defaults.hadoop_git_path)
            test_s3a = prompt_bool("Test S3A?", h_defaults.test_s3a)
            cloudstore_git_path = prompt_str("Cloudstore git path (empty to fetch latest)",
                                             h_defaults.cloudstore_git_path)
            hadoop = HadoopConfig(
                num_nodes=num_nodes,
                hadoop_git_path=hadoop_git_path,
                cloudstore_git_path=cloudstore_git_path,
                test_s3a=test_s3a
            )
        cfg = Config(hadoop=hadoop)
        want_save = prompt_bool("Save this configuration?", True)
        if want_save:
            self.save(cfg)
        return cfg

    def ensure_exists(self) -> Config:
        """Ensure that a configuration file exists, creating with defaults if needed."""
        config = self.load()
        if not config:
            print(f"No existing config; creating {self.CONF_FILENAME} w/ defaults.")
            config = self.load_template_or_throw()
        return config

    def create(self, is_interactive: bool) -> Config:
        if is_interactive:
            return self.create_interactive()
        else:
            return self.ensure_exists()

    def save(self, config: Config, filename: Optional[Path] = None):
        """Save the given configuration to a file."""
        data = {}
        if config.hadoop:
            data['hadoop'] = {  # pyright: ignore[reportArgumentType]
                'num_nodes': config.hadoop.num_nodes,
                'hadoop_git_path': config.hadoop.hadoop_git_path,
                'cloudstore_git_path': config.hadoop.cloudstore_git_path,
                'test_s3a': config.hadoop.test_s3a
            }
        filename = filename or Path(self.CONF_FILENAME)
        filename = Project.get_project_root() / filename
        with open(filename, 'wb') as f:
            f.write(tomli_w.dumps(data).encode('utf-8'))
