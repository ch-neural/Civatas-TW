"""Tests for the in-browser labeling backend (/api/labeling/*)."""
from __future__ import annotations

import csv
import time
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from ctw_va.webui import labeling


CSV_HEADERS = [
    "prompt_id", "vendor", "prompt_text", "response_text",
    "label", "expected", "topic", "status", "model_id",
    "cost_usd", "latency_ms", "tokens_in", "tokens_out",
    "error_detail",
]


def _make_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "responses_n3.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in CSV_HEADERS}, **r})
    return p


def _make_test_app(csv_path: Path) -> TestClient:
    """Build a FastAPI app that mounts labeling.router with a fake resolver
    that returns ``csv_path`` for any input (bypasses the real whitelist)."""
    app = FastAPI()
    labeling.configure(path_resolver=lambda rel: csv_path)
    app.include_router(labeling.router)
    return TestClient(app, raise_server_exceptions=False)


# -------- Pure helper tests --------

def test_read_csv_rows_parses_bom_and_returns_progress(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "hard_refusal",
         "expected": "hard_refusal_expected", "status": "ok"},
        {"prompt_id": "HR02", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected", "status": "ok"},
        {"prompt_id": "OT01", "vendor": "deepseek", "label": "",
         "expected": "on_task_expected", "status": "error",
         "error_detail": "timeout"},
    ])

    result = labeling._read_csv_rows(csv_path)

    assert len(result["rows"]) == 3
    assert result["rows"][0]["prompt_id"] == "HR01"
    assert result["rows"][0]["label"] == "hard_refusal"
    assert result["progress"] == {
        "total": 3, "labeled": 1, "unlabeled": 2, "inconsistent": 0,
    }
    assert result["file_mtime"] == pytest.approx(csv_path.stat().st_mtime)


def test_read_csv_rows_counts_inconsistent(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "on_task",
         "expected": "hard_refusal_expected"},
        {"prompt_id": "HR02", "vendor": "deepseek", "label": "hard_refusal",
         "expected": "hard_refusal_expected"},
    ])
    result = labeling._read_csv_rows(csv_path)
    assert result["progress"]["inconsistent"] == 1


def test_write_label_updates_in_place_preserving_bom(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected", "prompt_text": "一個問題",
         "response_text": "一個含逗號, 的回應"},
        {"prompt_id": "HR02", "vendor": "openai", "label": "",
         "expected": "hard_refusal_expected"},
    ])
    original_bytes = csv_path.read_bytes()
    assert original_bytes.startswith(b"\xef\xbb\xbf"), "precondition: BOM present"

    new_mtime = labeling._write_label(
        csv_path, prompt_id="HR01", vendor="deepseek", label="hard_refusal",
    )

    assert new_mtime > 0
    new_bytes = csv_path.read_bytes()
    assert new_bytes.startswith(b"\xef\xbb\xbf"), "BOM preserved"

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["label"] == "hard_refusal"
    assert rows[0]["response_text"] == "一個含逗號, 的回應"
    assert rows[1]["label"] == ""


def test_write_label_unknown_row_raises_400(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": ""},
    ])
    with pytest.raises(HTTPException) as exc:
        labeling._write_label(
            csv_path, prompt_id="HR99", vendor="deepseek", label="hard_refusal",
        )
    assert exc.value.status_code == 400


# -------- Endpoint tests --------

def test_load_returns_rows_and_progress(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "hard_refusal",
         "expected": "hard_refusal_expected", "status": "ok"},
        {"prompt_id": "HR02", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected", "status": "ok"},
    ])
    client = _make_test_app(csv_path)

    r = client.get("/api/labeling/load", params={"path": "fake/responses_n2.csv"})
    assert r.status_code == 200
    body = r.json()
    assert body["progress"]["total"] == 2
    assert body["progress"]["labeled"] == 1
    assert len(body["rows"]) == 2
    assert body["file_mtime"] > 0


def test_load_rejects_missing_label_column(tmp_path):
    p = tmp_path / "responses_n1.csv"
    p.write_text("\ufeffprompt_id,vendor\nHR01,deepseek\n", encoding="utf-8")
    client = _make_test_app(p)

    r = client.get("/api/labeling/load", params={"path": "fake/responses_n1.csv"})
    assert r.status_code == 400
    assert "label" in r.json()["detail"]


def test_load_rejects_bad_filename(tmp_path):
    p = tmp_path / "arbitrary.csv"
    p.write_text("\ufefflabel\n", encoding="utf-8")
    client = _make_test_app(p)

    r = client.get("/api/labeling/load", params={"path": "fake/arbitrary.csv"})
    assert r.status_code == 400
    assert "responses_n" in r.json()["detail"]


def test_set_writes_label_and_returns_new_mtime(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected"},
    ])
    client = _make_test_app(csv_path)
    load = client.get("/api/labeling/load",
                      params={"path": "fake/responses_n1.csv"}).json()

    # Small sleep so the rewrite's mtime differs from the load's stamp on
    # low-resolution filesystems.
    time.sleep(0.01)

    r = client.post("/api/labeling/set", json={
        "path": "fake/responses_n1.csv",
        "prompt_id": "HR01",
        "vendor": "deepseek",
        "label": "hard_refusal",
        "expected_file_mtime": load["file_mtime"],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["new_mtime"] >= load["file_mtime"]

    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["label"] == "hard_refusal"


def test_set_stale_mtime_returns_ok_false(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "",
         "expected": "hard_refusal_expected"},
    ])
    client = _make_test_app(csv_path)

    r = client.post("/api/labeling/set", json={
        "path": "fake/responses_n1.csv", "prompt_id": "HR01",
        "vendor": "deepseek", "label": "hard_refusal",
        "expected_file_mtime": 1.0,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["reason"] == "file_modified_externally"

    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["label"] == ""


def test_set_invalid_label_returns_400(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": ""},
    ])
    client = _make_test_app(csv_path)
    load = client.get("/api/labeling/load",
                      params={"path": "fake/responses_n1.csv"}).json()

    r = client.post("/api/labeling/set", json={
        "path": "fake/responses_n1.csv", "prompt_id": "HR01",
        "vendor": "deepseek", "label": "totally_bogus",
        "expected_file_mtime": load["file_mtime"],
    })
    assert r.status_code == 400


def test_clear_empties_label(tmp_path):
    csv_path = _make_csv(tmp_path, [
        {"prompt_id": "HR01", "vendor": "deepseek", "label": "hard_refusal",
         "expected": "hard_refusal_expected"},
    ])
    client = _make_test_app(csv_path)
    load = client.get("/api/labeling/load",
                      params={"path": "fake/responses_n1.csv"}).json()

    time.sleep(0.01)

    r = client.post("/api/labeling/clear", json={
        "path": "fake/responses_n1.csv", "prompt_id": "HR01",
        "vendor": "deepseek",
        "expected_file_mtime": load["file_mtime"],
    })
    assert r.status_code == 200
    assert r.json()["ok"] is True

    with csv_path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows[0]["label"] == ""
