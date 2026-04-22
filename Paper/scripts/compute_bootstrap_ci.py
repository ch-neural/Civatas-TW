#!/usr/bin/env python3
"""Bootstrap 95% BCa CIs for headline paper statistics.

Resamples **prompts** (the N=200 prompt bank), not individual rows, so the
paired-on-prompt design is respected — each prompt contributes one response
per vendor, and those 5 responses move together under resampling.

Outputs paper_figures/bootstrap_ci.json for paper § / dashboard consumption.
"""
from __future__ import annotations

import csv
import importlib
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "experiments" / "refusal_calibration" / "responses_n200.csv"
OUT_JSON = REPO_ROOT / "paper_figures" / "bootstrap_ci.json"

VENDORS = ["openai", "gemini", "grok", "deepseek", "kimi"]
CATEGORIES = ["hard_refusal", "soft_refusal", "on_task", "api_blocked"]
N_RESAMPLES = 5000   # 5k = tight enough for CI width, ~30s total


def classify(row):
    if (row.get("status") or "") == "error":
        return "api_blocked"
    return (row.get("label") or "").strip() or "unlabeled"


def main():
    sys.path.insert(0, str(REPO_ROOT / "src"))
    ctw_boot = importlib.import_module("ctw_va.analytics.bootstrap")
    ctw_jsd = importlib.import_module("ctw_va.analytics.jsd")

    with open(DEFAULT_CSV, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    # Group rows by prompt_id — each prompt is one bootstrap unit
    by_prompt: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by_prompt[r["prompt_id"]][r["vendor"]] = r

    # Only keep prompts where ALL 5 vendors responded (should be all 200)
    prompts = [
        pid for pid, vendor_map in by_prompt.items()
        if all(v in vendor_map for v in VENDORS)
    ]
    prompt_bundles = [by_prompt[pid] for pid in prompts]
    print(f"Bootstrap over {len(prompt_bundles)} prompt bundles, "
          f"{N_RESAMPLES} resamples, 95% BCa CI")

    out: dict = {"n_prompts": len(prompt_bundles), "n_resamples": N_RESAMPLES}

    # ─────────── 1. Per-vendor on_task rate ───────────
    print("\n1. Per-vendor on_task rate")
    on_task_ci = {}
    for v in VENDORS:
        def stat(bundles, vendor=v):
            rows_v = [b[vendor] for b in bundles]
            if not rows_v:
                return 0.0
            return sum(1 for r in rows_v if classify(r) == "on_task") / len(rows_v) * 100

        res = ctw_boot.paired_bootstrap(
            prompt_bundles, stat, n_resamples=N_RESAMPLES, seed=20260422,
        )
        on_task_ci[v] = res.as_dict()
        print(f"  {v:<10}  {res.estimate:>5.2f}%  [{res.ci_low:>5.2f}, {res.ci_high:>5.2f}]  "
              f"({res.method})")
    out["on_task_rate_pct"] = on_task_ci

    # ─────────── 2. Per-vendor refusal rate (hard + soft + api_blocked) ───────────
    print("\n2. Per-vendor refusal rate")
    refusal_ci = {}
    for v in VENDORS:
        def stat(bundles, vendor=v):
            rows_v = [b[vendor] for b in bundles]
            refusal = sum(1 for r in rows_v
                          if classify(r) in ("hard_refusal", "soft_refusal", "api_blocked"))
            return 100 * refusal / len(rows_v) if rows_v else 0.0

        res = ctw_boot.paired_bootstrap(
            prompt_bundles, stat, n_resamples=N_RESAMPLES, seed=20260422,
        )
        refusal_ci[v] = res.as_dict()
        print(f"  {v:<10}  {res.estimate:>5.2f}%  [{res.ci_low:>5.2f}, {res.ci_high:>5.2f}]")
    out["refusal_rate_pct"] = refusal_ci

    # ─────────── 3. Pairwise JSD ───────────
    print("\n3. Pairwise JSD on 4-class distributions")
    jsd_ci = {}
    for i, vi in enumerate(VENDORS):
        for j, vj in enumerate(VENDORS):
            if i >= j:    # only upper triangle
                continue
            key = f"{vi}__{vj}"

            def stat(bundles, va=vi, vb=vj):
                ca = {c: 0 for c in CATEGORIES}
                cb = {c: 0 for c in CATEGORIES}
                for b in bundles:
                    ca[classify(b[va])] = ca.get(classify(b[va]), 0) + 1
                    cb[classify(b[vb])] = cb.get(classify(b[vb]), 0) + 1
                pa = ctw_jsd.counts_to_probs(ca, CATEGORIES)
                pb = ctw_jsd.counts_to_probs(cb, CATEGORIES)
                return float(ctw_jsd.jsd(pa, pb))

            res = ctw_boot.paired_bootstrap(
                prompt_bundles, stat, n_resamples=N_RESAMPLES, seed=20260422,
            )
            jsd_ci[key] = res.as_dict()
            print(f"  {vi:<10} ↔ {vj:<10}  {res.estimate:.4f}  "
                  f"[{res.ci_low:.4f}, {res.ci_high:.4f}]")
    out["pairwise_jsd"] = jsd_ci

    # ─────────── 4. HR→SR elasticity (Δ on_task among labeled) ───────────
    print("\n4. HR → SR Δ on_task (labeled rows only)")
    elast_ci = {}
    for v in VENDORS:
        def stat(bundles, vendor=v):
            hr_rows = []
            sr_rows = []
            for b in bundles:
                row = b[vendor]
                if row["status"] == "error":
                    continue
                if row["expected"] == "hard_refusal_expected":
                    hr_rows.append(row)
                elif row["expected"] == "soft_refusal_expected":
                    sr_rows.append(row)
            if not hr_rows or not sr_rows:
                return 0.0
            hr_ot = sum(1 for r in hr_rows if r["label"] == "on_task") / len(hr_rows)
            sr_ot = sum(1 for r in sr_rows if r["label"] == "on_task") / len(sr_rows)
            return 100 * (sr_ot - hr_ot)

        res = ctw_boot.paired_bootstrap(
            prompt_bundles, stat, n_resamples=N_RESAMPLES, seed=20260422,
        )
        elast_ci[v] = res.as_dict()
        print(f"  {v:<10}  Δ={res.estimate:>6.2f}pp  [{res.ci_low:>6.2f}, {res.ci_high:>6.2f}]")
    out["hr_to_sr_delta_pp"] = elast_ci

    # ─────────── 5. Sovereignty on_task per vendor (Finding 5) ───────────
    print("\n5. Sovereignty-topic on_task rate (Finding 5)")
    sov_ci = {}
    for v in VENDORS:
        def stat(bundles, vendor=v):
            rows_v = [b[vendor] for b in bundles
                      if b[vendor]["topic"] == "sovereignty" and b[vendor]["status"] != "error"]
            if not rows_v:
                return 0.0
            return 100 * sum(1 for r in rows_v if r["label"] == "on_task") / len(rows_v)

        res = ctw_boot.paired_bootstrap(
            prompt_bundles, stat, n_resamples=N_RESAMPLES, seed=20260422,
        )
        sov_ci[v] = res.as_dict()
        print(f"  {v:<10}  {res.estimate:>5.2f}%  [{res.ci_low:>5.2f}, {res.ci_high:>5.2f}]")
    out["sovereignty_on_task_pct"] = sov_ci

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n✓ Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
