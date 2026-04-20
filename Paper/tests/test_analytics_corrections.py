import numpy as np
import pytest

from ctw_va.analytics.corrections import benjamini_hochberg, holm_bonferroni


def test_holm_basic():
    p = [0.01, 0.04, 0.03, 0.005]
    adj = holm_bonferroni(p)
    # Sorted: 0.005 → × 4 = 0.020; 0.01 → × 3 = 0.03; 0.03 → × 2 = 0.06; 0.04 → × 1 = 0.04.
    # Running max enforced in sort order → [0.020, 0.030, 0.060, 0.060].
    # Mapped back to input indices [0.01, 0.04, 0.03, 0.005] → [0.03, 0.06, 0.06, 0.02].
    assert adj.tolist() == pytest.approx([0.03, 0.06, 0.06, 0.02])


def test_holm_clips_at_one():
    adj = holm_bonferroni([0.5, 0.5, 0.5, 0.5])
    # Each × (n − rank): 4·0.5=2, 3·0.5=1.5, 2·0.5=1, 1·0.5=0.5 → all clipped to 1.0.
    assert adj.tolist() == pytest.approx([1.0, 1.0, 1.0, 1.0])


def test_bh_basic():
    p = [0.01, 0.02, 0.03, 0.04, 0.05]
    adj = benjamini_hochberg(p)
    # sorted ascending: k=1..5, adj_k = p_k · n / k.
    # k=1: 0.01·5/1 = 0.05; k=2: 0.02·5/2 = 0.05; k=3: 0.03·5/3 = 0.05;
    # k=4: 0.04·5/4 = 0.05; k=5: 0.05·5/5 = 0.05. Running min (right-to-left) = 0.05.
    assert adj.tolist() == pytest.approx([0.05] * 5)


def test_bh_monotone_in_sort_order():
    p = np.asarray([0.001, 0.005, 0.5, 0.8])
    adj = benjamini_hochberg(p)
    # Assert monotonicity in sort order.
    order = np.argsort(p)
    sorted_adj = adj[order]
    for i in range(len(sorted_adj) - 1):
        assert sorted_adj[i] <= sorted_adj[i + 1] + 1e-12


def test_bh_clips_to_one():
    adj = benjamini_hochberg([0.9, 0.95, 0.99])
    assert all(v <= 1.0 for v in adj)


def test_empty_input_returns_empty():
    assert holm_bonferroni([]).size == 0
    assert benjamini_hochberg([]).size == 0
