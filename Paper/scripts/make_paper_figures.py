#!/usr/bin/env python3
"""Paper figures + tables for CTW-VA-2026 (Stage 17 onwards).

Reads the labeled refusal CSV (responses_n200.csv by default) and emits
figures + tables under Paper/paper_figures/.

Usage
-----
    python scripts/make_paper_figures.py --all
    python scripts/make_paper_figures.py --figure 1 4
    python scripts/make_paper_figures.py --list

Outputs: PDF (for arXiv) + PNG (for GitHub README) for each figure;
tables as CSV + LaTeX booktabs.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


# Project roots
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO_ROOT / "experiments" / "refusal_calibration" / "responses_n200.csv"
OUT_DIR = REPO_ROOT / "paper_figures"

# Vendor display order (matches paper Table 1 column order)
VENDORS = ["openai", "gemini", "grok", "deepseek", "kimi"]
VENDOR_DISPLAY = {
    "openai": "OpenAI",
    "gemini": "Gemini",
    "grok": "Grok",
    "deepseek": "DeepSeek",
    "kimi": "Kimi",
}

# Consistent palette — neutral greys + one accent for the outlier (Grok)
VENDOR_COLORS = {
    "openai":   "#5b7ba3",
    "gemini":   "#7a9abf",
    "grok":     "#d97757",   # accent — Finding 3 outlier
    "deepseek": "#8b6fa6",
    "kimi":     "#c76e86",
}

# Category display labels (rows in figure legends / tables)
CATEGORY_ORDER = ["hard_refusal", "soft_refusal", "on_task", "api_blocked"]
CATEGORY_LABELS = {
    "hard_refusal": "Hard refusal",
    "soft_refusal": "Soft refusal",
    "on_task":      "On-task",
    "api_blocked":  "API-blocked",
}
CATEGORY_COLORS = {
    "hard_refusal": "#c85250",
    "soft_refusal": "#e09c50",
    "on_task":      "#62a15c",
    "api_blocked":  "#4c4c4c",
}


# ────────────────────── Data loader ──────────────────────


def load_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def classify(row: dict) -> str:
    """Map CSV row to one of CATEGORY_ORDER. Error rows = api_blocked."""
    if (row.get("status") or "").strip() == "error":
        return "api_blocked"
    lbl = (row.get("label") or "").strip()
    return lbl or "unlabeled"


def per_vendor_counts(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Returns {vendor: {category: count, ...}} — only labeled + api_blocked."""
    out: dict[str, dict[str, int]] = {
        v: {c: 0 for c in CATEGORY_ORDER} for v in VENDORS
    }
    for r in rows:
        v = r.get("vendor", "")
        if v not in out:
            continue
        cat = classify(r)
        if cat in out[v]:
            out[v][cat] += 1
    return out


# ────────────────────── Style helpers ──────────────────────


def apply_style():
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "figure.dpi": 110,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def save_figure(fig, stem: str) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("pdf", "png"):
        p = OUT_DIR / f"{stem}.{ext}"
        fig.savefig(p)
        paths.append(p)
    plt.close(fig)
    return paths


# ────────────────────── Table 1 ──────────────────────


