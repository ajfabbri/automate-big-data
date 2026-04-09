#!/usr/bin/env python3

import argparse
import json
import logging
import sys
from typing import List

from abd import task_registry
from abd import project
from abd.config.phase import ConfigTask
from abd.config.raw import Config
from abd.config.raw import Loader
import abd.command as cmd
from abd.container.cluster_node import ClusterNodeBuild
from abd.container.container import Containers
from abd.context import App, Args
from abd.job.job import Job
from abd.job.phases import PhaseType
from abd.project import ExitCode
from abd.runner import NewRunner
from abd.ui import Ui

log = logging.getLogger(__name__)


def do_config(is_interactive: bool, ui: Ui) -> Config:
    loader = Loader()
    return loader.create(is_interactive, ui)


def do_build(app: App) -> ExitCode:
    runner = NewRunner(app)
    return runner.run(f"{PhaseType.BUILD}:", app.args.cached, single_thread=app.args.is_serial)


def do_deploy(app: App, args: argparse.Namespace) -> ExitCode:
    ret: ExitCode = 0
    runner = NewRunner(app)
    name_filter = args.name if hasattr(args, "name") else None
    want_json = args.json if hasattr(args, "json") else False
    match args.deploy_cmd:
        case "list":
            for line in Containers.list(name_filter, want_json=want_json):
                if want_json:
                    obj = json.loads(line)
                    print(json.dumps(obj, indent=2))
                else:
                    print(line)
        case "run":
            return runner.run(f"{PhaseType.DEPLOY}:", app.args.cached)
        case "stop":
            return Containers.stop(name_filter)
        case "attach":
            if not name_filter:
                log.error("Must provide --name argument for attach command.")
                ret = 1
            else:
                return Containers.attach(name_filter)
    return ret


def do_exec(app: App) -> ExitCode:
    if app.args.raw.shell:
        cmd = app.args.raw.shell.strip()
        ConfigTask().run(app, is_cached=False, is_dryrun=app.args.is_dryrun)
        deploy = app.get_config().get_deploy_cfg("cluster-node")
        errors = []
        for host in ClusterNodeBuild.get_deploy_hosts(deploy):
            (err, output) = host.run_command(cmd)
            if err != 0:
                errors.append(f"[host {host.get_name()}] error executing `{cmd}`:\n {output}")
            print(f"{host.get_name()}> {output}")
        if errors:
            log.error("Errors executing command on hosts:\n" + "\n".join(errors))
            return 1
        return 0
    else:
        err = 0
        runner = NewRunner(app)
        task_str = app.args.task_str if app.args.task_str else f"{PhaseType.EXECUTE}:"
        err = runner.run(task_str, app.args.cached, single_thread=app.args.is_serial)
        if err != 0:
            log.error(f"⛔️ Error {err} executing task(s).")
        return err


def do_tasks(app: App):
    show_graph = app.args.raw.graph if hasattr(app.args.raw, 'graph') else False
    job = Job()
    dot = job.to_dot_graph()
    build_dir = project.Project.get_build_dir()
    print_text = True
    if show_graph:
        # use graphviz if available, else just print .dot file
        if cmd.which("dot"):
            dot_path = build_dir / "abd_tasks.dot"
            svg_path = build_dir / "abd_tasks.svg"
            try:
                with open(dot_path, "w") as f:
                    f.write(dot)
                cmd.run_throws(f"dot -Tsvg {dot_path} -o {svg_path}")
                # attempt to display the image
                if cmd.which("xdg-open"):
                    cmd.run_throws(f"xdg-open {svg_path}", quiet=True)
                elif cmd.which("open"):
                    cmd.run_throws(f"open {svg_path}", quiet=True)
                print_text = False
            except Exception as e:
                log.warning(f"Failed display graph w/ graphviz: {e}")
        if print_text:
            print(dot)
    else:
        for t in sorted(job.get_tasks().keys(), key=lambda x: (x.phase_type.value, x.name)):
            print(t)


def add_interactive_opt(parser: argparse.ArgumentParser):
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")


def add_name_opt(parser: argparse.ArgumentParser):
    parser.add_argument("-n", "--name", help="name filter")


def add_dryrun_opt(parser: argparse.ArgumentParser):
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing.")


TASKID_HELP = "    TASK_STR '<phase>:<name>' to match one task. \n" \
    + "        Use '<phase>:' to match all tasks in that phase. \n" \
    + "        Otherwise, '<name>' to match any tasks with that name, \n" \
    + "        where 'all' matches all tasks. Separate multiple TASK_STRs \n" \
    + "        with `,`."


