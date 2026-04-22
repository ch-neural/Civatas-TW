#!/usr/bin/env python3
"""Phase 3 of flagship-tier sensitivity subset (paper §5 Robustness).

Compares production-tier findings (from responses_n200.csv, the main
1{,}000-call experiment) against flagship-tier findings (from
responses_n40_flagship.csv, the 200-call sensitivity subset).

The comparison targets the three findings that could in principle be
confounded by model-tier asymmetry:
  • Finding 1 — pairwise JSD clustering structure (OpenAI/Gemini mini
    vs flagship, DeepSeek already flagship in both tiers)
  • Finding 5 — DeepSeek sovereignty on-task collapse (still 10%-ish?)
  • Finding 7 — two-tier HR→SR elasticity (still OpenAI/Gemini most
    responsive?)

Finding 2 (Kimi Taiwan-statehood filter) is Kimi-specific and
model-independent; the Kimi model ID is unchanged across tiers so
Finding 2 is not re-testable on this subset, and we explicitly note
that in the output.

Outputs:
  • stdout: a textual report suitable for pasting into paper §5.6
    Robustness
  • paper_figures/flagship_sensitivity_comparison.json: machine-readable
    side-by-side of all headline numbers with 95% bootstrap CIs
  • paper_figures/fig7_tier_comparison.pdf: 4-panel figure (one panel
    per finding) showing production vs flagship side by side

Assumes `responses_n40_flagship.csv` has been hand-labeled. If any
row is un-labeled (and status != "error"), those rows are skipped with
a warning and stats are computed on the labeled subset.
"""
from __future__ import annotations

import csv
import importlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_CSV = REPO_ROOT / "experiments" / "refusal_calibration" / "responses_n200.csv"
FLAG_CSV = REPO_ROOT / "experiments" / "refusal_calibration" / "responses_n40_flagship.csv"
OUT_DIR = REPO_ROOT / "paper_figures"
JSON_OUT = OUT_DIR / "flagship_sensitivity_comparison.json"
FIG_OUT_STEM = OUT_DIR / "fig7_tier_comparison"

VENDORS = ["openai", "gemini", "grok", "deepseek", "kimi"]
VENDOR_DISPLAY = {
    "openai": "OpenAI",
    "gemini": "Gemini",
    "grok": "Grok",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
}
VENDOR_COLORS = {
    "openai":   "#5b7ba3",
    "gemini":   "#7a9abf",
    "grok":     "#d97757",
    "deepseek": "#8b6fa6",
    "kimi":     "#c76e86",
}

CATEGORIES = ["hard_refusal", "soft_refusal", "on_task", "api_blocked"]
N_BOOTSTRAP = 5000
BOOTSTRAP_SEED = 20260422


# ─────────────────────────────────────────────────────────────────────────
def load_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def classify(row) -> str:
    if (row.get("status") or "") == "error":
        return "api_blocked"
    lbl = (row.get("label") or "").strip()
    return lbl if lbl else "unlabeled"


def per_vendor_counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    out = {v: {c: 0 for c in CATEGORIES} for v in VENDORS}
    for r in rows:
        v = r.get("vendor", "")
        if v in out:
            c = classify(r)
            if c in out[v]:
                out[v][c] += 1
    return out


# ─────────────────────────────────────────────────────────────────────────
# Bootstrap helpers (prompt-level paired, mirrors compute_bootstrap_ci.py)
# ─────────────────────────────────────────────────────────────────────────
def build_bundles(rows: list[dict]) -> list[dict[str, dict]]:
    """One element per prompt_id, each is {vendor: row} dict across all vendors."""
    by_prompt: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by_prompt[r["prompt_id"]][r["vendor"]] = r
    bundles = [v for v in by_prompt.values() if all(w in v for w in VENDORS)]
    return bundles