def make_table1(rows: list[dict]) -> list[Path]:
    counts = per_vendor_counts(rows)
    totals = {v: sum(counts[v].values()) for v in VENDORS}

    # CSV
    csv_path = OUT_DIR / "table1_per_vendor_breakdown.csv"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "Vendor", "n", "Hard refusal", "Soft refusal",
            "On-task", "API-blocked",
            "Hard %", "Soft %", "On-task %", "API-blocked %",
            "Refusal rate %",     # hard + soft + api_blocked
        ])
        for v in VENDORS:
            n = totals[v]
            c = counts[v]
            refusal = c["hard_refusal"] + c["soft_refusal"] + c["api_blocked"]
            w.writerow([
                VENDOR_DISPLAY[v], n,
                c["hard_refusal"], c["soft_refusal"],
                c["on_task"], c["api_blocked"],
                _pct(c["hard_refusal"], n),
                _pct(c["soft_refusal"], n),
                _pct(c["on_task"], n),
                _pct(c["api_blocked"], n),
                _pct(refusal, n),
            ])

    # LaTeX booktabs
    tex_path = OUT_DIR / "table1_per_vendor_breakdown.tex"
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\small",
        r"\caption{Per-vendor refusal breakdown on the N=200 Taiwan-political "
        r"prompt bank (1,000 calls total). API-blocked rows are pre-generation "
        r"content-filter refusals and are disjoint from the three model-level "
        r"labels.}",
        r"\label{tab:per-vendor-breakdown}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Vendor & $n$ & Hard & Soft & On-task & API-blocked & Refusal \% \\",
        r"\midrule",
    ]
    for v in VENDORS:
        c = counts[v]; n = totals[v]
        refusal = c["hard_refusal"] + c["soft_refusal"] + c["api_blocked"]
        lines.append(
            f"{VENDOR_DISPLAY[v]} & {n} & "
            f"{c['hard_refusal']} & {c['soft_refusal']} & "
            f"{c['on_task']} & {c['api_blocked']} & "
            f"{_pct(refusal, n)} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return [csv_path, tex_path]


def _pct(x: int, n: int) -> str:
    if not n:
        return "0.0"
    return f"{100 * x / n:.1f}"


# ────────────────────── Figure 1 ──────────────────────


def make_figure1(rows: list[dict]) -> list[Path]:
    """Stacked bar: 4-category × 5-vendor refusal breakdown (percent)."""
    counts = per_vendor_counts(rows)
    totals = {v: sum(counts[v].values()) for v in VENDORS}

    fig, ax = plt.subplots(figsize=(7.2, 4.0))

    x = np.arange(len(VENDORS))
    width = 0.62

    # Percent stacks in CATEGORY_ORDER, bottom→top
    bottom = np.zeros(len(VENDORS))
    for cat in CATEGORY_ORDER:
        vals = np.array([
            100 * counts[v][cat] / max(totals[v], 1) for v in VENDORS
        ])
        ax.bar(
            x, vals, width, bottom=bottom,
            label=CATEGORY_LABELS[cat], color=CATEGORY_COLORS[cat],
            edgecolor="white", linewidth=0.6,
        )
        # In-bar percent labels (only for segments ≥ 4%)
        for i, v in enumerate(vals):
            if v >= 4.0:
                ax.text(
                    x[i], bottom[i] + v / 2, f"{v:.1f}",
                    ha="center", va="center",
                    fontsize=8.5, color="white", fontweight="bold",
                )
        bottom += vals

    ax.set_xticks(x)
    ax.set_xticklabels([VENDOR_DISPLAY[v] for v in VENDORS])
    ax.set_ylabel("Share of responses (%)")
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_title("Per-vendor response distribution (N=200 prompts × 5 vendors)", pad=12)

    # Legend below plot for arXiv readability
    ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.12),
        ncol=4, frameon=False, fontsize=9,
    )
    fig.tight_layout()
    return save_figure(fig, "fig1_per_vendor_distribution")


# ────────────────────── Figure 3 ──────────────────────


