from __future__ import annotations

from bytejson.mmap_reader import MmapReader


def test_read_returns_correct_slice(tmp_path):
    p = tmp_path / "data.bin"
    p.write_bytes(b"0123456789")
    reader = MmapReader(str(p))
    try:
        assert reader.read(0, 3) == b"012"
        assert reader.read(3, 4) == b"3456"
        assert reader.read(9, 1) == b"9"
    finally:
        reader.close()


def test_empty_file_reads_empty_bytes(tmp_path):
    p = tmp_path / "empty.bin"
    p.write_bytes(b"")
    reader = MmapReader(str(p))
    try:
        assert reader.read(0, 10) == b""
    finally:
        reader.close()


def test_context_manager(tmp_path):
    p = tmp_path / "data.bin"
    p.write_bytes(b"hello")
    with MmapReader(str(p)) as reader:
        assert reader.read(0, 5) == b"hello"
