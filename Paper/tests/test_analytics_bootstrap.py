import numpy as np
import pytest

from ctw_va.analytics.bootstrap import paired_bootstrap, percentile_ci


def test_bootstrap_mean_ci_contains_true_value():
    rng = np.random.default_rng(42)
    data = rng.normal(loc=5.0, scale=1.0, size=200).tolist()
    res = paired_bootstrap(data, statistic=lambda x: float(np.mean(x)), n_resamples=2000, seed=1)
    assert res.ci_low <= 5.0 <= res.ci_high
    # Estimate should be close to the sample mean (which itself is close to 5.0).
    assert res.estimate == pytest.approx(float(np.mean(data)), abs=1e-9)


def test_bootstrap_constant_data_has_zero_width_ci():
    data = [3.0] * 50
    res = paired_bootstrap(data, statistic=lambda x: float(np.mean(x)), n_resamples=500, seed=7)
    # Every resample of a constant vector has the same mean, so CI collapses.
    assert res.ci_low == pytest.approx(3.0, abs=1e-12)
    assert res.ci_high == pytest.approx(3.0, abs=1e-12)
    assert res.estimate == pytest.approx(3.0)


def test_percentile_ci_matches_quantile():
    samples = np.linspace(0, 100, 1001)
    lo, hi = percentile_ci(samples, confidence=0.95)
    assert lo == pytest.approx(2.5, abs=1.0)
    assert hi == pytest.approx(97.5, abs=1.0)


def test_bootstrap_small_sample_falls_back_to_percentile():
    # n=2 triggers the percentile fallback (BCa requires ≥3 for jackknife).
    data = [1.0, 5.0]
    res = paired_bootstrap(data, statistic=lambda x: float(np.mean(x)), n_resamples=200, seed=3)
    assert res.method == "percentile"
    assert res.ci_low <= res.estimate <= res.ci_high


def test_bootstrap_raises_on_empty():
    with pytest.raises(ValueError):
        paired_bootstrap([], statistic=lambda x: 0.0)
