"""VendorRouter tests (mocked — no real API calls)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from ctw_va.adapter.client import VendorResponse
from ctw_va.adapter.router import VendorRouter, prompt_hash


def _mock_response(vendor="openai", status="ok", cost=0.0001):
    return VendorResponse(
        vendor=vendor, model_id=f"{vendor}-model", status=status,
        raw_text="test reply", input_tokens=10, output_tokens=5,
        cost_usd=cost, latency_ms=100,
    )


def test_prompt_hash_deterministic():
    h1 = prompt_hash("sys", "user")
    h2 = prompt_hash("sys", "user")
    assert h1 == h2
    # Different prompts → different hashes
    assert prompt_hash("sys", "user") != prompt_hash("sys2", "user")


def test_router_single_vendor(tmp_path):
    from ctw_va.storage import db as storage_db
    storage_db.set_db_path(tmp_path / "test.db")

    mock_client = AsyncMock()
    mock_client.chat.return_value = _mock_response("openai")
    mock_client.model_id = "gpt-4o-mini"
    mock_client.vendor_name = "openai"

    router = VendorRouter(clients={"openai": mock_client})
    result = asyncio.run(router.chat_one(
        vendor="openai", system_prompt="sys", user_prompt="user",
        seed=1, experiment_id="t1", persona_id="p1", sim_day=0,
    ))
    assert result.status == "ok"
    assert result.vendor == "openai"
    mock_client.chat.assert_awaited_once()


def test_router_multivendor_fan_out(tmp_path):
    from ctw_va.storage import db as storage_db
    storage_db.set_db_path(tmp_path / "test2.db")

    mocks = {}
    for v in ("openai", "gemini", "kimi"):
        m = AsyncMock()
        m.chat.return_value = _mock_response(v)
        m.model_id = f"{v}-model"
        m.vendor_name = v
        mocks[v] = m

    router = VendorRouter(clients=mocks)
    result = asyncio.run(router.chat_multivendor(
        vendors=["openai", "gemini", "kimi"],
        system_prompt="same prompt", user_prompt="to all vendors",
        seed=1, experiment_id="t2", persona_id="p1", sim_day=0,
    ))
    assert len(result.results) == 3
    for v in ("openai", "gemini", "kimi"):
        assert result.results[v].status == "ok"

    # Invariant: prompt_hash same for all
    assert result.prompt_hash == prompt_hash("same prompt", "to all vendors")


def test_router_failure_no_fallback(tmp_path):
    """When a vendor fails, result should have status=error — NOT fallback to another."""
    from ctw_va.storage import db as storage_db
    storage_db.set_db_path(tmp_path / "test3.db")

    ok_client = AsyncMock()
    ok_client.chat.return_value = _mock_response("openai")
    ok_client.model_id = "gpt-4o-mini"
    ok_client.vendor_name = "openai"

    fail_client = AsyncMock()
    fail_client.chat.side_effect = RuntimeError("simulated API down")
    fail_client.model_id = "kimi-model"
    fail_client.vendor_name = "kimi"

    router = VendorRouter(clients={"openai": ok_client, "kimi": fail_client})
    result = asyncio.run(router.chat_multivendor(
        vendors=["openai", "kimi"],
        system_prompt="sys", user_prompt="user", seed=1,
        experiment_id="t3", persona_id="p1", sim_day=0,
    ))
    assert result.results["openai"].status == "ok"
    assert result.results["kimi"].status == "error"
    # Ensure NO fallback occurred (kimi.chat was called, and no fallback to openai for kimi slot)
    fail_client.chat.assert_awaited_once()


def test_budget_kill_switch(tmp_path):
    """When total_cost >= HARD_BUDGET_USD, router raises BudgetExceededError."""
    from ctw_va.storage import db as storage_db
    from ctw_va.adapter.router import BudgetExceededError

    storage_db.set_db_path(tmp_path / "test4.db")

    # Monkey-patch total_cost to return above cap
    with patch.object(storage_db, "total_cost", return_value=450.0):
        mock_client = AsyncMock()
        mock_client.chat.return_value = _mock_response("openai")
        mock_client.model_id = "gpt-4o-mini"
        mock_client.vendor_name = "openai"

        router = VendorRouter(clients={"openai": mock_client})
        with pytest.raises(BudgetExceededError):
            asyncio.run(router.chat_one(
                vendor="openai", system_prompt="sys", user_prompt="u",
                seed=1, experiment_id="t4", persona_id="p", sim_day=0,
            ))
