import json
import logging
from typing import override
from abd.config import Config
import abd.command as cmd
from abd.container.container import ContainerBuild, Containers
from abd.context import App
from abd.project import ExitCode

log = logging.getLogger(__name__)


class LocalstackBuild(ContainerBuild):
    """ Support for localstack container. """

    @override
    def __init__(self, app: App, cfg: Config):
        super().__init__(app, cfg)
        # TODO

    @override
    def get_image_name(self) -> str:
        return "localstack/localstack"

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        if index != 0:
            log.warning("localstack container is single-instance; ignoring index.")

        run_cmd = f"""
        docker run --rm -dit
              -p 127.0.0.1:4566:4566
              -p 127.0.0.1:4510-4559:4510-4559
              -v /var/run/docker.sock:/var/run/docker.sock
              --name abd-localstack
              --network {self.app.container_network}
              {self.get_image_name()}
        """

        if self.get_image_name() in Containers.list():
            log.info(f"Container {self.get_image_name()} already running.")
            return 0
        else:
            return cmd.run_with_status(self.app, run_cmd)

    def ensure_s3_bucket(self, bucket_name: str = "abd-bucket") -> ExitCode:
        ls_list_cmd = "awslocal s3api list-buckets"
        list_cmd = f"docker exec abd-localstack bash -c '{ls_list_cmd}'"
        ls_create_cmd = f"awslocal s3api create-bucket --bucket {bucket_name}"
        (err, output) = cmd.run(list_cmd)
        if err != 0:
            log.error(f"Failed to list buckets in localstack: {output}")
            return err
        listing = json.loads(output)
        buckets = [b["Name"] for b in listing.get("Buckets", [])]
        if bucket_name in buckets:
            log.info(f"Bucket {bucket_name} already exists in localstack.")
            return 0
        create_cmd = f"docker exec abd-localstack bash -c '{ls_create_cmd}'"
        (err, output) = cmd.run(create_cmd)
        if err != 0:
            log.error(f"Failed to create bucket {bucket_name} in localstack: {output}")
        else:
            log.info(f"Created bucket {bucket_name} in localstack.")
        return 0
