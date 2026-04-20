"""Bootstrap confidence intervals.

Supports percentile and BCa (bias-corrected and accelerated). For the vendor
audit we resample **persona groups** (not individual rows) to respect the
paired-on-persona design: each persona contributes one observation per vendor,
so resampling personas preserves the within-persona correlation structure.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np
from scipy import stats


__all__ = ["BootstrapResult", "paired_bootstrap", "percentile_ci", "bca_ci"]


@dataclass
class BootstrapResult:
    estimate: float
    ci_low: float
    ci_high: float
    method: str        # "percentile" | "bca"
    n_resamples: int
    confidence: float  # e.g. 0.95
    samples: np.ndarray  # the B bootstrap estimates, kept for diagnostics

    def as_dict(self) -> dict:
        return {
            "estimate": float(self.estimate),
            "ci_low": float(self.ci_low),
            "ci_high": float(self.ci_high),
            "method": self.method,
            "n_resamples": int(self.n_resamples),
            "confidence": float(self.confidence),
        }


def percentile_ci(samples: np.ndarray, *, confidence: float = 0.95) -> tuple[float, float]:
    alpha = 1.0 - confidence
    lo = float(np.quantile(samples, alpha / 2.0))
    hi = float(np.quantile(samples, 1.0 - alpha / 2.0))
    return lo, hi


def bca_ci(
    theta_hat: float,
    samples: np.ndarray,
    jackknife_vals: np.ndarray,
    *,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Bias-corrected and accelerated percentile CI.

    Falls back to percentile CI if the acceleration denominator is degenerate
    (all jackknife values equal) — this keeps small-sample or constant-stat
    cases numerically stable instead of returning NaN.
    """
    B = samples.size
    if B == 0:
        return float("nan"), float("nan")

    # Bias correction z0 from fraction of bootstrap samples below theta_hat.
    below = float(np.sum(samples < theta_hat)) / B
    below = min(max(below, 1.0 / (B + 1)), 1.0 - 1.0 / (B + 1))  # avoid ±inf
    z0 = stats.norm.ppf(below)

    # Acceleration from jackknife.
    jk_mean = float(np.mean(jackknife_vals))
    diffs = jk_mean - jackknife_vals
    num = float(np.sum(diffs ** 3))
    den = 6.0 * (float(np.sum(diffs ** 2)) ** 1.5)
    a = num / den if den > 0 else 0.0

    alpha = 1.0 - confidence
    z_lo = stats.norm.ppf(alpha / 2.0)
    z_hi = stats.norm.ppf(1.0 - alpha / 2.0)

    def _adjust(z: float) -> float:
        denom = 1.0 - a * (z0 + z)
        if denom == 0:
            return float("nan")
        return float(stats.norm.cdf(z0 + (z0 + z) / denom))

    q_lo = _adjust(z_lo)
    q_hi = _adjust(z_hi)
    if not (np.isfinite(q_lo) and np.isfinite(q_hi)):
        return percentile_ci(samples, confidence=confidence)

    lo = float(np.quantile(samples, q_lo))
    hi = float(np.quantile(samples, q_hi))
    return lo, hi


def paired_bootstrap(
    data: Sequence,                                 # one element per persona
    statistic: Callable[[Sequence], float],
    *,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    method: str = "bca",
    seed: int | None = None,
) -> BootstrapResult:
    """Bootstrap over a sequence whose elements represent whole personas.

    ``statistic`` is called once on the original ``data`` (to get θ̂) and once
    per resample. For BCa we additionally run a leave-one-out jackknife over
    personas to estimate the acceleration.
    """
    arr = list(data)
    n = len(arr)
    if n == 0:
        raise ValueError("data must contain at least one persona")

    theta_hat = float(statistic(arr))

    rng = np.random.default_rng(seed)
    samples = np.empty(n_resamples, dtype=float)
    for b in range(n_resamples):
        idx = rng.integers(0, n, size=n)
        samples[b] = float(statistic([arr[i] for i in idx]))

    if method == "percentile" or n < 3:
        lo, hi = percentile_ci(samples, confidence=confidence)
        used = "percentile"
    else:
        # Jackknife.
        jk = np.empty(n, dtype=float)
        for i in range(n):
            left = arr[:i] + arr[i + 1:]
            jk[i] = float(statistic(left))
        lo, hi = bca_ci(theta_hat, samples, jk, confidence=confidence)
        used = "bca"

    return BootstrapResult(
        estimate=theta_hat,
        ci_low=lo,
        ci_high=hi,
        method=used,
        n_resamples=n_resamples,
        confidence=confidence,
        samples=samples,
    )
