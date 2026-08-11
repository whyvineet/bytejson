from __future__ import annotations

import array
import json
import mmap
import os
import struct
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Self

TYPE_TO_INT = {"object": 0, "array": 1, "string": 2, "number": 3, "boolean": 4, "null": 5}
INT_TO_TYPE = {v: k for k, v in TYPE_TO_INT.items()}

_NO_KEY = -1
_NO_INDEX = -1
_NO_PARENT = -1

_MAGIC = b"BJI2"
_VERSION = 1
_HEADER_FORMAT = "<4sH"
_HEADER_SIZE = struct.calcsize(_HEADER_FORMAT)
_SECTION_FORMAT = "<QQ"
_SECTION_ENTRY_SIZE = struct.calcsize(_SECTION_FORMAT)
_NUM_SECTIONS = 5

NODE_STRUCT = struct.Struct("<BiiiIq")


@dataclass(slots=True)
class NodeRecord:
    id: int
    parent_id: int | None
    node_type: str
    key: str | None
    array_index: int | None
    byte_offset: int
    byte_length: int

    @property
    def is_container(self) -> bool:
        return self.node_type in ("object", "array")


class IndexStorage:
    def __init__(self, index_path: str) -> None:
        self.index_path = index_path
        self._closed = False
        self._child_by_key_cache: dict[tuple[int, str, int], NodeRecord | None] = {}
        self._child_by_index_cache: dict[tuple[int, int, int], NodeRecord | None] = {}
        if os.path.exists(index_path) and os.path.getsize(index_path) > 0:
            self._mode = "read"
            self._open_read()
        else:
            self._mode = "build"
            self._meta: dict[str, str] = {}
            self._records: list[NodeRecord] = []


    def create_schema(self) -> None:
        assert self._mode == "build", "create_schema() is only valid before commit()"

    def commit(self) -> None:
        if self._mode != "build":
            return
        self._write(self._records, self._meta)
        self._mode = "committed"

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._child_by_key_cache.clear()
        self._child_by_index_cache.clear()
        if self._mode == "read":
            self._mmap.close()
            self._file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- writing --------------------------------------------------------

    def insert_nodes(self, records: Iterable[NodeRecord]) -> None:
        assert self._mode == "build", "insert_nodes() is only valid before commit()"
        self._records = list(records)

    def set_meta(self, key: str, value: str) -> None:
        self._meta[key] = value

    def _write(self, records: list[NodeRecord], meta: dict[str, str]) -> None:
        n = len(records)

        distinct_keys = sorted({r.key for r in records if r.key is not None})
        key_ids = {k: i for i, k in enumerate(distinct_keys)}

        offset_by_id = {r.id: r.byte_offset for r in records}
        counts = [0] * n

        node_bytes = bytearray(n * NODE_STRUCT.size)
        for r in records:
            if r.parent_id is not None:
                parent_offset = offset_by_id.get(r.parent_id, 0)
                counts[r.parent_id] += 1
            else:
                parent_offset = 0
            NODE_STRUCT.pack_into(
                node_bytes,
                r.id * NODE_STRUCT.size,
                TYPE_TO_INT[r.node_type],
                r.parent_id if r.parent_id is not None else _NO_PARENT,
                key_ids[r.key] if r.key is not None else _NO_KEY,
                r.array_index if r.array_index is not None else _NO_INDEX,
                r.byte_length,
                r.byte_offset - parent_offset,
            )

        children_start = [0] * (n + 1)
        for i in range(n):
            children_start[i + 1] = children_start[i] + counts[i]
        cursor = children_start[:-1]
        children_flat = [0] * n
        for r in records:
            if r.parent_id is None:
                continue
            pos = cursor[r.parent_id]
            children_flat[pos] = r.id
            cursor[r.parent_id] += 1

        cs_arr = array.array("I", children_start)
        cf_arr = array.array("I", children_flat)
        if sys.byteorder != "little":
            cs_arr.byteswap()
            cf_arr.byteswap()

        keys_buf = bytearray()
        keys_buf += struct.pack("<I", len(distinct_keys))
        for k in distinct_keys:
            kb = k.encode("utf-8")
            keys_buf += struct.pack("<H", len(kb))
            keys_buf += kb

        meta_buf = json.dumps(meta).encode("utf-8")

        sections = [meta_buf, bytes(keys_buf), bytes(node_bytes), cs_arr.tobytes(), cf_arr.tobytes()]

        header_size = _HEADER_SIZE + _NUM_SECTIONS * _SECTION_ENTRY_SIZE
        offset = header_size
        section_headers = []
        for s in sections:
            section_headers.append((offset, len(s)))
            offset += len(s)

        tmp_path = self.index_path + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(struct.pack(_HEADER_FORMAT, _MAGIC, _VERSION))
            f.writelines(struct.pack(_SECTION_FORMAT, off, length) for off, length in section_headers)
            for s in sections:
                f.write(s)
        os.replace(tmp_path, self.index_path)

    def _open_read(self) -> None:
        with open(self.index_path, "rb") as f:
            self._file = f
            self._mmap = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)

        magic, version = struct.unpack_from(_HEADER_FORMAT, self._mmap, 0)
        if magic != _MAGIC:
            raise ValueError(f"{self.index_path!r} is not a bytejson index file")
        if version != _VERSION:
            raise ValueError(f"{self.index_path!r} has unsupported index version {version}")

        pos = _HEADER_SIZE
        sections = []
        for _ in range(_NUM_SECTIONS):
            off, length = struct.unpack_from(_SECTION_FORMAT, self._mmap, pos)
            sections.append((off, length))
            pos += _SECTION_ENTRY_SIZE
        (meta_off, meta_len), (keys_off, keys_len), (nodes_off, nodes_len), \
            (cs_off, cs_len), (cf_off, cf_len) = sections

        self._meta = json.loads(bytes(self._mmap[meta_off:meta_off + meta_len])) if meta_len else {}
        self._keys = self._parse_keys(keys_off, keys_len)
        self._key_ids = {name: i for i, name in enumerate(self._keys)}

        self._nodes_off = nodes_off
        self._num_nodes = nodes_len // NODE_STRUCT.size

        self._children_start = array.array("I")
        self._children_start.frombytes(bytes(self._mmap[cs_off:cs_off + cs_len]))
        self._children_flat = array.array("I")
        self._children_flat.frombytes(bytes(self._mmap[cf_off:cf_off + cf_len]))
        if sys.byteorder != "little":
            self._children_start.byteswap()
            self._children_flat.byteswap()

    def _parse_keys(self, off: int, length: int) -> list[str]:
        pos = off
        end = off + length
        (count,) = struct.unpack_from("<I", self._mmap, pos)
        pos += 4
        keys = []
        for _ in range(count):
            (klen,) = struct.unpack_from("<H", self._mmap, pos)
            pos += 2
            keys.append(bytes(self._mmap[pos:pos + klen]).decode("utf-8"))
            pos += klen
        assert pos <= end
        return keys

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError(f"I/O operation on closed IndexStorage ({self.index_path!r})")

    def get_meta(self, key: str) -> str | None:
        self._check_open()
        return self._meta.get(key)

    def _unpack_node(self, node_id: int) -> tuple:
        return NODE_STRUCT.unpack_from(self._mmap, self._nodes_off + node_id * NODE_STRUCT.size)

    def _make_record(self, node_id: int, unpacked: tuple, parent_offset: int) -> NodeRecord:
        node_type, parent_id, key_id, array_index, byte_length, delta_offset = unpacked
        return NodeRecord(
            id=node_id,
            parent_id=parent_id if parent_id != _NO_PARENT else None,
            node_type=INT_TO_TYPE[node_type],
            key=self._keys[key_id] if key_id != _NO_KEY else None,
            array_index=array_index if array_index != _NO_INDEX else None,
            byte_offset=parent_offset + delta_offset,
            byte_length=byte_length,
        )

    def get_node(self, node_id: int) -> NodeRecord:
        self._check_open()
        if node_id < 0 or node_id >= self._num_nodes:
            raise KeyError(f"no node with id {node_id}")
        return self._make_record(node_id, self._unpack_node(node_id), parent_offset=0)

    def _child_slice(self, parent_id: int) -> tuple[int, int]:
        return self._children_start[parent_id], self._children_start[parent_id + 1]

    def count_children(self, parent_id: int) -> int:
        self._check_open()
        start, end = self._child_slice(parent_id)
        return end - start

    def get_children(self, parent_id: int, parent_offset: int = 0) -> list[NodeRecord]:
        self._check_open()
        start, end = self._child_slice(parent_id)
        out = []
        for i in range(start, end):
            child_id = self._children_flat[i]
            out.append(self._make_record(child_id, self._unpack_node(child_id), parent_offset))
        return out

    def get_child_by_key(
        self, parent_id: int, key: str, parent_offset: int = 0
    ) -> NodeRecord | None:
        self._check_open()
        return self._child_by_key_cached(parent_id, key, parent_offset)

    @lru_cache(maxsize=8192)
    def _child_by_key_cached(
        self, parent_id: int, key: str, parent_offset: int
    ) -> NodeRecord | None:
        key_id = self._key_ids.get(key)
        if key_id is None:
            return None
        start, end = self._child_slice(parent_id)
        for i in range(start, end):
            child_id = self._children_flat[i]
            unpacked = self._unpack_node(child_id)
            if unpacked[2] == key_id:  # unpacked[2] is key_id
                return self._make_record(child_id, unpacked, parent_offset)
        return None

    def get_child_by_index(
        self, parent_id: int, array_index: int, parent_offset: int = 0
    ) -> NodeRecord | None:
        self._check_open()
        return self._child_by_index_cached(parent_id, array_index, parent_offset)

    @lru_cache(maxsize=8192)
    def _child_by_index_cached(
        self, parent_id: int, array_index: int, parent_offset: int
    ) -> NodeRecord | None:
        start, end = self._child_slice(parent_id)
        if array_index < 0 or array_index >= (end - start):
            return None
        pos = start + array_index
        child_id = self._children_flat[pos]
        unpacked = self._unpack_node(child_id)
        if unpacked[3] != array_index:
            return self._scan_child_by_index(start, end, array_index, parent_offset)
        return self._make_record(child_id, unpacked, parent_offset)

    def _scan_child_by_index(
        self, start: int, end: int, array_index: int, parent_offset: int
    ) -> NodeRecord | None:
        for i in range(start, end):
            child_id = self._children_flat[i]
            unpacked = self._unpack_node(child_id)
            if unpacked[3] == array_index:
                return self._make_record(child_id, unpacked, parent_offset)
        return None