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

from abd.context import App
from abd.project import CmdResult, ExitCode

log = logging.getLogger(__name__)


def _join_lines(cmd: str) -> str:
    # split into lines, trim them, then join with a single space
    return " ".join(line.strip() for line in cmd.splitlines())


def run_throws(cmd: str, cwd: Path | None = None, input: str = "") -> str:
    """ Run a command and return its output, or throw if it fails. """
    exit_code, output = run(cmd, cwd, input)
    if exit_code != 0:
        raise Exception(f"Command '{_join_lines(cmd)}' failed with exit code {exit_code}")
    return output


def run(cmd: str, cwd: Path | None = None, input: str = "") -> CmdResult:
    """ Run a command and capture its output. """
    cmd = _join_lines(cmd)
    log.info(f"-> {cmd} (cwd={cwd})")
    result = subprocess.run(cmd, shell=True, input=input, text=True, capture_output=True, cwd=cwd)
    if result.returncode != 0:
        log.error(result.stderr)
    return CmdResult(exit_code=result.returncode, std_out=result.stdout)


def run_raw(cmd: list[str], cwd: Path | None = None) -> ExitCode:
    log.info(f"-> {cmd} (cwd={cwd})")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        log.error(f"Command failed with exit code {result.returncode}")
    return result.returncode


def run_print(cmd: str, cwd: Path | None = None) -> ExitCode:
    """ Run a command and stream its output to the console. """
    cmd = _join_lines(cmd)
    log.info(f"-> {cmd} (cwd={cwd})")
    with Popen(cmd, shell=True, text=True, cwd=cwd, stdout=subprocess.PIPE,
               stderr=subprocess.STDOUT) as proc:
        if proc.stdout is None:
            log.error("Failed to capture command output")
            return 1
        for line in proc.stdout:
            sys.stdout.write("> " + line)
            sys.stdout.flush()
        ret = proc.wait()
        if ret != 0:
            log.error(f"Command failed with exit code {proc.returncode}")
        return ret


def run_with_status(app: App, cmd: str, cwd: Path | None = None) -> ExitCode:
    cmd = _join_lines(cmd)
    output_lines = []
    start = time.time()
    console_height = app.console.size.height
    output_rows = console_height - 1
    layout = Layout()
    layout.split(
        Layout(name="output", size=output_rows),
        Layout(name="status", size=1)
    )
    with Live(layout, refresh_per_second=4):
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
