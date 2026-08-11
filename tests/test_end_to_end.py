from __future__ import annotations

import json

import bytejson


def test_end_to_end_against_generated_dataset(tmp_path):
    data = {
        "users": [{"id": i, "email": f"u{i}@x.com"} for i in range(500)],
        "posts": [
            {"id": i, "title": f"Post {i}", "comments": [{"id": 0, "text": "hi"}]}
            for i in range(500)
        ],
    }
    path = tmp_path / "big.json"
    path.write_text(json.dumps(data))

    db = bytejson.open(str(path))
    try:
        assert db["users"][250]["email"] == "u250@x.com"
        assert db["posts"][499]["title"] == "Post 499"
        assert db["posts"][10]["comments"][0]["text"] == "hi"
        assert len(db["users"]) == 500
        assert len(db["posts"]) == 500
    finally:
        db.close()
