from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging
from queue import SimpleQueue, Empty
from threading import Lock
import time
from typing import Callable, MutableMapping

from abd.config.phase import ConfigTask
from abd.core.context import App
from abd.core.task.job import Job, TaskIdSet
from abd.core.task.phases import Task, TaskId
from abd.core.project import ExitCode

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
            if c_id != ConfigTask.task_id:
                deps.add(ConfigTask.task_id)  # all tasks depend on config phase

            self.parents[c_id] = deps
            for p_id in self.parents[c_id]:
                if p_id not in self.children:
                    self.children[p_id] = set()
                self.children[p_id].add(c_id)
            if c_id not in self.children:
                self.children[c_id] = set()

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

    def _propagate_cached(self, cached_tasks: TaskIdSet):
        """ For each t in cached_tasks, mark everything it depends on as also
        cached, modifying `cached_tasks` """
        cached = cached_tasks.get()
        to_add: set[TaskId] = set()
        stack: list[TaskId] = list(cached)
        while stack:
            t = stack.pop()
            for p in self.parents.get(t, []):
                if p not in cached and p not in to_add:
                    to_add.add(p)
                    stack.append(p)
        cached.update(to_add)

    def _compute_in_degree(self, needed: set[TaskId]) -> MutableMapping[TaskId, int]:
        in_degree = {}
        for t in needed:
            # TODO omit the `p in needed` check, assuming needed includes
            # all parents (recursively)?
            in_degree[t] = sum(1 for p in self.parents[t] if p in needed)
        return in_degree

    def run_parallel(self, target_task: str, execute_fn: Callable[[Task, bool], None],
                     cached_tasks: TaskIdSet, max_threads: int = 4) -> ExitCode:
        # Only include tasks required for target phase
        targets = TaskIdSet(self.job, set([target_task])).get()
        needed = self._collect_needed(targets)
        log.debug(f"{len(needed)} tasks needed for {target_task} w/ {len(targets)} targets")
        # Calculate number of dependencies remaining for each task
        in_degree = self._compute_in_degree(needed)
        # If we don't want to rebuild something, also avoid rebuilding stuff it depends on
        self._propagate_cached(cached_tasks)
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
        has_error = False

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
                    elif has_error:
                        log.debug(f"Worker {idx} exiting early due to error.")
                        return
                    else:
                        continue
                task = self.job.get_tasks()[t]
                log.debug(f"Worker {idx} executing task {task.task_id}")
                execute_fn(self.job.get_tasks()[t], t in cached_tasks)

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
        with ThreadPoolExecutor(max_workers=max_threads) as pool:
            workers = range(max_threads)
            future_to_worker = {pool.submit(worker, idx): idx for idx in workers}
            for future in as_completed(future_to_worker):
                idx = future_to_worker[future]
                try:
                    # no return yet, but propagate exceptions
                    log.debug(f"( o)( o) Waiting for worker {idx} to finish.")
                    future.result()
                    log.debug(f"         done: worker {idx}")
                except Exception as e:
                    log.exception(f"[thread {idx}] raised an exception: {e}")
                    has_error = True
        return 1 if has_error else 0


class NewRunner:
    """ Top-level execution of Jobs. """
    def __init__(self, app: App):
        self.app = app
        self.job = Job()

    def run(self, target_str: str, cached_tasks: set[str], single_thread=False) -> ExitCode:
        plan = ExecutionPlan(self.job)
        cached_ids = TaskIdSet(self.job, cached_tasks)

        def execute(task: Task, is_cached: bool):
            start_timestamp = time.monotonic()
            cstatus = " (cached)" if is_cached else ""
            log.info(f"Executing task: {task.task_id}{cstatus}")
            task.run(self.app, is_cached, self.app.args.is_dryrun)
            elapsed = time.monotonic() - start_timestamp
            log.info(f"✔️ {task.task_id} finished in {elapsed:.2f}s{cstatus}")

        if single_thread:
            log.info("Running in single-threaded mode.")
            return plan.run_parallel(target_str, execute, cached_ids, max_threads=1)
        else:
            return plan.run_parallel(target_str, execute, cached_ids)
