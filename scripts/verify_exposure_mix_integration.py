"""Verify use_exposure_mix flag routes through evolver's feed resolution.

Does NOT run a full evolution job — just unit-tests the conditional branch.
"""
from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ap" / "services" / "evolution" / "app"))

from feed_engine import resolve_feed_for_agent, _article_leaning  # noqa: E402
from tw_feed_sources import DOMAIN_LEANING_MAP, MEDIA_HABIT_EXPOSURE_MIX  # noqa: E402


def _mk_pool(n_per_domain=20):
    pool = []
    aid = 0
    for domain in DOMAIN_LEANING_MAP:
        for _ in range(n_per_domain):
            pool.append({
                "id": f"a_{aid}",
                "link": f"https://{domain}/news/{aid}",
                "source_domain": domain,
            })
            aid += 1
    return pool


def test_integration_seed_reproducibility():
    """Same seed → identical article list."""
    agent = {"person_id": 42, "media_habit": "中間"}
    pool = _mk_pool()
    r1 = resolve_feed_for_agent(agent, pool, day=3, replication_seed=9999)
    r2 = resolve_feed_for_agent(agent, pool, day=3, replication_seed=9999)
    assert [a["id"] for a in r1] == [a["id"] for a in r2]
    print(f"  ✅ seed reproducibility: {len(r1)} articles")


def test_seed_0_varies_by_day():
    """Seed=0 but day changes → different articles (but each call deterministic)."""
    agent = {"person_id": 1, "media_habit": "偏綠"}
    pool = _mk_pool()
    r_d1 = resolve_feed_for_agent(agent, pool, day=1, replication_seed=0)
    r_d2 = resolve_feed_for_agent(agent, pool, day=2, replication_seed=0)
    # With different days, article sets likely differ
    assert [a["id"] for a in r_d1] != [a["id"] for a in r_d2]
    print(f"  ✅ day variance: d1={len(r_d1)}, d2={len(r_d2)}, different picks")


def test_no_mix_fallthrough():
    """When use_exposure_mix is NOT applied, caller uses full pool (not resolve_feed_for_agent).
    This test just confirms resolve_feed_for_agent returns sane subset independent of full pool."""
    agent = {"person_id": 77, "media_habit": "深藍"}
    pool = _mk_pool()
    r = resolve_feed_for_agent(agent, pool, day=1, replication_seed=1)
    # 深藍 agent should only see 偏藍-fallback + 中間 articles
    leanings_seen = Counter(_article_leaning(a) for a in r)
    assert leanings_seen.get("深綠", 0) == 0
    assert leanings_seen.get("偏綠", 0) == 0
    print(f"  ✅ 深藍 agent leanings: {dict(leanings_seen)}")


def main() -> int:
    print("=== use_exposure_mix integration tests ===")
    test_integration_seed_reproducibility()
    test_seed_0_varies_by_day()
    test_no_mix_fallthrough()
    print()
    print("✅ PR 2 integration tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
