
from pathlib import Path
import logging

from abd import command

log = logging.getLogger(__name__)


class Git:
    def __init__(self, repo_uri: str, local_path: Path):
        self.repo_uri = repo_uri
        # Path.resolve() breaks on MacOS due to prepending SIP path
        self.local_path = local_path.absolute()

    @staticmethod
    def git_command(args, cwd=None):
        output = command.run(" ".join(["git", *args]), cwd=cwd)
        log.debug(f"(git) {output}")

    def ensure_clone(self, repo_ref: str):
        local_parent = self.local_path.parent
        """ Ensure that there is a local clone of given repo at local_path. """
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
