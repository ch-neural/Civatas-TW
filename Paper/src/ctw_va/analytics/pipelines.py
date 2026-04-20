"""Pipelines that pull experiment data from SQLite and compute metrics.

Data sources:
- ``vendor_call_log`` — raw vendor responses (refusal pipeline input)
- ``agent_day_vendor`` — per-persona per-day per-vendor state (distribution
  metrics on ``party_choice`` / ``party_lean_5``)

The pipelines are decoupled from the CLI so they can also be invoked from
tests or the webui in-process.
"""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

from . import bootstrap as bs
from . import corrections as mc
from .jsd import jsd as _jsd, party_distribution_from_choices
from .nemd import PARTY_LEAN_ORDER, lean_distribution, nemd_ordinal


# CEC 2024 official result (see CLAUDE.md Stage 1 validation).
CEC_2024_TRUTH: dict[str, float] = {
    "DPP": 0.4005,
    "KMT": 0.3349,
    "TPP": 0.2646,
}

PARTY_ORDER: list[str] = ["DPP", "KMT", "TPP", "IND", "undecided"]


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def load_final_day_rows(
    db_path: str | Path, experiment_id: str, *, sim_day: int | None = None,
) -> list[dict]:
    """Load ``agent_day_vendor`` rows for the chosen day.

    If ``sim_day`` is None, uses MAX(sim_day) per (persona, vendor) pair — i.e.
    each persona-vendor's final state.
    """
    conn = _connect(db_path)
    try:
        if sim_day is None:
            sql = """
                SELECT a.* FROM agent_day_vendor a
                JOIN (
                    SELECT persona_id, vendor, MAX(sim_day) AS max_day
                    FROM agent_day_vendor
                    WHERE experiment_id = ?
                    GROUP BY persona_id, vendor
                ) m
                  ON a.persona_id = m.persona_id
                 AND a.vendor     = m.vendor
                 AND a.sim_day    = m.max_day
                WHERE a.experiment_id = ?
            """
            cur = conn.execute(sql, (experiment_id, experiment_id))
        else:
            cur = conn.execute(
                "SELECT * FROM agent_day_vendor WHERE experiment_id = ? AND sim_day = ?",
                (experiment_id, sim_day),
            )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return rows


