from __future__ import annotations

import os
import time

import pytest

import bytejson
from bytejson import parser


def test_random_access_matches_source(sample_json_path, sample_data):
    db = bytejson.open(sample_json_path)
    try:
        assert db["users"][0]["name"] == "alice"
        assert db["users"][2]["email"] == "carol@example.com"
        assert db["posts"][0]["meta"]["likes"] == 10
        assert db["posts"][0]["tags"][1] == "first"
        assert db["flags"]["enabled"] is False
        assert db["flags"]["note"] is None
        assert db["flags"]["ratio"] == 0.5
        assert db["nested"]["a"]["b"]["c"][2]["d"] == "deep"
    finally:
        db.close()


def test_missing_key_raises_key_error(sample_json_path):
    db = bytejson.open(sample_json_path)
    try:
        with pytest.raises(KeyError):
            db["users"][0]["does_not_exist"]
    finally:
        db.close()


def test_out_of_range_index_raises_index_error(sample_json_path):
    db = bytejson.open(sample_json_path)
    try:
        with pytest.raises(IndexError):
            db["users"][999]
    finally:
        db.close()


def test_negative_index(sample_json_path):
    db = bytejson.open(sample_json_path)
    try:
        assert db["users"][-1]["name"] == "carol"
    finally:
        db.close()


def test_len_and_iteration(sample_json_path, sample_data):
    db = bytejson.open(sample_json_path)
    try:
        assert len(db["users"]) == 3
        names = [u["name"] for u in db["users"]]
        assert names == ["alice", "bob", "carol"]
        assert set(db["flags"].keys()) == set(sample_data["flags"].keys())
    finally:
        db.close()


def test_to_python_matches_source_subtree(sample_json_path, sample_data):
    db = bytejson.open(sample_json_path)
    try:
        assert db["posts"][0].to_python() == sample_data["posts"][0]
        assert db.to_python() == sample_data
    finally:
        db.close()


def test_only_requested_leaf_is_parsed(sample_json_path, monkeypatch):
    db = bytejson.open(sample_json_path)
    calls = []
    original = parser.parse_leaf

    def counting(raw):
        calls.append(raw)
        return original(raw)

    monkeypatch.setattr(parser, "parse_leaf", counting)

    try:
        value = db["nested"]["a"]["b"]["c"][2]["d"]
        assert value == "deep"
        assert len(calls) == 1
    finally:
        db.close()


def test_open_reuses_existing_index(sample_json_path):
    db1 = bytejson.open(sample_json_path)
    index_path = db1.index_path
    db1.close()
    mtime_after_build = os.path.getmtime(index_path)

    time.sleep(0.05)
    db2 = bytejson.open(sample_json_path)
    db2.close()
    assert os.path.getmtime(index_path) == mtime_after_build


def test_open_rebuilds_when_file_changes(sample_json_path):
    db1 = bytejson.open(sample_json_path)
    index_path = db1.index_path
    db1.close()
    mtime_after_first_build = os.path.getmtime(index_path)

    time.sleep(0.05)
    with open(sample_json_path, "a") as f:
        pass
    with open(sample_json_path) as f:
        content = f.read()
    with open(sample_json_path, "w") as f:
        f.write(content)

    db2 = bytejson.open(sample_json_path)
    db2.close()
    assert os.path.getmtime(index_path) != mtime_after_first_build


def test_open_rebuilds_when_index_missing(sample_json_path):
    db1 = bytejson.open(sample_json_path)
    index_path = db1.index_path
    db1.close()
    os.remove(index_path)

    db2 = bytejson.open(sample_json_path)
    assert os.path.exists(index_path)
    assert db2["users"][0]["name"] == "alice"
    db2.close()


def test_context_manager_closes_resources(sample_json_path):
    with bytejson.open(sample_json_path) as db:
        assert db["users"][0]["name"] == "alice"
    with pytest.raises(ValueError):
        db["users"][0]
