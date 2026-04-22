#!/usr/bin/env python3
"""Recompute ALL paper-relevant statistics from the final labeled CSV.

Outputs a single stdout report covering:
  A. Per-vendor distribution (hard / soft / on_task / api_blocked) + refusal %
  B. Pairwise JSD matrix on 4-class refusal distributions (Finding 1)
  C. Kimi api_blocked detailed breakdown — by topic + by expected + prompt list (Finding 2)
  D. Grok on_task gap vs median + other low-refusal evidence (Finding 3)
  E. HR→SR refusal elasticity per vendor (Finding 7)
  F. Prompt bank validity — OT baseline on_task rate, HR actual refusal rate
  G. Cross-vendor per-topic on_task rates (sovereignty vs non-sovereignty split,
     Finding 4/5 evidence for context-switching / 2-layer architecture)

Use this as the single source of truth when updating CLAUDE.md / paper drafts.
"""
from __future__ import annotations

import csv
import importlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "experiments" / "refusal_calibration" / "responses_n200.csv"

VENDORS = ["openai", "gemini", "grok", "deepseek", "kimi"]
VENDOR_DISPLAY = {v: v.capitalize() for v in VENDORS}
VENDOR_DISPLAY["openai"] = "OpenAI"
VENDOR_DISPLAY["deepseek"] = "DeepSeek"

CATEGORIES = ["hard_refusal", "soft_refusal", "on_task", "api_blocked"]


def classify(row):
    if (row.get("status") or "") == "error":
        return "api_blocked"
    return (row.get("label") or "").strip() or "unlabeled"


def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def per_vendor_counts(rows):
    out = {v: {c: 0 for c in CATEGORIES} for v in VENDORS}
    for r in rows:
        v = r.get("vendor", "")
        if v in out:
            cat = classify(r)
            if cat in out[v]:
                out[v][cat] += 1
    return out


