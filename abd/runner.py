from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import tempfile
import logging
from queue import SimpleQueue, Empty
from threading import Lock
from typing import Callable, MutableMapping

from abd.builder.hadoop import HadoopBuild
from abd.config.phase import ConfigTask
from abd.container.localstack import LocalstackBuild
from abd.config.raw import Config, BuildType
from abd.container.cluster_node import ClusterNodeBuild
from abd.container.container import Containers
from abd.context import App
from abd.job.job import Job
from abd.job.phases import Task, TaskId, PhaseType
from abd.project import ExitCode, Project

log = logging.getLogger(__name__)


@dataclass
class ExecutionPlan:
    # I wanted fast parallel execution of build / deploy / run tasks.
    # This is an attempt as a "simple" "DAG of dependencies" task runner.
    def __init__(self, job: Job):
        self.children: dict[TaskId, set[TaskId]] = {}  # things that depend on a phase
        self.parents: dict[TaskId, set[TaskId]] = {}  # things that a phase depends on

        self.job = job
        for c_id, c_phase in job.get_tasks().items():
            deps = c_phase.dependencies()
            if c_id != ConfigTask.phase_id:
                deps.add(ConfigTask.phase_id)  # all tasks depend on config phase

            self.parents[c_id] = deps
            for p_id in self.parents[c_id]:
                if p_id not in self.children:
                    self.children[p_id] = set()
                self.children[p_id].add(c_id)
            if c_id not in self.children:
                self.children[c_id] = set()

    def _tasks_in_phase(self, phase_type: PhaseType, name_filter: str | None) -> set[TaskId]:
        tasks = set()
        for task_id in self.children.keys():
            try:
                task = self.job.get_tasks()[task_id]
            except KeyError:
                e = f"Required task {task_id} not found in job tasks!"
                log.error(e)
                raise RuntimeError(e)
            if task.phase_id.phase_type == phase_type and \
                    (not name_filter or task.phase_id.name == name_filter):
                tasks.add(task_id)
            else:
                log.debug(f"Skipping task {task_id} (name filter {name_filter})")
        return tasks

    def _collect_needed(self, targets: set[TaskId]) -> set[TaskId]:
        needed = set()
        stack: list[TaskId] = list(targets)

        while stack:
            t = stack.pop()
            if t in needed:
                continue
            needed.add(t)
            stack.extend(self.parents.get(t, []))
        return needed

    def _compute_in_degree(self, needed: set[TaskId]) -> MutableMapping[TaskId, int]:
        in_degree = {}
        for t in needed:
            # TODO omit the `p in needed` check, assuming needed includes
            # all parents (recursively)?
            in_degree[t] = sum(1 for p in self.parents[t] if p in needed)
        return in_degree

    def run_parallel(self, phase: PhaseType,
                     execute_fn: Callable[[Task], None], max_threads: int = 4):
        # Only include tasks required for target phase
        targets = self._tasks_in_phase(phase, None)
        needed = self._collect_needed(targets)
        log.debug(f"{len(needed)} tasks needed for phase {phase} w/ {len(targets)} targets")
        # Calculate number of dependencies remaining for each task
        in_degree = self._compute_in_degree(needed)
        # Init ready queue with tasks without dependencies
        ready = SimpleQueue()
        num_waiters = len(needed)
        for t in needed:
            if in_degree[t] == 0:
                log.debug(f"Task {t} has no dependencies, adding to ready queue.")
                ready.put(t)
                num_waiters -= 1
            else:
                log.debug(f"Task {t} has {in_degree[t]} dependencies, not ready yet.")

        lock = Lock()

        def get_num_waiters() -> int:
            with lock:
                return num_waiters

        def worker(idx: int):
            while True:
                # execute next ready task
                try:
                    # TODO a condition var or other way to signal
                    # workers to exit when all tasks are done.
                    t = ready.get(block=True, timeout=0.1)
                except Empty:
                    if get_num_waiters() == 0:
                        log.debug(f"Worker {idx} finished.")
                        return
                    else:
                        continue
                task = self.job.get_tasks()[t]
                log.debug(f"Worker {idx} executing task {task.phase_id}")
                execute_fn(self.job.get_tasks()[t])

                # update finished task's dependencies
                for c in self.children.get(t, []):
                    if c not in needed:
                        continue
                    with lock:
                        in_degree[c] -= 1
                        if in_degree[c] == 0:
                            ready.put(c)
                            nonlocal num_waiters
                            num_waiters -= 1

        # Start worker threads
        futures: list[Future] = []
        with ThreadPoolExecutor(max_workers=max_threads) as pool:
            for idx in range(max_threads):
                futures.append(pool.submit(worker, idx))
            for (i, f) in enumerate(futures):
                # no return yet, but propagate exceptions
                log.debug(f"( o)( o) Waiting for worker {i} to finish.")
                f.result()
                log.debug(f"         done: worker {i}")


