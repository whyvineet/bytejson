from __future__ import annotations

import mmap
from typing import Self


class MmapReader:

    def __init__(self, path: str) -> None:
        self._file = open(path, "rb")
        if self._file_is_empty():
            self._mmap: mmap.mmap | None = None
        else:
            self._mmap = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)

    def _file_is_empty(self) -> bool:
        pos = self._file.tell()
        self._file.seek(0, 2)
        size = self._file.tell()
        self._file.seek(pos)
        return size == 0

    def read(self, offset: int, length: int) -> bytes:
        if self._mmap is None:
            return b""
        return self._mmap[offset : offset + length]

    def close(self) -> None:
        if self._mmap is not None:
            self._mmap.close()
        self._file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
