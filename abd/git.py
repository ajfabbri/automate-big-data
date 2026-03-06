
from pathlib import Path
import logging

from abd import command
from abd.ui import Ui

log = logging.getLogger(__name__)


class Git:
    def __init__(self, repo_uri: str, local_path: Path, ui: Ui = Ui()):
        self.repo_uri = repo_uri
        # Path.resolve() breaks on MacOS due to prepending SIP path
        self.local_path = local_path.absolute()
        self.ui = ui

    @staticmethod
    def git_command(args, cwd=None):
        output = command.run(" ".join(["git", *args]), cwd=cwd)
        log.debug(f"(git) {output}")

    def clone(self, repo_ref: str, is_interactive: bool = False):
        """ Ensure that there is a local clone of given repo at local_path. """
        if is_interactive:
            q = f"Git clone {self.repo_uri} to {self.local_path} and checkout {repo_ref}"
            answer = self.ui.prompt_bool(q, default=True)
            if not answer:
                print(f"Skipping git clone of {self.repo_uri}!")
                return
        local_parent = self.local_path.parent
        if self.local_path.exists():
            log.info(f"Local path {self.local_path} already exists, skipping clone.")
        else:
            print(f"Cloning {self.repo_uri} to {self.local_path}...")
            print(f" -> mkdir {local_parent}")
            local_parent.mkdir(parents=True, exist_ok=True)
            self.git_command(["clone", self.repo_uri, str(self.local_path)], cwd=local_parent)
            log.info(f"Cloned {self.repo_uri} to {self.local_path}")

        # ensure we have `repo_ref` checked out, unless it is "HEAD"
        if repo_ref == "HEAD":
            log.info(f"Using HEAD ref for {self.repo_uri}, skipping checkout.")
            return
        self.git_command(["fetch"], cwd=str(self.local_path))
        self.git_command(["checkout", repo_ref], cwd=str(self.local_path))
        self.git_command(["pull"], cwd=str(self.local_path))
        log.info(f"Latest ref {repo_ref} checked out in {self.local_path}")