def make_figure3(rows: list[dict]) -> list[Path]:
    """Kimi api_blocked: (a) by topic + (b) by expected category — Finding 2."""
    kimi_rows = [r for r in rows if r.get("vendor") == "kimi"]

    # Panel (a): by topic
    topic_totals: dict[str, int] = defaultdict(int)
    topic_blocked: dict[str, int] = defaultdict(int)
    for r in kimi_rows:
        t = r.get("topic") or "unknown"
        topic_totals[t] += 1
        if (r.get("status") or "") == "error":
            topic_blocked[t] += 1
    topics = sorted(
        topic_totals.keys(),
        key=lambda t: -(topic_blocked[t] / max(topic_totals[t], 1)),
    )
    t_rates = [100 * topic_blocked[t] / max(topic_totals[t], 1) for t in topics]
    t_ns = [topic_totals[t] for t in topics]
    t_blocks = [topic_blocked[t] for t in topics]

    # Panel (b): by expected category
    exp_order = ["hard_refusal_expected", "soft_refusal_expected", "on_task_expected"]
    exp_display = {
        "hard_refusal_expected": "HR-expected\n(designed to provoke)",
        "soft_refusal_expected": "SR-expected\n(ambiguous)",
        "on_task_expected":      "OT-expected\n(neutral factual)",
    }
    exp_totals = Counter(r.get("expected") for r in kimi_rows)
    exp_blocked = Counter(r.get("expected") for r in kimi_rows if (r.get("status") or "") == "error")
    e_rates = [100 * exp_blocked[e] / max(exp_totals[e], 1) for e in exp_order]
    e_ns = [exp_totals[e] for e in exp_order]
    e_blocks = [exp_blocked[e] for e in exp_order]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.0, 3.8), gridspec_kw={"width_ratios": [6, 4]})

    # Panel (a)
    colors1 = ["#d97757" if r > 10 else "#8b95a5" for r in t_rates]
    ax1.bar(
        np.arange(len(topics)), t_rates,
        color=colors1, edgecolor="white", linewidth=0.6, width=0.66,
    )
    for i, (rate, b, n) in enumerate(zip(t_rates, t_blocks, t_ns)):
        ax1.text(
            i, rate + 0.8, f"{b}/{n}\n({rate:.1f}%)",
            ha="center", va="bottom", fontsize=8.5, color="#333",
        )
    ax1.set_xticks(np.arange(len(topics)))
    ax1.set_xticklabels(topics, rotation=25, ha="right")
    ax1.set_ylabel("Kimi API-blocked rate (%)")
    ax1.set_ylim(0, max(t_rates) * 1.28 + 5)
    ax1.set_title("(a) by prompt topic", pad=8, fontsize=10.5)

    # Panel (b) — the OT bar is the headline
    colors2 = ["#d97757" if e == "hard_refusal_expected" else
               "#b74f1f" if e == "on_task_expected" else     # emphasize OT
               "#8b95a5"
               for e in exp_order]
    ax2.bar(
        np.arange(len(exp_order)), e_rates,
        color=colors2, edgecolor="white", linewidth=0.6, width=0.62,
    )
    for i, (rate, b, n) in enumerate(zip(e_rates, e_blocks, e_ns)):
        ax2.text(
            i, rate + 0.3, f"{b}/{n}\n({rate:.1f}%)",
            ha="center", va="bottom", fontsize=8.5, color="#333",
        )
    # Annotate the OT surprise
    ot_idx = exp_order.index("on_task_expected")
    ax2.annotate(
        "4 blocked prompts are\nneutral factual\nquestions about\nTaiwan institutions",
        xy=(ot_idx, e_rates[ot_idx]),
        xytext=(ot_idx - 1.0, e_rates[ot_idx] + 3.5),
        fontsize=8.2, color="#8B3A0E",
        arrowprops=dict(arrowstyle="->", color="#8B3A0E", lw=0.8),
    )
    ax2.set_xticks(np.arange(len(exp_order)))
    ax2.set_xticklabels([exp_display[e] for e in exp_order], fontsize=8.5)
    ax2.set_ylabel("Kimi API-blocked rate (%)")
    ax2.set_ylim(0, max(e_rates) * 1.6 + 2)
    ax2.set_title("(b) by prompt design intent", pad=8, fontsize=10.5)

    fig.suptitle(
        "Kimi's pre-generation filter: Taiwan-statehood blocking, not opinion blocking",
        fontsize=11, y=1.02,
    )
    fig.tight_layout()
    return save_figure(fig, "fig3_kimi_api_blocked_by_topic")


# ────────────────────── Figure 4 ──────────────────────


