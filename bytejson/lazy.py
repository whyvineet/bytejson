from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from . import parser
from .mmap_reader import MmapReader
from .storage import IndexStorage, NodeRecord


def wrap_node(storage: IndexStorage, reader: MmapReader, node: NodeRecord) -> Any:
    if node.node_type == "object":
        return LazyObject(storage, reader, node)
    if node.node_type == "array":
        return LazyArray(storage, reader, node)
    raw = reader.read(node.byte_offset, node.byte_length)
    return parser.parse_leaf(raw)


class _LazyContainer:

    def __init__(self, storage: IndexStorage, reader: MmapReader, node: NodeRecord):
        self._storage = storage
        self._reader = reader
        self._node = node

    def __len__(self) -> int:
        return self._storage.count_children(self._node.id)

    def to_python(self) -> Any:
        raw = self._reader.read(self._node.byte_offset, self._node.byte_length)
        return parser.parse_full(raw)

    def __repr__(self) -> str:
        return f"<{type(self).__name__} id={self._node.id} len={len(self)}>"


class LazyObject(_LazyContainer):

    def __getitem__(self, key: str) -> Any:
        child = self._storage.get_child_by_key(self._node.id, key, self._node.byte_offset)
        if child is None:
            raise KeyError(key)
        return wrap_node(self._storage, self._reader, child)

    def get(self, key: str, default: Any = None) -> Any:
        child = self._storage.get_child_by_key(self._node.id, key, self._node.byte_offset)
        if child is None:
            return default
        return wrap_node(self._storage, self._reader, child)

    def __contains__(self, key: str) -> bool:
        return self._storage.get_child_by_key(self._node.id, key, self._node.byte_offset) is not None

    def keys(self) -> list[str]:
        return [c.key for c in self._storage.get_children(self._node.id, self._node.byte_offset)]

    def values(self) -> Iterator[Any]:
        for c in self._storage.get_children(self._node.id, self._node.byte_offset):
            yield wrap_node(self._storage, self._reader, c)

    def items(self) -> Iterator[tuple[str, Any]]:
        for c in self._storage.get_children(self._node.id, self._node.byte_offset):
            yield c.key, wrap_node(self._storage, self._reader, c)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())


class LazyArray(_LazyContainer):

    def __getitem__(self, index: int | slice) -> Any:
        if isinstance(index, slice):
            children = self._storage.get_children(self._node.id, self._node.byte_offset)
            return [
                wrap_node(self._storage, self._reader, c) for c in children[index]
            ]

        if index < 0:
            index += len(self)
        child = self._storage.get_child_by_index(self._node.id, index, self._node.byte_offset)
        if child is None:
            raise IndexError("array index out of range")
        return wrap_node(self._storage, self._reader, child)

    def __iter__(self) -> Iterator[Any]:
        for c in self._storage.get_children(self._node.id, self._node.byte_offset):
            yield wrap_node(self._storage, self._reader, c)