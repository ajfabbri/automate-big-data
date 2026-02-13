#!/usr/bin/env python3

import argparse
import logging
import sys

from abd.config import CLOUDSTORE_GIT_URI, CLOUSTORE_GIT_REF, Config
from abd.config import HADOOP_GIT_URI, HADOOP_GIT_REF, Loader
from pathlib import Path

from abd.container import Containers, HadoopBuild
from abd.context import App
from abd.project import ExitCode
from abd.ui import prompt_bool
from abd.git import Git

log = logging.getLogger(__name__)


def do_config(is_interactive: bool) -> Config:
    loader = Loader()
    return loader.create(is_interactive)


def do_check(app: App):
    print("XXX TODO Running checks...")


def clone_git(local_dir: Path, git_uri: str, git_ref: str, is_interactive: bool):
    if is_interactive:
        answer = prompt_bool(f"Git clone {git_uri} to {local_dir} and checkout {git_ref}", True)
        if not answer:
            print(f"Skipping git clone of {git_uri}!")
            return
    git = Git(git_uri, local_dir)
    git.ensure_clone(git_ref)


def do_install(app: App, is_interactive: bool = True) -> Config:
    """ Check config and install local clones of git repos. """

    cfg = do_config(is_interactive)
    if not cfg.hadoop:
        print("Hadoop not enabled in config, skipping install.")
        return cfg

    if not cfg.hadoop.hadoop_git_path:
        print("Hadoop git path not set in config, skipping install.")
        return cfg

    if not cfg.hadoop.cloudstore_git_path:
        print("Cloudstore git path not set in config, skipping install.")
        return cfg

    local_hadoop = Path(cfg.hadoop.hadoop_git_path)
    clone_git(local_hadoop, HADOOP_GIT_URI, HADOOP_GIT_REF, is_interactive)

    local_cloudstore = Path(cfg.hadoop.cloudstore_git_path)
    clone_git(local_cloudstore, CLOUDSTORE_GIT_URI, CLOUSTORE_GIT_REF, is_interactive)
    return cfg


def do_test(app: App):
    print("XXX TODO test")


def do_build(app: App, cfg: Config) -> ExitCode:
    """Handle container build command. Returns exit code (0 on success)."""
    h_build = HadoopBuild(app, cfg)
    return h_build.build_image()


def init_container_cfg(app: App, args: argparse.Namespace, is_build: bool) -> Config:
    """ Ensure we're ready for container operations and return the config."""
    if args.cached or not is_build:
        cfg = Loader().load()
        if not cfg:
            e = "No config found, try `config -i`."
            raise Exception(e)
    else:
        is_interactive = args.interactive if hasattr(args, "interactive") else False
        cfg = do_install(app, is_interactive)
    return cfg


def do_container(app: App, args: argparse.Namespace) -> ExitCode:
    ret = 0
    try:
        do_container_throws(app, args)
    except Exception as e:
        log.error(f"Container command failed: {e}")
        ret = 1
    return ret


def do_container_throws(app: App, args: argparse.Namespace):
    """Handle container subcommands. Return exit code (0 for success)."""

    cfg = init_container_cfg(app, args, is_build=(args.container_cmd == "build"))
    if not cfg.hadoop:
        print("Hadoop not enabled in config, skipping.")
        return

    containers = Containers(app, cfg)
    if args.container_cmd == "build":
        return do_build(app, cfg)
    elif args.container_cmd == "list":
        print(containers.list(args.name))
    elif args.container_cmd == "run":
        containers.run_all()
    elif args.container_cmd == "stop":
        containers.stop(args.name)
    elif args.container_cmd == "attach":
        containers.attach(args.name)
    else:
        e = f"Unknown container command: {args.container_cmd}"
        raise Exception(e)


def add_interactive_opt(parser: argparse.ArgumentParser):
    parser.add_argument("-i", "--interactive", action="store_true", help="Run in interactive mode")


def main() -> ExitCode:
    # Define CLI args
    parser = argparse.ArgumentParser(prog="abd",
                                     description="abd: automate big data CLI tool.")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    subparsers = parser.add_subparsers(dest="command", required=True)
    config_p = subparsers.add_parser("config", help="Configure settings")
    add_interactive_opt(config_p)
    _ = subparsers.add_parser("test", help="Run tests")
    _ = subparsers.add_parser("check", help="Run checks")
    install_p = subparsers.add_parser("install", help="Install dependencies")
    add_interactive_opt(install_p)
    container_p = subparsers.add_parser("container", help="Container commands")
    container_p.add_argument("-n", "--name", help="container name / filter")
    container_p.add_argument("-c", "--cached", action="store_true",
                             help="Skip updating dependencies / images / build")
    container_sub = container_p.add_subparsers(dest="container_cmd", required=True)
    c_build_p = container_sub.add_parser("build", help="Build containers")
    _ = container_sub.add_parser("list", help="List containers")
    _ = container_sub.add_parser("run", help="Run container(s)")
    _ = container_sub.add_parser("stop", help="Stop container(s)")
    _ = container_sub.add_parser("attach", help="Attach to a running container")
    add_interactive_opt(c_build_p)

    # Parse args and configure logging
    args = parser.parse_args()
    log_level = logging.WARNING
    if args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG
    logging.basicConfig(level=log_level, format='%(name)s - %(levelname)s - %(message)s')

    if args.command == "config":
        do_config(args.interactive)
    else:
        # init main app context
        app = App()
        if args.command == "test":
            do_test(app)
        elif args.command == "check":
            do_check(app)
        elif args.command == "install":
            do_install(app, args.interactive)
        elif args.command == "container":
            do_container(app, args)
        else:
            print(f"Unknown command: {args.command}")
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
