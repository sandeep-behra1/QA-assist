from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from app.core.config import get_settings
from app.services.storage.base import FileNotFoundInStorage, StoredFile


class LocalFileStorage:
    """Filesystem-backed storage rooted at a configured media directory.

    Keys are validated to stay inside the root so a crafted key can never
    read or write outside the media directory.
    """

    def __init__(self, root: Path | None = None):
        self.root = Path(root or get_settings().media_root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if not candidate.is_relative_to(root):
            raise ValueError(f"Storage key escapes the media root: {key!r}")
        return candidate

    def save(self, key: str, fileobj: BinaryIO, content_type: str | None = None) -> StoredFile:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as destination:
            shutil.copyfileobj(fileobj, destination)
        return StoredFile(key=key, size_bytes=path.stat().st_size, content_type=content_type)

    def open(self, key: str) -> BinaryIO:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundInStorage(key)
        return path.open("rb")

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            path.unlink()

    def size(self, key: str) -> int:
        path = self._resolve(key)
        if not path.exists():
            raise FileNotFoundInStorage(key)
        return path.stat().st_size

    def absolute_path(self, key: str) -> Path:
        return self._resolve(key)


_storage: LocalFileStorage | None = None


def get_file_storage() -> LocalFileStorage:
    global _storage
    if _storage is None:
        _storage = LocalFileStorage()
    return _storage
