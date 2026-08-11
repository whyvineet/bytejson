from __future__ import annotations

from bytejson.index import build_index
from bytejson.storage import IndexStorage


def test_meta_roundtrip(sample_json_path):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        assert storage.get_meta("source_path") == sample_json_path
        assert storage.get_meta("root_id") is not None
        assert storage.get_meta("does_not_exist") is None
    finally:
        storage.close()


def test_get_child_by_key_missing_returns_none(sample_json_path):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        assert storage.get_child_by_key(root_id, "does_not_exist") is None
    finally:
        storage.close()


def test_get_child_by_index_missing_returns_none(sample_json_path):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        users = storage.get_child_by_key(root_id, "users")
        assert storage.get_child_by_index(users.id, 999) is None
    finally:
        storage.close()


def test_get_children_preserves_array_order(sample_json_path):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        users = storage.get_child_by_key(root_id, "users")
        children = storage.get_children(users.id)
        assert [c.array_index for c in children] == [0, 1, 2]
    finally:
        storage.close()
