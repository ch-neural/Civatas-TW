"""Blind-validation subset sampler.

Given a primary labeled CSV (e.g. responses_n200.csv), emit a smaller CSV
with the same schema but label column cleared, stratified by (vendor × expected).
Rater opens the blind CSV in the webui with AI suggestions hidden and re-labels
from scratch. Cohen's κ between primary and blind labels quantifies rater
reliability for paper §3.5.

Naming convention: output filename uses `_blind` suffix so the webui's
`^responses_n\\d+(_\\w+)?\\.csv$` whitelist accepts it.
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

from .csv_io import CSV_COLUMNS


def sample_blind_subset(
    input_csv: str,
    output_csv: str,
    n: int = 50,
    seed: int = 20260422,
) -> dict:
    """Stratified sample N labeled rows for blind re-annotation.

    Only rows where status != 'error' AND label is non-empty are eligible.
    Sampling allocates proportionally to each (vendor, expected) stratum size,
    using largest-remainder rounding to hit exactly N (or fewer if strata are
    smaller than their allocation).
    """
    rows = _read_labeled(input_csv)
    if not rows:
        raise ValueError(f"No labeled rows in {input_csv}")
    if n <= 0:
        raise ValueError(f"n must be > 0 (got {n})")
    if n > len(rows):
        raise ValueError(
            f"requested n={n} exceeds {len(rows)} eligible rows in {input_csv}"
        )

    strata = _build_strata(rows)
    allocations = _allocate(strata, n)

    rng = random.Random(seed)
    sampled: list[dict] = []
    breakdown: dict[tuple[str, str], int] = {}
    for key in sorted(strata.keys()):
        k = allocations[key]
        if k == 0:
            continue
        picked = rng.sample(strata[key], k)
        sampled.extend(picked)
        breakdown[key] = k

    sampled.sort(key=lambda r: (r.get("prompt_id", ""), r.get("vendor", "")))
    _write_blinded(sampled, output_csv)

    return {
        "input": str(input_csv),
        "output": str(output_csv),
        "eligible": len(rows),
        "sampled": len(sampled),
        "seed": seed,
        "by_stratum": {f"{v}|{e}": c for (v, e), c in breakdown.items()},
    }


def _read_labeled(csv_path: str) -> list[dict]:
    eligible: list[dict] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("status") or "") == "error":
                continue
            if not (row.get("label") or "").strip():
                continue
            eligible.append(row)
    return eligible


def _build_strata(rows: list[dict]) -> dict[tuple[str, str], list[dict]]:
    strata: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        key = (r.get("vendor", ""), r.get("expected", ""))
        strata[key].append(r)
    return strata


def _allocate(
    strata: dict[tuple[str, str], list[dict]], n: int
) -> dict[tuple[str, str], int]:
    """Largest-remainder allocation: floor quotas + distribute remainder by fractional part."""
    total = sum(len(v) for v in strata.values())
    quotas: dict[tuple[str, str], float] = {
        k: n * len(v) / total for k, v in strata.items()
    }
    alloc: dict[tuple[str, str], int] = {k: int(q) for k, q in quotas.items()}
    # Cap: never exceed stratum size
    for k in alloc:
        alloc[k] = min(alloc[k], len(strata[k]))

    remainder = n - sum(alloc.values())
    # Distribute remainder one-by-one to strata with largest fractional part
    # AND available capacity.
    order = sorted(
        strata.keys(),
        key=lambda k: (quotas[k] - int(quotas[k]), len(strata[k])),
        reverse=True,
    )
    i = 0
    while remainder > 0 and i < len(order) * 4:
        k = order[i % len(order)]
        if alloc[k] < len(strata[k]):
            alloc[k] += 1
            remainder -= 1
        i += 1
    return alloc


def _write_blinded(rows: list[dict], output_csv: str) -> None:
    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            out = {k: r.get(k, "") for k in CSV_COLUMNS}
            out["label"] = ""  # clear for blind re-annotation
            writer.writerow(out)
