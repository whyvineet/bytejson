from __future__ import annotations

import mmap
import os
import re

from .parser import parse_leaf
from .storage import IndexStorage, NodeRecord
from .utils import compute_file_fingerprint

_TRUE = b"true"
_FALSE = b"false"
_NULL = b"null"

_STRING_RE = re.compile(rb'"(?:[^"\\]|\\.)*"', re.DOTALL)

_NUMBER_CHARS = frozenset(b"-+.eE0123456789")
_WS_CHARS = frozenset(b" \t\n\r")


class JSONScanError(ValueError):
    pass


class _Scanner:

    def __init__(self, buf: mmap.mmap) -> None:
        self.buf = buf
        self.length = len(buf)
        self._next_id = 0
        self.records: list[NodeRecord] = []

    def _alloc_id(self) -> int:
        node_id = self._next_id
        self._next_id += 1
        return node_id

    def _add(
        self,
        parent_id: int | None,
        node_type: str,
        key: str | None,
        array_index: int | None,
        offset: int,
        length: int,
    ) -> int:
        node_id = self._alloc_id()
        self.records.append(
            NodeRecord(
                id=node_id,
                parent_id=parent_id,
                node_type=node_type,
                key=key,
                array_index=array_index,
                byte_offset=offset,
                byte_length=length,
            )
        )
        return node_id

    def _skip_ws(self, pos: int) -> int:
        buf = self.buf
        n = self.length
        while pos < n and buf[pos] in _WS_CHARS:
            pos += 1
        return pos

    def _expect(self, pos: int, ch: int) -> int:
        if pos >= self.length or self.buf[pos] != ch:
            raise JSONScanError(f"expected {chr(ch)!r} at byte offset {pos}")
        return pos + 1

    def _string_end(self, pos: int) -> int:
        m = _STRING_RE.match(self.buf, pos)
        if m is None:
            raise JSONScanError(f"unterminated string starting at {pos}")
        return m.end()

    def _number_end(self, pos: int) -> int:
        buf = self.buf
        n = self.length
        i = pos
        while i < n and buf[i] in _NUMBER_CHARS:
            i += 1
        if i == pos:
            raise JSONScanError(f"invalid number at byte offset {pos}")
        return i

    def _decode_key(self, start: int, end: int) -> str:
        body = self.buf[start + 1 : end - 1]
        if b"\\" not in body:
            return body.decode("utf-8")
        
        return parse_leaf(bytes(self.buf[start:end]))

    def parse_value(
        self,
        pos: int,
        parent_id: int | None,
        key: str | None,
        array_index: int | None,
        path: str,
    ) -> tuple[int, int]:
        pos = self._skip_ws(pos)
        if pos >= self.length:
            raise JSONScanError("unexpected end of input")
        c = self.buf[pos]

        if c == 0x7B:  # '{'
            return self._parse_object(pos, parent_id, key, array_index, path)
        if c == 0x5B:  # '['
            return self._parse_array(pos, parent_id, key, array_index, path)
        if c == 0x22:  # '"'
            end = self._string_end(pos)
            node_id = self._add(
                parent_id, "string", key, array_index, pos, end - pos
            )
            return node_id, end
        if self.buf[pos : pos + 4] == _TRUE:
            node_id = self._add(parent_id, "boolean", key, array_index, pos, 4)
            return node_id, pos + 4
        if self.buf[pos : pos + 5] == _FALSE:
            node_id = self._add(parent_id, "boolean", key, array_index, pos, 5)
            return node_id, pos + 5
        if self.buf[pos : pos + 4] == _NULL:
            node_id = self._add(parent_id, "null", key, array_index, pos, 4)
            return node_id, pos + 4
        if c == 0x2D or 0x30 <= c <= 0x39:  # '-' or digit
            end = self._number_end(pos)
            node_id = self._add(
                parent_id, "number", key, array_index, pos, end - pos
            )
            return node_id, end

        raise JSONScanError(f"unexpected byte {chr(c)!r} at offset {pos}")

    def _parse_object(
        self,
        pos: int,
        parent_id: int | None,
        key: str | None,
        array_index: int | None,
        path: str,
    ) -> tuple[int, int]:
        start = pos
        node_id = self._alloc_id()
        
        rec = NodeRecord(
            id=node_id,
            parent_id=parent_id,
            node_type="object",
            key=key,
            array_index=array_index,
            byte_offset=start,
            byte_length=-1,
        )
        self.records.append(rec)

        pos = self._expect(pos, 0x7B)  # '{'
        pos = self._skip_ws(pos)
        if pos < self.length and self.buf[pos] == 0x7D:  # '}'
            pos += 1
        else:
            while True:
                pos = self._skip_ws(pos)
                if pos >= self.length or self.buf[pos] != 0x22:
                    raise JSONScanError(f"expected object key at offset {pos}")
                key_start = pos
                key_end = self._string_end(pos)
                child_key = self._decode_key(key_start, key_end)
                pos = self._skip_ws(key_end)
                pos = self._expect(pos, 0x3A)  # ':'
                pos = self._skip_ws(pos)
                child_path = f"{path}.{child_key}"
                _, pos = self.parse_value(pos, node_id, child_key, None, child_path)
                pos = self._skip_ws(pos)
                if pos >= self.length:
                    raise JSONScanError("unterminated object")
                if self.buf[pos] == 0x2C:  # ','
                    pos += 1
                    continue
                if self.buf[pos] == 0x7D:  # '}'
                    pos += 1
                    break
                raise JSONScanError(f"expected ',' or '}}' at offset {pos}")

        rec.byte_length = pos - start
        return node_id, pos

    def _parse_array(
        self,
        pos: int,
        parent_id: int | None,
        key: str | None,
        array_index: int | None,
        path: str,
    ) -> tuple[int, int]:
        
        start = pos
        node_id = self._alloc_id()
        rec = NodeRecord(
            id=node_id,
            parent_id=parent_id,
            node_type="array",
            key=key,
            array_index=array_index,
            byte_offset=start,
            byte_length=-1,
        )
        self.records.append(rec)

        pos = self._expect(pos, 0x5B)  # '['
        pos = self._skip_ws(pos)
        if pos < self.length and self.buf[pos] == 0x5D:  # ']'
            pos += 1
        else:
            idx = 0
            while True:
                pos = self._skip_ws(pos)
                child_path = f"{path}[{idx}]"
                _, pos = self.parse_value(pos, node_id, None, idx, child_path)
                pos = self._skip_ws(pos)
                if pos >= self.length:
                    raise JSONScanError("unterminated array")
                if self.buf[pos] == 0x2C:  # ','
                    pos += 1
                    idx += 1
                    continue
                if self.buf[pos] == 0x5D:  # ']'
                    pos += 1
                    break
                raise JSONScanError(f"expected ',' or ']' at offset {pos}")

        rec.byte_length = pos - start
        return node_id, pos


def build_index(json_path: str, index_path: str | None = None) -> str:

    json_path = os.path.abspath(json_path)
    index_path = os.path.abspath(index_path) if index_path else json_path + ".bjidx"

    with open(json_path, "rb") as f:
        buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            scanner = _Scanner(buf)
            start = scanner._skip_ws(0)
            root_id, _ = scanner.parse_value(start, None, None, None, "$")
        finally:
            buf.close()

    if os.path.exists(index_path):
        os.remove(index_path)

    storage = IndexStorage(index_path)
    try:
        storage.create_schema()
        storage.insert_nodes(scanner.records)

        fp = compute_file_fingerprint(json_path)
        storage.set_meta("version", "2")
        storage.set_meta("source_path", json_path)
        storage.set_meta("file_size", str(fp.size))
        storage.set_meta("mtime_ns", str(fp.mtime_ns))
        storage.set_meta("sample_hash", fp.sample_hash)
        storage.set_meta("root_id", str(root_id))
        storage.commit()
    finally:
        storage.close()

    return index_path