"""In-browser labeling for calibration CSVs.

See docs/superpowers/specs/2026-04-20-calibration-inline-labeling-design.md
for the full design. This module exposes three FastAPI endpoints on a router
that ``app.py`` mounts at application startup.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..refusal.csv_io import CSV_COLUMNS
from ..refusal.prompts import VALID_LABELS


# Files we are allowed to write via this router. The generic whitelist
# (``experiments/ runs/ data/``) still applies via the injected path
# resolver — this regex is an extra safety net that rejects arbitrary CSVs
# within those roots.
_LABELING_FILENAME_RE = re.compile(r"^responses_n\d+(_\w+)?\.csv$")


# Allowed mtime drift when comparing the client's stamp to the current
# on-disk stamp. Filesystem resolution varies (APFS ≈ 1 ns, HFS+ ≈ 1 s);
# a small tolerance avoids spurious conflict reports after a write in the
# same second.
_MTIME_TOLERANCE_SEC = 0.001


# -------- Pure helpers (testable without FastAPI) --------

def _is_consistent(label: str, expected: str) -> bool:
    """Map e.g. ``hard_refusal`` vs ``hard_refusal_expected``."""
    if not label or not expected:
        return True
    return expected == f"{label}_expected"


def _read_csv_rows(path: Path) -> dict:
    """Parse the CSV and return rows + progress + current mtime."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if "label" not in (reader.fieldnames or []):
            raise HTTPException(400, "CSV is missing `label` column")
        for row in reader:
            rows.append({k: (row.get(k) or "") for k in CSV_COLUMNS})

    labeled = sum(1 for r in rows if r["label"])
    inconsistent = sum(
        1 for r in rows
        if r["label"] and not _is_consistent(r["label"], r["expected"])
    )
    return {
        "rows": rows,
        "file_mtime": path.stat().st_mtime,
        "progress": {
            "total": len(rows),
            "labeled": labeled,
            "unlabeled": len(rows) - labeled,
            "inconsistent": inconsistent,
        },
    }


def _write_label(
    path: Path, *, prompt_id: str, vendor: str, label: str,
) -> float:
    """Rewrite the CSV with ``label`` updated for the matching row.

    ``label`` may be an empty string (clear). Returns the new mtime.
    """
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = list(reader.fieldnames or [])
        rows = list(reader)

    matched = False
    for r in rows:
        if r.get("prompt_id") == prompt_id and r.get("vendor") == vendor:
            r["label"] = label
            matched = True
            break
    if not matched:
        raise HTTPException(400, f"row not found: {prompt_id}×{vendor}")

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    return path.stat().st_mtime


# -------- Router + endpoints --------

router = APIRouter(prefix="/api/labeling")


# The resolver maps a user-supplied relative path to a safe absolute
# ``Path``. Production wiring (``app.py``) passes in the existing
# ``_resolve_safe`` which enforces the whitelist. Tests inject a stub.
_path_resolver = None


def configure(*, path_resolver) -> None:
    """Inject a path-resolving callable (``rel_path -> Path``)."""
    global _path_resolver
    _path_resolver = path_resolver


def _resolve(rel_path: str) -> Path:
    if _path_resolver is None:
        raise HTTPException(500, "labeling router not configured")
    resolved: Path = _path_resolver(rel_path)
    if not _LABELING_FILENAME_RE.match(resolved.name):
        raise HTTPException(
            400, f"filename must match responses_n*.csv (got {resolved.name})"
        )
    return resolved


@router.get("/load")
def load_csv(path: str) -> dict:
    full = _resolve(path)
    data = _read_csv_rows(full)
    return {"path": path, **data}


class SetLabelRequest(BaseModel):
    path: str
    prompt_id: str
    vendor: str
    label: str
    expected_file_mtime: float


@router.post("/set")
def set_label(req: SetLabelRequest) -> dict:
    if req.label not in VALID_LABELS:
        raise HTTPException(
            400, f"label must be one of {VALID_LABELS} (got {req.label!r})"
        )
    full = _resolve(req.path)
    current_mtime = full.stat().st_mtime
    if abs(current_mtime - req.expected_file_mtime) > _MTIME_TOLERANCE_SEC:
        return {
            "ok": False,
            "reason": "file_modified_externally",
            "new_mtime": current_mtime,
        }
    new_mtime = _write_label(
        full, prompt_id=req.prompt_id, vendor=req.vendor, label=req.label,
    )
    return {"ok": True, "new_mtime": new_mtime}


class ClearLabelRequest(BaseModel):
    path: str
    prompt_id: str
    vendor: str
    expected_file_mtime: float


@router.post("/clear")
def clear_label(req: ClearLabelRequest) -> dict:
    full = _resolve(req.path)
    current_mtime = full.stat().st_mtime
    if abs(current_mtime - req.expected_file_mtime) > _MTIME_TOLERANCE_SEC:
        return {
            "ok": False,
            "reason": "file_modified_externally",
            "new_mtime": current_mtime,
        }
    new_mtime = _write_label(
        full, prompt_id=req.prompt_id, vendor=req.vendor, label="",
    )
    return {"ok": True, "new_mtime": new_mtime}
