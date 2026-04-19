"""Persona slate tests per CTW-VA-2026 spec §A3.

Tests:
    test_reproducibility  — two builds with same seed → byte-identical output
    test_n_exact          — build_slate(n=300) produces exactly 300
    test_party_lean_within_tolerance  — 5-bucket distribution ±2pp
    test_ethnicity_within_tolerance   — 5-group distribution ±1pp
    test_fields_present                — all required fields per spec §A3.3
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from ctw_va.persona.slate_builder import (
    build_slate,
    write_slate_jsonl,
    PARTY_LEAN_5_RATIOS,
    ETHNICITY_RATIOS,
)


def test_n_exact():
    personas = build_slate(n=300, seed=20240113)
    assert len(personas) == 300


def test_reproducibility(tmp_path):
    """Two builds with same (n, seed) → byte-identical JSONL → same SHA."""
    out1 = tmp_path / "slate1.jsonl"
    out2 = tmp_path / "slate2.jsonl"

    p1 = build_slate(n=300, seed=20240113)
    r1 = write_slate_jsonl(p1, out1)

    p2 = build_slate(n=300, seed=20240113)
    r2 = write_slate_jsonl(p2, out2)

    assert out1.read_bytes() == out2.read_bytes(), "byte-identical output violated"
    assert r1["sha256"] == r2["sha256"]


def test_different_seed_different_output():
    """Different seeds → different personas (sanity)."""
    p1 = build_slate(n=300, seed=20240113)
    p2 = build_slate(n=300, seed=20280116)
    assert [p.party_lean for p in p1] != [p.party_lean for p in p2]


def test_party_lean_within_tolerance():
    """5-bucket party_lean marginal distribution within ±2pp of target."""
    personas = build_slate(n=300, seed=20240113)
    n = len(personas)
    obs = Counter(p.party_lean for p in personas)
    for bucket, target in PARTY_LEAN_5_RATIOS.items():
        obs_p = obs.get(bucket, 0) / n
        delta = abs(obs_p - target)
        assert delta <= 0.02, (
            f"party_lean[{bucket}]: observed {obs_p:.3f} vs target {target:.3f}, "
            f"delta {delta:.3f} > 2pp"
        )


def test_ethnicity_within_tolerance():
    """Ethnicity marginal distribution within ±1pp of target."""
    personas = build_slate(n=300, seed=20240113)
    n = len(personas)
    obs = Counter(p.ethnicity for p in personas)
    for eth, target in ETHNICITY_RATIOS.items():
        obs_p = obs.get(eth, 0) / n
        delta = abs(obs_p - target)
        assert delta <= 0.01, (
            f"ethnicity[{eth}]: observed {obs_p:.3f} vs target {target:.3f}, "
            f"delta {delta:.3f} > 1pp"
        )


def test_fields_present():
    """All required fields per spec §A3.3 are present and non-empty."""
    personas = build_slate(n=50, seed=1)
    required = {
        "person_id", "age", "gender", "county", "township",
        "education", "occupation", "ethnicity", "household_income",
        "party_lean", "media_habit",
    }
    for p in personas:
        as_dict = p.__dict__
        missing = required - set(as_dict)
        assert not missing, f"persona {p.person_id} missing fields: {missing}"
        for field in ("party_lean", "ethnicity", "county", "township", "gender",
                       "education", "occupation", "household_income", "media_habit"):
            assert getattr(p, field), f"{p.person_id}.{field} empty"


def test_persona_id_format_and_sort():
    """persona_id is 'p_000001'..'p_000300', sorted ascending."""
    personas = build_slate(n=300, seed=20240113)
    ids = [p.person_id for p in personas]
    assert ids == sorted(ids)
    assert ids[0] == "p_000001"
    assert ids[-1] == "p_000300"
    # All unique
    assert len(set(ids)) == 300


def test_townships_plausible():
    """Townships conform to admin_key format 縣市|行政區."""
    personas = build_slate(n=300, seed=20240113)
    for p in personas:
        assert "|" in p.township, f"{p.person_id}.township={p.township!r} missing |"
        county_part, district_part = p.township.split("|", 1)
        assert county_part == p.county, (
            f"{p.person_id}: township county mismatch "
            f"({county_part!r} vs p.county={p.county!r})"
        )
        assert district_part, f"{p.person_id}: township district empty"
