"""Normalized Earth Mover's Distance for 5-bucket ordinal party_lean.

For two probability vectors P, Q over ordered categories [0..k-1]:

    EMD  = Σ_{i=0..k-2} |CDF_P(i) − CDF_Q(i)|
    NEMD = EMD / (k − 1)

NEMD is bounded in [0, 1] and captures ordinal distance (moving mass from
「深綠」 to 「偏綠」 is smaller than 「深綠」 to 「深藍」).
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np


__all__ = ["PARTY_LEAN_ORDER", "emd_ordinal", "nemd_ordinal", "lean_distribution"]


PARTY_LEAN_ORDER: tuple[str, ...] = ("深綠", "偏綠", "中間", "偏藍", "深藍")


def _as_prob(vec: Iterable[float]) -> np.ndarray:
    v = np.asarray(list(vec), dtype=float)
    s = v.sum()
    if s <= 0:
        raise ValueError("distribution must have positive mass")
    return v / s


def emd_ordinal(p: Iterable[float], q: Iterable[float]) -> float:
    """Earth Mover's Distance on a 1-D ordinal support with unit spacing."""
    P = _as_prob(p)
    Q = _as_prob(q)
    if P.shape != Q.shape:
        raise ValueError(f"shape mismatch: {P.shape} vs {Q.shape}")
    cdf_p = np.cumsum(P)
    cdf_q = np.cumsum(Q)
    # Sum of |CDF_P - CDF_Q| at positions 0..k-2 (the last term is always 0).
    return float(np.sum(np.abs(cdf_p[:-1] - cdf_q[:-1])))


def nemd_ordinal(p: Iterable[float], q: Iterable[float]) -> float:
    """Normalized EMD: EMD divided by max possible (= k − 1)."""
    P = np.asarray(list(p), dtype=float)
    if P.size < 2:
        return 0.0
    return emd_ordinal(p, q) / float(P.size - 1)


def lean_distribution(
    buckets: Iterable[str], *, order: tuple[str, ...] = PARTY_LEAN_ORDER,
) -> np.ndarray:
    """Count bucket labels and return a probability vector in ``order``."""
    counts: dict[str, int] = {c: 0 for c in order}
    for b in buckets:
        if b in counts:
            counts[b] += 1
    total = sum(counts.values())
    if total == 0:
        return np.full(len(order), 1.0 / len(order))
    return np.asarray([counts[c] / total for c in order], dtype=float)


def dist_from_counts(counts: Mapping[str, float], *, order: tuple[str, ...] = PARTY_LEAN_ORDER) -> np.ndarray:
    """Convert a dict {bucket: count} → probability vector in the canonical order."""
    total = float(sum(counts.get(c, 0.0) for c in order))
    if total <= 0:
        return np.full(len(order), 1.0 / len(order))
    return np.asarray([counts.get(c, 0.0) / total for c in order], dtype=float)
