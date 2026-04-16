from pathlib import Path
import re
from typing import NamedTuple

ExitCode = int


class CmdResult(NamedTuple):
    exit_code: ExitCode
    std_out: str


class Project:
    """Project-level utility methods."""
    @staticmethod
    def get_project_root() -> Path:
        """Get the root directory of the project."""
        return Path(__file__).parent.parent

    @staticmethod
    def get_build_dir() -> Path:
        return Project.get_project_root() / "build"


def camel_to_snake(name: str) -> str:
    """Convert a CamelCase string to snake_case."""
    if not name:
        return ""
    # First replace: Handle cases like 'HTTPServer' -> 'HTTP_Server'
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    # Second replace: Handle cases like 'MyHTTPServer' -> 'My_HTTP_Server'
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    return s2.lower()
