"""Snapshot consistency: feed_sources.json must match feed_sources.py.

Prevents drift between the Python canonical source and the JSON audit trail.
Regenerate via: python -m ctw_va.cli.__main__ news-pool regen-snapshot  (future),
or manually the one-liner in experiments/news_pool_2024_jan/README.md.
"""
import json
from pathlib import Path

from ctw_va.data.feed_sources import (
    DOMAIN_LEANING_MAP,
    DEEP_BLUE_FALLBACK_DOMAINS,
    MEDIA_HABIT_EXPOSURE_MIX,
    NON_NEWS_DOMAINS,
)

SNAPSHOT_PATH = Path(__file__).parent.parent / "src" / "ctw_va" / "data" / "feed_sources.json"


def test_snapshot_exists():
    assert SNAPSHOT_PATH.exists(), f"snapshot missing: {SNAPSHOT_PATH}"


def test_domain_map_matches_snapshot():
    snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert snap["domain_leaning_map"] == dict(sorted(DOMAIN_LEANING_MAP.items())), \
        "DOMAIN_LEANING_MAP drift between .py and .json — regenerate snapshot"


def test_deep_blue_fallback_matches():
    snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert sorted(snap["deep_blue_fallback_domains"]) == sorted(DEEP_BLUE_FALLBACK_DOMAINS)


def test_mix_matches():
    snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert snap["media_habit_exposure_mix"] == MEDIA_HABIT_EXPOSURE_MIX


def test_non_news_matches():
    snap = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    assert sorted(snap["non_news_domains"]) == sorted(NON_NEWS_DOMAINS)


def test_news_pool_domain_coverage():
    """≥ 90% of articles in merged_pool.jsonl must have a leaning assigned (spec §A2)."""
    pool_path = (
        Path(__file__).parent.parent
        / "experiments"
        / "news_pool_2024_jan"
        / "merged_pool.jsonl"
    )
    if not pool_path.exists():
        import pytest
        pytest.skip("merged_pool.jsonl not produced yet (run civatas-exp news-pool merge)")
    articles = [json.loads(l) for l in pool_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    classified = [a for a in articles if not a.get("excluded")]
    known = sum(1 for a in classified if a.get("source_leaning") != "unknown")
    coverage = known / len(classified)
    assert coverage >= 0.90, f"domain coverage {coverage:.1%} < 90% spec requirement"
