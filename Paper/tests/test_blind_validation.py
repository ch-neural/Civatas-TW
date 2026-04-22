"""Tests for blind-validation subset sampler + Cohen's κ agreement."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from ctw_va.refusal import blind, agreement


CSV_HEADERS = [
    "prompt_id", "vendor", "prompt_text", "response_text",
    "label", "expected", "topic", "status", "model_id",
    "cost_usd", "latency_ms", "tokens_in", "tokens_out",
    "error_detail",
]


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in CSV_HEADERS}, **r})


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _fixture_rows(n_per_cell: int = 10) -> list[dict]:
    """5 vendor × 3 expected = 15 cells; n_per_cell rows each."""
    vendors = ["openai", "gemini", "grok", "deepseek", "kimi"]
    categories = ["hard_refusal_expected", "soft_refusal_expected", "on_task_expected"]
    labels_cycle = ["hard_refusal", "soft_refusal", "on_task"]
    rows: list[dict] = []
    counter = 0
    for v in vendors:
        for cat in categories:
            for i in range(n_per_cell):
                counter += 1
                rows.append({
                    "prompt_id": f"P{counter:04d}",
                    "vendor": v,
                    "prompt_text": f"Q {counter}",
                    "response_text": f"R {counter}",
                    "label": labels_cycle[counter % 3],
                    "expected": cat,
                    "topic": "factual",
                    "status": "ok",
                })
    return rows


# ─────────────── blind.sample_blind_subset ───────────────

def test_blind_sample_basic_shape(tmp_path):
    src = tmp_path / "responses_n100.csv"
    _write_csv(src, _fixture_rows(n_per_cell=10))
    out = tmp_path / "responses_n100_blind.csv"
    r = blind.sample_blind_subset(str(src), str(out), n=30, seed=42)
    assert r["sampled"] == 30
    assert r["eligible"] == 150
    written = _read_csv(out)
    assert len(written) == 30


def test_blind_sample_labels_cleared(tmp_path):
    src = tmp_path / "responses_n50.csv"
    _write_csv(src, _fixture_rows(n_per_cell=5))
    out = tmp_path / "responses_n50_blind.csv"
    blind.sample_blind_subset(str(src), str(out), n=15, seed=1)
    for row in _read_csv(out):
        assert row["label"] == ""
        # All other data preserved
        assert row["prompt_id"].startswith("P")
        assert row["vendor"] in {"openai", "gemini", "grok", "deepseek", "kimi"}


def test_blind_sample_deterministic_with_seed(tmp_path):
    src = tmp_path / "responses_n50.csv"
    _write_csv(src, _fixture_rows(n_per_cell=5))
    out1 = tmp_path / "a_blind.csv"
    out2 = tmp_path / "b_blind.csv"
    blind.sample_blind_subset(str(src), str(out1), n=20, seed=2026)
    blind.sample_blind_subset(str(src), str(out2), n=20, seed=2026)
    rows1 = [(r["prompt_id"], r["vendor"]) for r in _read_csv(out1)]
    rows2 = [(r["prompt_id"], r["vendor"]) for r in _read_csv(out2)]
    assert rows1 == rows2


def test_blind_sample_different_seeds_differ(tmp_path):
    src = tmp_path / "responses_n50.csv"
    _write_csv(src, _fixture_rows(n_per_cell=5))
    out1 = tmp_path / "a_blind.csv"
    out2 = tmp_path / "b_blind.csv"
    blind.sample_blind_subset(str(src), str(out1), n=20, seed=1)
    blind.sample_blind_subset(str(src), str(out2), n=20, seed=999)
    rows1 = {(r["prompt_id"], r["vendor"]) for r in _read_csv(out1)}
    rows2 = {(r["prompt_id"], r["vendor"]) for r in _read_csv(out2)}
    # Very unlikely to fully overlap with different seeds
    assert rows1 != rows2


def test_blind_sample_excludes_error_and_unlabeled(tmp_path):
    src = tmp_path / "responses_n20.csv"
    _write_csv(src, [
        {"prompt_id": "A1", "vendor": "kimi", "expected": "hard_refusal_expected",
         "label": "", "status": "error"},        # un-labelable
        {"prompt_id": "A2", "vendor": "kimi", "expected": "hard_refusal_expected",
         "label": "", "status": "ok"},           # not yet labeled
        {"prompt_id": "A3", "vendor": "openai", "expected": "on_task_expected",
         "label": "on_task", "status": "ok"},
        {"prompt_id": "A4", "vendor": "openai", "expected": "on_task_expected",
         "label": "on_task", "status": "ok"},
        {"prompt_id": "A5", "vendor": "gemini", "expected": "soft_refusal_expected",
         "label": "soft_refusal", "status": "ok"},
        {"prompt_id": "A6", "vendor": "gemini", "expected": "soft_refusal_expected",
         "label": "soft_refusal", "status": "ok"},
    ])
    out = tmp_path / "x_blind.csv"
    r = blind.sample_blind_subset(str(src), str(out), n=4, seed=1)
    assert r["eligible"] == 4  # only the 4 labeled+non-error rows
    picked_ids = {row["prompt_id"] for row in _read_csv(out)}
    assert "A1" not in picked_ids and "A2" not in picked_ids


def test_blind_sample_stratification_proportional(tmp_path):
    src = tmp_path / "responses_n150.csv"
    _write_csv(src, _fixture_rows(n_per_cell=10))  # 150 rows, balanced
    out = tmp_path / "responses_n150_blind.csv"
    r = blind.sample_blind_subset(str(src), str(out), n=45, seed=3)
    # 15 cells of equal size, n=45 → 3 per cell exactly
    assert r["sampled"] == 45
    for cell, count in r["by_stratum"].items():
        assert count == 3, f"stratum {cell} got {count}, expected 3"


def test_blind_sample_n_too_large_raises(tmp_path):
    src = tmp_path / "responses_n10.csv"
    _write_csv(src, [
        {"prompt_id": f"P{i}", "vendor": "kimi", "expected": "hard_refusal_expected",
         "label": "hard_refusal", "status": "ok"} for i in range(5)
    ])
    out = tmp_path / "x_blind.csv"
    with pytest.raises(ValueError, match="exceeds"):
        blind.sample_blind_subset(str(src), str(out), n=100, seed=1)


def test_blind_sample_bom_preserved(tmp_path):
    src = tmp_path / "responses_n15.csv"
    _write_csv(src, _fixture_rows(n_per_cell=1))
    out = tmp_path / "responses_n15_blind.csv"
    blind.sample_blind_subset(str(src), str(out), n=5, seed=1)
    # utf-8-sig writes a BOM as first 3 bytes
    assert out.read_bytes()[:3] == b"\xef\xbb\xbf"


# ─────────────── agreement.compute ───────────────

def _paired_csvs(tmp_path, pairs: list[tuple[str, str, str, str]]) -> tuple[Path, Path]:
    """Each pair = (prompt_id, vendor, primary_label, blind_label)."""
    primary_rows = []
    blind_rows = []
    for pid, vendor, p_lbl, b_lbl in pairs:
        primary_rows.append({
            "prompt_id": pid, "vendor": vendor, "label": p_lbl,
            "status": "ok", "expected": "hard_refusal_expected",
        })
        blind_rows.append({
            "prompt_id": pid, "vendor": vendor, "label": b_lbl,
            "status": "ok", "expected": "hard_refusal_expected",
        })
    p = tmp_path / "primary.csv"
    b = tmp_path / "blind.csv"
    _write_csv(p, primary_rows)
    _write_csv(b, blind_rows)
    return p, b


def test_agreement_perfect(tmp_path):
    pairs = [
        ("Q1", "openai", "hard_refusal", "hard_refusal"),
        ("Q2", "openai", "soft_refusal", "soft_refusal"),
        ("Q3", "gemini", "on_task", "on_task"),
        ("Q4", "gemini", "soft_refusal", "soft_refusal"),
        ("Q5", "grok", "on_task", "on_task"),
    ]
    p, b = _paired_csvs(tmp_path, pairs)
    r = agreement.compute(str(p), str(b))
    assert r["overall"]["kappa"] == pytest.approx(1.0)
    assert r["overall"]["observed_agreement"] == pytest.approx(1.0)
    assert r["overall"]["n"] == 5


def test_agreement_partial(tmp_path):
    # 3 hard / 3 soft / 3 on_task; flip one of each → 6/9 agreement
    pairs = [
        ("Q1", "openai", "hard_refusal", "hard_refusal"),
        ("Q2", "openai", "hard_refusal", "hard_refusal"),
        ("Q3", "openai", "hard_refusal", "soft_refusal"),  # disagreement
        ("Q4", "gemini", "soft_refusal", "soft_refusal"),
        ("Q5", "gemini", "soft_refusal", "soft_refusal"),
        ("Q6", "gemini", "soft_refusal", "on_task"),       # disagreement
        ("Q7", "grok", "on_task", "on_task"),
        ("Q8", "grok", "on_task", "on_task"),
        ("Q9", "grok", "on_task", "hard_refusal"),         # disagreement
    ]
    p, b = _paired_csvs(tmp_path, pairs)
    r = agreement.compute(str(p), str(b))
    assert r["overall"]["n"] == 9
    assert r["overall"]["observed_agreement"] == pytest.approx(6 / 9)
    assert 0 < r["overall"]["kappa"] < 1


def test_agreement_confusion_matrix(tmp_path):
    pairs = [
        ("Q1", "openai", "hard_refusal", "hard_refusal"),
        ("Q2", "openai", "hard_refusal", "soft_refusal"),
        ("Q3", "openai", "soft_refusal", "on_task"),
        ("Q4", "openai", "on_task", "on_task"),
    ]
    p, b = _paired_csvs(tmp_path, pairs)
    r = agreement.compute(str(p), str(b))
    cm = r["confusion_matrix"]["rows_primary_cols_blind"]
    assert cm["hard_refusal"]["hard_refusal"] == 1
    assert cm["hard_refusal"]["soft_refusal"] == 1
    assert cm["soft_refusal"]["on_task"] == 1
    assert cm["on_task"]["on_task"] == 1


def test_agreement_coverage_gap_reporting(tmp_path):
    # Blind has Q1 labeled, Q2 unlabeled, Q3 not in primary at all
    p = tmp_path / "primary.csv"
    b = tmp_path / "blind.csv"
    _write_csv(p, [
        {"prompt_id": "Q1", "vendor": "openai", "label": "hard_refusal", "status": "ok"},
    ])
    _write_csv(b, [
        {"prompt_id": "Q1", "vendor": "openai", "label": "hard_refusal", "status": "ok"},
        {"prompt_id": "Q2", "vendor": "openai", "label": "", "status": "ok"},
        {"prompt_id": "Q3", "vendor": "openai", "label": "on_task", "status": "ok"},
    ])
    r = agreement.compute(str(p), str(b))
    assert r["coverage"]["blind_subset_total"] == 3
    assert r["coverage"]["blind_labeled"] == 2
    assert r["coverage"]["blind_unlabeled"] == 1
    # Q3 exists in blind but not primary → missing
    assert r["coverage"]["missing_in_primary"] == 1
    # Only Q1 contributes to κ
    assert r["coverage"]["compared_pairs"] == 1


def test_agreement_degenerate_single_class_all_agree(tmp_path):
    # Both raters gave 'soft_refusal' for everything → κ undefined; we return 1.0
    pairs = [("Q1", "openai", "soft_refusal", "soft_refusal")] * 5
    # Make prompt_ids unique
    pairs = [(f"Q{i}", v, p, b) for i, (_, v, p, b) in enumerate(pairs)]
    p_path, b_path = _paired_csvs(tmp_path, pairs)
    r = agreement.compute(str(p_path), str(b_path))
    assert r["overall"]["kappa"] == pytest.approx(1.0)


def test_agreement_empty_blind_raises(tmp_path):
    p = tmp_path / "primary.csv"
    b = tmp_path / "blind.csv"
    _write_csv(p, [{"prompt_id": "Q1", "vendor": "openai", "label": "on_task", "status": "ok"}])
    _write_csv(b, [{"prompt_id": "Q1", "vendor": "openai", "label": "", "status": "ok"}])
    with pytest.raises(ValueError, match="no labeled rows"):
        agreement.compute(str(p), str(b))


def test_agreement_per_vendor(tmp_path):
    pairs = [
        # openai: 3 rows, all agree
        ("Q1", "openai", "hard_refusal", "hard_refusal"),
        ("Q2", "openai", "soft_refusal", "soft_refusal"),
        ("Q3", "openai", "on_task", "on_task"),
        # gemini: 3 rows, all disagree adjacent
        ("Q4", "gemini", "hard_refusal", "soft_refusal"),
        ("Q5", "gemini", "soft_refusal", "on_task"),
        ("Q6", "gemini", "on_task", "hard_refusal"),
    ]
    p, b = _paired_csvs(tmp_path, pairs)
    r = agreement.compute(str(p), str(b))
    assert r["per_vendor"]["openai"]["agreement_rate"] == pytest.approx(1.0)
    assert r["per_vendor"]["openai"]["kappa"] == pytest.approx(1.0)
    assert r["per_vendor"]["gemini"]["agreement_rate"] == pytest.approx(0.0)
    # κ for 100% disagreement on balanced 3-class is typically negative
    assert r["per_vendor"]["gemini"]["kappa"] < 0
