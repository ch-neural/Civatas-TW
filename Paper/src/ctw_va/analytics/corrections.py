"""Multiple-testing corrections.

Implements Holm-Bonferroni (FWER) and Benjamini-Hochberg (FDR). Both return
adjusted p-values aligned to the input order (not the sort order), so the
caller does not need to un-permute.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np


__all__ = ["holm_bonferroni", "benjamini_hochberg"]


def holm_bonferroni(pvals: Iterable[float]) -> np.ndarray:
    """Return Holm-adjusted p-values (strong FWER control).

    For sorted p-values p_(1) ≤ … ≤ p_(n):
        adj_(k) = max_{j ≤ k} [ (n − j + 1) · p_(j) ],  clipped to [0, 1].
    The prefix-max enforces monotonicity in the sorted order.
    """
    arr = np.asarray(list(pvals), dtype=float)
    n = arr.size
    if n == 0:
        return arr
    order = np.argsort(arr, kind="mergesort")
    adj = np.empty(n, dtype=float)
    running_max = 0.0
    for rank, idx in enumerate(order):
        val = (n - rank) * arr[idx]
        running_max = max(running_max, val)
        adj[idx] = min(running_max, 1.0)
    return adj


def benjamini_hochberg(pvals: Iterable[float]) -> np.ndarray:
    """Return BH-adjusted p-values (FDR control, step-up).

    For sorted p-values p_(1) ≤ … ≤ p_(n):
        adj_(k) = min_{j ≥ k} [ (n / j) · p_(j) ],  clipped to [0, 1].
    The suffix-min is the standard BH step-up procedure.
    """
    arr = np.asarray(list(pvals), dtype=float)
    n = arr.size
    if n == 0:
        return arr
    order = np.argsort(arr, kind="mergesort")
    adj = np.empty(n, dtype=float)
    running_min = 1.0
    for rank in range(n - 1, -1, -1):
        idx = order[rank]
        val = arr[idx] * n / (rank + 1)
        running_min = min(running_min, val)
        adj[idx] = min(running_min, 1.0)
    return adj
