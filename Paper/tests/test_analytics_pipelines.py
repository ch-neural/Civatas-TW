"""End-to-end pipeline tests using a synthetic SQLite fixture."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ctw_va.analytics import pipelines
from ctw_va.storage import db as storage_db


def _seed_agent_day_vendor(db_path: Path, experiment_id: str, rows: list[dict]) -> None:
    # Trigger schema init by opening a connection through storage.db.
    storage_db.set_db_path(db_path)
    with storage_db.connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO experiment_run "
            "(experiment_id, persona_slate_id, news_pool_id, scenario, replication_seed, pipeline_version) "
            "VALUES (?, 'slate', 'pool', 'scn', 0, 'test')",
            (experiment_id,),
        )
        for r in rows:
            conn.execute(
                "INSERT OR REPLACE INTO agent_day_vendor "
                "(experiment_id, persona_id, sim_day, vendor, satisfaction, anxiety, "
                " candidate_awareness, candidate_sentiment, candidate_support, "
                " party_choice, party_lean_5, diary_text, diary_tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    experiment_id, r["persona_id"], r["sim_day"], r["vendor"],
                    r.get("satisfaction", 50), r.get("anxiety", 50),
                    "{}", "{}", "{}",
                    r["party_choice"], r["party_lean_5"],
                    "", "{}",
                ),
            )


def test_distribution_metrics_shape(tmp_path):
    db = tmp_path / "x.db"
    rows = []
    # 10 personas × 2 vendors, both with varied party_choice and party_lean_5.
    personas = [f"p{i:02d}" for i in range(10)]
    party_openai = (["DPP"] * 4 + ["KMT"] * 3 + ["TPP"] * 3)
    party_gemini = (["DPP"] * 5 + ["KMT"] * 3 + ["TPP"] * 2)
    leans = (["深綠", "偏綠", "中間", "偏藍", "深藍"] * 2)
    for i, pid in enumerate(personas):
        rows.append({
            "persona_id": pid, "sim_day": 12, "vendor": "openai",
            "party_choice": party_openai[i], "party_lean_5": leans[i],
        })
        rows.append({
            "persona_id": pid, "sim_day": 12, "vendor": "gemini",
            "party_choice": party_gemini[i], "party_lean_5": leans[i],
        })
    _seed_agent_day_vendor(db, "expX", rows)

    result = pipelines.pipeline_distribution(
        db, "expX", sim_day=12, n_resamples=200, seed=0,
    )
    assert result["n_rows"] == 20
    assert result["n_personas"] == 10
    assert set(result["vendors"]) == {"openai", "gemini"}
    # Ground-truth JSD exists for every vendor.
    assert set(result["jsd_vs_truth"].keys()) == {"openai", "gemini"}
    for v, d in result["jsd_vs_truth"].items():
        assert 0.0 <= d["value"] <= 1.0
        assert d["ci_low"] <= d["value"] + 1e-9
        assert d["value"] <= d["ci_high"] + 1e-9
    # Pairwise keys present and contain p-value + corrections.
    key = "gemini|openai"
    assert key in result["jsd_pairwise"]
    assert "p_value" in result["jsd_pairwise"][key]
    assert "p_adj_holm" in result["jsd_pairwise"][key]
    assert "p_adj_bh" in result["jsd_pairwise"][key]


def test_distribution_no_bootstrap_skips_ci(tmp_path):
    db = tmp_path / "y.db"
    rows = [
        {"persona_id": "p1", "sim_day": 0, "vendor": "openai", "party_choice": "DPP", "party_lean_5": "深綠"},
        {"persona_id": "p1", "sim_day": 0, "vendor": "kimi",   "party_choice": "KMT", "party_lean_5": "深藍"},
    ]
    _seed_agent_day_vendor(db, "expY", rows)
    result = pipelines.pipeline_distribution(db, "expY", sim_day=0, bootstrap=False)
    # No CI keys when bootstrap disabled.
    for d in result["jsd_vs_truth"].values():
        assert "ci_low" not in d


def test_write_json_creates_parent_dirs(tmp_path):
    target = tmp_path / "deep" / "nested" / "out.json"
    payload = {"x": 1, "中文": "ok"}
    pipelines.write_json(target, payload)
    assert target.exists()
    roundtrip = json.loads(target.read_text(encoding="utf-8"))
    assert roundtrip == payload
