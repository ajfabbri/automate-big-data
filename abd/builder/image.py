import logging
from pathlib import Path

import abd.command as cmd
from abd.project import ExitCode

log = logging.getLogger(__name__)


class ImageBuilder:
    def __init__(self, image_name: str, build_path: Path):
        self.image_name = image_name
        self.build_path = build_path.resolve(strict=True)

    def build_dockerfile(self, dockerfile: Path, build_args: list[str] = []) -> ExitCode:
        log.info(f"Building image {self.image_name} from {dockerfile}...")
        args_str = " ".join(f"--build-arg {arg}" for arg in build_args)
        command = f"docker build -t {self.image_name} -f {dockerfile} {args_str} ."
        (exit_code, output) = cmd.run(command, cwd=self.build_path)
        log.debug(f"Build output: {output}")
        return exit_code

    def build_input(self, input: str) -> ExitCode:
        log.info(f"Building image {self.image_name} from input...")
        log.debug(f"Input: {input}")
        command = f"docker build -t {self.image_name} -"
        (exit_code, _) = cmd.run(command, cwd=self.build_path, input=input)
        return exit_code

    def clean_image(self) -> ExitCode:
        return self.clean_image_by_name(self.image_name)

    @classmethod
    def clean_image_by_name(cls, image_name: str) -> ExitCode:
        command = f"docker rmi {image_name}"
        (err, _) = cmd.run(command)
        return err
