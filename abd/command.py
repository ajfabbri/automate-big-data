import re
from typing import Iterator
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
import logging
from pathlib import Path
import subprocess
from subprocess import Popen
import sys
import time

from abd.project import CmdResult, ExitCode
from abd.ui import Ui

log = logging.getLogger(__name__)


def _join_lines(cmd: str) -> str:
    # split into lines, trim them, then join with a single space
    return " ".join(line.strip() for line in cmd.splitlines())


def run_throws(cmd: str, cwd: Path | None = None, input: str = "", quiet=False) -> str:
    """ Run a command and return its output, or throw if it fails. """
    exit_code, output = run(cmd, cwd, input, quiet=quiet)
    if exit_code != 0:
        raise Exception(f"Command '{_join_lines(cmd)}' failed with exit code {exit_code}")
    return output


def run(cmd: str, cwd: Path | None = None, input: str = "", is_dryrun=False,
        quiet=False) -> CmdResult:
    """ Run a command and capture its output. """
    output = ""
    cmd = _join_lines(cmd)
    if is_dryrun:
        print(f"[DRY RUN] {cmd} (cwd={cwd})")
        return CmdResult(exit_code=0, std_out="")
    log.info(f"-> {cmd} (cwd={cwd})")
    result = subprocess.run(cmd, shell=True, input=input, text=True, capture_output=True, cwd=cwd)
    serr = result.stderr.strip()
    sout = result.stdout.strip()
    if result.returncode != 0:
        fn = log.error if not quiet else log.info
        fn(f"{cmd} -> {result.stderr}")
        output = serr
    if output and sout:
        output += "\n"
    output += sout
    return CmdResult(exit_code=result.returncode, std_out=output)


def run_raw(cmd: list[str], cwd: Path | None = None) -> ExitCode:
    log.info(f"-> {cmd} (cwd={cwd})")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        log.error(f"Command failed with exit code {result.returncode}")
    return result.returncode


def run_print(cmd: str, cwd: Path | None = None, log_prefix="", quiet=False,
              is_dryrun=False) -> ExitCode:
    """ Run a command and stream its output to the console. """
    cmd = _join_lines(cmd)
    p = f"[{log_prefix}] " if log_prefix else ""
    if is_dryrun:
        print(f"{p}[DRY RUN] {cmd} (cwd={cwd})")
        return 0
    log.info(f"{p}-> {cmd} (cwd={cwd})")
    with Popen(cmd, shell=True, text=True, cwd=cwd, stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT) as proc:
        if proc.stdout is None:
            log.error("Failed to capture command output")
            return 1
        for line in proc.stdout:
            sys.stdout.write("> " + line)
            sys.stdout.flush()
        ret = proc.wait()
        if ret != 0 and not quiet:
            log.error(f"Command failed with exit code {proc.returncode}")
        return ret


def run_streaming(cmd: str, filter_re=".*", quiet=False,
                  is_dryrun=False) -> Iterator[str | ExitCode]:
    """ Run a command and return output lines until finished, then return an
        ExitCode. Only returns matching lines when filter_re is provided. """
    cmd = _join_lines(cmd)
    if is_dryrun:
        print(f"[DRY RUN] {cmd}")
        yield 0
        return
    log.info(f"-> {cmd}")
    regex = re.compile(filter_re)
    with Popen(cmd, shell=True, text=True, stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT) as proc:
        if proc.stdout is None:
            log.error("Failed to capture command output")
            yield 1
            return
        for line in proc.stdout:
            if regex.search(line):
                log.debug(f"( match  ) {line}")
                yield line.rstrip()
            else:
                log.debug(f"(filtered) {line}")
        ret = proc.wait()
        if ret != 0 and not quiet:
            log.error(f"Command failed with exit code {proc.returncode}")
        yield proc.returncode


def run_with_status(ui: Ui, cmd: str, cwd: Path | None = None,
                    is_dryrun: bool = False) -> ExitCode:
    """ Use Rich to run a command and display its output in a live-updating
    panel, along with a status line showing the elapsed time. """
    if is_dryrun:
        return run_print(cmd, cwd, is_dryrun=is_dryrun)
    cmd = _join_lines(cmd)
    output_lines = []
    start = time.time()
    console_height = 40  # app.console.size.height
    output_rows = console_height - 1
    layout = Layout()
    layout.split(
        Layout(name="output", size=output_rows),
        Layout(name="status", size=1)
    )
    with Live(layout, refresh_per_second=4, screen=False):
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, cwd=cwd, text=True)
        if proc.stdout is None:
            log.error("Failed to capture command output")
            return 1
        for line in proc.stdout:
            output_lines.append(line.rstrip())
            visible_output = output_lines[-output_rows:]
            while len(visible_output) < output_rows:
                visible_output.insert(0, "")
            layout["output"].update(Panel(Text("\n".join(visible_output)),
                                          title="Output", border_style="blue"))
            elapsed = int(time.time() - start)
            status = f"[green]Running:[/green] {cmd} ([yellow]{elapsed} seconds elapsed[/yellow])"
            layout["status"].update(status)
        ret = proc.wait()
        elapsed = int(time.time() - start)
        if ret == 0:
            status = "[bold green]Success:[/bold green] "
        else:
            status = "[bold red]Failed:[/bold red] "
        return ret


def userinfo() -> tuple[str, int]:
    """ Return the current user name and uid. """
    username = run_throws("whoami").strip()
    uid = int(run_throws("id -u").strip())
    return username, uid


def which(cmd: str) -> str | None:
    """ Return the path to an executable, or None if not found. """
    try:
        return run_throws(f"which {cmd}", quiet=True).strip()
    except Exception:
        return None
