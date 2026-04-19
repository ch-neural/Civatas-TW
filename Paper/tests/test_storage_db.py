import pytest

from ctw_va.adapter.client import VendorResponse
from ctw_va.storage import db as storage_db


def test_log_and_sum(tmp_path):
    storage_db.set_db_path(tmp_path / "t.db")
    response = VendorResponse(
        vendor="openai", model_id="gpt-4o-mini", status="ok",
        raw_text="hi", input_tokens=10, output_tokens=5,
        cost_usd=0.0012, latency_ms=100,
    )
    storage_db.log_vendor_call(
        call_id="c1", experiment_id="e1", persona_id="p1", sim_day=0,
        vendor="openai", model_id="gpt-4o-mini",
        articles_shown=["a1", "a2"],
        prompt_hash="h1", response=response,
    )
    assert storage_db.total_cost("e1") == 0.0012
    assert storage_db.cost_by_vendor("e1") == {"openai": 0.0012}
    assert storage_db.call_count("e1") == {"ok": 1}


def test_multiple_calls_aggregate(tmp_path):
    storage_db.set_db_path(tmp_path / "t2.db")
    for i in range(3):
        r = VendorResponse(
            vendor="kimi", model_id="kimi-k2-0905", status="ok" if i < 2 else "error",
            raw_text=f"r{i}", input_tokens=100, output_tokens=50,
            cost_usd=0.001 * (i + 1),
        )
        storage_db.log_vendor_call(
            call_id=f"c{i}", experiment_id="e2", persona_id=f"p{i}",
            sim_day=i, vendor="kimi", model_id="kimi-k2-0905",
            articles_shown=[], prompt_hash="h", response=r,
        )
    assert storage_db.total_cost("e2") == pytest.approx(0.001 + 0.002 + 0.003)
    assert storage_db.call_count("e2") == {"ok": 2, "error": 1}
