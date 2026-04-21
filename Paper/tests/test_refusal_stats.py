"""Tests for `calibration stats` stat computation (refusal/stats.py)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ctw_va.refusal import stats


CSV_HEADERS = [
    "prompt_id", "vendor", "prompt_text", "response_text",
    "label", "expected", "topic", "status", "model_id",
    "cost_usd", "latency_ms", "tokens_in", "tokens_out",
    "error_detail",
]


def _make_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in CSV_HEADERS}, **r})


def _make_sidecar(path: Path, entries: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def test_empty_csv(tmp_path):
    p = tmp_path / "responses_n0.csv"
    _make_csv(p, [])
    s = stats.compute(str(p))
    assert s["total"] == 0
    assert s["errors"] == 0
    assert s["labelable"] == 0
    assert s["labeled"] == 0
    assert s["unlabeled"] == 0
    assert s["by_label"] == {"hard_refusal": 0, "soft_refusal": 0, "on_task": 0}
    assert s["ai"] is None  # sidecar not present


def test_counts_and_labels(tmp_path):
    p = tmp_path / "responses_n3.csv"
    _make_csv(p, [
        {"prompt_id": "HR01", "vendor": "openai", "expected": "hard_refusal_expected",
         "status": "ok", "label": "soft_refusal"},
        {"prompt_id": "HR01", "vendor": "gemini", "expected": "hard_refusal_expected",
         "status": "ok", "label": "hard_refusal"},
        {"prompt_id": "HR01", "vendor": "kimi", "expected": "hard_refusal_expected",
         "status": "error", "error_detail": "ContentFilterError"},
        {"prompt_id": "OT01", "vendor": "openai", "expected": "on_task_expected",
         "status": "ok", "label": "on_task"},
        {"prompt_id": "OT01", "vendor": "gemini", "expected": "on_task_expected",
         "status": "ok", "label": ""},  # unlabeled
    ])
    s = stats.compute(str(p))
    assert s["total"] == 5
    assert s["errors"] == 1
    assert s["labelable"] == 4
    assert s["labeled"] == 3
    assert s["unlabeled"] == 1
    assert s["by_label"] == {"hard_refusal": 1, "soft_refusal": 1, "on_task": 1}


def test_invalid_label_is_not_counted(tmp_path):
    p = tmp_path / "responses_n1.csv"
    _make_csv(p, [
        {"prompt_id": "X1", "vendor": "openai", "status": "ok", "label": "wrong_label"},
        {"prompt_id": "X2", "vendor": "openai", "status": "ok", "label": "on_task"},
    ])
    s = stats.compute(str(p))
    assert s["labeled"] == 1
    assert s["invalid_labels"] == 1


def test_by_vendor_breakdown(tmp_path):
    p = tmp_path / "responses.csv"
    _make_csv(p, [
        {"prompt_id": "A", "vendor": "openai", "status": "ok", "label": "soft_refusal"},
        {"prompt_id": "B", "vendor": "openai", "status": "ok", "label": "on_task"},
        {"prompt_id": "A", "vendor": "kimi", "status": "error"},
        {"prompt_id": "B", "vendor": "kimi", "status": "ok", "label": ""},
    ])
    s = stats.compute(str(p))
    bv = s["by_vendor"]
    assert bv["openai"]["total"] == 2
    assert bv["openai"]["labeled"] == 2
    assert bv["openai"]["errors"] == 0
    assert bv["kimi"]["total"] == 2
    assert bv["kimi"]["labeled"] == 0
    assert bv["kimi"]["errors"] == 1
    # unlabeled = total - errors - labeled
    assert bv["kimi"]["unlabeled"] == 1


def test_by_expected_category(tmp_path):
    p = tmp_path / "responses.csv"
    _make_csv(p, [
        {"prompt_id": "HR01", "vendor": "o", "status": "ok",
         "expected": "hard_refusal_expected", "label": "hard_refusal"},
        {"prompt_id": "HR01", "vendor": "g", "status": "ok",
         "expected": "hard_refusal_expected", "label": "soft_refusal"},
        {"prompt_id": "SR01", "vendor": "o", "status": "ok",
         "expected": "soft_refusal_expected", "label": "soft_refusal"},
        {"prompt_id": "OT01", "vendor": "o", "status": "ok",
         "expected": "on_task_expected", "label": "on_task"},
    ])
    s = stats.compute(str(p))
    be = s["by_expected"]
    assert be["hard_refusal_expected"]["total"] == 2
    assert be["hard_refusal_expected"]["labeled"] == 2
    assert be["hard_refusal_expected"]["by_label"]["hard_refusal"] == 1
    assert be["hard_refusal_expected"]["by_label"]["soft_refusal"] == 1
    assert be["soft_refusal_expected"]["labeled"] == 1
    assert be["on_task_expected"]["labeled"] == 1


def test_ai_sidecar_overlap(tmp_path):
    p = tmp_path / "responses_n3.csv"
    _make_csv(p, [
        # human labeled + AI cached (match)
        {"prompt_id": "A", "vendor": "openai", "status": "ok", "label": "soft_refusal"},
        # human labeled + AI cached (disagree)
        {"prompt_id": "A", "vendor": "gemini", "status": "ok", "label": "soft_refusal"},
        # human labeled only (no AI)
        {"prompt_id": "B", "vendor": "openai", "status": "ok", "label": "on_task"},
        # AI only (no human label)
        {"prompt_id": "C", "vendor": "openai", "status": "ok", "label": ""},
    ])
    sc = p.with_suffix("").with_suffix(".ai_suggest.jsonl")
    _make_sidecar(sc, [
        {"prompt_id": "A", "vendor": "openai", "label": "soft_refusal"},  # agree
        {"prompt_id": "A", "vendor": "gemini", "label": "hard_refusal"},  # disagree
        {"prompt_id": "C", "vendor": "openai", "label": "on_task"},        # ai-only
    ])
    s = stats.compute(str(p))
    ai = s["ai"]
    assert ai is not None
    assert ai["total_entries"] == 3
    assert ai["overlap"] == 2       # rows where both human+AI labeled
    assert ai["human_only"] == 1    # B/openai
    assert ai["ai_only"] == 1       # C/openai
    assert ai["agree"] == 1
    assert ai["disagree"] == 1


def test_ai_sidecar_latest_wins(tmp_path):
    """Multiple entries for same (pid, vendor) — latest line wins."""
    p = tmp_path / "responses.csv"
    _make_csv(p, [
        {"prompt_id": "A", "vendor": "openai", "status": "ok", "label": "hard_refusal"},
    ])
    sc = p.with_suffix("").with_suffix(".ai_suggest.jsonl")
    _make_sidecar(sc, [
        {"prompt_id": "A", "vendor": "openai", "label": "soft_refusal"},  # earlier
        {"prompt_id": "A", "vendor": "openai", "label": "hard_refusal"},  # latest → agree
    ])
    s = stats.compute(str(p))
    assert s["ai"]["overlap"] == 1
    assert s["ai"]["agree"] == 1
    assert s["ai"]["disagree"] == 0


def test_explicit_sidecar_path(tmp_path):
    p = tmp_path / "responses.csv"
    _make_csv(p, [
        {"prompt_id": "A", "vendor": "o", "status": "ok", "label": "on_task"},
    ])
    sc = tmp_path / "custom_location.jsonl"
    _make_sidecar(sc, [{"prompt_id": "A", "vendor": "o", "label": "on_task"}])
    s = stats.compute(str(p), sidecar_path=str(sc))
    assert s["ai"]["total_entries"] == 1
    assert s["ai"]["agree"] == 1


def test_missing_sidecar_ok(tmp_path):
    p = tmp_path / "responses.csv"
    _make_csv(p, [{"prompt_id": "A", "vendor": "o", "status": "ok", "label": "on_task"}])
    s = stats.compute(str(p))
    assert s["ai"] is None


def test_format_text_human_readable(tmp_path):
    p = tmp_path / "responses_n2.csv"
    _make_csv(p, [
        {"prompt_id": "A", "vendor": "openai", "status": "ok",
         "expected": "hard_refusal_expected", "label": "soft_refusal"},
        {"prompt_id": "A", "vendor": "kimi", "status": "error"},
    ])
    s = stats.compute(str(p))
    text = stats.format_text(s, csv_path=str(p))
    assert "Total rows" in text
    assert "soft_refusal" in text
    assert "kimi" in text
