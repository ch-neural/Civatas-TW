"""Feed resolver: deterministic per-agent article sampling.

Ported from ap/services/evolution/app/feed_engine.py (commit 171b7c51).
Standalone version with imports from ..data.feed_sources instead of main Civatas.

Key functions:
    resolve_feed_for_agent — main entry point (MEDIA_HABIT_EXPOSURE_MIX-driven)
    _article_domain        — extract bare domain from article dict
    _article_leaning       — resolve article leaning (domain → source_tag → fallback)
    sample_k_from          — safe k-sample helper
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


def _article_domain(article: dict) -> str:
    """Extract the domain of an article's source URL.

    Prefers explicit ``source_domain`` if set by upstream (e.g. site_scoped_search);
    falls back to parsing ``link`` / ``url`` field.
    """
    if article.get("source_domain"):
        return article["source_domain"].lower().removeprefix("www.")
    url = article.get("link") or article.get("url") or ""
    if not url:
        return ""
    return (urlparse(url).netloc or "").lower().removeprefix("www.")


def _article_leaning(article: dict) -> str:
    """Resolve an article's leaning using (in order, authoritative first):
       1. domain → DOMAIN_LEANING_MAP (authoritative, derived from Stage A-C pilots)
       2. source_tag → DEFAULT_SOURCE_LEANINGS (Chinese source name mapping)
       3. explicit ``source_leaning`` field (legacy; stale "中間" default in pre-Stage 8.3
          injected articles means this is only used as last resort before fallback)
       4. fallback '中間'
    """
    # 1. Domain lookup (most authoritative)
    domain = _article_domain(article)
    if domain:
        by_domain = domain_to_leaning(domain)
        if by_domain:
            return by_domain
    # 2. Chinese source name lookup
    source_tag = article.get("source_tag") or article.get("source") or ""
    by_name = DEFAULT_SOURCE_LEANINGS.get(source_tag)
    if by_name:
        return by_name
    # 3. Explicit source_leaning (last resort — may be stale default)
    explicit = article.get("source_leaning")
    if explicit and explicit not in ("Tossup", "中間"):
        return explicit
    # 4. Fallback
    return "中間"


def sample_k_from(pool: list, k: int, rng: random.Random) -> list:
    """Sample up to ``k`` items from ``pool`` using ``rng``. Safe for empty/small pools."""
    if not pool or k <= 0:
        return []
    k = min(k, len(pool))
    return rng.sample(pool, k)


def resolve_feed_for_agent(
    agent: dict,
    news_pool: list[dict],
    day: int,
    replication_seed: int = 0,
    target_n: int = 30,
) -> list[dict]:
    """Return the candidate article pool for an agent on a given simulation day.

    Uses MEDIA_HABIT_EXPOSURE_MIX as the target exposure distribution.
    For each leaning bucket, takes ``proportion × target_n`` articles
    (rounded, at most what the bucket has available), so the final list
    has the requested leaning mix regardless of pool-bucket size imbalances.

    RNG is seeded by (agent.id or person_id, day, replication_seed) so the
    same simulation can be reproduced exactly.

    Special case: 深藍 agents have no online 深藍 source; the 偏藍 bucket
    is restricted to DEEP_BLUE_FALLBACK_DOMAINS (chinatimes, tvbs, udn).

    Args:
        agent: Dict with keys id/person_id/agent_id, party_lean, media_habit.
        news_pool: List of article dicts from the merged pool.
        day: Simulation day integer (used for RNG seeding).
        replication_seed: Experiment-level seed (all vendors use same value).
        target_n: Target articles per agent per day.

    Returns:
        List of article dicts (may be shorter than target_n if pool is thin).
    """
    agent_id = agent.get("id") or agent.get("person_id") or agent.get("agent_id") or ""
    rng = random.Random(hash((str(agent_id), day, replication_seed)))

    # MEDIA_HABIT_EXPOSURE_MIX is keyed by 5-bucket political leaning (深綠/偏綠/
    # 中間/偏藍/深藍). Read party_lean first; only fall back to media_habit if
    # its value happens to be a 5-bucket label (legacy / custom data).
    _bucket_labels = {"深綠", "偏綠", "中間", "偏藍", "深藍"}
    _raw_habit = agent.get("party_lean") or agent.get("media_habit") or "中間"
    leaning_bucket = _raw_habit if _raw_habit in _bucket_labels else "中間"
    mix = MEDIA_HABIT_EXPOSURE_MIX.get(leaning_bucket)
    if not mix:
        # Unknown leaning → return full pool (no filtering)
        return list(news_pool)

    # Pre-bucket articles by leaning once
    by_leaning: dict[str, list[dict]] = {l: [] for l in ("深綠", "偏綠", "中間", "偏藍", "深藍")}
    for a in news_pool:
        l = _article_leaning(a)
        if l in by_leaning:
            by_leaning[l].append(a)

    # Deep-blue source tag whitelist (for manual-inject articles without URLs)
    _deep_blue_source_tags = {
        "中時新聞網", "中時電子報", "TVBS 新聞", "TVBS新聞", "聯合新聞網", "聯合報",
    }

    selected: list[dict] = []
    for leaning, proportion in mix.items():
        if proportion <= 0:
            continue
        pool = by_leaning.get(leaning, [])
        if leaning_bucket == "深藍" and leaning == "偏藍":
            # 深藍 fallback: accept if domain is in DEEP_BLUE_FALLBACK_DOMAINS
            # OR source_tag matches top-partisan Chinese source name.
            # This handles manual-inject articles without URLs (no domain available).
            pool = [
                a for a in pool
                if _article_domain(a) in DEEP_BLUE_FALLBACK_DOMAINS
                or (a.get("source_tag") or a.get("source") or "") in _deep_blue_source_tags
            ]
        if not pool:
            continue
        # Determine count: proportion of target_n (min 1 when proportion > 0)
        k = max(1, round(proportion * target_n))
        selected.extend(sample_k_from(pool, k, rng))

    return selected
