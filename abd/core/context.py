import argparse
from dataclasses import dataclass
from abd.config.raw import Config
from abd.core.infra.host import Host
from abd.core.sysinfo import Sysinfo
from abd.ui import Ui


@dataclass
class Args:
    """CLI args etc."""
    is_dryrun: bool
    # list of task IDs, or strings to match them
    cached: set[str]
    is_interactive: bool
    task_str: str | None
    is_serial: bool
    # TODO finer granularity cached option?
    # cache_build: bool
    # cache_image: bool
    # cache_install: bool
    raw: argparse.Namespace


class App:
    """ Application-level context. """
    def __init__(self, args: Args):
        # app lifetime stuff
        # TODO use ui for input/output, enables colors / TUI
        self.ui = Ui()
        sysinfo = Sysinfo()
        if sysinfo.load() != 0:
            raise Exception("Failed to load system info.")
        self.sysinfo = sysinfo
        self.args = args

        # config
        self.container_network = "abd-network"
        self.config: Config | None = None

        # operation state
        # TODO thread safety
        self.hosts: set[Host] = set()

    def try_get_config(self) -> Config | None:
        return self.config

    def get_config(self) -> Config:
        if not self.config:
            raise RuntimeError("Config not loaded.")
        return self.config
