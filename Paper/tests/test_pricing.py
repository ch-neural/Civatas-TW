"""Unit tests for pricing.py — verify estimate_cost for all 5 vendors."""
from __future__ import annotations

import pytest

from ctw_va.data.pricing import PRICING_TABLE, estimate_cost


INPUT_TOKENS = 2000
OUTPUT_TOKENS = 500


def test_all_vendors_present():
    """All 5 experiment vendors must have entries in PRICING_TABLE."""
    assert set(PRICING_TABLE.keys()) == {"openai", "gemini", "grok", "deepseek", "kimi"}


def test_estimate_cost_openai():
    """gpt-4o-mini: input=0.15/1M, output=0.60/1M. No cache."""
    cost = estimate_cost("openai", INPUT_TOKENS, OUTPUT_TOKENS)
    expected = 2000 * 0.15 / 1_000_000 + 500 * 0.60 / 1_000_000
    assert abs(cost - expected) < 1e-10, f"openai cost mismatch: {cost} != {expected}"


def test_estimate_cost_gemini():
    """gemini-2.5-flash-lite: input=0.10/1M, output=0.40/1M."""
    cost = estimate_cost("gemini", INPUT_TOKENS, OUTPUT_TOKENS)
    expected = 2000 * 0.10 / 1_000_000 + 500 * 0.40 / 1_000_000
    assert abs(cost - expected) < 1e-10, f"gemini cost mismatch: {cost} != {expected}"


def test_estimate_cost_grok():
    """grok-4.1-fast: input=0.20/1M, output=0.50/1M, no cache."""
    cost = estimate_cost("grok", INPUT_TOKENS, OUTPUT_TOKENS)
    expected = 2000 * 0.20 / 1_000_000 + 500 * 0.50 / 1_000_000
    assert abs(cost - expected) < 1e-10, f"grok cost mismatch: {cost} != {expected}"


def test_estimate_cost_deepseek():
    """deepseek-chat: input=0.28/1M, output=0.42/1M."""
    cost = estimate_cost("deepseek", INPUT_TOKENS, OUTPUT_TOKENS)
    expected = 2000 * 0.28 / 1_000_000 + 500 * 0.42 / 1_000_000
    assert abs(cost - expected) < 1e-10, f"deepseek cost mismatch: {cost} != {expected}"


def test_estimate_cost_kimi():
    """kimi-k2-0905: input=0.60/1M, output=2.50/1M."""
    cost = estimate_cost("kimi", INPUT_TOKENS, OUTPUT_TOKENS)
    expected = 2000 * 0.60 / 1_000_000 + 500 * 2.50 / 1_000_000
    assert abs(cost - expected) < 1e-10, f"kimi cost mismatch: {cost} != {expected}"


def test_estimate_cost_with_cache_openai():
    """Cache hit reduces cost: 500 cached tokens use cached_per_1m=0.075."""
    cost = estimate_cost("openai", INPUT_TOKENS, OUTPUT_TOKENS, cached_tokens=500)
    non_cached = (2000 - 500) * 0.15 / 1_000_000
    cached = 500 * 0.075 / 1_000_000
    output = 500 * 0.60 / 1_000_000
    expected = non_cached + cached + output
    assert abs(cost - expected) < 1e-10


def test_estimate_cost_with_cache_grok():
    """Grok has no cache (cached_per_1m=None) — cached_tokens ignored."""
    cost_no_cache = estimate_cost("grok", INPUT_TOKENS, OUTPUT_TOKENS)
    cost_with_cache = estimate_cost("grok", INPUT_TOKENS, OUTPUT_TOKENS, cached_tokens=500)
    # cached_tokens should have no effect when cached_per_1m is None
    assert abs(cost_no_cache - cost_with_cache) < 1e-10


def test_unknown_vendor_raises():
    with pytest.raises(KeyError):
        estimate_cost("unknown_vendor", 1000, 200)
