from pathlib import Path
import logging
from typing import override
from abd.builder.image import ImageBuilder
from abd.config import BuildType, Config
import abd.command as cmd
from abd.container.container import ContainerBuild, Containers
from abd.context import App
from abd.project import ExitCode

log = logging.getLogger(__name__)

HADOOP_BASE_DOCKERFILE = Path("Dockerfile_ubuntu_24")
HADOOP_BASE_DOCKERFILE_ARM = Path("Dockerfile_ubuntu_24_aarch64")
HADOOP_BUILD_CONTAINER = "hadoop-build"


class HadoopBuild(ContainerBuild):
    """ Support for building a container to build hadoop in. """

    @override
    def __init__(self, app: App, cfg: Config):
        super().__init__(app, cfg)
        hcfg = cfg.get_build_cfg(BuildType.HADOOP)
        ccfg = cfg.get_build_cfg(BuildType.CLOUDSTORE)
        if hcfg:
            self.h_cfg = hcfg
            self.local_hadoop = Path(self.h_cfg.git_path).absolute()
            if ccfg:
                self.c_cfg = ccfg
                self.local_cloudstore = Path(self.c_cfg.git_path).absolute()
        else:
            raise Exception("Hadoop config is required for HadoopBuild.")

    @override
    def get_image_name(self) -> str:
        # just throw on error; should be unlikely at this point
        return f"hadoop-build-{self.user}"

    @override
    def get_container_name(self, index: int = 0) -> str:
        return HADOOP_BUILD_CONTAINER

    @override
    def build_image(self, is_cached: bool) -> ExitCode:
        # Use upstream hadoop container definition for a build machine
        if is_cached:
            images = Containers.list_images()
            log.debug("Cached images: " + ", ".join(images))
            if self.get_image_name() in images:
                log.info(f"cached: Image {self.get_image_name()} exists, skipping build.")
                return 0

        # Build base image
        hadoop_path = Path(self.h_cfg.git_path)
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
        RUN apt-get update && apt-get install -y iputils-ping
        RUN rm -f /var/log/faillog /var/log/lastlog
        RUN userdel -r $(getent passwd {self.uid} | cut -d: -f1) 2>/dev/null || :
        RUN groupadd --non-unique -g {self.gid} {self.user}
        RUN useradd -g {self.gid} -u {self.uid} -k /root -m {self.user} -d "/home/{self.user}"
        RUN echo "{self.user} ALL=NOPASSWD: ALL" > "/etc/sudoers.d/hadoop-build-{self.uid}"
        ENV HOME="/home/{self.user}"
        ENV MAVEN_OPTS="-Xms256m -Xmx8g"
        """
        u_builder = ImageBuilder(self.get_image_name(), base_dockerfile.parent)
        return u_builder.build_input(docker_input)

    @override
    def run_container(self, index: int = 0) -> ExitCode:
        if index != 0:
            log.warning("Hadoop build container is single-instance; ignoring index.")

        build_image = self.get_image_name()
        # local_cloudstore = Path(self.h_cfg.hadoop.cloudstore_git_path)

        # From hadoop.git:
        # By mapping the .m2 directory you can do an mvn install from
        # within the container and use the result on your normal
        # system.  And this also is a significant speedup in subsequent
        # builds because the dependencies are downloaded only once.

        run_cmd = f"""
        docker run --rm=true
                -v "{self.local_hadoop}:{self.docker_home_dir}/hadoop"
                -v "{self.local_cloudstore}:{self.docker_home_dir}/cloudstore"
                -w "{self.docker_home_dir}/hadoop"
                -v "{self.local_home}/.m2:{self.docker_home_dir}/.m2"
                -v "{self.local_home}/.gnupg:{self.docker_home_dir}/.gnupg"
                -u "{self.uid}"
                --network "{self.app.container_network}"
                --name "{HADOOP_BUILD_CONTAINER}"
                -m 16g --oom-kill-disable
                -dit
                {build_image}
        """
        if self.get_container_name() in Containers.list():
            log.info(f"Container {self.get_container_name()} already running.")
            return 0
        else:
            return cmd.run_with_status(self.app, run_cmd, cwd=self.local_hadoop)

    def build_in_container(self) -> ExitCode:
        """ build hadoop common and cloudstore """
        mvn_build = "mvn package -Pdist,native -DskipTests -Dtar -Dmaven.javadoc.skip=true"
        mvn_build += " -Dhadoop-aws-package"
        # Skip slow BOM generation
        mvn_build += " -Dcyclonedx.skip=true"
        build_cmd = f"""
        docker exec hadoop-build bash -ilc
        "cd {self.docker_home_dir}/hadoop && {mvn_build}"
        """
        # err = cmd.run_print(build_cmd)
        # if err != 0:
        #     log.error("Failed to build hadoop in container.")
        #     return err
        build_cmd = f"""
        docker exec hadoop-build bash -ilc
        "cd {self.docker_home_dir}/cloudstore && mvn clean install -DskipTests"
        """
        return cmd.run_print(build_cmd)

    def find_hadoop_release(self) -> Path | None:
        dist_dir = Path(self.docker_home_dir) / "hadoop" / "hadoop-dist" / "target"
        list_cmd = f"docker exec hadoop-build bash -c 'find {dist_dir} -name hadoop-*.tar.gz'"
        (exit_code, output) = cmd.run(list_cmd)
        paths = [Path(line.strip()) for line in output.splitlines() if line.strip()]
        # prefers newer versions, and prefer release builds over -SNAPSHOT builds
        paths.sort(reverse=True)
        if exit_code != 0 or len(paths) == 0:
            log.error(f"Failed to find hadoop release.. {output}")
            return None
        return paths[0]

    def find_cloudstore_release(self) -> Path | None:
        dist_dir = Path(self.docker_home_dir) / "cloudstore" / "target"
        list_cmd = f"docker exec hadoop-build bash -c 'find {dist_dir} -name cloudstore-*.jar'"
        (exit_code, output) = cmd.run(list_cmd)
        paths = [Path(line.strip()) for line in output.splitlines() if line.strip()]
        # prefers newer versions
        paths.sort(reverse=True)
        if exit_code != 0 or len(paths) == 0:
            log.error(f"Failed to find cloudstore release.. {output}")
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

    def fetch_cloudstore_build(self, local_dir: Path) -> tuple[ExitCode, Path | None]:
        path = self.find_cloudstore_release()
        if not path:
            return (1, None)
        log.debug(f"Using cloudstore build: {path}")
        c = f"docker cp hadoop-build:{path} {local_dir}/"
        (ret, _) = cmd.run(c)
        if ret != 0:
            log.error("Failed to copy cloudstore release from {HADOOP_BUILD_CONTAINER}.")
            return (ret, None)
        return (0, local_dir / path.name)
