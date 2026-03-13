from pathlib import Path
import logging
from time import sleep
from typing import Set, Tuple, override
from abd.builder.image import ImageBuilder
from abd.config.raw import HADOOP_GIT_URI, BuildType
import abd.command as cmd
from abd.container.cluster import ClusterTask
from abd.container.cluster_node import ClusterNodeBuild
from abd.container.container import ContainerBuild, Containers
from abd.context import App
from abd.git import Git
from abd.job.phases import Task, TaskId, PhaseType
from abd.project import ExitCode, Project

log = logging.getLogger(__name__)

HADOOP_BASE_DOCKERFILE = Path("Dockerfile_ubuntu_24")
HADOOP_BASE_DOCKERFILE_ARM = Path("Dockerfile_ubuntu_24_aarch64")
HADOOP_BUILD_CONTAINER = "hadoop-build"
HADOOP_HOME = "/opt/hadoop"


class HadoopBuild(ContainerBuild):
    """ Support for building a container to build hadoop in. """

    @override
    def __init__(self, app: App):
        cfg = app.get_config()
        super().__init__(app)
        hcfg = cfg.get_build_cfg(BuildType.HADOOP)
        ccfg = cfg.get_build_cfg(BuildType.CLOUDSTORE)
        if hcfg:
            self.h_cfg = hcfg
            proj_dir = Project.get_project_root()
            hpath = Path(self.h_cfg.git_path)
            if not hpath.is_absolute():
                hpath = proj_dir / hpath
            self.local_hadoop = hpath
            if ccfg:
                self.c_cfg = ccfg
                cpath = Path(self.c_cfg.git_path)
                if not cpath.is_absolute():
                    cpath = proj_dir / cpath
                self.local_cloudstore = cpath
        else:
            raise Exception("Hadoop config is required for HadoopBuild.")

    @override
    def get_image_name(self) -> str:
        # just throw on error; should be unlikely at this point
        return f"hadoop-build-{self.user}"

    @override
    @classmethod
    def get_container_name(cls, index: int = 0) -> str:
        return HADOOP_BUILD_CONTAINER

    @override
    def build_image(self, is_cached: bool, is_dryrun: bool) -> ExitCode:
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
        result = base_builder.build_dockerfile(docker_file, is_dryrun)
        if result != 0:
            log.error(f"Failed to build base image from {base_dockerfile}")
            return result

        # build user-specific image
        packages = "iputils-ping neovim rsync ripgrep"
        docker_input = f"""
        FROM hadoop-build
        RUN apt-get update && apt-get install -y {packages}
        RUN rm -f /var/log/faillog /var/log/lastlog
        RUN userdel -r $(getent passwd {self.uid} | cut -d: -f1) 2>/dev/null || :
        RUN groupadd --non-unique -g {self.gid} {self.user}
        RUN useradd -g {self.gid} -u {self.uid} -k /root -m {self.user} -d "/home/{self.user}"
        RUN echo "{self.user} ALL=NOPASSWD: ALL" > "/etc/sudoers.d/hadoop-build-{self.uid}"
        ENV HOME="/home/{self.user}"
        ENV MAVEN_OPTS="-Xms256m -Xmx8g"
        WORKDIR "/home/{self.user}"
        RUN mkdir -p hadoop; chown {self.user}:{self.user} hadoop
        """
        u_builder = ImageBuilder(self.get_image_name(), base_dockerfile.parent)
        return u_builder.build_input(docker_input, is_dryrun)

    def _push_hadoop_source(self, is_dryrun: bool) -> ExitCode:
        """ Push updates to hadoop source tree into container's dir. """
        # MacOS bind mounts are buggy: we manually copy from hadoop-host to hadoop
        # every time we want to pull source updates into the container :-|
        log.info("ℹ️Refreshing hadoop source from host..")
        rsync_cmd = f"""
        docker exec hadoop-build bash -c '
            rsync -av --delete --exclude=.git --exclude=target
                /home/{self.user}/hadoop-host/ /home/{self.user}/hadoop/'
        """
        return cmd.run_print(rsync_cmd, is_dryrun=is_dryrun)

    @override
    def run_container(self, is_dryrun: bool, index: int = 0) -> ExitCode:
        if index != 0:
            log.warning("Hadoop build container is single-instance; ignoring index.")

        build_image = self.get_image_name()

        # From hadoop.git:
        # By mapping the .m2 directory you can do an mvn install from
        # within the container and use the result on your normal
        # system.  And this also is a significant speedup in subsequent
        # builds because the dependencies are downloaded only once.

        # on linux, add --oom-kill-disable
        # Mac bind mounts are problematic and require same JDK versions:
        # -v "{self.local_home}/.m2:{self.docker_home_dir}/.m2"
        # -w "{self.docker_home_dir}/hadoop"
        run_cmd = f"""
        docker run --rm=true
                -v "{self.local_hadoop}:{self.docker_home_dir}/hadoop-host"
                -v "{self.local_cloudstore}:{self.docker_home_dir}/cloudstore"
                -v "{self.local_home}/.gnupg:{self.docker_home_dir}/.gnupg"
                -u "{self.uid}"
                --network "{self.app.container_network}"
                --name "{HADOOP_BUILD_CONTAINER}"
                --hostname "{HADOOP_BUILD_CONTAINER}"
                --memory=12g
                -dit
                {build_image}
        """
        err = 0
        if self.get_container_name() in Containers.list():
            log.info(f"Container {self.get_container_name()} already running.")
        else:
            # return cmd.run_with_status(self.app, run_cmd, cwd=self.local_hadoop,
            #                           is_dryrun=is_dryrun)
            err = cmd.run_print(run_cmd, cwd=self.local_hadoop, is_dryrun=is_dryrun)
        if err != 0:
            log.error("Failed to run hadoop-build container.")
            return err
        return self._push_hadoop_source(is_dryrun)

    def build_in_container(self, is_cached: bool, is_dryrun: bool) -> ExitCode:
        """ build hadoop common and cloudstore """

        if is_cached:
            (path, _) = self._find_hadoop_release()
            if path:
                log.info(f"[cache hit]: existing hadoop build {path}.")
                return 0
        check_cmd = "docker exec hadoop-build bash -lc '[ ! -z \"$MAVEN_OPTS\" ]'"
        (err, _) = cmd.run(check_cmd)
        if err != 0:
            log.warning("⚠️MAVEN_OPTS not set in container; builds may run out of memory.")
            sleep(2)
        self._push_hadoop_source(is_dryrun)
        mvn_build = "mvn package -Pdist,native -DskipTests -Dtar -Dmaven.javadoc.skip=true"
        mvn_build += " -Dhadoop-aws-package"
        # Skip slow BOM generation
        mvn_build += " -Dcyclonedx.skip=true"
        build_cmd = f"""
        docker exec hadoop-build bash -lc
        "cd {self.docker_home_dir}/hadoop && {mvn_build}"
        """
        err = cmd.run_print(build_cmd)
        if err != 0:
            log.error("Failed to build hadoop in container.")
            return err
        build_cmd = f"""
        docker exec hadoop-build bash -lc
        "cd {self.docker_home_dir}/cloudstore && mvn clean install -DskipTests"
        """
        return cmd.run_print(build_cmd, is_dryrun=is_dryrun)

    def _find_hadoop_release(self) -> Tuple[Path | None, str]:
        """ Find hadoop path, Returns (path, "") or (None, command_output) on failure. """
        dist_dir = Path(self.docker_home_dir) / "hadoop" / "hadoop-dist" / "target"
        # TODO use Host run method instead of raw-dogging docker container
        list_cmd = f"docker exec hadoop-build bash -c 'find {dist_dir} -name hadoop-*.tar.gz'"
        (exit_code, output) = cmd.run(list_cmd)
        paths = [Path(line.strip()) for line in output.splitlines() if line.strip()]
        # prefers newer versions, and prefer release builds over -SNAPSHOT builds
        paths.sort(reverse=True)
        if exit_code != 0 or len(paths) == 0:
            log.error(f"Failed to find hadoop release.. {output}")
            return (None, output)
        return (paths[0], "")

    def find_hadoop_release(self) -> Path | None:
        (path, output) = self._find_hadoop_release()
        if not path:
            log.error(f"Failed to find hadoop release.. {output}")
        return path

    def _find_cloudstore_release(self) -> Tuple[Path | None, str]:
        dist_dir = Path(self.docker_home_dir) / "cloudstore" / "target"
        list_cmd = f"docker exec hadoop-build bash -c 'find {dist_dir} -name cloudstore-*.jar'"
        (exit_code, output) = cmd.run(list_cmd)
        paths = [Path(line.strip()) for line in output.splitlines() if line.strip()]
        # prefers newer versions
        paths.sort(reverse=True)
        if exit_code != 0 or len(paths) == 0:
            log.error(f"Failed to find cloudstore release.. {output}")
            return (None, output)
        return (paths[0], "")

    def find_cloudstore_release(self) -> Path | None:
        (path, output) = self._find_cloudstore_release()
        if not path:
            log.error(f"Failed to find cloudstore release.. {output}")
        return path

    def fetch_hadoop_build(self, local_dir: Path, is_cached=False) -> tuple[ExitCode, Path | None]:
        if is_cached:
            paths = local_dir.glob("hadoop-*.tar.gz")
            first_match = next(paths, None)
            if first_match:
                log.info(f"[cache hit] existing hadoop build {first_match}.")
                return (0, first_match)
        path = self.find_hadoop_release()
        if not path:
            return (1, None)
        log.debug(f"Using hadoop build: {path}")
        local_dir.mkdir(parents=True, exist_ok=True)
        c = f"docker cp hadoop-build:{path} {local_dir}/"
        (ret, _) = cmd.run(c)
        if ret != 0:
            log.error(f"Failed to copy hadoop release from {HADOOP_BUILD_CONTAINER}.")
            return (ret, None)
        return (0, local_dir / path.name)

    def fetch_cloudstore_build(self, local_dir: Path,
                               is_dryrun: bool) -> tuple[ExitCode, Path | None]:
        path = self.find_cloudstore_release()
        if not path:
            return (1, None)
        log.debug(f"Using cloudstore build: {path}")
        c = f"docker cp hadoop-build:{path} {local_dir}/"
        (ret, _) = cmd.run(c, is_dryrun=is_dryrun)
        if ret != 0:
            log.error("Failed to copy cloudstore release from {HADOOP_BUILD_CONTAINER}.")
            return (ret, None)
        return (0, local_dir / path.name)


