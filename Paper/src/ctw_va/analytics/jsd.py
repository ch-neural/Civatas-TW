"""Jensen-Shannon divergence on categorical distributions.

JSD(P, Q) = 0.5·KL(P‖M) + 0.5·KL(Q‖M) where M = (P+Q)/2.
Using log base 2, JSD is bounded in [0, 1] which is convenient for the
paper's vendor comparison tables.
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np


__all__ = [
    "counts_to_probs",
    "align_distributions",
    "jsd",
    "party_distribution_from_choices",
]

_LN2 = float(np.log(2.0))


def counts_to_probs(counts: Mapping[str, float], categories: list[str]) -> np.ndarray:
    """Turn a category→count dict into a probability vector ordered by ``categories``.

    Missing categories are treated as zero. If the total is zero, returns a
    uniform distribution (so JSD is well-defined but large vs. any real dist).
    """
    vec = np.asarray([float(counts.get(c, 0.0)) for c in categories], dtype=float)
    total = vec.sum()
    if total == 0.0:
        return np.full(len(categories), 1.0 / max(len(categories), 1))
    return vec / total


def align_distributions(
    p: Mapping[str, float], q: Mapping[str, float], *, categories: Iterable[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (P, Q, category_list) aligned on the union (or fixed) category list."""
    if categories is None:
        keys = sorted(set(p.keys()) | set(q.keys()))
    else:
        keys = list(categories)
    return counts_to_probs(p, keys), counts_to_probs(q, keys), keys


def jsd(p: Iterable[float], q: Iterable[float], *, base: float = 2.0) -> float:
    """Jensen-Shannon divergence between two probability vectors.

    Inputs are normalized internally. Returns a scalar in [0, 1] when base=2.
    """
    P = np.asarray(list(p), dtype=float)
    Q = np.asarray(list(q), dtype=float)
    if P.shape != Q.shape:
        raise ValueError(f"shape mismatch: {P.shape} vs {Q.shape}")
    sP = P.sum()
    sQ = Q.sum()
    if sP <= 0 or sQ <= 0:
        raise ValueError("distributions must have positive mass")
    P = P / sP
    Q = Q / sQ
    M = 0.5 * (P + Q)

    def _kl(a: np.ndarray, b: np.ndarray) -> float:
        mask = (a > 0) & (b > 0)
        if not mask.any():
            return 0.0
        return float(np.sum(a[mask] * np.log(a[mask] / b[mask])))

    val = 0.5 * _kl(P, M) + 0.5 * _kl(Q, M)
    if base == 2.0:
        val /= _LN2
    elif base != float(np.e):
        val /= float(np.log(base))
    # Numerical clamp; the theoretical upper bound is log_base(2).
    return max(0.0, min(1.0, val))


def party_distribution_from_choices(choices: Iterable[str], categories: list[str]) -> np.ndarray:
    """Count a sequence of party_choice strings and return a probability vector."""
    counts: dict[str, int] = {c: 0 for c in categories}
    other = 0
    for ch in choices:
        if ch in counts:
            counts[ch] += 1
        else:
            other += 1
    if other:
        # Drop OOV labels silently; caller is expected to pre-normalise.
        pass
    total = sum(counts.values())
    if total == 0:
        return np.full(len(categories), 1.0 / len(categories))
    return np.asarray([counts[c] / total for c in categories], dtype=float)
