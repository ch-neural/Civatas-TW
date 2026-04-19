"""Vendor pricing table for CTW-VA-2026.

Verbatim from spec §B1. Used for cost estimation and budget tracking.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VendorPricing:
    vendor: str
    model_id: str
    input_per_1m: float    # USD per 1M input tokens
    output_per_1m: float
    cached_per_1m: float | None
    knowledge_cutoff: str
    context_window: int
    fetched_at: str


PRICING_TABLE: dict[str, VendorPricing] = {
    "openai": VendorPricing(
        vendor="openai",
        model_id="gpt-4o-mini",
        input_per_1m=0.15,
        output_per_1m=0.60,
        cached_per_1m=0.075,
        knowledge_cutoff="2024-10",
        context_window=128_000,
        fetched_at="2026-04-19",
    ),
    "gemini": VendorPricing(
        vendor="gemini",
        model_id="gemini-2.5-flash-lite",
        input_per_1m=0.10,
        output_per_1m=0.40,
        cached_per_1m=0.025,
        knowledge_cutoff="2025-01",
        context_window=1_000_000,
        fetched_at="2026-04-19",
    ),
    "grok": VendorPricing(
        vendor="grok",
        model_id="grok-4.1-fast",
        input_per_1m=0.20,
        output_per_1m=0.50,
        cached_per_1m=None,
        knowledge_cutoff="2025-04",
        context_window=2_000_000,
        fetched_at="2026-04-19",
    ),
    "deepseek": VendorPricing(
        vendor="deepseek",
        model_id="deepseek-chat",  # V3.2, NOT deepseek-reasoner
        input_per_1m=0.28,
        output_per_1m=0.42,
        cached_per_1m=0.028,
        knowledge_cutoff="2024-07",
        context_window=128_000,
        fetched_at="2026-04-19",
    ),
    "kimi": VendorPricing(
        vendor="kimi",
        model_id="kimi-k2-0905-preview",
        input_per_1m=0.60,
        output_per_1m=2.50,
        cached_per_1m=0.15,
        knowledge_cutoff="2024-10",
        context_window=128_000,
        fetched_at="2026-04-19",
    ),
}


def estimate_cost(
    vendor: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """Estimate USD cost for a single vendor call.

    Args:
        vendor: One of openai / gemini / grok / deepseek / kimi.
        input_tokens: Total input token count (including cached portion).
        output_tokens: Output token count.
        cached_tokens: Portion of input_tokens served from cache (0 if
            vendor does not support caching or cache was cold).

    Returns:
        Estimated cost in USD.
    """
    p = PRICING_TABLE[vendor]
    cost = 0.0
    if cached_tokens and p.cached_per_1m is not None:
        # Vendor supports cache: non-cached portion at full rate, cached at reduced rate
        cost += (input_tokens - cached_tokens) * p.input_per_1m / 1_000_000
        cost += cached_tokens * p.cached_per_1m / 1_000_000
    else:
        # No cache support (or no cache hit): all input at full rate
        cost += input_tokens * p.input_per_1m / 1_000_000
    # Output
    cost += output_tokens * p.output_per_1m / 1_000_000
    return cost
