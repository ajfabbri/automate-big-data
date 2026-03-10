from dataclasses import dataclass
import dataclasses
from enum import StrEnum
from pathlib import Path
from typing import Dict, Optional, override
import tomllib
import tomli_w
import logging
from abd.project import Project
from abd.ui import Ui

log = logging.getLogger(__name__)

DEFAULT_NUM_NODES = 3
DEFAULT_HADOOP_PATH = "build/hadoop"
DEFAULT_HADOOP_REF = "trunk"

CLOUDSTORE_GIT_URI = "git@github.com:steveloughran/cloudstore.git"
CLOUSTORE_GIT_REF = "main"
HADOOP_GIT_URI = "git@github.com:apache/hadoop.git"

# TODO move to util types module?
type Primitive = str | int | bool | list | dict
type PrimitiveDict = Dict[str, str | int | bool | list | dict]

#
# Raw type definitions for (de)serialization to TOML
#


class BuildType(StrEnum):
    HADOOP = "hadoop"
    CLOUDSTORE = "cloudstore"


@dataclass
class Install:
    build_name: BuildType
    path: str


@dataclass
class BuildCfg:
    git_path: str
    # git ref to checkout, or "" for default
    git_ref: str

    @classmethod
    def get_default_git_ref(cls) -> str:
        return "main"

    def get_git_ref(self) -> str:
        return self.git_ref or self.get_default_git_ref()


@dataclass
class DeployCfg:
    num_nodes: int
    image_name: str
    installs: list[Install]


class HadoopCfg(BuildCfg):

    @override
    @classmethod
    def get_default_git_ref(cls) -> str:
        return "trunk"

    def __init__(self, git_path: str, git_ref: str | None = None):
        ref = git_ref or self.get_default_git_ref()
        super().__init__(git_path, ref)

    @classmethod
    def get_default(cls) -> 'HadoopCfg':
        return HadoopCfg(git_path=DEFAULT_HADOOP_PATH, git_ref=DEFAULT_HADOOP_REF)


class CloudstoreCfg(BuildCfg):
    @override
    @classmethod
    def get_default_git_ref(cls) -> str:
        return "main"

    def __init__(self, git_path: str, git_ref: str | None = None):
        ref = git_ref or self.get_default_git_ref()
        super().__init__(git_path, ref)

    @classmethod
    def get_default(cls) -> 'CloudstoreCfg':
        return CloudstoreCfg(git_path=CLOUDSTORE_GIT_URI, git_ref=CLOUSTORE_GIT_REF)