def add_cached_opt(parser: argparse.ArgumentParser):
    help = "Skip updating artifacts for specific tasks. Default \"all\"."
    parser.add_argument("-c", "--cached", metavar="TASK_STR", nargs="?", default=None,
                        const="all", help=help)


def add_task_opt(parser: argparse.ArgumentParser):
    parser.add_argument("--task", "-t", metavar="TASK_STR",
                        help="Run specific task(s) by id.")


def parse_args(parser: argparse.ArgumentParser, argv: List[str] | None) -> Args:
    # Parse args and configure logging
    args = parser.parse_args(argv)
    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG
        import faulthandler
        import signal
        faulthandler.register(signal.SIGUSR1)

    logging.basicConfig(level=log_level, format='%(name)s - %(levelname)s - %(message)s')
    dry = args.dry_run if hasattr(args, 'dry_run') else False
    if hasattr(args, 'cached') and args.cached is not None:
        split = args.cached.split(",")
        if len(split) == 1 and split[0] == '':
            split[0] = "all"
        cached = set(split)
    else:
        cached = set()
    log.debug(f"Requesting cached tasks for {cached}.")
    interactive = args.interactive if hasattr(args, 'interactive') else False
    task = args.task if hasattr(args, 'task') else None
    is_serial = args.one_thread if hasattr(args, 'one_thread') else False
    return Args(is_dryrun=dry, cached=cached, is_interactive=interactive,
                task_str=task, raw=args, is_serial=is_serial)


def main(argv: List[str] | None = None) -> ExitCode:
    # Define CLI args
    parser = argparse.ArgumentParser(prog="abd",
                                     description="abd: automate big data CLI tool.")
    # global options
    parser.add_argument("-v", "--verbose", action="count", default=0)
    subparsers = parser.add_subparsers(dest="command", required=True)
    # config command
    config_p = subparsers.add_parser("config", help="Settings and config generation.")
    add_interactive_opt(config_p)
    # build
    build_p = subparsers.add_parser("build", help=f"Build software and images.\n{TASKID_HELP}")
    add_interactive_opt(build_p)
    add_cached_opt(build_p)
    add_dryrun_opt(build_p)
    # deploy
    deploy_p = subparsers.add_parser("deploy", help="Deploy / provision / install.")
    deploy_sub = deploy_p.add_subparsers(dest="deploy_cmd", required=True)
    d_list_p = deploy_sub.add_parser("list", help="List deployment (hosts, etc.)")
    add_name_opt(d_list_p)
    d_list_p.add_argument("-j", "--json", action="store_true",
                          help="Output full host info in JSON format")

    d_run_p = deploy_sub.add_parser("run", help=f"Run deployment.\n{TASKID_HELP}")
    add_cached_opt(d_run_p)
    add_interactive_opt(d_run_p)
    add_dryrun_opt(d_run_p)
    d_stop_p = deploy_sub.add_parser("stop", help="Stop container / host(s)")
    add_name_opt(d_stop_p)
    d_attach_p = deploy_sub.add_parser("attach", help="Attach to a running host / container")
    add_name_opt(d_attach_p)
    # execute
    help = "Execute tasks / commands."
    exec_p = subparsers.add_parser("exec", help=help, epilog=TASKID_HELP)
    add_dryrun_opt(exec_p)
    add_task_opt(exec_p)
    add_cached_opt(exec_p)
    exec_p.add_argument("--shell", "-s", help="Run this shell command instead of registered task.")
    exec_p.add_argument("--one-thread", "-o", action="store_true",
                        help="Only use one thread for tasks")

    # tasks
    tasks_p = subparsers.add_parser("tasks", help="Show registered tasks.")
    tasks_p.add_argument("--graph", "-g", action="store_true",
                         help="Show graph of task dependencies")

    # init main app context
    _ = task_registry.init()
    args = parse_args(parser, argv)
    app = App(args)
    if args.raw.command == "config":
        # TODO just register a shell task and use runner?

        do_config(args.is_interactive, app.ui)
    else:
        if args.raw.command == "build":
            return do_build(app)
        elif args.raw.command == "deploy":
            return do_deploy(app, args.raw)
        elif args.raw.command == "exec":
            return do_exec(app)
        elif args.raw.command == "tasks":
            do_tasks(app)
        else:
            print(f"Unknown command: {args.raw.command}")
            return 1
    return 0


if __name__ == "__main__":
    err = main(sys.argv)
    if err != 0:
        log.error(f"⛔️ abd exiting with code {err}.")
    sys.exit(err)