def load_vendor_call_rows(db_path: str | Path, experiment_id: str) -> list[dict]:
    conn = _connect(db_path)
    try:
        cur = conn.execute(
            "SELECT * FROM vendor_call_log WHERE experiment_id = ?",
            (experiment_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
    return rows


# ---------------------------------------------------------------------------
# Distribution metrics (JSD + NEMD + pairwise + vs ground truth)
# ---------------------------------------------------------------------------

def _group_by_vendor(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[str(r.get("vendor") or "unknown")].append(r)
    return dict(out)


def _party_prob_from_rows(rows: list[dict], categories: list[str]) -> np.ndarray:
    choices = [str(r.get("party_choice") or "undecided") for r in rows]
    return party_distribution_from_choices(choices, categories)


def _lean_prob_from_rows(rows: list[dict]) -> np.ndarray:
    buckets = [str(r.get("party_lean_5") or "") for r in rows]
    return lean_distribution(buckets)


def _pair_key(a: str, b: str) -> str:
    return f"{a}|{b}"


def distribution_metrics(
    rows: list[dict],
    *,
    categories: list[str] | None = None,
    confidence: float = 0.95,
    n_resamples: int = 10_000,
    seed: int = 20240113,
    bootstrap: bool = True,
) -> dict:
    """Compute party distribution, JSD-vs-truth, pairwise JSD, NEMD pairwise.

    Rows must have ``vendor``, ``persona_id``, ``party_choice`` and
    ``party_lean_5`` keys. The function is tolerant to missing values (they
    are counted as "undecided" / "" respectively).
    """
    if not rows:
        return {"n_rows": 0, "vendors": [], "error": "no rows"}

    cats = categories or PARTY_ORDER
    by_vendor = _group_by_vendor(rows)
    vendors = sorted(by_vendor.keys())

    # Per-vendor distributions (deterministic over the whole row set).
    party_dist: dict[str, dict[str, float]] = {}
    lean_dist: dict[str, dict[str, float]] = {}
    for v in vendors:
        p = _party_prob_from_rows(by_vendor[v], cats)
        l = _lean_prob_from_rows(by_vendor[v])
        party_dist[v] = dict(zip(cats, map(float, p)))
        lean_dist[v] = dict(zip(PARTY_LEAN_ORDER, map(float, l)))

    # Build (persona_id → vendor → row) so paired bootstrap resamples personas.
    personas: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        personas[str(r["persona_id"])][str(r["vendor"])] = r
    persona_ids = sorted(personas.keys())

    def _party_dist_for_vendor(persona_ids_subset, vendor):
        subset = [personas[pid][vendor] for pid in persona_ids_subset if vendor in personas[pid]]
        return _party_prob_from_rows(subset, cats)

    def _lean_dist_for_vendor(persona_ids_subset, vendor):
        subset = [personas[pid][vendor] for pid in persona_ids_subset if vendor in personas[pid]]
        return _lean_prob_from_rows(subset)

    # JSD vs CEC truth (party_choice only — DPP/KMT/TPP). Align on the 3-way
    # subset excluding undecided so the comparison is vote-share-style.
    truth_cats = list(CEC_2024_TRUTH.keys())
    truth_vec = np.asarray([CEC_2024_TRUTH[c] for c in truth_cats], dtype=float)

    def _stat_jsd_vs_truth(persona_ids_subset, vendor):
        p = _party_dist_for_vendor(persona_ids_subset, vendor)
        # Reproject onto {DPP, KMT, TPP} (drop IND / undecided).
        idx = [cats.index(c) for c in truth_cats]
        sub = p[idx]
        s = sub.sum()
        sub = sub / s if s > 0 else np.full(len(truth_cats), 1.0 / len(truth_cats))
        return _jsd(sub, truth_vec)

    jsd_vs_truth: dict[str, dict] = {}
    for v in vendors:
        if bootstrap and len(persona_ids) >= 3:
            res = bs.paired_bootstrap(
                persona_ids,
                lambda pids, v=v: _stat_jsd_vs_truth(pids, v),
                n_resamples=n_resamples, confidence=confidence, seed=seed,
            )
            jsd_vs_truth[v] = {
                "value": float(res.estimate),
                "ci_low": float(res.ci_low),
                "ci_high": float(res.ci_high),
                "ci_method": res.method,
            }
        else:
            jsd_vs_truth[v] = {"value": float(_stat_jsd_vs_truth(persona_ids, v))}

    # Pairwise JSD + NEMD (+ optional CI). Both metrics share the same paired
    # bootstrap: resample personas once per pair.
    def _stat_jsd_pair(persona_ids_subset, v1, v2):
        p = _party_dist_for_vendor(persona_ids_subset, v1)
        q = _party_dist_for_vendor(persona_ids_subset, v2)
        return _jsd(p, q)

    def _stat_nemd_pair(persona_ids_subset, v1, v2):
        p = _lean_dist_for_vendor(persona_ids_subset, v1)
        q = _lean_dist_for_vendor(persona_ids_subset, v2)
        return nemd_ordinal(p, q)

    jsd_pairwise: dict[str, dict] = {}
    nemd_pairwise: dict[str, dict] = {}
    raw_jsd_estimates: list[tuple[str, str, float]] = []
    raw_nemd_estimates: list[tuple[str, str, float]] = []

    for i, v1 in enumerate(vendors):
        for v2 in vendors[i + 1:]:
            key = _pair_key(v1, v2)
            if bootstrap and len(persona_ids) >= 3:
                res_j = bs.paired_bootstrap(
                    persona_ids,
                    lambda pids, v1=v1, v2=v2: _stat_jsd_pair(pids, v1, v2),
                    n_resamples=n_resamples, confidence=confidence, seed=seed,
                )
                res_n = bs.paired_bootstrap(
                    persona_ids,
                    lambda pids, v1=v1, v2=v2: _stat_nemd_pair(pids, v1, v2),
                    n_resamples=n_resamples, confidence=confidence, seed=seed,
                )
                # Two-sided p-value against H0: metric == 0 via bootstrap CDF.
                # (Since metric ≥ 0, this is a conservative upper bound.)
                p_j = float(np.mean(res_j.samples <= 0.0)) * 2
                p_n = float(np.mean(res_n.samples <= 0.0)) * 2
                p_j = min(max(p_j, 1e-6), 1.0)
                p_n = min(max(p_n, 1e-6), 1.0)
                jsd_pairwise[key] = {
                    "value": float(res_j.estimate),
                    "ci_low": float(res_j.ci_low),
                    "ci_high": float(res_j.ci_high),
                    "ci_method": res_j.method,
                    "p_value": p_j,
                }
                nemd_pairwise[key] = {
                    "value": float(res_n.estimate),
                    "ci_low": float(res_n.ci_low),
                    "ci_high": float(res_n.ci_high),
                    "ci_method": res_n.method,
                    "p_value": p_n,
                }
                raw_jsd_estimates.append((v1, v2, p_j))
                raw_nemd_estimates.append((v1, v2, p_n))
            else:
                jsd_pairwise[key] = {"value": float(_stat_jsd_pair(persona_ids, v1, v2))}
                nemd_pairwise[key] = {"value": float(_stat_nemd_pair(persona_ids, v1, v2))}

    # Multiple-testing corrections on the pairwise p-values.
    if raw_jsd_estimates:
        pvals = np.asarray([p for _, _, p in raw_jsd_estimates])
        holm = mc.holm_bonferroni(pvals)
        bh = mc.benjamini_hochberg(pvals)
        for (v1, v2, _), h, b_ in zip(raw_jsd_estimates, holm, bh):
            jsd_pairwise[_pair_key(v1, v2)]["p_adj_holm"] = float(h)
            jsd_pairwise[_pair_key(v1, v2)]["p_adj_bh"] = float(b_)
    if raw_nemd_estimates:
        pvals = np.asarray([p for _, _, p in raw_nemd_estimates])
        holm = mc.holm_bonferroni(pvals)
        bh = mc.benjamini_hochberg(pvals)
        for (v1, v2, _), h, b_ in zip(raw_nemd_estimates, holm, bh):
            nemd_pairwise[_pair_key(v1, v2)]["p_adj_holm"] = float(h)
            nemd_pairwise[_pair_key(v1, v2)]["p_adj_bh"] = float(b_)

    return {
        "n_rows": len(rows),
        "n_personas": len(persona_ids),
        "vendors": vendors,
        "party_categories": cats,
        "lean_categories": list(PARTY_LEAN_ORDER),
        "party_distribution": party_dist,
        "lean_distribution": lean_dist,
        "ground_truth": dict(CEC_2024_TRUTH),
        "jsd_vs_truth": jsd_vs_truth,
        "jsd_pairwise": jsd_pairwise,
        "nemd_pairwise": nemd_pairwise,
        "config": {
            "confidence": confidence,
            "n_resamples": n_resamples if bootstrap else 0,
            "seed": seed,
            "bootstrap": bootstrap,
        },
    }


# ---------------------------------------------------------------------------
# Orchestrator helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def write_json(path: str | Path, payload: dict) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return p


def pipeline_distribution(
    db_path: str | Path, experiment_id: str, *, sim_day: int | None = None,
    confidence: float = 0.95, n_resamples: int = 10_000, seed: int = 20240113,
    bootstrap: bool = True,
) -> dict:
    rows = load_final_day_rows(db_path, experiment_id, sim_day=sim_day)
    result = distribution_metrics(
        rows, confidence=confidence, n_resamples=n_resamples, seed=seed,
        bootstrap=bootstrap,
    )
    result["experiment_id"] = experiment_id
    result["db_path"] = str(db_path)
    result["sim_day"] = sim_day  # None → final per (persona, vendor)
    result["computed_at"] = now_iso()
    return result


def pipeline_refusal(
    *, classifier_path: str | Path,
    db_path: str | Path | None = None, experiment_id: str | None = None,
    labeled_path: str | Path | None = None,
) -> dict:
    """Apply the classifier either to DB responses or to a labelled JSONL."""
    from .refusal import RefusalClassifier, classify_rows, load_labeled_jsonl

    clf = RefusalClassifier.load(classifier_path)

    rows: list[dict]
    if labeled_path is not None:
        rows = load_labeled_jsonl(labeled_path)
        for r in rows:
            # calibration JSONL uses "response_text"; keep as-is.
            r.setdefault("response_text", r.get("response_raw") or "")
        source = f"labeled_jsonl:{labeled_path}"
    elif db_path is not None and experiment_id is not None:
        raw = load_vendor_call_rows(db_path, experiment_id)
        rows = []
        for r in raw:
            rows.append({
                "vendor": r.get("vendor"),
                "response_text": r.get("response_raw") or "",
                # vendor_call_log has no topic column; refusal-by-topic only
                # works on calibration data.
                "topic": None,
                "persona_id": r.get("persona_id"),
            })
        source = f"db:{db_path}#{experiment_id}"
    else:
        raise ValueError("provide either labeled_path, or (db_path + experiment_id)")

    result = classify_rows(rows, clf)
    result["source"] = source
    result["classifier_path"] = str(classifier_path)
    result["classifier_meta"] = {
        "train_size": clf.train_size,
        "test_accuracy": clf.test_accuracy,
        "test_macro_f1": clf.test_macro_f1,
        "labels": list(clf.labels),
    }
    result["computed_at"] = now_iso()
    return result