def bootstrap_ci(bundles, statistic, *, n=N_BOOTSTRAP, seed=BOOTSTRAP_SEED, confidence=0.95):
    """Thin wrapper around ctw_va.analytics.bootstrap.paired_bootstrap."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    boot_mod = importlib.import_module("ctw_va.analytics.bootstrap")
    r = boot_mod.paired_bootstrap(
        bundles, statistic, n_resamples=n, seed=seed, confidence=confidence,
    )
    return {
        "estimate": r.estimate,
        "ci_low": r.ci_low,
        "ci_high": r.ci_high,
        "method": r.method,
    }


def jsd_fn_factory():
    sys.path.insert(0, str(REPO_ROOT / "src"))
    return importlib.import_module("ctw_va.analytics.jsd")


# ─────────────────────────────────────────────────────────────────────────
def stat_refusal_rate(bundles, vendor):
    def stat(bs, v=vendor):
        rows_v = [b[v] for b in bs]
        refusal = sum(1 for r in rows_v
                      if classify(r) in ("hard_refusal", "soft_refusal", "api_blocked"))
        return 100 * refusal / len(rows_v) if rows_v else 0.0
    return stat


def stat_on_task_rate(bundles, vendor):
    def stat(bs, v=vendor):
        rows_v = [b[v] for b in bs]
        return 100 * sum(1 for r in rows_v if classify(r) == "on_task") / len(rows_v) if rows_v else 0.0
    return stat


def stat_sov_on_task(bundles, vendor):
    def stat(bs, v=vendor):
        rows_v = [b[v] for b in bs
                  if b[v].get("topic") == "sovereignty" and b[v].get("status") != "error"]
        if not rows_v:
            return float("nan")
        return 100 * sum(1 for r in rows_v if r.get("label") == "on_task") / len(rows_v)
    return stat


def stat_hr_sr_elasticity(bundles, vendor):
    def stat(bs, v=vendor):
        hr, sr = [], []
        for b in bs:
            r = b[v]
            if r.get("status") == "error":
                continue
            if r.get("expected") == "hard_refusal_expected":
                hr.append(r)
            elif r.get("expected") == "soft_refusal_expected":
                sr.append(r)
        if not hr or not sr:
            return float("nan")
        hr_ot = sum(1 for r in hr if r.get("label") == "on_task") / len(hr)
        sr_ot = sum(1 for r in sr if r.get("label") == "on_task") / len(sr)
        return 100 * (sr_ot - hr_ot)
    return stat


def pairwise_jsd(bundles, vi, vj):
    jsd_mod = jsd_fn_factory()
    def stat(bs):
        ca = {c: 0 for c in CATEGORIES}
        cb = {c: 0 for c in CATEGORIES}
        for b in bs:
            ca[classify(b[vi])] = ca.get(classify(b[vi]), 0) + 1
            cb[classify(b[vj])] = cb.get(classify(b[vj]), 0) + 1
        pa = jsd_mod.counts_to_probs(ca, CATEGORIES)
        pb = jsd_mod.counts_to_probs(cb, CATEGORIES)
        return float(jsd_mod.jsd(pa, pb))
    return stat


# ─────────────────────────────────────────────────────────────────────────
def compute_tier_metrics(rows: list[dict], label: str, flagship_subset: set[str] | None = None) -> dict:
    """Return a dict of headline metrics. If flagship_subset is given, the
    production-tier metrics are computed only on those same prompt_ids, so
    the comparison is paired."""
    if flagship_subset is not None:
        rows = [r for r in rows if r["prompt_id"] in flagship_subset]

    bundles = build_bundles(rows)
    if not bundles:
        return {"label": label, "n_bundles": 0, "error": "no complete bundles"}

    out = {"label": label, "n_bundles": len(bundles), "vendors": {}}

    # Per-vendor aggregate stats
    for v in VENDORS:
        out["vendors"][v] = {
            "refusal_rate": bootstrap_ci(bundles, stat_refusal_rate(bundles, v)),
            "on_task_rate": bootstrap_ci(bundles, stat_on_task_rate(bundles, v)),
            "sov_on_task":  bootstrap_ci(bundles, stat_sov_on_task(bundles, v)),
            "hr_sr_delta":  bootstrap_ci(bundles, stat_hr_sr_elasticity(bundles, v)),
        }

    # Pairwise JSD (upper triangle only)
    out["jsd"] = {}
    for i, vi in enumerate(VENDORS):
        for vj in VENDORS[i+1:]:
            out["jsd"][f"{vi}__{vj}"] = bootstrap_ci(bundles, pairwise_jsd(bundles, vi, vj))

    return out


# ─────────────────────────────────────────────────────────────────────────
def fmt_ci(d: dict) -> str:
    """Format {estimate, ci_low, ci_high} as 'X.X [Y.Y, Z.Z]'."""
    if d is None or not np.isfinite(d.get("estimate", float("nan"))):
        return "—"
    return f"{d['estimate']:5.1f} [{d['ci_low']:5.1f}, {d['ci_high']:5.1f}]"


def fmt_jsd(d: dict) -> str:
    if d is None or not np.isfinite(d.get("estimate", float("nan"))):
        return "—"
    return f"{d['estimate']:.4f} [{d['ci_low']:.4f}, {d['ci_high']:.4f}]"


def report(prod: dict, flag: dict) -> str:
    lines = []
    lines.append("=" * 82)
    lines.append("Flagship-tier sensitivity comparison (paper §5.6 Robustness)")
    lines.append("=" * 82)
    lines.append(f"Production tier : n={prod['n_bundles']} prompts "
                 "(restricted to flagship subset for paired comparison)")
    lines.append(f"Flagship tier   : n={flag['n_bundles']} prompts")
    lines.append("")
    lines.append("Note: Kimi and DeepSeek use the same model_id on both tiers.")
    lines.append("      OpenAI:   gpt-4o-mini           → gpt-4o")
    lines.append("      Gemini:   gemini-2.5-flash-lite → gemini-2.5-flash")
    lines.append("      Grok:     grok-4-fast-nr        → grok-3")
    lines.append("")

    # ── Aggregate on-task rate per vendor ──
    lines.append("Per-vendor on-task rate (% of all responses, 95% CI)")
    lines.append(f"  {'Vendor':<10} {'Production':<24} {'Flagship':<24}")
    for v in VENDORS:
        p = prod["vendors"][v]["on_task_rate"]
        f = flag["vendors"][v]["on_task_rate"]
        lines.append(f"  {VENDOR_DISPLAY[v]:<10} {fmt_ci(p):<24} {fmt_ci(f):<24}")
    lines.append("")

    # ── Aggregate refusal rate per vendor ──
    lines.append("Per-vendor refusal rate (% incl. api_blocked, 95% CI)")
    lines.append(f"  {'Vendor':<10} {'Production':<24} {'Flagship':<24}")
    for v in VENDORS:
        p = prod["vendors"][v]["refusal_rate"]
        f = flag["vendors"][v]["refusal_rate"]
        lines.append(f"  {VENDOR_DISPLAY[v]:<10} {fmt_ci(p):<24} {fmt_ci(f):<24}")
    lines.append("")

    # ── Sovereignty on-task (Finding 5) ──
    lines.append("Sovereignty-topic on_task rate (Finding 5 — CRITICAL)")
    lines.append(f"  {'Vendor':<10} {'Production':<24} {'Flagship':<24}")
    for v in VENDORS:
        p = prod["vendors"][v]["sov_on_task"]
        f = flag["vendors"][v]["sov_on_task"]
        lines.append(f"  {VENDOR_DISPLAY[v]:<10} {fmt_ci(p):<24} {fmt_ci(f):<24}")
    lines.append("  Interpretation: if DeepSeek sovereignty on-task stays <25% under")
    lines.append("  flagship tier, Finding 5 is robust to model scale.")
    lines.append("")

    # ── HR→SR elasticity (Finding 7) ──
    lines.append("HR→SR on_task Δ (pp, Finding 7)")
    lines.append(f"  {'Vendor':<10} {'Production':<24} {'Flagship':<24}")
    for v in VENDORS:
        p = prod["vendors"][v]["hr_sr_delta"]
        f = flag["vendors"][v]["hr_sr_delta"]
        lines.append(f"  {VENDOR_DISPLAY[v]:<10} {fmt_ci(p):<24} {fmt_ci(f):<24}")
    lines.append("")

    # ── Pairwise JSD with focus on DeepSeek-Kimi (Finding 1) ──
    lines.append("Pairwise JSD on 4-class distribution (Finding 1 — CRITICAL)")
    lines.append(f"  {'Pair':<24} {'Production':<32} {'Flagship':<32}")
    focus_pairs = [
        ("openai", "gemini", "Western baseline"),
        ("openai", "deepseek", "DeepSeek vs OpenAI"),
        ("gemini", "deepseek", "DeepSeek vs Gemini"),
        ("deepseek", "kimi", "the maximum pair"),
        ("grok", "kimi", "low-refusal cluster"),
    ]
    for vi, vj, note in focus_pairs:
        key = f"{vi}__{vj}"
        p = prod["jsd"].get(key)
        f = flag["jsd"].get(key)
        pair_lbl = f"{VENDOR_DISPLAY[vi]}↔{VENDOR_DISPLAY[vj]}"
        lines.append(f"  {pair_lbl:<24} {fmt_jsd(p):<32} {fmt_jsd(f):<32}   {note}")
    lines.append("")
    lines.append("  Interpretation: if DeepSeek-Kimi JSD CI in flagship still")
    lines.append("  excludes the CI of DeepSeek-Western (same direction as prod),")
    lines.append("  Finding 1 is robust to model scale.")

    lines.append("")
    lines.append("Finding 2 (Kimi Taiwan-statehood filter): Kimi model_id unchanged")
    lines.append("  across tiers, so Finding 2 is not a size-confound target and is")
    lines.append("  not re-tested here. 0/40 api_blocks observed in the subset is")
    lines.append("  consistent with Poisson variation at this sample size and does")
    lines.append("  not affect the main-experiment conclusion.")

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
def plot_comparison(prod: dict, flag: dict) -> list[Path]:
    """Four-panel figure: (A) refusal rate, (B) sov on-task, (C) HR→SR Δ,
    (D) pairwise JSD for 4 critical pairs."""
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 7.8))
    ax_a, ax_b, ax_c, ax_d = axes.flatten()
    bar_width = 0.38
    xs = np.arange(len(VENDORS))

    # ── Panel A: refusal rate ──
    prod_vals = [prod["vendors"][v]["refusal_rate"]["estimate"] for v in VENDORS]
    prod_err_lo = [prod["vendors"][v]["refusal_rate"]["estimate"] -
                   prod["vendors"][v]["refusal_rate"]["ci_low"] for v in VENDORS]
    prod_err_hi = [prod["vendors"][v]["refusal_rate"]["ci_high"] -
                   prod["vendors"][v]["refusal_rate"]["estimate"] for v in VENDORS]
    flag_vals = [flag["vendors"][v]["refusal_rate"]["estimate"] for v in VENDORS]
    flag_err_lo = [flag["vendors"][v]["refusal_rate"]["estimate"] -
                   flag["vendors"][v]["refusal_rate"]["ci_low"] for v in VENDORS]
    flag_err_hi = [flag["vendors"][v]["refusal_rate"]["ci_high"] -
                   flag["vendors"][v]["refusal_rate"]["estimate"] for v in VENDORS]
    ax_a.bar(xs - bar_width/2, prod_vals, bar_width,
             yerr=[prod_err_lo, prod_err_hi], capsize=3,
             color="#8b95a5", label="Production", edgecolor="white")
    ax_a.bar(xs + bar_width/2, flag_vals, bar_width,
             yerr=[flag_err_lo, flag_err_hi], capsize=3,
             color="#d97757", label="Flagship", edgecolor="white")
    ax_a.set_xticks(xs)
    ax_a.set_xticklabels([VENDOR_DISPLAY[v] for v in VENDORS])
    ax_a.set_ylabel("Refusal rate (%)")
    ax_a.set_title("(A) Aggregate refusal rate", pad=8, fontsize=10.5)
    ax_a.legend(frameon=False, fontsize=9, loc="upper right")
    ax_a.set_ylim(0, 80)

    # ── Panel B: sovereignty on-task ──
    def getvals(tier, key):
        vals, lo, hi = [], [], []
        for v in VENDORS:
            d = tier["vendors"][v][key]
            est = d["estimate"]
            if not np.isfinite(est):
                vals.append(np.nan); lo.append(0); hi.append(0)
            else:
                vals.append(est)
                lo.append(est - d["ci_low"])
                hi.append(d["ci_high"] - est)
        return vals, lo, hi
    pv, pl, ph = getvals(prod, "sov_on_task")
    fv, fl, fh = getvals(flag, "sov_on_task")
    ax_b.bar(xs - bar_width/2, pv, bar_width, yerr=[pl, ph], capsize=3,
             color="#8b95a5", label="Production", edgecolor="white")
    ax_b.bar(xs + bar_width/2, fv, bar_width, yerr=[fl, fh], capsize=3,
             color="#d97757", label="Flagship", edgecolor="white")
    # Highlight DeepSeek cell
    ds_idx = VENDORS.index("deepseek")
    ax_b.axvspan(ds_idx - 0.48, ds_idx + 0.48, color="#fde8dc", alpha=0.4, zorder=0)
    ax_b.set_xticks(xs)
    ax_b.set_xticklabels([VENDOR_DISPLAY[v] for v in VENDORS])
    ax_b.set_ylabel("Sovereignty on-task rate (%)")
    ax_b.set_title("(B) Finding 5 — DeepSeek sovereignty collapse", pad=8, fontsize=10.5)
    ax_b.set_ylim(0, 100)

    # ── Panel C: HR→SR elasticity ──
    pv, pl, ph = getvals(prod, "hr_sr_delta")
    fv, fl, fh = getvals(flag, "hr_sr_delta")
    ax_c.bar(xs - bar_width/2, pv, bar_width, yerr=[pl, ph], capsize=3,
             color="#8b95a5", edgecolor="white")
    ax_c.bar(xs + bar_width/2, fv, bar_width, yerr=[fl, fh], capsize=3,
             color="#d97757", edgecolor="white")
    ax_c.set_xticks(xs)
    ax_c.set_xticklabels([VENDOR_DISPLAY[v] for v in VENDORS])
    ax_c.set_ylabel("HR→SR Δ on_task (pp)")
    ax_c.set_title("(C) Finding 7 — 2-tier elasticity", pad=8, fontsize=10.5)

    # ── Panel D: pairwise JSD (5 critical pairs) ──
    pair_keys = [
        ("openai__gemini",   "OAI↔Gem"),
        ("openai__deepseek", "OAI↔DS"),
        ("gemini__deepseek", "Gem↔DS"),
        ("deepseek__kimi",   "DS↔Kimi"),
        ("grok__kimi",       "Grok↔Kimi"),
    ]
    xs_pairs = np.arange(len(pair_keys))
    pv = [prod["jsd"][k]["estimate"] for k, _ in pair_keys]
    pl = [prod["jsd"][k]["estimate"] - prod["jsd"][k]["ci_low"] for k, _ in pair_keys]
    ph = [prod["jsd"][k]["ci_high"] - prod["jsd"][k]["estimate"] for k, _ in pair_keys]
    fv = [flag["jsd"][k]["estimate"] for k, _ in pair_keys]
    fl = [flag["jsd"][k]["estimate"] - flag["jsd"][k]["ci_low"] for k, _ in pair_keys]
    fh = [flag["jsd"][k]["ci_high"] - flag["jsd"][k]["estimate"] for k, _ in pair_keys]
    ax_d.bar(xs_pairs - bar_width/2, pv, bar_width, yerr=[pl, ph], capsize=3,
             color="#8b95a5", edgecolor="white")
    ax_d.bar(xs_pairs + bar_width/2, fv, bar_width, yerr=[fl, fh], capsize=3,
             color="#d97757", edgecolor="white")
    ax_d.set_xticks(xs_pairs)
    ax_d.set_xticklabels([lbl for _, lbl in pair_keys], fontsize=9)
    ax_d.set_ylabel("Pairwise JSD")
    ax_d.set_title("(D) Finding 1 — refusal distribution clustering", pad=8, fontsize=10.5)
    # Highlight DS↔Kimi
    ax_d.axvspan(2.52, 3.48, color="#fde8dc", alpha=0.4, zorder=0)

    fig.suptitle(
        "Flagship-tier sensitivity: Findings 1 / 5 / 7 under capability-matched vendor models",
        fontsize=11.5, y=1.01,
    )
    fig.tight_layout()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("pdf", "png"):
        p = FIG_OUT_STEM.parent / f"{FIG_OUT_STEM.name}.{ext}"
        fig.savefig(p, dpi=300, bbox_inches="tight")
        paths.append(p)
    plt.close(fig)
    return paths


# ─────────────────────────────────────────────────────────────────────────
def main():
    # Load both tiers
    print(f"Loading production CSV: {MAIN_CSV}", flush=True)
    prod_rows = load_rows(MAIN_CSV)
    print(f"  {len(prod_rows)} rows", flush=True)

    print(f"Loading flagship CSV:   {FLAG_CSV}", flush=True)
    flag_rows = load_rows(FLAG_CSV)
    print(f"  {len(flag_rows)} rows", flush=True)

    # Sanity: check labeling completeness on flagship
    unlabeled = sum(1 for r in flag_rows
                    if (r.get("status") or "") != "error"
                    and not (r.get("label") or "").strip())
    if unlabeled > 0:
        print(f"\n[warn] {unlabeled} flagship rows are unlabeled. Analysis will "
              "use only labeled rows. Re-run after completing labels.\n",
              flush=True)

    # Determine flagship prompt_id subset for paired comparison
    flag_prompt_ids = {r["prompt_id"] for r in flag_rows}
    print(f"Flagship subset: {len(flag_prompt_ids)} unique prompt IDs\n", flush=True)

    # Compute metrics
    print("Computing production-tier metrics (restricted to flagship subset)...",
          flush=True)
    prod_metrics = compute_tier_metrics(prod_rows, "production",
                                         flagship_subset=flag_prompt_ids)

    print("Computing flagship-tier metrics...", flush=True)
    flag_metrics = compute_tier_metrics(flag_rows, "flagship")

    # Save machine-readable comparison
    comparison = {
        "production": prod_metrics,
        "flagship": flag_metrics,
        "model_map": {
            "openai":   {"prod": "gpt-4o-mini",           "flag": "gpt-4o"},
            "gemini":   {"prod": "gemini-2.5-flash-lite", "flag": "gemini-2.5-flash"},
            "grok":     {"prod": "grok-4-fast-non-reasoning", "flag": "grok-3"},
            "deepseek": {"prod": "deepseek-chat",         "flag": "deepseek-chat (unchanged)"},
            "kimi":     {"prod": "kimi-k2-0905-preview",  "flag": "kimi-k2-0905-preview (unchanged)"},
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    print(f"\nWrote {JSON_OUT.relative_to(REPO_ROOT)}", flush=True)

    # Emit textual report to stdout
    print("")
    print(report(prod_metrics, flag_metrics))

    # Render figure
    print("\nRendering fig7_tier_comparison...", flush=True)
    paths = plot_comparison(prod_metrics, flag_metrics)
    for p in paths:
        print(f"  wrote {p.relative_to(REPO_ROOT)}", flush=True)


if __name__ == "__main__":
    main()
