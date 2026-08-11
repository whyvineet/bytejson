from __future__ import annotations

import argparse
import gc
import json
import os
import random
import sys
import time
import tracemalloc
from dataclasses import dataclass, field

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from generate_sample import build_dataset

import bytejson

DATA_PATH = os.path.join(os.path.dirname(__file__), "benchmark_data.json")
LOOKUP_COUNTS = [1, 10, 100, 500, 1_000, 5_000, 10_000]


@dataclass
class Measurement:
    result: object
    seconds: float
    peak_bytes: int


@dataclass
class SweepResult:
    counts: list[int] = field(default_factory=list)
    json_access: list[float] = field(default_factory=list)
    bj_access: list[float] = field(default_factory=list)


def fmt_time(seconds: float) -> str:
    if seconds < 1e-3:
        return f"{seconds * 1e6:.1f} us"
    if seconds < 1:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds:.3f} s"


def fmt_mem(num_bytes: float) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def measure(fn) -> Measurement:
    gc.collect()
    tracemalloc.start()
    t0 = time.perf_counter()
    result = fn()
    t1 = time.perf_counter()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return Measurement(result, t1 - t0, peak)


def lookup_indices(num_posts: int, n: int, rng: random.Random, sequential: bool) -> list[int]:
    n = min(n, num_posts)
    if sequential:
        step = max(1, num_posts // n)
        return list(range(0, num_posts, step))[:n]
    return rng.sample(range(num_posts), n)


def time_json_access(data: dict, indices: list[int]) -> float:
    return measure(lambda: [data["posts"][i]["title"] for i in indices]).seconds


def time_bytejson_access(db, indices: list[int]) -> float:
    return measure(lambda: [db["posts"][i]["title"] for i in indices]).seconds


def linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    slope = num / den if den else 0.0
    return slope, mean_y - slope * mean_x


def estimate_crossover(
    json_setup: float, json_slope: float, json_intercept: float,
    bj_setup: float, bj_slope: float, bj_intercept: float,
) -> float | None:
    a = json_slope - bj_slope
    b = (json_setup + json_intercept) - (bj_setup + bj_intercept)
    if a == 0:
        return None
    n_star = -b / a
    return n_star if n_star > 0 else None


def run_sweep(
    data: dict, db, num_posts: int, rng: random.Random, sequential: bool,
    json_setup_s: float, bj_warm_setup_s: float,
) -> SweepResult:
    label = "Sequential" if sequential else "Random"
    print(f"\n== {label} access: total time (setup + access) across lookup counts ==")
    header = f"{'lookups':>8}  {'json.load':>12}  {'bytejson warm':>14}  {'faster':>10}"
    print(header)
    print("-" * len(header))

    sweep = SweepResult()
    for n in LOOKUP_COUNTS:
        if n > num_posts:
            continue
        idx = lookup_indices(num_posts, n, rng, sequential)
        j_access = time_json_access(data, idx)
        bj_access = time_bytejson_access(db, idx)
        sweep.counts.append(n)
        sweep.json_access.append(j_access)
        sweep.bj_access.append(bj_access)

        json_total = json_setup_s + j_access
        bj_total = bj_warm_setup_s + bj_access
        winner = "bytejson" if bj_total < json_total else "json.load"
        print(f"{n:>8}  {fmt_time(json_total):>12}  {fmt_time(bj_total):>14}  {winner:>10}")

    return sweep


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--posts", type=int, default=15_000)
    parser.add_argument("--users", type=int, default=5_000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    rng = random.Random(args.seed)

    if not os.path.exists(DATA_PATH):
        print(f"Generating benchmark dataset ({args.posts} posts, {args.users} users)...")
        dataset = build_dataset(num_users=args.users, num_posts=args.posts, seed=args.seed)
        with open(DATA_PATH, "w") as f:
            json.dump(dataset, f)

    file_size_mb = os.path.getsize(DATA_PATH) / (1024 * 1024)

    def load_json_data() -> dict:
        with open(DATA_PATH) as f:
            return json.load(f)

    json_m = measure(load_json_data)
    data = json_m.result
    num_posts = len(data["posts"])

    index_path = DATA_PATH + ".bjidx"
    if os.path.exists(index_path):
        os.remove(index_path)

    db_cold = measure(lambda: bytejson.open(DATA_PATH))
    db_cold.result.close()

    bj_warm = measure(lambda: bytejson.open(DATA_PATH))
    db = bj_warm.result

    index_size_mb = os.path.getsize(index_path) / (1024 * 1024) if os.path.exists(index_path) else 0.0

    print(f"File: {DATA_PATH}")
    print(f"Size: {file_size_mb:.1f} MB, {num_posts} posts")
    if index_size_mb:
        print(f"Index (.bjidx): {index_size_mb:.1f} MB ({100 * index_size_mb / file_size_mb:.1f}% of file size)")

    run_sweep(data, db, num_posts, rng, True, json_m.seconds, bj_warm.seconds)
    rand = run_sweep(data, db, num_posts, rng, False, json_m.seconds, bj_warm.seconds)

    if len(rand.counts) >= 2:
        j_slope, j_intercept = linear_fit(rand.counts, rand.json_access)
        bj_slope, bj_intercept = linear_fit(rand.counts, rand.bj_access)
        crossover = estimate_crossover(
            json_m.seconds, j_slope, j_intercept,
            bj_warm.seconds, bj_slope, bj_intercept,
        )
        print("\n== Estimated crossover point (linear fit on random-access data) ==")
        if crossover is None:
            cheaper = "bytejson" if bj_warm.seconds < json_m.seconds else "json.load"
            print(f"No crossover in range — {cheaper} is cheaper at every lookup count tested.")
        else:
            print(f"~{crossover:.0f} lookups")
            print("Below this: bytejson (warm) is faster. Above this: json.load is faster.")

    print("\n== bytejson open cost ==")
    print(f"{'cold (builds index)':<22}  {fmt_time(db_cold.seconds):>12}")
    print(f"{'warm (index cached)':<22}  {fmt_time(bj_warm.seconds):>12}")

    print("\n== Peak Python-heap memory (tracemalloc) ==")
    print(f"{'json.load (full parse)':<22}  {fmt_mem(json_m.peak_bytes):>12}")
    print(f"{'bytejson (warm open)':<22}  {fmt_mem(bj_warm.peak_bytes):>12}")

    db.close()


if __name__ == "__main__":
    main()