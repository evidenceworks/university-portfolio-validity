#!/usr/bin/env python3
"""Verify the deterministic 400-case historical sample selection."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import heapq
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXPECTED_UNIVERSE_SHA256 = "f80461d1b9e9c0ddbde2c7d35749332ae5cce06b571b0beaaaf78845543e4dd3"
EXPECTED_UNIVERSE_ROWS = 1_045_601
EXPECTED_EXCLUSION_COUNT = 354
EXPECTED_PUBLIC_EXCLUSION_SHA256 = "f4908728b46100f631e1658696eade14e57b34eed923d020d62c7e0006ae7174"
SEED = "C09_DENOM_V2_FINAL_2026-09-16"


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def norm_id(value: str) -> str:
    value = (value or "").strip()
    if value.startswith("W") and value[1:].isdigit():
        return "https://openalex.org/" + value
    return value


def read_csv(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--universe",
        default=str(DATA / "selection-universe.csv.gz"),
        help="Path to the two-column selection universe (default: data/selection-universe.csv.gz).",
    )
    args = parser.parse_args()

    universe = Path(args.universe).expanduser().resolve()
    if not universe.is_file():
        fail(f"universe file not found: {universe}")
    if sha256(universe) != EXPECTED_UNIVERSE_SHA256:
        fail("universe SHA-256 mismatch")

    exclusions_path = DATA / "excluded-works.csv"
    if sha256(exclusions_path) != EXPECTED_PUBLIC_EXCLUSION_SHA256:
        fail("public exclusion list hash mismatch")
    exclusions = {norm_id(row["work_id"]) for row in read_csv(exclusions_path)}
    if len(exclusions) != EXPECTED_EXCLUSION_COUNT:
        fail(f"expected {EXPECTED_EXCLUSION_COUNT} unique exclusions, found {len(exclusions)}")

    institutions = read_csv(DATA / "institutions.csv")
    if len(institutions) != 50:
        fail(f"expected 50 institutions, found {len(institutions)}")
    expected_counts = {norm_id(row["institution_id"]): int(row["candidate_count"]) for row in institutions}
    if len(expected_counts) != 50:
        fail("institution identifiers are not unique")

    heaps = defaultdict(list)
    candidate_counts = Counter()
    seen_focals = set()
    pair_count = 0
    with gzip.open(universe, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["focal_openalex_id", "work_openalex_id"]:
            fail("unexpected universe schema")
        for row in reader:
            pair_count += 1
            focal = norm_id(row["focal_openalex_id"])
            work = norm_id(row["work_openalex_id"])
            seen_focals.add(focal)
            if work in exclusions:
                continue
            candidate_counts[focal] += 1
            digest = hashlib.sha256(f"{SEED}|{focal}|{work}".encode("utf-8")).hexdigest()
            value = int(digest, 16)
            entry = (-value, work, digest)
            heap = heaps[focal]
            if len(heap) < 8:
                heapq.heappush(heap, entry)
            elif value < -heap[0][0] or (value == -heap[0][0] and work < heap[0][1]):
                heapq.heapreplace(heap, entry)

    if pair_count != EXPECTED_UNIVERSE_ROWS:
        fail(f"expected {EXPECTED_UNIVERSE_ROWS} universe rows, found {pair_count}")
    if seen_focals != set(expected_counts):
        fail("universe institution set does not match the deposited 50-institution frame")
    if any(len(heaps[focal]) != 8 for focal in expected_counts):
        fail("fewer than eight eligible works were available for at least one institution")

    selected = set()
    for focal in expected_counts:
        entries = sorted(heaps[focal], key=lambda entry: (entry[2], entry[1]))
        selected.update((focal, work) for _, work, _ in entries)

    with gzip.open(DATA / "cases.csv.gz", "rt", encoding="utf-8", newline="") as handle:
        cases = list(csv.DictReader(handle))
    deposited = {(norm_id(row["institution_id"]), norm_id(row["work_id"])) for row in cases}
    if len(cases) != 400 or len(deposited) != 400:
        fail("deposited case file does not contain 400 unique institution-work pairs")

    missing = deposited - selected
    unexpected = selected - deposited
    if missing or unexpected:
        fail(f"selected-pair mismatch: missing={len(missing)}, unexpected={len(unexpected)}")

    count_mismatches = {
        focal: (candidate_counts[focal], expected_counts[focal])
        for focal in expected_counts
        if candidate_counts[focal] != expected_counts[focal]
    }
    if count_mismatches:
        fail(f"institution candidate-count mismatch for {len(count_mismatches)} institutions")

    print("Selection verification PASS")
    print(f"Universe rows: {pair_count}")
    print(f"Universe SHA-256: {EXPECTED_UNIVERSE_SHA256}")
    print(f"Exclusions: {EXPECTED_EXCLUSION_COUNT} unique works")
    print("Selected pairs: 400/400 match")
    print("Institution candidate counts: 50/50 match")


if __name__ == "__main__":
    main()
