from __future__ import annotations

import argparse
import os
import time

import bytejson

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "reddit.json")


def timed(label: str, fn):
    t0 = time.perf_counter()
    result = fn()
    t1 = time.perf_counter()
    print(f"{label}: {t1 - t0:.4f}s")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=DEFAULT_PATH)
    args = parser.parse_args()

    if not os.path.exists(args.path):
        import json

        from generate_sample import build_dataset

        dataset = build_dataset(num_users=8000, num_posts=8000, seed=42)
        with open(args.path, "w") as f:
            json.dump(dataset, f)

    print(f"File size: {os.path.getsize(args.path) / (1024 * 1024):.1f} MB\n")

    db = timed("bytejson.open()", lambda: bytejson.open(args.path))

    print(f"\nnum users: {len(db['users'])}")
    print(f"num posts: {len(db['posts'])}")

    print(f"\ndb['posts'][500]['title'] -> {db['posts'][500]['title']!r}")
    print(f"db['users'][123]['email'] -> {db['users'][123]['email']!r}")

    comments = db["posts"][10]["comments"]
    if len(comments) > 0:
        print(f"db['posts'][10]['comments'][0]['text'] -> {comments[0]['text']!r}")
    else:
        print("post 10 has no comments")

    print("\nfields on posts[0]:", list(db["posts"][0].keys()))

    small = db["posts"][0]["comments"].to_python()
    print(f"posts[0]['comments'].to_python() -> {small!r}"[:120])

    def many_lookups():
        for i in range(0, 200, 10):
            _ = db["posts"][i]["title"]

    timed("\n20 scattered lookups", many_lookups)

    db.close()


if __name__ == "__main__":
    main()