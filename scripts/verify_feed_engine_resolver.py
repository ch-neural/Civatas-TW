"""Verify resolve_feed_for_agent: reproducibility, deep-blue fallback, mix distribution.

Run: python3 scripts/verify_feed_engine_resolver.py
Exit 0 = pass.
"""
from __future__ import annotations
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ap" / "services" / "evolution" / "app"))

from feed_engine import resolve_feed_for_agent, sample_k_from  # noqa: E402
from tw_feed_sources import (  # noqa: E402
    DOMAIN_LEANING_MAP, DEEP_BLUE_FALLBACK_DOMAINS, MEDIA_HABIT_EXPOSURE_MIX,
)


def _mk_article(aid, domain, title="test"):
    return {"id": aid, "link": f"https://{domain}/news/{aid}", "title": title,
            "source_domain": domain}


def _mk_pool(n_per_domain=30):
    """Pool with every mapped domain, n_per_domain articles each."""
    pool = []
    aid = 0
    for domain in DOMAIN_LEANING_MAP:
        for _ in range(n_per_domain):
            pool.append(_mk_article(aid, domain))
            aid += 1
    return pool


def _mk_agent(pid, media_habit):
    return {"person_id": pid, "media_habit": media_habit}


# ── Test 1: Reproducibility ──────────────────────────────────────────────
def test_reproducibility():
    agent = _mk_agent("agent_5", "中間")
    pool = _mk_pool()
    r1 = resolve_feed_for_agent(agent, pool, day=7, replication_seed=20240113)
    r2 = resolve_feed_for_agent(agent, pool, day=7, replication_seed=20240113)
    ids1 = [a["id"] for a in r1]
    ids2 = [a["id"] for a in r2]
    assert ids1 == ids2, f"reproducibility failed: {ids1[:5]} != {ids2[:5]}"
    print(f"  ✅ test_reproducibility: {len(r1)} articles, deterministic")


# ── Test 2: Deep-blue fallback ───────────────────────────────────────────
def test_deep_blue_fallback():
    agent = _mk_agent("agent_db", "深藍")
    pool = _mk_pool()
    result = resolve_feed_for_agent(agent, pool, day=1, replication_seed=1)
    # All blue-category articles (which for 深藍 agents mean mix['偏藍']=0.85)
    # should come from DEEP_BLUE_FALLBACK_DOMAINS.
    blue_articles = [a for a in result
                      if a["source_domain"] in
                      {d for d, l in DOMAIN_LEANING_MAP.items() if l == "偏藍"}]
    # Among blue-leaning articles, all must be fallback-whitelisted.
    not_fallback = [a for a in blue_articles
                     if a["source_domain"] not in DEEP_BLUE_FALLBACK_DOMAINS]
    assert not not_fallback, f"deep-blue agent got non-fallback blue: {not_fallback[:3]}"
    # And no 深綠/偏綠 articles should appear (mix = 0)
    no_blue_domains = {d for d, l in DOMAIN_LEANING_MAP.items() if l in ("深綠", "偏綠")}
    wrong = [a for a in result if a["source_domain"] in no_blue_domains]
    assert not wrong, f"深藍 agent got 綠 articles: {wrong[:3]}"
    print(f"  ✅ test_deep_blue_fallback: {len(result)} articles, all blue from fallback")


# ── Test 3: Exposure mix distribution ────────────────────────────────────
def test_media_habit_distribution():
    # Run for 300 simulation days to average out sampling variance
    agent = _mk_agent("agent_dg", "深綠")
    pool = _mk_pool(n_per_domain=50)
    all_articles = []
    for day in range(300):
        all_articles.extend(resolve_feed_for_agent(agent, pool, day=day, replication_seed=1))

    from feed_engine import _article_leaning
    observed = Counter(_article_leaning(a) for a in all_articles)
    total = sum(observed.values())
    if total == 0:
        raise AssertionError("no articles returned across 300 days")

    expected = MEDIA_HABIT_EXPOSURE_MIX["深綠"]
    print(f"  distribution over 300 days (n={total}):")
    for leaning in ("深綠", "偏綠", "中間", "偏藍", "深藍"):
        obs_pct = observed.get(leaning, 0) / total
        exp_pct = expected.get(leaning, 0.0)
        delta = abs(obs_pct - exp_pct)
        status = "✅" if delta < 0.10 else "⚠️"  # 10% tolerance
        print(f"    {leaning}: observed {obs_pct:.2%} vs expected {exp_pct:.2%} {status}")
        # Assert within 10% absolute tolerance (stochastic, but 300 days is plenty)
        assert delta < 0.10, f"{leaning} distribution off by {delta:.2%}"
    print(f"  ✅ test_media_habit_distribution: 深綠 agent mix matches ±10%")


def main() -> int:
    print("=== resolve_feed_for_agent tests ===")
    test_reproducibility()
    test_deep_blue_fallback()
    test_media_habit_distribution()
    print()
    print("✅ All 3 tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
