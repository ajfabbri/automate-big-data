from pathlib import Path
from typing import Tuple
import logging
import urllib.request

from abd.project import ExitCode

log = logging.getLogger(__name__)

# TODO unit tests


def download_text(url: str) -> Tuple[ExitCode, str | None]:
    """Download text file from the given URL and return its content."""
    try:
        log.info(f"Fetching text from {url}...")
        with urllib.request.urlopen(url) as response:
            # Check HTTP status
            if response.status != 200:
                e = f"HTTP Error: {response.status} {response.reason}"
                log.error(e)
                return (1, None)
            content = response.read().decode('utf-8')
    except Exception as e:
        log.error(f"Failed to download file from {url}: {e}")
        return (1, None)
    log.info(f"File downloaded successfully from {url}")
    return (0, content)


def download_binary(url: str, save_path: Path, cached=False) -> Tuple[ExitCode, Path | None]:
    """Download binary file from the given URL and save to the specified path."""
    if cached and save_path.exists():
        log.info(f"[skipped] File already exists at {save_path}.")
        return (0, save_path)
    try:
        log.info(f"Starting download from {url}...")
        with urllib.request.urlopen(url) as response:
            # Check HTTP status
            if response.status != 200:
                e = f"HTTP Error: {response.status} {response.reason}"
                log.error(e)
                return (1, None)

            # Create directory if it doesn't exist
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Open file in binary write mode
            with open(save_path, 'wb') as out_file:
                chunk_size = 8192
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_file.write(chunk)
    except Exception as e:
        log.error(f"Failed to download file from {url}: {e}")
        return (1, None)

    log.info(f"File downloaded successfully: {save_path}")
    return (0, save_path)