def make_figure4(rows: list[dict]) -> list[Path]:
    """On-task rate per vendor — Grok is the low-refusal outlier (Finding 3)."""
    counts = per_vendor_counts(rows)
    totals = {v: sum(counts[v].values()) for v in VENDORS}

    # Use on_task as share of ALL responses (incl. api_blocked) so cross-vendor
    # apples-to-apples — Kimi doesn't get to dodge by having 14 api-blocks.
    on_task_rates = {
        v: 100 * counts[v]["on_task"] / max(totals[v], 1)
        for v in VENDORS
    }
    refusal_rates = {
        v: 100 - on_task_rates[v] for v in VENDORS
    }

    # Sort by on_task rate ascending → Grok / Kimi end up highest
    order = sorted(VENDORS, key=lambda v: on_task_rates[v])

    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    x = np.arange(len(order))
    colors = [VENDOR_COLORS[v] for v in order]
    bars = ax.bar(
        x, [on_task_rates[v] for v in order],
        color=colors, edgecolor="white", linewidth=0.6, width=0.66,
    )
    for i, v in enumerate(order):
        rate = on_task_rates[v]
        ax.text(
            i, rate + 1.2, f"{rate:.1f}%",
            ha="center", va="bottom", fontsize=9.5, fontweight="bold",
            color="#222",
        )

    # Reference: median vendor's on_task rate
    median = float(np.median(list(on_task_rates.values())))
    ax.axhline(median, color="#777", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.text(
        len(order) - 0.5, median + 0.8,
        f"median = {median:.1f}%",
        ha="right", va="bottom", fontsize=8, color="#666",
    )

    ax.set_xticks(x)
    ax.set_xticklabels([VENDOR_DISPLAY[v] for v in order])
    ax.set_ylabel("On-task rate (% of all responses)")
    ax.set_ylim(0, 100)
    ax.set_title("Grok engages most; DeepSeek refuses most", pad=10)
    fig.tight_layout()
    return save_figure(fig, "fig4_on_task_rate_by_vendor")


# ────────────────────── Figure 2 ──────────────────────


def make_figure2(rows: list[dict]) -> list[Path]:
    """5×5 pairwise JSD heatmap of refusal-category distributions.

    JSD treats the 4-class distribution (hard/soft/on_task/api_blocked) as
    a probability vector per vendor. Smaller JSD → more similar refusal
    behaviour. DeepSeek-Western clustering is the headline finding.
    """
    # Import JSD helpers. analytics/__init__.py re-exports `jsd` as a function,
    # shadowing the submodule — import the helpers directly from the submodule
    # via importlib to sidestep that.
    sys.path.insert(0, str(REPO_ROOT / "src"))
    import importlib
    jsd_submod = importlib.import_module("ctw_va.analytics.jsd")
    counts_to_probs = jsd_submod.counts_to_probs
    jsd_fn = jsd_submod.jsd

    counts = per_vendor_counts(rows)
    n = len(VENDORS)
    mat = np.zeros((n, n))
    for i, vi in enumerate(VENDORS):
        for j, vj in enumerate(VENDORS):
            pi = counts_to_probs(
                {c: counts[vi][c] for c in CATEGORY_ORDER}, CATEGORY_ORDER,
            )
            pj = counts_to_probs(
                {c: counts[vj][c] for c in CATEGORY_ORDER}, CATEGORY_ORDER,
            )
            mat[i, j] = jsd_fn(pi, pj)

    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    vmax = float(mat.max()) if mat.max() > 0 else 1.0
    im = ax.imshow(
        mat, cmap="viridis_r", vmin=0, vmax=vmax,
        aspect="equal",
    )
    ax.set_xticks(np.arange(n))
    ax.set_yticks(np.arange(n))
    ax.set_xticklabels([VENDOR_DISPLAY[v] for v in VENDORS], rotation=30, ha="right")
    ax.set_yticklabels([VENDOR_DISPLAY[v] for v in VENDORS])
    ax.set_title("Pairwise Jensen-Shannon divergence\nbetween vendor refusal distributions", pad=12)

    # Annotate cells
    for i in range(n):
        for j in range(n):
            val = mat[i, j]
            color = "white" if val > vmax * 0.5 else "#222"
            ax.text(
                j, i, f"{val:.3f}",
                ha="center", va="center", fontsize=8.5, color=color,
            )
    fig.colorbar(im, ax=ax, shrink=0.82, label="JSD (log₂, 0 = identical)")
    fig.tight_layout()
    return save_figure(fig, "fig2_pairwise_jsd_heatmap")


# ────────────────────── Figure 5 ──────────────────────


def make_figure5(rows: list[dict]) -> list[Path]:
    """HR→SR refusal elasticity per vendor (Finding 7).

    For each vendor, compute on_task rate on hard_refusal_expected prompts vs
    soft_refusal_expected prompts. A steep upward slope = responsive RLHF
    (vendor loosens on softer prompts). Flat slope = stiff refusal regime.
    """
    by_vendor_expected: dict[str, dict[str, Counter]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    for r in rows:
        v = r.get("vendor", "")
        if v not in VENDORS:
            continue
        exp = r.get("expected", "")
        by_vendor_expected[v][exp][classify(r)] += 1

    def on_task_rate(vendor: str, expected: str) -> float:
        c = by_vendor_expected[vendor][expected]
        total = sum(c.values())
        if total == 0:
            return float("nan")
        return 100 * c["on_task"] / total

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    xs = [0, 1]
    xlabels = ["HR-expected\n(designed to provoke)", "SR-expected\n(ambiguous)"]

    # Classify vendors into 3 regimes based on HR-level and Δ shape
    # - Responsive RLHF: starts low, large Δ (OpenAI, Gemini)
    # - Stiff across board: starts low, small Δ (DeepSeek)
    # - Ceiling-bound: starts high, small Δ (Grok, Kimi)
    regime = {
        "openai":   "responsive",
        "gemini":   "responsive",
        "deepseek": "stiff",
        "grok":     "ceiling",
        "kimi":     "ceiling",
    }
    regime_style = {
        "responsive": {"linestyle": "-",  "alpha": 1.0},
        "stiff":      {"linestyle": "--", "alpha": 1.0},
        "ceiling":    {"linestyle": ":",  "alpha": 1.0},
    }

    for v in VENDORS:
        hr = on_task_rate(v, "hard_refusal_expected")
        sr = on_task_rate(v, "soft_refusal_expected")
        st = regime_style[regime[v]]
        ax.plot(
            xs, [hr, sr], marker="o", markersize=8,
            linewidth=2.2, color=VENDOR_COLORS[v],
            label=f"{VENDOR_DISPLAY[v]}  (Δ = +{sr - hr:.1f}pp, {regime[v]})",
            **st,
        )
        ax.text(xs[0] - 0.05, hr, f"{hr:.0f}%", ha="right", va="center", fontsize=8.5, color=VENDOR_COLORS[v])
        ax.text(xs[1] + 0.05, sr, f"{sr:.0f}%", ha="left", va="center", fontsize=8.5, color=VENDOR_COLORS[v])

    ax.set_xticks(xs)
    ax.set_xticklabels(xlabels, fontsize=9)
    ax.set_ylabel("On-task rate (%, labeled responses only)")
    ax.set_ylim(0, 105)
    ax.set_xlim(-0.35, 1.35)
    ax.set_title(
        "Two-tier HR→SR elasticity: responsive RLHF vs ceiling-bound / stiff regimes",
        pad=10,
    )
    ax.legend(loc="lower right", frameon=False, fontsize=8.2)
    fig.tight_layout()
    return save_figure(fig, "fig5_hr_sr_elasticity")


# ────────────────────── Entry point ──────────────────────


def make_figure6(rows: list[dict]) -> list[Path]:
    """Per-topic on_task heatmap (5 vendors × 6 topics) — Finding 5.

    Exposes the 4-profile vendor taxonomy:
      DeepSeek collapses on sovereignty (10.3%) vs non-sov (54%)
      Kimi / Grok topic-agnostic (high across board)
      Western moderate sovereign dampening
    """
    all_topics = sorted(set(r["topic"] for r in rows if r.get("topic")))

    # Build 5×T matrix of on_task %, non-API-blocked responses only
    mat = np.zeros((len(VENDORS), len(all_topics)))
    ns = np.zeros_like(mat, dtype=int)
    for i, v in enumerate(VENDORS):
        for j, t in enumerate(all_topics):
            vt = [r for r in rows if r["vendor"] == v and r["topic"] == t and r["status"] != "error"]
            if not vt:
                mat[i, j] = np.nan
                continue
            ns[i, j] = len(vt)
            mat[i, j] = 100 * sum(1 for r in vt if r["label"] == "on_task") / len(vt)

    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    # Diverging-style colormap centered around ~60%; we want low on_task to pop as red
    # Custom scale: 0 = deep red, 60 = white-ish, 100 = green
    cmap = plt.get_cmap("RdYlGn")
    im = ax.imshow(mat, cmap=cmap, vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(np.arange(len(all_topics)))
    ax.set_xticklabels(all_topics, rotation=25, ha="right")
    ax.set_yticks(np.arange(len(VENDORS)))
    ax.set_yticklabels([VENDOR_DISPLAY[v] for v in VENDORS])

    # Annotate each cell
    for i in range(len(VENDORS)):
        for j in range(len(all_topics)):
            val = mat[i, j]
            if np.isnan(val):
                ax.text(j, i, "–", ha="center", va="center", fontsize=9, color="#999")
                continue
            color = "white" if (val < 35 or val > 90) else "#222"
            weight = "bold" if val < 20 else "normal"
            ax.text(j, i, f"{val:.0f}%",
                    ha="center", va="center", fontsize=9, color=color, fontweight=weight)

    # Emphasize the DeepSeek × sovereignty cell
    ds_idx = VENDORS.index("deepseek")
    try:
        sov_idx = all_topics.index("sovereignty")
        ax.add_patch(plt.Rectangle(
            (sov_idx - 0.5, ds_idx - 0.5), 1, 1,
            fill=False, edgecolor="#111", linewidth=2.2,
        ))
    except ValueError:
        pass

    ax.set_title(
        "On-task rate per vendor × topic — DeepSeek sovereignty collapse (Finding 5)",
        pad=10,
    )
    fig.colorbar(im, ax=ax, shrink=0.82, label="On-task rate (%)")
    fig.tight_layout()
    return save_figure(fig, "fig6_on_task_topic_heatmap")


FIGURE_REGISTRY = {
    "table1": make_table1,
    "1": make_figure1,
    "2": make_figure2,
    "3": make_figure3,
    "4": make_figure4,
    "5": make_figure5,
    "6": make_figure6,
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=str(DEFAULT_CSV),
                    help="Labeled refusal CSV (default: responses_n200.csv)")
    ap.add_argument("--all", action="store_true",
                    help="Emit every figure + table")
    ap.add_argument("--figure", nargs="+",
                    help=f"Specific figures, from {list(FIGURE_REGISTRY.keys())}")
    ap.add_argument("--list", action="store_true",
                    help="List available figures and exit")
    args = ap.parse_args(argv)

    if args.list:
        print("Available:")
        for k, fn in FIGURE_REGISTRY.items():
            print(f"  {k:<7}  {fn.__doc__.strip().splitlines()[0] if fn.__doc__ else ''}")
        return 0

    if not args.all and not args.figure:
        ap.error("specify --all or --figure N")

    apply_style()
    rows = load_rows(Path(args.csv))
    print(f"Loaded {len(rows)} rows from {args.csv}")

    keys = list(FIGURE_REGISTRY.keys()) if args.all else args.figure
    for k in keys:
        if k not in FIGURE_REGISTRY:
            print(f"  skip unknown: {k}")
            continue
        fn = FIGURE_REGISTRY[k]
        paths = fn(rows)
        print(f"  ✓ {k:<7} → {', '.join(str(p.name) for p in paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
