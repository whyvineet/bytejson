from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_data() -> dict:
    return {
        "users": [
            {"id": 0, "name": "alice", "email": "alice@example.com", "active": True},
            {"id": 1, "name": "bob", "email": "bob@example.com", "active": False},
            {"id": 2, "name": "carol", "email": "carol@example.com", "active": True},
        ],
        "posts": [
            {
                "id": 0,
                "title": "Hello World",
                "tags": ["intro", "first"],
                "meta": {"likes": 10, "shares": 2},
            },
            {
                "id": 1,
                "title": "Second Post",
                "tags": [],
                "meta": {"likes": 0, "shares": 0},
            },
        ],
        "empty_object": {},
        "empty_array": [],
        "flags": {"enabled": False, "note": None, "ratio": 0.5, "count": -3},
        "nested": {"a": {"b": {"c": [1, 2, {"d": "deep"}]}}},
    }


@pytest.fixture
def sample_json_path(tmp_path, sample_data) -> str:
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(sample_data))
    return str(path)
