"""Merge Stage A/B/C JSONL outputs into a frozen, deduplicated news pool.

A1 implementation: dedup by URL, enrich with source_leaning via DOMAIN_LEANING_MAP,
write sorted merged_pool.jsonl + SHA-256 + ingestion_metadata.json.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from ..data.feed_sources import domain_to_leaning, NON_NEWS_DOMAINS


def merge_pool(inputs_dir: str, output: str) -> dict:
    """Merge stage A/B/C JSONL files, dedup by URL, write frozen pool + SHA-256.

    Args:
        inputs_dir: Directory containing stage_a_output.jsonl, stage_b_output.jsonl,
            stage_c_output.jsonl.
        output: Path to write merged_pool.jsonl.

    Returns:
        {"count": int, "excluded_count": int, "sha256": str, "leaning_distribution": dict}

    Raises:
        FileNotFoundError: If any of the three stage files are missing.
    """
    inputs_dir = Path(inputs_dir)
    candidates: list[dict] = []
    for stage in ("a", "b", "c"):
        p = inputs_dir / f"stage_{stage}_output.jsonl"
        if not p.exists():
            raise FileNotFoundError(f"Missing: {p}")
        with p.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    candidates.append(json.loads(line))

    # Dedup by URL — later stages (B/C) take precedence (more authoritative domain mapping)
    by_url: dict[str, dict] = {}
    for art in candidates:
        url = art.get("url") or ""
        if not url:
            continue
        # Enrich with leaning + excluded flag
        domain = art.get("source_domain", "")
        if domain in NON_NEWS_DOMAINS:
            art["excluded"] = True
            art["source_leaning"] = "非新聞媒體"
        else:
            resolved = domain_to_leaning(domain)
            art["source_leaning"] = resolved if resolved else "unknown"
            art["excluded"] = False
        by_url[url] = art

    merged = list(by_url.values())

    # Write output (deterministic order: sorted by url for SHA stability)
    merged_sorted = sorted(merged, key=lambda a: a["url"])
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for art in merged_sorted:
            f.write(json.dumps(art, ensure_ascii=False, sort_keys=True) + "\n")

    # SHA-256 of the written file
    h = hashlib.sha256(out_path.read_bytes()).hexdigest()
    (out_path.parent / "merged_pool.sha256").write_text(h + "\n")

    # Ingestion metadata
    meta = {
        "news_pool_id": h[:16],
        "sha256_full": h,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(merged_sorted),
        "excluded_count": sum(1 for a in merged_sorted if a.get("excluded")),
        "stages_included": ["A", "B", "C"],
    }
    (out_path.parent / "ingestion_metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2)
    )

    # Leaning distribution (exclude excluded=True articles)
    lean_counter = Counter(
        a["source_leaning"] for a in merged_sorted if not a.get("excluded")
    )

    return {
        "count": len(merged_sorted),
        "excluded_count": meta["excluded_count"],
        "sha256": h,
        "leaning_distribution": dict(lean_counter),
    }


def print_stats(pool_path: str) -> None:
    """Print leaning + stage + domain statistics for a merged pool."""
    p = Path(pool_path)
    articles = [
        json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    print(f"Total articles: {len(articles)}")
    print(f"Excluded (non-news): {sum(1 for a in articles if a.get('excluded'))}")
    print()

    lean = Counter(a.get("source_leaning", "unknown") for a in articles if not a.get("excluded"))
    print("Leaning distribution:")
    for k, v in lean.most_common():
        print(f"  {k}: {v}")
    print()

    stages = Counter(a.get("stage", "?") for a in articles)
    print("Stage source:")
    for k, v in stages.most_common():
        print(f"  {k}: {v}")
    print()

    domains = Counter(a.get("source_domain", "?") for a in articles)
    print("Top 15 domains:")
    for d, n in domains.most_common(15):
        lean_label = domain_to_leaning(d) or "unknown"
        print(f"  {d}: {n}  [{lean_label}]")
