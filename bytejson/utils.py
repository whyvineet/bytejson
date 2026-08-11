from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

WHITESPACE = frozenset(b" \t\n\r")
NUMBER_CHARS = frozenset(b"-+.eE0123456789")
_SAMPLE_SIZE = 4096


@dataclass(frozen=True)
class FileFingerprint:
    size: int
    mtime_ns: int
    sample_hash: str


def compute_file_fingerprint(path: str) -> FileFingerprint:
    stat = os.stat(path)
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        head = f.read(_SAMPLE_SIZE)
        hasher.update(head)
        if stat.st_size > _SAMPLE_SIZE:
            f.seek(max(0, stat.st_size - _SAMPLE_SIZE))
            hasher.update(f.read(_SAMPLE_SIZE))
    return FileFingerprint(
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sample_hash=hasher.hexdigest(),
    )


def index_matches_file(storage, json_path: str) -> bool:
    fp = compute_file_fingerprint(json_path)
    try:
        stored_size = int(storage.get_meta("file_size"))
        stored_mtime = int(storage.get_meta("mtime_ns"))
        stored_hash = storage.get_meta("sample_hash")
    except (TypeError, ValueError):
        return False
    return (
        stored_size == fp.size
        and stored_mtime == fp.mtime_ns
        and stored_hash == fp.sample_hash
    )
