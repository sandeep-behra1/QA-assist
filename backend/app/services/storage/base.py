"""File storage abstraction.

Business logic only ever holds an opaque storage *key*. Swapping local disk
for S3/Azure Blob means writing another implementation of this protocol --
no scoring, API or UI code changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Protocol, runtime_checkable


@dataclass(frozen=True)
class StoredFile:
    key: str
    size_bytes: int
    content_type: str | None


@runtime_checkable
class FileStorage(Protocol):
    def save(self, key: str, fileobj: BinaryIO, content_type: str | None = None) -> StoredFile: ...

    def open(self, key: str) -> BinaryIO: ...

    def exists(self, key: str) -> bool: ...

    def delete(self, key: str) -> None: ...

    def size(self, key: str) -> int: ...


class FileNotFoundInStorage(FileNotFoundError):
    pass
