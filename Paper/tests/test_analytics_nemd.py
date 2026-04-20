import pytest

from ctw_va.analytics.nemd import (
    PARTY_LEAN_ORDER,
    emd_ordinal,
    lean_distribution,
    nemd_ordinal,
)


def test_nemd_identity_zero():
    p = [0.2, 0.2, 0.2, 0.2, 0.2]
    assert nemd_ordinal(p, p) == pytest.approx(0.0, abs=1e-12)


def test_nemd_adjacent_shift_smaller_than_extreme():
    # All mass in 深綠 vs. mass in 偏綠 (1 step) < All mass in 深綠 vs. 深藍 (4 steps).
    deep_green = [1, 0, 0, 0, 0]
    light_green = [0, 1, 0, 0, 0]
    deep_blue = [0, 0, 0, 0, 1]
    assert nemd_ordinal(deep_green, light_green) == pytest.approx(0.25, abs=1e-12)  # 1/4
    assert nemd_ordinal(deep_green, deep_blue) == pytest.approx(1.0, abs=1e-12)
    assert nemd_ordinal(deep_green, light_green) < nemd_ordinal(deep_green, deep_blue)


def test_nemd_symmetric():
    p = [0.1, 0.2, 0.4, 0.2, 0.1]
    q = [0.4, 0.3, 0.2, 0.1, 0.0]
    assert nemd_ordinal(p, q) == pytest.approx(nemd_ordinal(q, p), abs=1e-12)


def test_emd_unnormalized_matches_formula():
    # Manual: CDF_P = [1, 1, 1, 1, 1], CDF_Q = [0, 0, 0, 0, 1].
    # Sum over i=0..3 |CDF_P − CDF_Q| = 1 + 1 + 1 + 1 = 4.
    p = [1, 0, 0, 0, 0]
    q = [0, 0, 0, 0, 1]
    assert emd_ordinal(p, q) == pytest.approx(4.0)


def test_lean_distribution_ignores_unknown_labels():
    buckets = ["深綠", "深綠", "中間", "偏藍", "foo"]  # foo silently dropped
    vec = lean_distribution(buckets)
    # 2 深綠 + 1 中間 + 1 偏藍 = 4 total; foo excluded.
    assert list(zip(PARTY_LEAN_ORDER, vec.tolist())) == [
        ("深綠", 0.5), ("偏綠", 0.0), ("中間", 0.25), ("偏藍", 0.25), ("深藍", 0.0),
    ]