@dataclass
class Config:
    build: dict[str, BuildCfg]
    deploy: dict[str, DeployCfg]

    def get_build_cfg(self, build_type: BuildType) -> BuildCfg | None:
        match build_type:
            case BuildType.HADOOP | BuildType.CLOUDSTORE:
                return self.build.get(build_type)
            case _:
                raise ValueError(f"Unsupported build type: {build_type}")

    def try_get_deploy_cfg(self, deploy_name: str) -> DeployCfg | None:
        return self.deploy.get(deploy_name)

    def get_deploy_cfg(self, deploy_name: str) -> DeployCfg:
        cfg = self.try_get_deploy_cfg(deploy_name)
        if not cfg:
            raise ValueError(f"Deploy config not found: {deploy_name}")
        return cfg

    def to_dict(self) -> dict:
        """Convert config a dict of primitive types (for serialization)."""
        data = dataclasses.asdict(self)

        def resolve_enum_vals(obj: Primitive | PrimitiveDict) -> Primitive | PrimitiveDict:
            if isinstance(obj, StrEnum):
                return obj.value
            elif isinstance(obj, dict):
                return {k: resolve_enum_vals(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [resolve_enum_vals(i) for i in obj]
            else:
                return obj
        return resolve_enum_vals(data)  # type: ignore


class Loader:
    CONF_FILENAME = Path("abd.toml")
    CONF_TEMPLATE = Path("abd", "abd.toml.example")

    def load_builds(self, data: dict) -> dict[str, BuildCfg]:
        builds = {}
        for key, cfg in data.items():
            match key:
                case BuildType.HADOOP:
                    builds[key] = HadoopCfg(**cfg)
                case BuildType.CLOUDSTORE:
                    builds[key] = CloudstoreCfg(**cfg)
                case _:
                    log.error(f"Unknown build type in config: {key}")
        return builds

    def load_deploys(self, data: dict) -> dict[str, DeployCfg]:
        deploys = {}
        for deploy_name, cfg in data.items():
            try:
                image_name = cfg["image_name"]
                num_nodes = cfg["num_nodes"]
                install_cfg = cfg["installs"]
                installs = []
                for io in install_cfg:
                    match io:
                        case {"build_name": build_type, "path": dest_path}:
                            installs.append(Install(BuildType(build_type), dest_path))
                        case _:
                            log.error(f"Invalid install config in deploy '{deploy_name}': {io}")
                deploys[deploy_name] = (DeployCfg(num_nodes=num_nodes,
                                                  image_name=image_name,
                                                  installs=installs))
            except KeyError as e:
                log.error(f"Missing key in deploy config '{deploy_name}': {e}")
            except ValueError as e:
                log.error(f"Invalid value in deploy config '{deploy_name}': {e}")
        return deploys

    @classmethod
    def existing_path(cls, config_filename: Optional[Path] = None) -> Path | None:
        """Resolve the config file path, using the provided filename or default if not provided.
           Returns None if the resulting path doesn't exist.
        """
        _filename = config_filename or cls.CONF_FILENAME
        config_path: Path = Project.get_project_root() / _filename
        return config_path if config_path.exists() else None

    def load(self, config_filename: Optional[Path] = None) -> Optional[Config]:
        """Load configuration from file and return it, if it exists."""

        config_path = self.existing_path(config_filename)
        if not config_path:
            return None
        with open(config_path, 'rb') as f:
            data = tomllib.load(f)

        log.debug(f"Loaded config {config_path}: \n{data}")
        match data:
            case {"build": build_cfg, "deploy": deploy_cfg}:
                match (build_cfg, deploy_cfg):
                    case (dict(), dict()):
                        return Config(build=self.load_builds(build_cfg),
                                      deploy=self.load_deploys(deploy_cfg))
                    case _:
                        log.error("Invalid config format: 'build' and 'deploy' should be tables.")
                        log.error(f"Got build: {build_cfg}, deploy: {deploy_cfg}")
                        return None
            case _:
                log.error("Invalid config format: expected 'build' and 'deploy' keys.")
                return None

    def load_template_or_throw(self) -> Config:
        config = self.load(self.CONF_TEMPLATE)
        if not config:
            raise FileNotFoundError(f"Config template not found: {self.CONF_TEMPLATE}")
        return config

    def create_interactive(self, ui: Ui) -> Config:
        """Edit or create a new configuration, interactively."""

        # check for existing config
        existing_config = self.load()
        if existing_config:
            print("Existing configuration found:")
            print(existing_config)
            if not ui.prompt_bool("Do you want to edit existing config?", False):
                return existing_config
        else:
            existing_config = self.load_template_or_throw()

        existing_hadoop_cfg = existing_config.get_build_cfg(BuildType.HADOOP)
        existing_cloudstore_cfg = existing_config.get_build_cfg(BuildType.CLOUDSTORE)
        enable_hadoop = ui.prompt_bool("Enable Hadoop?", existing_hadoop_cfg is not None)
        builds: dict[str, BuildCfg] = {}
        deploys: dict[str, DeployCfg] = {}
        if enable_hadoop:
            h_defaults = existing_hadoop_cfg or HadoopCfg.get_default()
            c_defaults = existing_cloudstore_cfg or CloudstoreCfg.get_default()
            num_nodes = ui.prompt_int("Number of Hadoop nodes", DEFAULT_NUM_NODES)
            hadoop_git_path = ui.prompt_str("Hadoop git path (will fetch if doesn't exist)",
                                            h_defaults.git_path)
            hadoop_git_ref = ui.prompt_str("Hadoop git ref (HEAD to skip checkout)",
                                           h_defaults.git_ref)
            cloudstore_git_path = ui.prompt_str("Cloudstore git path (empty to fetch latest)",
                                                c_defaults.git_path)
            cloudstore_git_ref = ui.prompt_str("Cloudstore git ref (HEAD to skip checkout)",
                                               c_defaults.git_ref)
            builds[BuildType.HADOOP] = HadoopCfg(git_path=hadoop_git_path, git_ref=hadoop_git_ref)
            builds[BuildType.CLOUDSTORE] = CloudstoreCfg(git_path=cloudstore_git_path,
                                                         git_ref=cloudstore_git_ref)

            deploys["cluster-node"] = DeployCfg(num_nodes, "cluster-node",
                                                [Install(BuildType.HADOOP, "/home/hadoop"),
                                                 Install(BuildType.CLOUDSTORE, "/home/hadoop")])
        cfg = Config(build=builds, deploy=deploys)

        want_save = ui.prompt_bool("Save this configuration?", True)
        if want_save:
            self.save(cfg)
        return cfg

    def ensure_exists(self) -> Config:
        """Ensure that a configuration file exists, creating with defaults if needed."""
        config = self.load()
        if not config:
            existing = self.existing_path()
            if existing:
                e = f"Existing config file exists at template path but can't be loaded: {existing}"
                raise RuntimeError(e)
            print(f"No existing config; creating {self.CONF_FILENAME} w/ defaults.")
            config = self.load_template_or_throw()
        return config

    def create(self, is_interactive: bool, ui: Ui) -> Config:
        if is_interactive:
            return self.create_interactive(ui)
        else:
            return self.ensure_exists()

    def save(self, config: Config, filename: Optional[Path] = None):
        """Save the given configuration to a file."""
        data = config.to_dict()
        filename = filename or Path(self.CONF_FILENAME)
        filename = Project.get_project_root() / filename
        with open(filename, 'wb') as f:
            f.write(tomli_w.dumps(data).encode('utf-8'))
