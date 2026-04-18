"""Verify party_members snapshot schema and sanity.

Run: python3 scripts/verify_party_member_snapshot.py
Exit 0 = pass.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from datetime import date, datetime

ROOT = Path(__file__).resolve().parent.parent
SNAP = ROOT / "ap" / "shared" / "tw_data" / "party_members_2026.json"


def main() -> int:
    data = json.loads(SNAP.read_text(encoding="utf-8"))

    # Required top-level keys
    for k in ("as_of", "adult_pop_20plus", "parties"):
        assert k in data, f"missing top-level key: {k}"

    # adult_pop_20plus sane range (18-22M)
    assert 18_000_000 <= data["adult_pop_20plus"] <= 22_000_000, "adult pop out of range"

    # Each party has count + sources
    for party_code in ("KMT", "DPP", "TPP"):
        p = data["parties"][party_code]
        assert p["count"] > 0, f"{party_code} count must be positive"
        assert p["count"] < 1_000_000, f"{party_code} count unreasonably large"
        assert isinstance(p["sources"], list) and len(p["sources"]) >= 1, \
            f"{party_code} must have at least 1 source"
        for s in p["sources"]:
            assert s["url"].startswith("http"), f"{party_code} source url invalid"

    # as_of within reasonable window
    as_of = date.fromisoformat(data["as_of"])
    assert as_of.year >= 2024, "as_of too old"

    print(f"✅ party_members snapshot OK ({SNAP})")
    print(f"   KMT: {data['parties']['KMT']['count']:,}")
    print(f"   DPP: {data['parties']['DPP']['count']:,}")
    print(f"   TPP: {data['parties']['TPP']['count']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