class GitHadoop(Task):
    task_id = TaskId("git-hadoop", PhaseType.BUILD)

    # no dependencies

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        # TODO interactive support (via App + single thread)
        is_interactive = False
        # TODO option to download a release tar instead of git clone
        h_cfg = arg.get_config().get_build_cfg(BuildType.HADOOP)
        if not h_cfg:
            raise RuntimeError("Hadoop build config not found.")
        local_hadoop = Path(h_cfg.git_path)
        # TODO is_dryrun
        git = Git(HADOOP_GIT_URI, local_hadoop, arg.ui)
        git.clone(h_cfg.get_git_ref(), is_interactive)


class HadoopBuildImageTask(Task):
    task_id = TaskId("hadoop-build-image", PhaseType.BUILD)

    @override
    def dependencies(self) -> Set[TaskId]:
        return set([GitHadoop.task_id])

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        builder = HadoopBuild(arg)
        err = builder.build_image(is_cached, is_dryrun)
        if err != 0:
            raise RuntimeError("Failed to build hadoop build image.")


class DeployHadoopBuildContainer(Task):
    task_id = TaskId("hadoop-build", PhaseType.DEPLOY)

    @override
    def dependencies(self) -> Set[TaskId]:
        return {HadoopBuildImageTask.task_id}

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        builder = HadoopBuild(arg)
        err = builder.run_container(is_dryrun)
        if err != 0:
            raise RuntimeError("Failed to run hadoop build container.")


