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
#
# Raw type definitions for config (de)serialization to TOML
#
DEFAULT_NUM_NODES = 3

# TODO move to util types module?
type Primitive = str | int | bool | list | dict
type PrimitiveDict = Dict[str, str | int | bool | list | dict]


class BuildType(StrEnum):
    HADOOP = "hadoop"
    CLOUDSTORE = "cloudstore"
    SPARK = "spark"


@dataclass
class Install:
    build_name: BuildType
    path: str


@dataclass
class GitSource:
    git_path: str
    git_ref: str


@dataclass
class TarBuild:
    tar_path: str


type BuildSource = GitSource | TarBuild


def _default_git_ref(build_name: str) -> str:
    match build_name:
        case BuildType.HADOOP:
            return HadoopCfg.get_default_git_ref()
        case BuildType.CLOUDSTORE:
            return CloudstoreCfg.get_default_git_ref()
        case _:
            return "main"


def _get_build_source(build_name: str, git_path: str | None, git_ref: str | None,
                      tar_path: str | None) -> BuildSource:
    if tar_path:
        return TarBuild(tar_path)
    else:
        if not git_path:
            raise RuntimeError("Build config must contain git_path, or tar_path")
        git_ref = git_ref or _default_git_ref(build_name)
    return GitSource(git_path=git_path, git_ref=git_ref)


@dataclass
class BuildCfg:
    source: GitSource | TarBuild

    @classmethod
    def get_default_git_ref(cls) -> str:
        return "main"

    def get_git_ref(self) -> str:
        if isinstance(self.source, GitSource):
            return self.source.git_ref or self.get_default_git_ref()
        else:
            raise RuntimeError("get_git_ref() - no git source configured")

    def get_source(self) -> BuildSource:
        return self.source

    def get_git_source(self) -> GitSource:
        if not isinstance(self.source, GitSource):
            raise RuntimeError("get_git_source() - no git source configured")
        return self.source

    def get_tar_build(self) -> TarBuild:
        if not isinstance(self.source, TarBuild):
            raise RuntimeError("get_tar_build() - no tar source configured")
        return self.source


@dataclass
class DeployCfg:
    num_nodes: int
    image_name: str
    installs: list[Install]


DEFAULT_HADOOP_PATH = "build/hadoop"
DEFAULT_HADOOP_REF = "trunk"
CLOUDSTORE_GIT_URI = "git@github.com:steveloughran/cloudstore.git"
CLOUSTORE_GIT_REF = "main"
HADOOP_GIT_URI = "git@github.com:apache/hadoop.git"
DEFAULT_SPARK_TAR = "https://www.apache.org/dyn/closer.lua/spark/spark-4.1.1/" \
    + "spark-4.1.1-bin-without-hadoop.tgz"


class HadoopCfg(BuildCfg):
    @override
    @classmethod
    def get_default_git_ref(cls) -> str:
        return DEFAULT_HADOOP_REF

    @classmethod
    def load(cls, git_path: str | None = None, git_ref: str | None = None,
             tar_path: str | None = None) -> 'HadoopCfg':
        return HadoopCfg(_get_build_source("hadoop", git_path, git_ref, tar_path))

    @classmethod
    def get_default(cls) -> 'HadoopCfg':
        default_src = GitSource(git_path=DEFAULT_HADOOP_PATH, git_ref=DEFAULT_HADOOP_REF)
        return HadoopCfg(default_src)


class CloudstoreCfg(BuildCfg):
    @override
    @classmethod
    def get_default_git_ref(cls) -> str:
        return "main"

    @classmethod
    def load(cls, git_path: str | None = None, git_ref: str | None = None,
             tar_path: str | None = None) -> 'CloudstoreCfg':
        return CloudstoreCfg(_get_build_source("cloudstore", git_path, git_ref, tar_path))

    @classmethod
    def get_default(cls) -> 'CloudstoreCfg':
        default_src = GitSource(git_path=CLOUDSTORE_GIT_URI, git_ref=CLOUSTORE_GIT_REF)
        return CloudstoreCfg(default_src)


class SparkCfg(BuildCfg):
    @classmethod
    def load(cls, git_path: str | None = None, git_ref: str | None = None,
             tar_path: str | None = None) -> 'SparkCfg':
        if git_path or git_ref:
            raise NotImplementedError("Git source not yet supported for Spark builds")
        if not tar_path:
            raise ValueError("tar_path is required for Spark builds")
        return SparkCfg(TarBuild(tar_path=tar_path))

    @classmethod
    def get_default(cls) -> 'SparkCfg':
        default_src = TarBuild(tar_path=DEFAULT_SPARK_TAR)
        return SparkCfg(default_src)


