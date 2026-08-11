from __future__ import annotations

import argparse
import json
import os
import random


def build_dataset(num_users: int, num_posts: int, seed: int) -> dict:
    rng = random.Random(seed)

    users = [
        {
            "id": i,
            "username": f"user_{i}",
            "email": f"user_{i}@example.com",
            "karma": rng.randint(0, 100_000),
            "bio": f"This is the bio for user {i}. " * rng.randint(1, 5),
        }
        for i in range(num_users)
    ]

    posts = [
        {
            "id": i,
            "title": f"Post #{i}: " + "lorem ipsum " * rng.randint(1, 4),
            "author_id": rng.randint(0, num_users - 1),
            "body": "Lorem ipsum dolor sit amet. " * rng.randint(2, 10),
            "score": rng.randint(-50, 5000),
            "comments": [
                {
                    "id": j,
                    "author_id": rng.randint(0, num_users - 1),
                    "text": f"Comment {j} on post {i}.",
                    "score": rng.randint(-10, 500),
                }
                for j in range(rng.randint(0, 5))
            ],
        }
        for i in range(num_posts)
    ]

    return {
        "meta": {
            "generated_by": "bytejson.examples.generate_sample",
            "seed": seed,
            "num_users": num_users,
            "num_posts": num_posts,
        },
        "users": users,
        "posts": posts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=8000)
    parser.add_argument("--posts", type=int, default=8000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--out",
        default=os.path.join(os.path.dirname(__file__), "reddit.json"),
    )
    args = parser.parse_args()

    dataset = build_dataset(args.users, args.posts, args.seed)
    with open(args.out, "w") as f:
        json.dump(dataset, f)

    size_mb = os.path.getsize(args.out) / (1024 * 1024)
    print(f"Wrote {args.out} ({size_mb:.1f} MB, {args.users} users, {args.posts} posts)")


if __name__ == "__main__":
    main()