def main():
    rows = load_rows(DEFAULT_CSV)
    counts = per_vendor_counts(rows)
    totals = {v: sum(counts[v].values()) for v in VENDORS}

    # ─────────── A. Per-vendor distribution ───────────
    print("=" * 78)
    print("A. Per-vendor response distribution (from final labeled CSV)")
    print("=" * 78)
    print(f"  {'Vendor':<10} {'n':>4}  {'Hard':>5} {'Soft':>5} {'On-Task':>7} {'API-blk':>8}  {'Refusal%':>8}")
    print("  " + "-" * 72)
    refusal_by_vendor = {}
    for v in VENDORS:
        c = counts[v]; n = totals[v]
        refusal = c["hard_refusal"] + c["soft_refusal"] + c["api_blocked"]
        rate = 100 * refusal / n
        refusal_by_vendor[v] = rate
        print(f"  {VENDOR_DISPLAY[v]:<10} {n:>4}  "
              f"{c['hard_refusal']:>5} {c['soft_refusal']:>5} "
              f"{c['on_task']:>7} {c['api_blocked']:>8}  "
              f"{rate:>7.1f}%")

    # Totals
    grand = {c: sum(counts[v][c] for v in VENDORS) for c in CATEGORIES}
    grand_n = sum(totals.values())
    print(f"  {'TOTAL':<10} {grand_n:>4}  "
          f"{grand['hard_refusal']:>5} {grand['soft_refusal']:>5} "
          f"{grand['on_task']:>7} {grand['api_blocked']:>8}")
    print(f"  Percent   ---   {_pct(grand['hard_refusal'], grand_n):>5} "
          f"{_pct(grand['soft_refusal'], grand_n):>5} "
          f"{_pct(grand['on_task'], grand_n):>7} "
          f"{_pct(grand['api_blocked'], grand_n):>8}")

    # ─────────── B. Pairwise JSD ───────────
    print()
    print("=" * 78)
    print("B. Pairwise JSD on 4-class refusal distributions (log₂, bounded [0,1])")
    print("=" * 78)
    sys.path.insert(0, str(REPO_ROOT / "src"))
    jsd_mod = importlib.import_module("ctw_va.analytics.jsd")

    print(f"  {'':<10}" + "".join(f"{VENDOR_DISPLAY[v]:>10}" for v in VENDORS))
    jsd_matrix = {}
    for vi in VENDORS:
        row = [f"  {VENDOR_DISPLAY[vi]:<10}"]
        for vj in VENDORS:
            pi = jsd_mod.counts_to_probs(counts[vi], CATEGORIES)
            pj = jsd_mod.counts_to_probs(counts[vj], CATEGORIES)
            d = jsd_mod.jsd(pi, pj)
            jsd_matrix[(vi, vj)] = d
            row.append(f"{d:>10.4f}")
        print("".join(row))

    # Headline finding 1 evidence
    print()
    print("  Finding 1 evidence — DeepSeek vs Western cluster vs Kimi:")
    pairs_to_highlight = [
        ("openai", "gemini", "Western baseline (should be ~0)"),
        ("deepseek", "openai", "DeepSeek vs Western"),
        ("deepseek", "gemini", "DeepSeek vs Western"),
        ("deepseek", "kimi", "Two 'Chinese' vendors (should be small if aligned-culture theory holds…)"),
        ("kimi", "grok", "Kimi's closest neighbor"),
    ]
    for a, b, note in pairs_to_highlight:
        print(f"    JSD({VENDOR_DISPLAY[a]} ↔ {VENDOR_DISPLAY[b]}) = {jsd_matrix[(a,b)]:.4f}   {note}")

    # ─────────── C. Kimi api_blocked detail ───────────
    print()
    print("=" * 78)
    print("C. Kimi api_blocked — full detail")
    print("=" * 78)
    kimi_rows = [r for r in rows if r["vendor"] == "kimi"]
    blocked_rows = [r for r in kimi_rows if r["status"] == "error"]
    print(f"  Total Kimi calls:                  {len(kimi_rows)}")
    print(f"  Kimi api_blocked (status=error):   {len(blocked_rows)} ({100*len(blocked_rows)/len(kimi_rows):.1f}%)")
    print()

    # By topic
    print("  By topic:")
    by_topic_total = Counter(r["topic"] for r in kimi_rows)
    by_topic_block = Counter(r["topic"] for r in blocked_rows)
    for t in sorted(by_topic_total.keys(), key=lambda x: -by_topic_block[x]/by_topic_total[x]):
        n = by_topic_total[t]; b = by_topic_block[t]
        print(f"    {t:<12} {b:>2}/{n:<3}  {100*b/n:>5.1f}%")

    # By expected
    print()
    print("  By expected category:")
    by_exp_total = Counter(r["expected"] for r in kimi_rows)
    by_exp_block = Counter(r["expected"] for r in blocked_rows)
    for e in sorted(by_exp_total.keys()):
        n = by_exp_total[e]; b = by_exp_block[e]
        print(f"    {e:<25} {b:>2}/{n:<3}  {100*b/n:>5.1f}%")

    # Specific blocked prompts (full text for paper appendix)
    print()
    print("  All 14 blocked prompts (paper appendix material):")
    for r in sorted(blocked_rows, key=lambda x: (x["expected"], x["topic"], x["prompt_id"])):
        exp_short = {"hard_refusal_expected": "HR", "soft_refusal_expected": "SR",
                     "on_task_expected": "OT"}.get(r["expected"], "?")
        print(f"    [{r['prompt_id']}] {r['topic']:>11} / {exp_short}  "
              f"{r['prompt_text']}")

    # ─────────── D. Grok / Kimi low-refusal (Finding 3) ───────────
    print()
    print("=" * 78)
    print("D. Low-refusal outliers (Finding 3)")
    print("=" * 78)
    median_refusal = sorted(refusal_by_vendor.values())[2]
    print(f"  Median refusal rate:  {median_refusal:.1f}%")
    print()
    print(f"  {'Vendor':<10} {'Refusal%':>9} {'Gap from median':>17}")
    for v in sorted(VENDORS, key=lambda x: refusal_by_vendor[x]):
        gap = refusal_by_vendor[v] - median_refusal
        sign = "+" if gap >= 0 else ""
        print(f"  {VENDOR_DISPLAY[v]:<10} {refusal_by_vendor[v]:>8.1f}%   {sign}{gap:>5.1f}pp")

    # On-task rate (as it's the intuitive counterpart)
    print()
    print("  On-task rate (% of all responses):")
    on_task_rates = {v: 100 * counts[v]["on_task"] / totals[v] for v in VENDORS}
    for v in sorted(VENDORS, key=lambda x: -on_task_rates[x]):
        print(f"    {VENDOR_DISPLAY[v]:<10} {on_task_rates[v]:>6.1f}%")

    # ─────────── E. HR→SR elasticity (Finding 7) ───────────
    print()
    print("=" * 78)
    print("E. HR → SR refusal elasticity (Finding 7)")
    print("=" * 78)
    print("  on_task rate by vendor × expected category:")
    expected_cats = ["hard_refusal_expected", "soft_refusal_expected", "on_task_expected"]
    elast = {}
    print(f"  {'Vendor':<10} {'HR ontsk%':>9} {'SR ontsk%':>9} {'OT ontsk%':>9}  "
          f"{'HR→SR Δ':>8}  {'HR→OT Δ':>8}")
    for v in VENDORS:
        rate_by_exp = {}
        for e in expected_cats:
            v_rows = [r for r in rows if r["vendor"] == v and r["expected"] == e]
            # on_task rate among NON-API-blocked + all (both interesting)
            labelable = [r for r in v_rows if r["status"] != "error"]
            if labelable:
                ot = sum(1 for r in labelable if r["label"] == "on_task") / len(labelable)
                rate_by_exp[e] = 100 * ot
            else:
                rate_by_exp[e] = float("nan")
        hr = rate_by_exp["hard_refusal_expected"]
        sr = rate_by_exp["soft_refusal_expected"]
        ot = rate_by_exp["on_task_expected"]
        elast[v] = {"hr": hr, "sr": sr, "ot": ot, "hr_to_sr": sr - hr, "hr_to_ot": ot - hr}
        print(f"  {VENDOR_DISPLAY[v]:<10} {hr:>8.1f}%  {sr:>8.1f}%  {ot:>8.1f}%  "
              f"+{sr-hr:>6.1f}pp  +{ot-hr:>6.1f}pp")

    # ─────────── F. Prompt-bank validity ───────────
    print()
    print("=" * 78)
    print("F. Prompt-bank validity (OT baseline + HR actual refusal)")
    print("=" * 78)
    by_expected = defaultdict(Counter)
    for r in rows:
        if r["status"] == "error":
            by_expected[r["expected"]]["api_blocked"] += 1
        else:
            lbl = (r["label"] or "").strip()
            if lbl:
                by_expected[r["expected"]][lbl] += 1
    for e in ["hard_refusal_expected", "soft_refusal_expected", "on_task_expected"]:
        bucket = by_expected[e]
        n = sum(bucket.values())
        if n == 0:
            continue
        print(f"  {e}  (n={n}):")
        for cat in CATEGORIES:
            print(f"    {cat:<15}  {bucket[cat]:>4}  ({100*bucket[cat]/n:>5.1f}%)")

    # ─────────── G. Per-topic on_task by vendor (sovereignty vs rest) ───────────
    print()
    print("=" * 78)
    print("G. Context switching — on_task rate per vendor × topic (Finding 4/5)")
    print("=" * 78)
    all_topics = sorted(set(r["topic"] for r in rows if r["topic"]))
    print(f"  {'Vendor':<10}" + "".join(f"{t:>10}" for t in all_topics))
    for v in VENDORS:
        row_out = [f"  {VENDOR_DISPLAY[v]:<10}"]
        for t in all_topics:
            vt_rows = [r for r in rows if r["vendor"] == v and r["topic"] == t and r["status"] != "error"]
            if vt_rows:
                ot = sum(1 for r in vt_rows if r["label"] == "on_task") / len(vt_rows)
                row_out.append(f"{100*ot:>8.1f}%")
            else:
                row_out.append(f"{'--':>10}")
        print("".join(row_out))

    # Sovereignty vs non-sovereignty gap for Kimi / DeepSeek (2-layer architecture)
    print()
    print("  Sovereignty vs non-sovereignty on_task gap (where Chinese-vendor alignment")
    print("  is most visible):")
    for v in VENDORS:
        sov_rows = [r for r in rows if r["vendor"] == v and r["topic"] == "sovereignty" and r["status"] != "error"]
        non_rows = [r for r in rows if r["vendor"] == v and r["topic"] != "sovereignty" and r["status"] != "error"]
        sov_ot = (sum(1 for r in sov_rows if r["label"] == "on_task") / len(sov_rows)) if sov_rows else float("nan")
        non_ot = (sum(1 for r in non_rows if r["label"] == "on_task") / len(non_rows)) if non_rows else float("nan")
        print(f"    {VENDOR_DISPLAY[v]:<10} sovereignty {100*sov_ot:>5.1f}%   non-sov {100*non_ot:>5.1f}%   "
              f"gap {100*(sov_ot - non_ot):>+6.1f}pp")


def _pct(x, n):
    return f"{100*x/n:.1f}" if n else "0.0"


if __name__ == "__main__":
    main()
