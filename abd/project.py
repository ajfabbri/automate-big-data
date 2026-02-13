from pathlib import Path
from typing import NamedTuple

type ExitCode = int


class CmdResult(NamedTuple):
    exit_code: ExitCode
    std_out: str


class Project:
    """Project-level utility methods."""
    @staticmethod
    def get_project_root() -> Path:
        """Get the root directory of the project."""
        return Path(__file__).parent.parent
