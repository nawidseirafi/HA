import json
import os
from pathlib import Path
from backend.config import resolve_api_path


def music_dir() -> Path:
    return resolve_api_path("data/music", "data/music")


def socket_path() -> str:
    return str(music_dir() / "runtime.sock")


class Store:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or music_dir()

    def read(self, name: str, default):
        path = self.directory / f"{name}.json"
        if not path.exists():
            return default
        return json.loads(path.read_text())

    def write(self, name: str, value):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = self.directory / f"{name}.json"
        temp = path.with_suffix(".tmp")
        with temp.open("w") as handle:
            os.chmod(temp, 0o600)
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
        descriptor = os.open(self.directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
