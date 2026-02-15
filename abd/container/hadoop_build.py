from pathlib import Path
import logging
from typing import override
from abd.config import Config
import abd.command as cmd
from abd.container.container import HADOOP_BASE_DOCKERFILE, \
    HADOOP_BASE_DOCKERFILE_ARM, HADOOP_BUILD_CONTAINER, ContainerBuild, Containers, ImageBuilder
from abd.context import App
from abd.project import ExitCode

log = logging.getLogger(__name__)


class HadoopBuild(ContainerBuild):
    """ Support for building a container to build hadoop in. """

    @override
    def __init__(self, app: App, cfg: Config):
        super().__init__(app, cfg)
        if cfg.hadoop:
            self.h_cfg = cfg.hadoop
        else:
            raise Exception("Hadoop config is required for HadoopBuild.")
        self.local_hadoop = Path(self.h_cfg.hadoop_git_path).resolve(strict=True)

    @override
    def get_build_image_name(self) -> str:
        # just throw on error; should be unlikely at this point
        return f"hadoop-build-{self.user}"

    @override
    def build_image(self) -> ExitCode:
        # Use upstream hadoop container definition for a build machine

        # Build base image
        hadoop_path = Path(self.h_cfg.hadoop_git_path)
        if self.app.sysinfo.get_cpu_arch() in ["arm64", "aarch64"]:
            docker_file = HADOOP_BASE_DOCKERFILE_ARM
        else:
            docker_file = HADOOP_BASE_DOCKERFILE
        base_dockerfile = hadoop_path / "dev-support" / "docker" / docker_file
        base_builder = ImageBuilder("hadoop-build", base_dockerfile.parent)
        result = base_builder.build_dockerfile(docker_file)
        if result != 0:
            log.error(f"Failed to build base image from {base_dockerfile}")
            return result

        # build user-specific image
        docker_input = f"""
        FROM hadoop-build
        RUN rm -f /var/log/faillog /var/log/lastlog
        RUN userdel -r $(getent passwd {self.uid} | cut -d: -f1) 2>/dev/null || :
        RUN groupadd --non-unique -g {self.gid} {self.user}
        RUN useradd -g {self.gid} -u {self.uid} -k /root -m {self.user} -d "/home/{self.user}"
        RUN echo "{self.user} ALL=NOPASSWD: ALL" > "/etc/sudoers.d/hadoop-build-{self.uid}"
        ENV HOME="/home/{self.user}"
        """
        u_builder = ImageBuilder(self.get_build_image_name(), base_dockerfile.parent)
        return u_builder.build_input(docker_input)

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        if index != 0:
            log.warning("Hadoop build container is single-instance; ignoring index.")

        build_image = self.get_build_image_name()
        # local_cloudstore = Path(self.h_cfg.hadoop.cloudstore_git_path)

        # From hadoop.git:
        # By mapping the .m2 directory you can do an mvn install from
        # within the container and use the result on your normal
        # system.  And this also is a significant speedup in subsequent
        # builds because the dependencies are downloaded only once.

        run_cmd = f"""
        docker run --rm=true
                -v "{self.local_hadoop}:{self.docker_home_dir}/hadoop"
                -w "{self.docker_home_dir}/hadoop"
                -v "{self.local_home}/.m2:{self.docker_home_dir}/.m2"
                -v "{self.local_home}/.gnupg:{self.docker_home_dir}/.gnupg"
                -u "{self.uid}"
                --name "{HADOOP_BUILD_CONTAINER}"
                -dit
                {build_image}
        """
        if HADOOP_BUILD_CONTAINER in Containers.list():
            log.info(f"Container {HADOOP_BUILD_CONTAINER} already running.")
            return 0
        else:
            return cmd.run_with_status(self.app, run_cmd, cwd=self.local_hadoop)

    def build_in_container(self) -> ExitCode:
        build_cmd = f"""
        docker exec hadoop-build bash -c
        "cd {self.docker_home_dir}/hadoop && mvn package -Pdist,native -DskipTests -Dtar"
        """
        return cmd.run_with_status(self.app, build_cmd)

    def find_hadoop_release(self) -> Path | None:
        dist_dir = Path(self.docker_home_dir) / "hadoop" / "hadoop-dist" / "target"
        list_cmd = f"docker exec hadoop-build bash -c 'find {dist_dir} -name hadoop-*.tar.gz'"
        (exit_code, output) = cmd.run(list_cmd)
        paths = [Path(line.strip()) for line in output.splitlines() if line.strip()]
        # prefers newer veraions, and prefer release builds over -SNAPSHOT builds
        paths.sort(reverse=True)
        if exit_code != 0 or len(paths) == 0:
            log.error(f"Failed to find hadoop release.. {output}")
            return None
        return paths[0]

    def fetch_hadoop_build(self, local_dir: Path) -> tuple[ExitCode, Path | None]:
        path = self.find_hadoop_release()
        if not path:
            return (1, None)
        log.debug(f"Using hadoop build: {path}")
        c = f"docker cp hadoop-build:{path} {local_dir}/"
        (ret, _) = cmd.run(c)
        if ret != 0:
            log.error("Failed to copy hadoop release from {HADOOP_BUILD_CONTAINER}.")
            return (ret, None)
        return (0, local_dir / path.name)
