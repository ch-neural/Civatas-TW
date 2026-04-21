"""Progress + label distribution stats for a labeling CSV.

Used by ``civatas-exp calibration stats`` to report:
  - Total / labelable / labeled / unlabeled row counts
  - Label distribution (hard / soft / on_task) + invalid label count
  - Per-vendor and per-expected-category breakdown
  - Optional AI-sidecar comparison (overlap, agree/disagree) when a
    ``<csv_stem>.ai_suggest.jsonl`` file is found next to the CSV.

Pure function — no FS writes, no network. CLI (``cli/calibration.py``)
formats the dict for humans and/or ``--json`` output.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .prompts import VALID_LABELS


def _default_sidecar(csv_path: Path) -> Path:
    # For ``foo/responses_n200.csv`` → ``foo/responses_n200.ai_suggest.jsonl``
    # Matches webui.labeling_ai._sidecar_path().
    return csv_path.with_suffix("").with_suffix(".ai_suggest.jsonl")


def _load_sidecar(path: Path) -> dict[tuple[str, str], dict]:
    """Latest-wins dict keyed by (prompt_id, vendor)."""
    out: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return out
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = obj.get("prompt_id")
            v = obj.get("vendor")
            if pid and v:
                out[(pid, v)] = obj
    return out


def _empty_label_counts() -> dict[str, int]:
    return {lbl: 0 for lbl in VALID_LABELS}


def compute(csv_path: str, sidecar_path: str | None = None) -> dict:
    """Walk the CSV once and produce a stats dict.

    Parameters
    ----------
    csv_path
        Path to the responses CSV (UTF-8-sig header + 14 columns).
    sidecar_path
        Optional override. Default: sibling ``<stem>.ai_suggest.jsonl``.
        If the file does not exist, ``result["ai"]`` is ``None``.
    """
    cp = Path(csv_path)
    sc_path = Path(sidecar_path) if sidecar_path else _default_sidecar(cp)
    sidecar = _load_sidecar(sc_path) if sc_path.exists() else None

    total = 0
    errors = 0
    labeled = 0
    invalid_labels = 0
    by_label = _empty_label_counts()
    by_vendor: dict[str, dict] = {}
    by_expected: dict[str, dict] = {}

    # For AI overlap comparison we collect (pid, vendor, human_label).
    human_rows: dict[tuple[str, str], str] = {}

    with cp.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            status = (row.get("status") or "").strip()
            vendor = (row.get("vendor") or "").strip() or "_unknown"
            expected = (row.get("expected") or "").strip() or "_unspecified"
            raw_label = (row.get("label") or "").strip()
            pid = (row.get("prompt_id") or "").strip()

            is_error = status == "error"
            if is_error:
                errors += 1

            # Validity + counting
            is_valid_label = raw_label in VALID_LABELS
            if raw_label and not is_valid_label:
                invalid_labels += 1

            if is_valid_label:
                labeled += 1
                by_label[raw_label] += 1

            # Per-vendor bucket
            bv = by_vendor.setdefault(vendor, {
                "total": 0, "labeled": 0, "errors": 0, "unlabeled": 0,
                "by_label": _empty_label_counts(),
            })
            bv["total"] += 1
            if is_error:
                bv["errors"] += 1
            if is_valid_label:
                bv["labeled"] += 1
                bv["by_label"][raw_label] += 1

            # Per-expected bucket
            be = by_expected.setdefault(expected, {
                "total": 0, "labeled": 0, "errors": 0,
                "by_label": _empty_label_counts(),
            })
            be["total"] += 1
            if is_error:
                be["errors"] += 1
            if is_valid_label:
                be["labeled"] += 1
                be["by_label"][raw_label] += 1

            # For AI overlap we only track *actually-labeled* rows
            if is_valid_label and pid and vendor != "_unknown":
                human_rows[(pid, vendor)] = raw_label

    labelable = total - errors
    unlabeled = labelable - labeled

    # Fill per-vendor unlabeled
    for bv in by_vendor.values():
        bv["unlabeled"] = max(0, bv["total"] - bv["errors"] - bv["labeled"])

    out: dict = {
        "csv_path": str(cp),
        "total": total,
        "errors": errors,
        "labelable": labelable,
        "labeled": labeled,
        "unlabeled": unlabeled,
        "invalid_labels": invalid_labels,
        "by_label": by_label,
        "by_vendor": by_vendor,
        "by_expected": by_expected,
        "ai": None,
    }

    if sidecar is None:
        return out

    # AI sidecar comparison
    ai_keys = set(sidecar.keys())
    human_keys = set(human_rows.keys())
    overlap_keys = ai_keys & human_keys
    agree = 0
    disagree = 0
    for k in overlap_keys:
        ai_label = (sidecar[k].get("label") or "").strip()
        if ai_label == human_rows[k]:
            agree += 1
        else:
            disagree += 1

    out["ai"] = {
        "sidecar_path": str(sc_path),
        "total_entries": len(sidecar),
        "overlap": len(overlap_keys),
        "human_only": len(human_keys - ai_keys),
        "ai_only": len(ai_keys - human_keys),
        "agree": agree,
        "disagree": disagree,
    }
    return out


# --- Text formatter ---------------------------------------------------------


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):5.1f}%" if d > 0 else "  n/a"


def format_text(s: dict, csv_path: str | None = None) -> str:
    """Human-readable multi-line report."""
    lines: list[str] = []
    path = csv_path or s.get("csv_path", "")
    if path:
        lines.append(path)
        lines.append("")

    total = s["total"]
    errors = s["errors"]
    labelable = s["labelable"]
    labeled = s["labeled"]
    unlabeled = s["unlabeled"]

    lines.append(f"Total rows:    {total:>6}")
    lines.append(f"  Un-labelable:{errors:>6}  (status=error)")
    lines.append(f"  Labelable:   {labelable:>6}")
    lines.append("")
    lines.append(f"Labeled:       {labeled:>6}  ({_pct(labeled, labelable)} of labelable)")
    lines.append(f"Unlabeled:     {unlabeled:>6}")
    if s.get("invalid_labels", 0):
        lines.append(f"Invalid labels:{s['invalid_labels']:>6}  (label col filled but not one of valid 3)")
    lines.append("")

    lines.append("Label distribution:")
    for lbl in VALID_LABELS:
        n = s["by_label"][lbl]
        lines.append(f"  {lbl:<14} {n:>5}  ({_pct(n, labeled)})")
    lines.append("")

    # Per-vendor
    lines.append("By vendor:")
    lines.append(f"  {'vendor':<10} {'total':>6} {'err':>5} {'lbld':>5} {'unlb':>5}   "
                 f"{'hard':>5} {'soft':>5} {'ok':>5}")
    for vendor in sorted(s["by_vendor"].keys()):
        bv = s["by_vendor"][vendor]
        lines.append(
            f"  {vendor:<10} {bv['total']:>6} {bv['errors']:>5} "
            f"{bv['labeled']:>5} {bv['unlabeled']:>5}   "
            f"{bv['by_label']['hard_refusal']:>5} "
            f"{bv['by_label']['soft_refusal']:>5} "
            f"{bv['by_label']['on_task']:>5}"
        )
    lines.append("")

    # Per-expected
    if s["by_expected"]:
        lines.append("By expected category:")
        for cat in sorted(s["by_expected"].keys()):
            be = s["by_expected"][cat]
            lines.append(
                f"  {cat:<25} total={be['total']:<4} labeled={be['labeled']:<4}  "
                f"hard={be['by_label']['hard_refusal']} "
                f"soft={be['by_label']['soft_refusal']} "
                f"ok={be['by_label']['on_task']}"
            )
        lines.append("")

    # AI sidecar
    ai = s.get("ai")
    if ai:
        lines.append("AI suggestions (sidecar):")
        lines.append(f"  File:             {ai['sidecar_path']}")
        lines.append(f"  Total entries:    {ai['total_entries']}")
        lines.append(f"  Overlap w/ human: {ai['overlap']}  "
                     f"(agree={ai['agree']}, disagree={ai['disagree']})")
        if ai["overlap"] > 0:
            lines.append(f"  Agreement rate:   {_pct(ai['agree'], ai['overlap'])}")
        lines.append(f"  Human-only:       {ai['human_only']}  "
                     f"(labeled by human, no AI entry)")
        lines.append(f"  AI-only:          {ai['ai_only']}  "
                     f"(AI suggested, human not yet labeled)")
    else:
        lines.append("AI suggestions (sidecar): (none found)")

    return "\n".join(lines)
