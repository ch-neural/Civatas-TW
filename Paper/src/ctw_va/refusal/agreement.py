"""Inter-rater agreement between primary and blind labels.

Computes Cohen's κ for the blind-validation subset. Match rows by
(prompt_id, vendor) key; rows missing in either file or unlabeled in blind
are reported as coverage gaps but don't halt the run.

For paper §3.5 citation:
  - Overall κ (single number for abstract)
  - Per-vendor κ (check if one vendor drove disagreement)
  - 3×3 confusion matrix (primary rows × blind cols)
  - Coverage report (how many of blind subset got re-labeled)
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from .prompts import VALID_LABELS


def compute(primary_csv: str, blind_csv: str) -> dict:
    primary = _read_labeled_map(primary_csv)
    blind = _read_labeled_map(blind_csv)
    blind_keys = set(blind.keys())

    if not blind_keys:
        raise ValueError(f"{blind_csv} has no labeled rows — re-label first")

    # Only compare rows present + labeled in BOTH.
    # Unlabeled blind rows are coverage gaps, reported separately.
    blind_all = _read_all_map(blind_csv)
    blind_total = len(blind_all)
    blind_labeled = len(blind_keys)

    pairs: list[tuple[str, str, str]] = []  # (vendor, primary_label, blind_label)
    missing_in_primary: list[tuple[str, str]] = []
    for key, blind_lbl in blind.items():
        if key not in primary:
            missing_in_primary.append(key)
            continue
        pairs.append((key[1], primary[key], blind_lbl))

    overall_kappa = _kappa([(p, b) for (_, p, b) in pairs])
    n_agree = sum(1 for (_, p, b) in pairs if p == b)
    n_total = len(pairs)
    observed_agreement = (n_agree / n_total) if n_total else 0.0

    # Per-vendor κ
    by_vendor_pairs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for vendor, p, b in pairs:
        by_vendor_pairs[vendor].append((p, b))
    per_vendor: dict[str, dict] = {}
    for vendor, vpairs in by_vendor_pairs.items():
        per_vendor[vendor] = {
            "n": len(vpairs),
            "kappa": _kappa(vpairs),
            "agreement_rate": sum(1 for (p, b) in vpairs if p == b) / len(vpairs),
        }

    # 3×3 confusion matrix (rows=primary, cols=blind)
    matrix: dict[str, dict[str, int]] = {
        p: {b: 0 for b in VALID_LABELS} for p in VALID_LABELS
    }
    for _, p, b in pairs:
        if p in VALID_LABELS and b in VALID_LABELS:
            matrix[p][b] += 1

    return {
        "primary_csv": str(primary_csv),
        "blind_csv": str(blind_csv),
        "coverage": {
            "blind_subset_total": blind_total,
            "blind_labeled": blind_labeled,
            "blind_unlabeled": blind_total - blind_labeled,
            "compared_pairs": n_total,
            "missing_in_primary": len(missing_in_primary),
        },
        "overall": {
            "kappa": overall_kappa,
            "observed_agreement": observed_agreement,
            "n": n_total,
        },
        "per_vendor": per_vendor,
        "confusion_matrix": {
            "labels": list(VALID_LABELS),
            "rows_primary_cols_blind": matrix,
        },
    }


def format_text(result: dict) -> str:
    lines = []
    lines.append(result["primary_csv"] + "  vs  " + result["blind_csv"])
    lines.append("")
    cov = result["coverage"]
    lines.append(f"Coverage:")
    lines.append(f"  Blind subset rows:   {cov['blind_subset_total']}")
    lines.append(f"  Blind labeled:       {cov['blind_labeled']}")
    if cov["blind_unlabeled"]:
        lines.append(f"  Blind unlabeled:     {cov['blind_unlabeled']}  ← finish labeling first")
    if cov["missing_in_primary"]:
        lines.append(f"  Missing in primary:  {cov['missing_in_primary']}")
    lines.append(f"  Compared pairs:      {cov['compared_pairs']}")
    lines.append("")
    o = result["overall"]
    lines.append(f"Overall agreement (n={o['n']}):")
    lines.append(f"  Cohen's κ:           {o['kappa']:.4f}")
    lines.append(f"  Observed agreement:  {o['observed_agreement']:.2%}")
    lines.append("")
    lines.append(f"Per-vendor (n ≥ 3 only):")
    lines.append(f"  {'vendor':<10}{'n':>4}{'κ':>8}{'agree':>10}")
    for v in sorted(result["per_vendor"].keys()):
        pv = result["per_vendor"][v]
        if pv["n"] < 3:
            continue
        lines.append(
            f"  {v:<10}{pv['n']:>4}{pv['kappa']:>8.4f}{pv['agreement_rate']:>10.2%}"
        )
    lines.append("")
    # Confusion matrix
    cm = result["confusion_matrix"]
    labels = cm["labels"]
    matrix = cm["rows_primary_cols_blind"]
    header = f"  {'primary\\blind':>15}" + "".join(f"{_short(l):>14}" for l in labels)
    lines.append("Confusion matrix:")
    lines.append(header)
    for p in labels:
        row = f"  {_short(p):>15}" + "".join(f"{matrix[p][b]:>14}" for b in labels)
        lines.append(row)
    return "\n".join(lines)


def _short(label: str) -> str:
    return {"hard_refusal": "hard", "soft_refusal": "soft", "on_task": "on_task"}.get(label, label)


def _read_labeled_map(csv_path: str) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            lbl = (row.get("label") or "").strip()
            if not lbl or lbl not in VALID_LABELS:
                continue
            key = (row.get("prompt_id", ""), row.get("vendor", ""))
            out[key] = lbl
    return out


def _read_all_map(csv_path: str) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = (row.get("prompt_id", ""), row.get("vendor", ""))
            out[key] = (row.get("label") or "").strip()
    return out


def _kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's κ for 2 raters on categorical labels. Uses sklearn if available."""
    if not pairs:
        return 0.0
    try:
        from sklearn.metrics import cohen_kappa_score
        import math
        p_labels = [p for (p, _) in pairs]
        b_labels = [b for (_, b) in pairs]
        k = float(cohen_kappa_score(p_labels, b_labels, labels=list(VALID_LABELS)))
        # sklearn returns NaN when either rater's labels are degenerate
        # (all same class). Degenerate + all-agree collapses to 1.0; degenerate +
        # any disagreement is undefined — we report 0.0 to be conservative.
        if math.isnan(k):
            all_agree = all(p == b for (p, b) in pairs)
            return 1.0 if all_agree else 0.0
        return k
    except ImportError:
        # Manual fallback (should not happen — sklearn is a Paper dep)
        return _kappa_manual(pairs)


def _kappa_manual(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    if n == 0:
        return 0.0
    labels = list(VALID_LABELS)
    po = sum(1 for (p, b) in pairs if p == b) / n
    p_counts = {l: sum(1 for (p, _) in pairs if p == l) / n for l in labels}
    b_counts = {l: sum(1 for (_, b) in pairs if b == l) / n for l in labels}
    pe = sum(p_counts[l] * b_counts[l] for l in labels)
    if 1 - pe == 0:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1 - pe)
