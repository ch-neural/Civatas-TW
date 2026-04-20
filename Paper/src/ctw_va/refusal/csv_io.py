"""JSONL ↔ CSV round-trip for human annotation.

Workflow:
  1. fetcher.fetch() writes responses JSONL (label column empty).
  2. export_to_csv() dumps a tidy CSV that opens in Excel / Numbers.
  3. Human fills the ``label`` column (``hard_refusal`` / ``soft_refusal``
     / ``on_task``) and saves.
  4. import_labels_from_csv() merges labels back into a new JSONL.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from .prompts import VALID_LABELS


# The columns that appear in the exported CSV, in this order. Extra JSONL
# fields are preserved in a trailing ``_extras_json`` column so round-trip
# doesn't lose data.
CSV_COLUMNS = [
    "prompt_id", "vendor", "prompt_text", "response_text",
    "label",               # human fills this
    "expected", "topic", "status", "model_id",
    "cost_usd", "latency_ms", "tokens_in", "tokens_out",
    "error_detail",
]


def export_to_csv(input_jsonl: str, output_csv: str) -> dict:
    """Read responses JSONL and write a CSV with an empty ``label`` column."""
    rows = []
    with open(input_jsonl, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
    with open(output_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            r = {**r}
            r["label"] = r.get("label", "") or ""
            writer.writerow(r)

    return {
        "count": len(rows), "output": str(output_csv),
        "hint": (
            "Open the CSV in Excel / Numbers / LibreOffice. Fill the "
            "`label` column with one of: "
            + " / ".join(VALID_LABELS)
            + ". Save (keep UTF-8). Then import with `calibration import-labels`."
        ),
    }


def import_labels_from_csv(
    csv_path: str, output_jsonl: str, allow_partial: bool = True
) -> dict:
    """Read labeled CSV and write labeled JSONL (rows without labels are skipped).

    Returns counts so the CLI can print a summary.
    """
    labeled: list[dict] = []
    skipped = 0
    bad_labels: list[str] = []

    # utf-8-sig transparently strips BOM from Excel-saved files.
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lbl = (row.get("label") or "").strip()
            if not lbl:
                skipped += 1
                continue
            if lbl not in VALID_LABELS:
                bad_labels.append(f"{row.get('prompt_id')}×{row.get('vendor')}: {lbl!r}")
                skipped += 1
                continue
            # Coerce numeric columns back from strings
            for k in ("cost_usd", "latency_ms", "tokens_in", "tokens_out"):
                if k in row and row[k] != "":
                    try:
                        row[k] = float(row[k]) if k == "cost_usd" else int(row[k])
                    except ValueError:
                        pass
            labeled.append({k: row.get(k, "") for k in CSV_COLUMNS})

    if bad_labels and not allow_partial:
        raise ValueError(
            f"{len(bad_labels)} rows have invalid labels (valid: "
            f"{VALID_LABELS}). Examples: {bad_labels[:3]}"
        )

    Path(output_jsonl).parent.mkdir(parents=True, exist_ok=True)
    with open(output_jsonl, "w", encoding="utf-8") as f:
        for r in labeled:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    by_label = {lbl: sum(1 for r in labeled if r["label"] == lbl) for lbl in VALID_LABELS}
    return {
        "labeled": len(labeled),
        "skipped": skipped,
        "bad_labels": bad_labels,
        "by_label": by_label,
        "output": str(output_jsonl),
    }
