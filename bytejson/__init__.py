from __future__ import annotations

import os
from typing import Self

from .index import build_index
from .lazy import wrap_node
from .mmap_reader import MmapReader
from .storage import IndexStorage
from .utils import index_matches_file

__all__ = ["ByteJSONFile", "build_index", "open"]

__version__ = "0.1.0"


class ByteJSONFile:

    def __init__(self, json_path: str, index_path: str) -> None:
        self.json_path = json_path
        self.index_path = index_path
        self._storage = IndexStorage(index_path)
        self._reader = MmapReader(json_path)

        root_id = int(self._storage.get_meta("root_id"))
        self._root = self._storage.get_node(root_id)

    def __getitem__(self, key):
        return wrap_node(self._storage, self._reader, self._root)[key]

    def __len__(self) -> int:
        return len(wrap_node(self._storage, self._reader, self._root))

    def __iter__(self):
        return iter(wrap_node(self._storage, self._reader, self._root))

    def root(self):
        return wrap_node(self._storage, self._reader, self._root)

    def to_python(self):
        return self.root().to_python()

    def close(self) -> None:
        self._reader.close()
        self._storage.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<ByteJSONFile {self.json_path!r} index={self.index_path!r}>"


def open(json_path: str, index_path: str | None = None) -> ByteJSONFile:
    json_path = os.path.abspath(json_path)
    index_path = os.path.abspath(index_path) if index_path else json_path + ".bjidx"

    needs_build = not os.path.exists(index_path)

    if not needs_build:
        storage = IndexStorage(index_path)
        try:
            version = storage.get_meta("version")
            if version != "2":
                needs_build = True
            else:
                needs_build = not index_matches_file(storage, json_path)
        finally:
            storage.close()

    if needs_build:
        build_index(json_path, index_path)

    return ByteJSONFile(json_path, index_path)
