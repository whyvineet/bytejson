from __future__ import annotations

import os

from bytejson.index import build_index
from bytejson.storage import IndexStorage


def test_build_index_creates_bjidx_file(sample_json_path):
    index_path = build_index(sample_json_path)
    assert index_path == sample_json_path + ".bjidx"
    assert os.path.exists(index_path)


def test_index_root_matches_file_structure(sample_json_path, sample_data):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        root = storage.get_node(root_id)
        assert root.node_type == "object"
        assert root.parent_id is None

        top_keys = {c.key for c in storage.get_children(root.id)}
        assert top_keys == set(sample_data.keys())
    finally:
        storage.close()


def test_index_records_correct_byte_ranges(sample_json_path, sample_data):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        root = storage.get_node(root_id)
        users_node = storage.get_child_by_key(root.id, "users")

        with open(sample_json_path, "rb") as f:
            raw = f.read()
        slice_ = raw[users_node.byte_offset : users_node.byte_offset + users_node.byte_length]
        import json

        assert json.loads(slice_) == sample_data["users"]
    finally:
        storage.close()


def test_index_handles_empty_containers(sample_json_path):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        root = storage.get_node(root_id)
        empty_obj = storage.get_child_by_key(root.id, "empty_object")
        empty_arr = storage.get_child_by_key(root.id, "empty_array")
        assert storage.count_children(empty_obj.id) == 0
        assert storage.count_children(empty_arr.id) == 0
    finally:
        storage.close()


def test_index_records_scalar_types(sample_json_path):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        root = storage.get_node(root_id)
        flags = storage.get_child_by_key(root.id, "flags")
        types = {c.key: c.node_type for c in storage.get_children(flags.id)}
        assert types == {
            "enabled": "boolean",
            "note": "null",
            "ratio": "number",
            "count": "number",
        }
    finally:
        storage.close()


def test_index_preserves_object_key_order(sample_json_path, sample_data):
    index_path = build_index(sample_json_path)
    storage = IndexStorage(index_path)
    try:
        root_id = int(storage.get_meta("root_id"))
        root = storage.get_node(root_id)

        children = storage.get_children(root.id)
        actual_keys = [c.key for c in children]
        expected_keys = list(sample_data.keys())

        assert actual_keys == expected_keys, f"Expected {expected_keys}, got {actual_keys}"
    finally:
        storage.close()
