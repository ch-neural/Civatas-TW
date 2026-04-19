"""Feed resolver tests — ported from scripts/verify_feed_engine_resolver.py.

Tests:
    test_reproducibility        — same inputs → same output
    test_deep_blue_fallback     — 深藍 agents' 偏藍 articles from fallback domains only
    test_media_habit_distribution — 深綠 agent distribution matches MEDIA_HABIT_EXPOSURE_MIX ±10%
"""
from __future__ import annotations

from collections import Counter

from ctw_va.news.feed_resolver import (
    resolve_feed_for_agent,
    sample_k_from,
    _article_leaning,
)
from ctw_va.data.feed_sources import (
    DOMAIN_LEANING_MAP,
    DEEP_BLUE_FALLBACK_DOMAINS,
    MEDIA_HABIT_EXPOSURE_MIX,
)


def _mk_article(aid, domain, title="test"):
    return {
        "id": aid,
        "link": f"https://{domain}/news/{aid}",
        "title": title,
        "source_domain": domain,
    }


def _mk_pool(n_per_domain=30):
    """Pool with every mapped domain, n_per_domain articles each."""
    pool = []
    aid = 0
    for domain in DOMAIN_LEANING_MAP:
        for _ in range(n_per_domain):
            pool.append(_mk_article(aid, domain))
            aid += 1
    return pool


def _mk_agent(pid, party_lean):
    return {"person_id": pid, "party_lean": party_lean}


# ── Test 1: Reproducibility ──────────────────────────────────────────

def test_reproducibility():
    """Same (agent_id, day, seed) must return identical article IDs."""
    agent = _mk_agent("agent_5", "中間")
    pool = _mk_pool()
    r1 = resolve_feed_for_agent(agent, pool, day=7, replication_seed=20240113)
    r2 = resolve_feed_for_agent(agent, pool, day=7, replication_seed=20240113)
    ids1 = [a["id"] for a in r1]
    ids2 = [a["id"] for a in r2]
    assert ids1 == ids2, f"reproducibility failed: {ids1[:5]} != {ids2[:5]}"
    assert len(r1) > 0, "should return at least one article"


# ── Test 2: Deep-blue fallback ───────────────────────────────────────

def test_deep_blue_fallback():
    """深藍 agents' 偏藍 articles must all come from DEEP_BLUE_FALLBACK_DOMAINS."""
    agent = _mk_agent("agent_db", "深藍")
    pool = _mk_pool()
    result = resolve_feed_for_agent(agent, pool, day=1, replication_seed=1)

    # Articles identified as 偏藍 leaning
    blue_articles = [
        a for a in result
        if a["source_domain"] in {d for d, l in DOMAIN_LEANING_MAP.items() if l == "偏藍"}
    ]
    # All 偏藍 articles must be from fallback whitelist
    not_fallback = [
        a for a in blue_articles
        if a["source_domain"] not in DEEP_BLUE_FALLBACK_DOMAINS
    ]
    assert not not_fallback, (
        f"深藍 agent received non-fallback 偏藍 articles: "
        f"{[a['source_domain'] for a in not_fallback[:3]]}"
    )

    # No 深綠/偏綠 articles (mix = 0.00 for 深藍)
    no_green_domains = {d for d, l in DOMAIN_LEANING_MAP.items() if l in ("深綠", "偏綠")}
    wrong = [a for a in result if a["source_domain"] in no_green_domains]
    assert not wrong, (
        f"深藍 agent received 綠 articles: {[a['source_domain'] for a in wrong[:3]]}"
    )


# ── Test 3: Exposure mix distribution ───────────────────────────────

def test_media_habit_distribution():
    """深綠 agent distribution over 300 days matches MEDIA_HABIT_EXPOSURE_MIX within ±10%."""
    agent = _mk_agent("agent_dg", "深綠")
    pool = _mk_pool(n_per_domain=50)
    all_articles = []
    for day in range(300):
        all_articles.extend(
            resolve_feed_for_agent(agent, pool, day=day, replication_seed=1)
        )

    assert all_articles, "no articles returned across 300 days"

    observed = Counter(_article_leaning(a) for a in all_articles)
    total = sum(observed.values())
    expected = MEDIA_HABIT_EXPOSURE_MIX["深綠"]

    for leaning in ("深綠", "偏綠", "中間", "偏藍", "深藍"):
        obs_pct = observed.get(leaning, 0) / total
        exp_pct = expected.get(leaning, 0.0)
        delta = abs(obs_pct - exp_pct)
        assert delta < 0.10, (
            f"{leaning} distribution off by {delta:.2%} "
            f"(observed {obs_pct:.2%} vs expected {exp_pct:.2%})"
        )


# ── Test 4: sample_k_from safety ────────────────────────────────────

def test_sample_k_from_empty_pool():
    """sample_k_from on empty pool returns empty list without crash."""
    import random
    rng = random.Random(42)
    assert sample_k_from([], 5, rng) == []


def test_sample_k_from_smaller_than_k():
    """sample_k_from with k > len(pool) returns full pool."""
    import random
    rng = random.Random(42)
    pool = [1, 2, 3]
    result = sample_k_from(pool, 10, rng)
    assert sorted(result) == [1, 2, 3]