class NewRunner:
    """ Top-level execution of Jobs. """
    def __init__(self, app: App):
        self.app = app
        self.job = Job()

    def run(self, phase: PhaseType, phase_name: str | None = None) -> ExitCode:

        if phase_name:
            raise NotImplementedError("TODO Run by task name not implemented yet")
        plan = ExecutionPlan(self.job)

        def execute(task: Task):
            log.info(f"Executing task: {task.phase_id}")
            task.run(self.app, self.app.args.is_cached, self.app.args.is_dryrun)

        plan.run_parallel(phase, execute)

        return 0


class Runner:
    """ Running tasks on cluster nodes. """
    def __init__(self, app: App, cfg: Config):
        self.app = app
        self.cfg = cfg
        h_cfg = self.cfg.get_build_cfg(BuildType.HADOOP)
        if h_cfg:
            self.h_cfg = h_cfg
        else:
            raise RuntimeError("Hadoop not enabled in config, cannot run containers.")
        self.c_cfg = self.cfg.get_build_cfg(BuildType.CLOUDSTORE)
        node_deploy = cfg.get_deploy_cfg("cluster-node")
        if node_deploy:
            self.node_deploy = node_deploy
        else:
            raise RuntimeError("cluster-node deploy config not found, cannot run containers.")

    def run_all(self, is_cached: bool) -> ExitCode:
        # Start hadoop build container
        # create network for containers
        ret = Containers.create_network(self.app.container_network)
        if ret != 0:
            log.error("Failed to create container network.")
            return ret

        hbuild = HadoopBuild(self.app)

        ret = hbuild.run_container(False)
        if ret != 0:
            return ret

        if not is_cached:
            # 2. run build script in container
            ret = hbuild.build_in_container(False, False)
            if ret != 0:
                return ret

        # 3. start hadoop node containers
        nbuild = ClusterNodeBuild(self.app)
        for i in range(self.node_deploy.num_nodes):
            ret = nbuild.run_container(False)
            if ret != 0:
                return ret

        # 4. Deploy build(s) to node containers
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            (err, path) = hbuild.fetch_hadoop_build(tmpdir_path)
            if err != 0:
                return err
            if not path:
                return 1
            ret = nbuild.install_hadoop(path)
            if ret != 0:
                return ret

            (err, path) = hbuild.fetch_cloudstore_build(tmpdir_path)
            if err != 0:
                return err
            if not path:
                return 1
            err = nbuild.copy_to_containers(path)
            if err != 0:
                return err

        # Copy auth-keys.yml config for s3 (localstack) etc.
        config_path = Project.get_project_root() / "config" / "auth-keys.xml"
        dest_path = "$HOME"
        ret = nbuild.copy_to_containers(config_path, dest_path)
        if ret != 0:
            return ret

        # Start localstack, create s3 bucket
        ls_build = LocalstackBuild(self.app)
        ls_build.run_container(False)
        ls_build.ensure_s3_bucket("abd-bucket")

        # Run tests in node containers
        return 0