class BuildHadoopRelease(Task):
    task_id = TaskId("hadoop-release", PhaseType.BUILD)

    @override
    def dependencies(self) -> Set[TaskId]:
        return {DeployHadoopBuildContainer.task_id,
                GitHadoop.task_id}

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        builder = HadoopBuild(arg)
        err = builder.build_in_container(is_cached, is_dryrun)
        if err != 0:
            raise RuntimeError("Failed to build hadoop in container.")
        (err, path) = builder.fetch_hadoop_build(self.get_output_dir(), is_cached=is_cached)
        if err != 0 or not path:
            raise RuntimeError("Failed to fetch hadoop release from container.")
        log.info(f"Hadoop build downloaded to local {path}")


class InstallHadoop(Task):
    task_id = TaskId("hadoop-install", PhaseType.DEPLOY)

    @override
    def dependencies(self) -> Set[TaskId]:
        return {BuildHadoopRelease.task_id, ClusterTask.task_id}

    def _install_hadoop(self, app: App, is_cached: bool, is_dryrun: bool):
        n_build = ClusterNodeBuild(app)
        if is_cached and n_build.check_hadoop_install():
            log.info("[cache hit] existing Hadoop installation on cluster nodes.")
        else:
            h_build = HadoopBuild(app)
            (err, path) = h_build.fetch_hadoop_build(self.get_output_dir(), is_cached=is_cached)
            if err != 0 or not path:
                raise RuntimeError("Failed to fetch hadoop release from container.")
            err = n_build.install_hadoop(path, is_dryrun)
            if err != 0:
                raise RuntimeError("Failed to install hadoop on cluster nodes.")

        # Copy auth-keys.yml config for s3 (localstack) etc.
        config_path = Project.get_project_root() / "config" / "auth-keys.xml"
        dest_path = Path(HADOOP_HOME) / "etc" / "hadoop"
        ret = n_build.copy_to_containers(config_path, str(dest_path))
        if ret != 0:
            return ret

    def _install_cloudstore(self, app: App, is_cached: bool, is_dryrun: bool):
        n_build = ClusterNodeBuild(app)
        h_build = HadoopBuild(app)
        if is_cached:
            path = n_build.find_in_containers("cloudstore-*.jar")
            if path:
                log.info(f"[cache hit] existing cloudstore jar {path} on cluster nodes.")
                return

        (err, path) = h_build.fetch_cloudstore_build(Project.get_build_dir(), is_dryrun)
        if err == 0 and path:
            err = n_build.copy_to_containers(path, is_dryrun=is_dryrun)
            if err != 0:
                raise RuntimeError("Failed to copy cloudstore jar to cluster nodes.")

    def _patch_config(self, app: App, is_dryrun: bool):
        n_build = ClusterNodeBuild(app)
        err = n_build.copy_to_containers(Project.get_project_root() / "abd" / "scripts"
                                         / "hadoop-inject-config.sh", is_dryrun=is_dryrun)
        if err != 0:
            raise RuntimeError("Failed to copy hadoop-inject-config.sh to cluster nodes.")

        deploy = app.get_config().get_deploy_cfg("cluster-node")
        nodes = n_build.get_deploy_hosts(deploy)
        for host in nodes:
            (err, output) = host.run_command("./hadoop-inject-config.sh", is_dryrun=is_dryrun)
            if err != 0:
                e = f"Failed to inject config on {host}: {output}"
                log.error(e)
                raise RuntimeError(e)
        log.info("✅ Successfully injected hadoop config on cluster nodes.")

    @override
    def run(self, arg: App, is_cached: bool, is_dryrun: bool):
        self._install_hadoop(arg, is_cached, is_dryrun)
        self._patch_config(arg, is_dryrun)
        self._install_cloudstore(arg, is_cached, is_dryrun)
