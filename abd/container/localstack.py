import json
import logging
from typing import override
import abd.command as cmd
from abd.container.container import ContainerBuild, Containers
from abd.context import App
from abd.job.phases import Task, TaskId, PhaseType
from abd.project import ExitCode

log = logging.getLogger(__name__)


class LocalstackBuild(ContainerBuild):
    """ Support for localstack container. """

    @override
    def __init__(self, app: App):
        super().__init__(app)
        # TODO

    @override
    def get_image_name(self) -> str:
        return "localstack/localstack"

    @override
    def get_container_name(self, index: int = 0) -> str:
        return "abd-localstack"

    @override
    def run_container(self, is_dryrun: bool, index: int = 0) -> ExitCode:
        if index != 0:
            log.warning("localstack container is single-instance; ignoring index.")

        run_cmd = f"""
        docker run --rm -dit
              -p 127.0.0.1:4566:4566
              -p 127.0.0.1:4510-4559:4510-4559
              -v /var/run/docker.sock:/var/run/docker.sock
              --name {self.get_container_name(index)}
              --network {self.app.container_network}
              {self.get_image_name()}
        """

        containers = Containers.list()
        name = self.get_container_name(index)
        if name in containers:
            log.info(f"Container {name} already running.")
            return 0
        else:
            return cmd.run_print(run_cmd, is_dryrun=is_dryrun)

    def ensure_s3_bucket(self, bucket_name: str = "abd-bucket") -> ExitCode:
        ls_list_cmd = "awslocal s3api list-buckets"
        list_cmd = f"docker exec {self.get_container_name()} bash -c '{ls_list_cmd}'"
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


class LocalstackTask(Task):
    phase_id = TaskId("localstack", PhaseType.DEPLOY)

    def __init__(self):
        pass

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        localstack = LocalstackBuild(arg)
        localstack.run_container(is_dryrun)