@dataclass
class Config:
    build: dict[str, BuildCfg]
    deploy: dict[str, DeployCfg]

    def get_build_cfg(self, build_type: BuildType) -> BuildCfg | None:
        match build_type:
            case BuildType.HADOOP | BuildType.CLOUDSTORE | BuildType.SPARK:
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
            try:
                match key:
                    case BuildType.HADOOP:
                        builds[key] = HadoopCfg.load(**cfg)
                    case BuildType.CLOUDSTORE:
                        builds[key] = CloudstoreCfg.load(**cfg)
                    case BuildType.SPARK:
                        builds[key] = SparkCfg.load(**cfg)
                    case _:
                        log.error(f"Unknown build type in config: {key}")
            except Exception as e:
                log.error(f"Error loading build config '{key}': {e}")
                log.debug(f"Build config data: {data}")
                raise e
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

    def _prompt_source(self, name: str, ui: Ui, default: BuildSource) -> BuildSource:
        default_git = isinstance(default, GitSource)
        is_git = ui.prompt_bool(f"{name}: Use git source?", default_git)
        if is_git:
            default_ref = default.git_ref if default_git else "main"
            default_path = default.git_path if default_git else Path("build") / name
            git_ref = ui.prompt_str(f"{name}: git ref?", default_ref)
            git_path = ui.prompt_str(f"{name}: git path?", default_path)
            return GitSource(git_path=git_path, git_ref=git_ref)
        else:
            # Conditionals are silly, but help type checking
            default_tar = default.tar_path if not default_git else Path("build") / "example.tar"
            path_str = ui.prompt_str(f"{name}: tar path?", default_tar)
            return TarBuild(path_str)

    def create_interactive(self, ui: Ui) -> Config:
        """Edit or create a new configuration, interactively."""

        builds: dict[str, BuildCfg] = {}
        deploys: dict[str, DeployCfg] = {}

        def add_install(install: Install, num_nodes=DEFAULT_NUM_NODES):
            if "cluster-node" in deploys:
                deploys["cluster-node"].installs.append(install)
            else:
                deploys["cluster-node"] = DeployCfg(num_nodes, "cluster-node", [install])

        # check for existing config
        existing_config = self.load()
        if existing_config:
            print("Existing configuration found:")
            print(existing_config)
            if not ui.prompt_bool("Do you want to edit existing config?", False):
                return existing_config
        else:
            existing_config = self.load_template_or_throw()

        # Hadoop Ecosystem
        existing_hadoop_cfg = existing_config.get_build_cfg(BuildType.HADOOP)
        enable_hadoop = ui.prompt_bool("Enable Hadoop?", existing_hadoop_cfg is not None)
        if enable_hadoop:
            # Hadoop Common
            h_defaults = existing_hadoop_cfg or HadoopCfg.get_default()
            num_nodes = ui.prompt_int("Number of Hadoop nodes", DEFAULT_NUM_NODES)
            hadoop_src = self._prompt_source("Hadoop", ui, h_defaults.source)
            builds[BuildType.HADOOP] = HadoopCfg(hadoop_src)
            add_install(Install(BuildType.HADOOP, "/home/hadoop"), num_nodes)

            # Cloudstore
            existing_cs = existing_config.get_build_cfg(BuildType.CLOUDSTORE)
            c_defaults = existing_cs or CloudstoreCfg.get_default()
            enable_cloudstore = ui.prompt_bool("Enable Cloudstore?", existing_cs is not None)
            if enable_cloudstore:
                cloudstore_src = self._prompt_source("Cloudstore", ui, c_defaults.source)
                builds[BuildType.CLOUDSTORE] = CloudstoreCfg(cloudstore_src)
                add_install(Install(BuildType.CLOUDSTORE, "/home/hadoop"))

            # Spark
            existing_spark = existing_config.get_build_cfg(BuildType.SPARK)
            enable_spark = ui.prompt_bool("Enable Spark?", existing_spark is not None)
            if enable_spark:
                s_defaults = existing_spark or SparkCfg.get_default()
                spark_src = self._prompt_source("Spark", ui, s_defaults.source)
                builds[BuildType.SPARK] = SparkCfg(spark_src)
                # TODO these actually install in /opt/hadoop and /opt/spark,
                # this home path is only used for downloads.
                add_install(Install(BuildType.SPARK, "/home/hadoop"))
        else:
            log.info("Hadoop disabled. Skipping dependencies Spark, Cloudstore, etc.")

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

    @classmethod
    def _flatten_sources(cls, config: dict):
        """ Modify `config`, flattening any 'source' objects (inlining their
            fields, removing source key)"""
        for build_cfg in config.get("build", {}).values():
            if "source" in build_cfg:
                source_cfg = build_cfg.pop("source")
                for key, val in source_cfg.items():
                    build_cfg[key] = val

    def save(self, config: Config, filename: Optional[Path] = None):
        """Save the given configuration to a file."""
        data = config.to_dict()
        self._flatten_sources(data)
        filename = filename or Path(self.CONF_FILENAME)
        filename = Project.get_project_root() / filename
        with open(filename, 'wb') as f:
            f.write(tomli_w.dumps(data).encode('utf-8'))
