from dataclasses import dataclass
import logging
from pathlib import Path

import abd.command as cmd
from abd.project import ExitCode

log = logging.getLogger(__name__)


@dataclass
class Info:
    user: str
    uid: int
    gid: int
    cpu_arch: str
    user_home: Path


class Sysinfo:
    """ Convenience class for grabbing system / user information. """
    def __init__(self):
        self.info: Info | None = None

    def _lazy_init(self) -> ExitCode:
        try:
            self._lazy_init_throws()
        except Exception as e:
            log.error(f"Failed to get user or machine info: {e}")
            return 1
        return 0

    def _lazy_init_throws(self) -> Info:
        if self.info:
            # already gathered info
            return self.info

        # gather machine and user info
        (user, uid) = cmd.userinfo()
        osname = cmd.run_throws("uname -s").strip().lower()
        if osname == "linux":
            gid = int(cmd.run_throws("id -g").strip())
        elif osname == "darwin":
            gid = 100
        else:
            raise Exception(f"Unsupported OS: {osname}")
        cpu_arch = cmd.run_throws("uname -m").strip()
        home = cmd.run_throws("echo $HOME").strip()
        self.info = Info(user=user, uid=uid, gid=gid, cpu_arch=cpu_arch, user_home=Path(home))
        return self.info

    def load(self) -> ExitCode:
        """ Explicit init function for propagating exit code. Call this first
            or accesors may throw.
        """
        return self._lazy_init()

    def get_user(self) -> str:
        return self._lazy_init_throws().user

    def get_uid(self) -> int:
        return self._lazy_init_throws().uid

    def get_gid(self) -> int:
        return self._lazy_init_throws().gid

    def get_cpu_arch(self) -> str:
        return self._lazy_init_throws().cpu_arch

    def get_user_home(self) -> Path:
        return self._lazy_init_throws().user_home
