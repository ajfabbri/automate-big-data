import hashlib
from pathlib import Path
from typing import Tuple
import logging
import urllib.request
from urllib.parse import urlsplit

from abd.project import ExitCode

log = logging.getLogger(__name__)
# TODO unit tests


class URI(str):
    """ A simple wrapper around string to represent a URI. """
    def __init__(self, uri: str):
        # parse with urllib and ensure valid http, https, or local file
        self.split_result = urlsplit(uri)

    def scheme(self) -> str:
        return self.split_result.scheme

    def name(self) -> str:
        return Path(self.split_result.path).name


class Downloader:
    """ Download utility for text or binary files. Includes
        logic for caching and verifying downloaded archive files. """

    @classmethod
    def get_text(cls, url: URI, save_dir: Path | None = None) -> Tuple[ExitCode, str | None]:
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
                if save_dir:
                    with open(save_dir / url.name(), 'w', encoding='utf-8') as out_file:
                        out_file.write(content)
                        log.debug(f"Saved text content to {save_dir / url.name()}")
        except Exception as e:
            log.error(f"Failed to download file from {url}: {e}")
            return (1, None)
        log.info(f"File downloaded successfully from {url}")
        return (0, content)

    @classmethod
    def save_binary(cls, url: str, save_path: Path, cached=False) -> ExitCode:
        """Download binary file from the given URL and save to the specified path."""
        if cached and save_path.exists():
            log.info(f"[skipped] File already exists at {save_path}.")
            return 0
        try:
            log.info(f"Starting download from {url}...")
            # don't overwrite destination until download complete
            temp_path = save_path.with_suffix(save_path.suffix + ".tmp")
            with urllib.request.urlopen(url) as response:
                # Check HTTP status
                if response.status != 200:
                    e = f"HTTP Error: {response.status} {response.reason}"
                    log.error(e)
                    return 1

                # Create directory if it doesn't exist
                save_path.parent.mkdir(parents=True, exist_ok=True)

                # Open file in binary write mode
                with open(temp_path, 'wb') as out_file:
                    chunk_size = 8192
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
                # Move temp file to final destination
                if save_path.exists():
                    save_path.unlink()
                temp_path.rename(save_path)
        except Exception as e:
            log.error(f"Failed downloading file from {url}: {e}")
            return 1

        log.info(f"File downloaded successfully: {save_path}")
        return 0

    def __init__(self, uri: URI, save_dir: Path, cached=True):
        self.save_dir = save_dir
        self.uri = uri
        self.want_cached = cached
        self.name = Path(uri.split_result.path).name
        if not self.save_dir.exists():
            self.save_dir.mkdir(parents=True)

    def local_path(self) -> Path:
        return self.save_dir / self.name

    def _validate_checksum(self, binary_path: Path, checksum_path: Path) -> bool:
        with open(checksum_path, "r") as f:
            expect = f.read().split("=")[1].strip()
            sha512 = hashlib.sha512()
            with open(binary_path, "rb") as bf:
                for chunk in iter(lambda: bf.read(8192), b""):
                    sha512.update(chunk)
        calc = sha512.hexdigest()
        if calc != expect:
            log.info(f"Checksum mismatch {binary_path}: expect {expect}, got {calc}")
            return False
        log.debug(f"Checksum match {binary_path}: {expect}")
        return True

    def _fetch(self, uri: URI, cached=True) -> Path:
        local = self.save_dir / uri.name()
        if not (local.exists() and cached):
            err = self.save_binary(uri, local, cached=cached)
            if err != 0:
                e = f"Failed to download file from {uri}"
                log.error(e)
                raise Exception(e)
        return local

    def _fetch_checksum(self, cached=True) -> Path:
        checksum_uri = URI(self.uri + ".sha512")
        # TODO check self.want_cached
        return self._fetch(checksum_uri, cached=cached)

    def _ensure_fetched(self, cached=True):
        if self.uri.scheme() in ["http", "https"]:
            checksum_path = self._fetch_checksum(cached)
            _ = self._fetch(self.uri, cached=cached)
            if not self._validate_checksum(self.local_path(), checksum_path):
                e = f"Bad hash. Disable caching or delete checksum file to refresh: {checksum_path}"
                log.error(e)
                raise Exception(e)

        elif self.uri.scheme() == "":
            if not self.local_path().exists():
                e = f"Hadoop tar build not found at {self.local_path()}. " \
                    + "Did you mean to specify a URL?"
                log.error(e)
                raise Exception(e)
        else:
            e = f"Bad URL scheme {self.uri.scheme()} for download."
            log.error(e)
            raise Exception(e)

    def fetch(self, cached=True) -> Path:
        """Fetch the file from the URI and return the local path."""
        self._ensure_fetched(cached=cached)
        return self.local_path()
