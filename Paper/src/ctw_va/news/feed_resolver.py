"""Feed resolver: deterministic per-agent article sampling.

Ported from ap/services/evolution/app/feed_engine.py (commit 171b7c51),
refactored to match CTW-VA-2026 spec §A4 signature for research purity.

Key functions:
    resolve_feed_for_agent — main entry point (spec §A4)
    _article_leaning        — resolve article leaning (fallback chain)
    _article_domain         — extract bare domain from article dict
    sample_k_from           — safe k-sample helper
"""
from __future__ import annotations

import random
from urllib.parse import urlparse

from ..data.feed_sources import (
    DOMAIN_LEANING_MAP,
    DEEP_BLUE_FALLBACK_DOMAINS,
    MEDIA_HABIT_EXPOSURE_MIX,
    DEFAULT_SOURCE_LEANINGS,
    domain_to_leaning,
)

# Top-partisan 偏藍 source_tag whitelist for 深藍 fallback when articles
# lack a resolvable domain (e.g. manual-inject). Paper pool has URLs so
# this is used only as belt-and-suspenders defense.
_DEEP_BLUE_SOURCE_TAGS = {
    "中時新聞網", "中時電子報", "TVBS 新聞", "TVBS新聞", "聯合新聞網", "聯合報",
}

_BUCKET_LABELS = ("深綠", "偏綠", "中間", "偏藍", "深藍")


def _article_domain(article: dict) -> str:
    """Extract the domain of an article's source URL."""
    if article.get("source_domain"):
        return article["source_domain"].lower().removeprefix("www.")
    url = article.get("url") or article.get("link") or ""
    if not url:
        return ""
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def _article_leaning(article: dict) -> str:
    """Resolve article leaning (priority: explicit source_leaning → domain → source_tag → fallback).

    Paper's A1 merge pre-computes `source_leaning` via domain_to_leaning() so
    the explicit field is authoritative. Other paths are defensive fallbacks.
    """
    # 1. Explicit source_leaning (Paper A1 merge writes this)
    explicit = article.get("source_leaning")
    if explicit and explicit in _BUCKET_LABELS:
        return explicit
    # 2. Domain lookup
    domain = _article_domain(article)
    if domain:
        by_domain = domain_to_leaning(domain)
        if by_domain:
            return by_domain
    # 3. Chinese source_tag lookup
    source_tag = article.get("source_tag") or article.get("source") or ""
    by_name = DEFAULT_SOURCE_LEANINGS.get(source_tag)
    if by_name:
        return by_name
    return "中間"


def sample_k_from(pool: list, k: int, rng: random.Random) -> list:
    """Sample up to ``k`` items from ``pool`` using ``rng``. Safe for empty/small pools."""
    if not pool or k <= 0:
        return []
    k = min(k, len(pool))
    return rng.sample(pool, k)


def resolve_feed_for_agent(
    agent_id: str,
    agent_media_habit: str,
    news_pool: list[dict],
    sim_day: int,
    replication_seed: int,
    k: int = 3,
) -> list[dict]:
    """Deterministic stratified sampling of daily articles for one agent.

    Per CTW-VA-2026 spec §A4. Same (agent_id, sim_day, replication_seed) →
    identical output. All five vendors must call this with the same args →
    all five see identical articles.

    Algorithm:
      1. For each leaning bucket in MEDIA_HABIT_EXPOSURE_MIX[agent_media_habit]:
         a. Filter news_pool to that bucket (respecting excluded=True).
         b. For 深藍 agents' 偏藍 bucket: further restrict to DEEP_BLUE_FALLBACK_DOMAINS.
         c. Oversample proportion × k × 3 articles from the bucket.
      2. Concatenate all bucket samples into candidates.
      3. If candidates ≤ k → return all; else rng.sample(candidates, k).

    Args:
        agent_id: Unique persona identifier (stringifiable).
        agent_media_habit: Political leaning bucket label — one of
            {"深綠", "偏綠", "中間", "偏藍", "深藍"}. Despite the name
            "media_habit" (legacy), this is the political exposure class
            used to index MEDIA_HABIT_EXPOSURE_MIX.
        news_pool: List of article dicts. Each should have either
            `source_leaning` (preferred, pre-computed during A1 merge) or
            `source_domain` / `url` for fallback resolution.
            Articles with `excluded=True` are filtered out.
        sim_day: Simulation day integer (seed input).
        replication_seed: Experiment-level seed (all vendors same value).
        k: Target articles per agent per day. Default 3 per spec.

    Returns:
        List of ≤ k article dicts, deterministic for given args.

    Raises:
        KeyError: If agent_media_habit is not a valid bucket.
    """
    rng = random.Random(hash((str(agent_id), sim_day, replication_seed)))
    mix = MEDIA_HABIT_EXPOSURE_MIX[agent_media_habit]

    candidates: list[dict] = []
    for leaning, proportion in mix.items():
        if proportion <= 0:
            continue

        # Build the per-bucket candidate pool
        if agent_media_habit == "深藍" and leaning == "偏藍":
            # Deep-blue fallback: accept domain in whitelist OR source_tag match
            pool = [
                a for a in news_pool
                if not a.get("excluded", False)
                and _article_leaning(a) == leaning
                and (
                    _article_domain(a) in DEEP_BLUE_FALLBACK_DOMAINS
                    or (a.get("source_tag") or a.get("source") or "") in _DEEP_BLUE_SOURCE_TAGS
                )
            ]
        else:
            pool = [
                a for a in news_pool
                if not a.get("excluded", False)
                and _article_leaning(a) == leaning
            ]

        if not pool:
            continue

        # Oversample (spec: k × proportion × 3), bounded by pool size
        target_k = max(1, int(k * proportion * 3))
        target_k = min(target_k, len(pool))
        candidates.extend(rng.sample(pool, target_k))

    # Final trim to k
    if len(candidates) <= k:
        return candidates
    return rng.sample(candidates, k)
