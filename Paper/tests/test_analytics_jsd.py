import numpy as np
import pytest

from ctw_va.analytics.jsd import (
    align_distributions,
    counts_to_probs,
    jsd,
    party_distribution_from_choices,
)


def test_jsd_identity_is_zero():
    p = [0.3, 0.4, 0.3]
    assert jsd(p, p) == pytest.approx(0.0, abs=1e-12)


def test_jsd_symmetric():
    p = [0.1, 0.6, 0.3]
    q = [0.4, 0.4, 0.2]
    assert jsd(p, q) == pytest.approx(jsd(q, p), abs=1e-12)


def test_jsd_bounded_by_one():
    # Disjoint support — maximum divergence.
    p = [1.0, 0.0, 0.0]
    q = [0.0, 0.0, 1.0]
    assert jsd(p, q) == pytest.approx(1.0, abs=1e-12)


def test_jsd_handles_zeros():
    p = [0.5, 0.5, 0.0]
    q = [0.25, 0.25, 0.5]
    val = jsd(p, q)
    assert 0.0 < val < 1.0
    assert np.isfinite(val)


def test_jsd_rejects_empty_distribution():
    with pytest.raises(ValueError):
        jsd([0, 0, 0], [0.5, 0.5, 0.0])


def test_counts_to_probs_missing_filled_with_zero():
    vec = counts_to_probs({"A": 3, "B": 1}, ["A", "B", "C"])
    assert vec.tolist() == pytest.approx([0.75, 0.25, 0.0])


def test_align_distributions_union():
    P, Q, keys = align_distributions({"A": 1, "B": 1}, {"B": 1, "C": 2})
    assert keys == ["A", "B", "C"]
    assert P.tolist() == pytest.approx([0.5, 0.5, 0.0])
    assert Q.tolist() == pytest.approx([0.0, 1 / 3, 2 / 3])


def test_party_distribution_from_choices_oov_dropped():
    vec = party_distribution_from_choices(
        ["DPP", "DPP", "KMT", "IND", "???"], ["DPP", "KMT", "TPP", "IND"],
    )
    # 2 DPP + 1 KMT + 0 TPP + 1 IND = 4 valid; OOV silently dropped.
    assert vec.tolist() == pytest.approx([0.5, 0.25, 0.0, 0.25])
