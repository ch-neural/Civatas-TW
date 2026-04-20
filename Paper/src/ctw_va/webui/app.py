"""FastAPI app for the civatas-exp webui."""
from __future__ import annotations

import csv as csv_mod
import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import jobs as jobs_mod
from . import labeling as labeling_mod
from . import spec as spec_mod
from . import status as status_mod
from ..adapter.clients import register_default_clients


STATIC_DIR = Path(__file__).parent / "static"
PAPER_ROOT = jobs_mod.PAPER_ROOT

ALL_VENDORS = ("openai", "gemini", "grok", "deepseek", "kimi")


app = FastAPI(title="CTW-VA-2026 WebUI", version="0.1.0")


class RunRequest(BaseModel):
    group: str
    subcommand: str
    # list[{flag, value, name?}]. Ordering matters for positional args.
    fields: list[dict]
    vendor: Optional[str] = None
    label: Optional[str] = None


@app.on_event("startup")
def _startup() -> None:
    jobs_mod.load_existing_jobs()


@app.get("/api/spec")
def get_spec() -> dict:
    """Full UI manifest: commands grouped by phase + vendor status."""
    registered = register_default_clients()
    return {
        "commands": spec_mod.COMMANDS,
        "category_intros": spec_mod.category_intros(),
        "vendors": [
            {
                "name": v,
                "available": v in registered,
                "env_key": _env_key_for(v),
            }
            for v in ALL_VENDORS
        ],
        "paper_root": str(PAPER_ROOT),
    }


def _env_key_for(vendor: str) -> str:
    return {
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "grok": "XAI_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "kimi": "MOONSHOT_API_KEY",
    }.get(vendor, "")


@app.post("/api/jobs")
def post_job(req: RunRequest) -> dict:
    # Validate group/subcommand against spec.
    match = [
        c for c in spec_mod.COMMANDS
        if c["group"] == req.group and c["subcommand"] == req.subcommand
    ]
    if not match:
        raise HTTPException(404, f"unknown command: {req.group} {req.subcommand}")
    cmd_spec = match[0]

    # Guard: only commands with supports_vendors may receive a vendor flag.
    vendor = req.vendor
    if vendor and not cmd_spec.get("supports_vendors"):
        vendor = None

    params = {"fields": req.fields}
    label = req.label or (
        f"{req.group} {req.subcommand}"
        + (f" [{vendor}]" if vendor else "")
    )

    job = jobs_mod.spawn_job(
        group=req.group, subcommand=req.subcommand,
        params=params, vendor=vendor, label=label,
    )
    return job.to_dict()


@app.get("/api/jobs")
def list_jobs(limit: int = 100) -> list[dict]:
    return jobs_mod.list_jobs(limit=limit)


@app.get("/api/status")
def get_status() -> dict:
    """Per-step completion state for the sidebar indicator + step banner."""
    return status_mod.compute_all_statuses()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    j = jobs_mod.get_job(job_id)
    if not j:
        raise HTTPException(404, f"job not found: {job_id}")
    return j


@app.get("/api/jobs/{job_id}/log")
def get_log(job_id: str, offset: int = 0) -> dict:
    if not jobs_mod.get_job(job_id):
        raise HTTPException(404, f"job not found: {job_id}")
    return jobs_mod.get_log(job_id, offset=offset)


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str) -> dict:
    ok = jobs_mod.cancel_job(job_id)
    if not ok:
        raise HTTPException(404, f"job not running: {job_id}")
    return {"cancelled": True}


# -------- Experiment stats (reads SQLite logs produced by runs) --------

@app.get("/api/experiments")
def list_experiments() -> list[dict]:
    """Enumerate runs/*/data.db and summarise each."""
    runs_dir = PAPER_ROOT / "runs"
    out: list[dict] = []
    if not runs_dir.exists():
        return out
    for sub in sorted(runs_dir.iterdir()):
        db = sub / "data.db"
        if not db.exists():
            continue
        out.append(_summarise_experiment(sub.name, db))
    return out


@app.get("/api/experiments/{experiment_id}")
def experiment_detail(experiment_id: str) -> dict:
    db = PAPER_ROOT / "runs" / experiment_id / "data.db"
    if not db.exists():
        raise HTTPException(404, f"experiment not found: {experiment_id}")
    summary = _summarise_experiment(experiment_id, db)
    summary["calls"] = _recent_calls(db, limit=50)
    return summary


def _summarise_experiment(experiment_id: str, db_path: Path) -> dict:
    """Aggregate vendor_call_log for a single experiment."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        by_vendor: dict[str, dict] = {}
        rows = conn.execute(
            "SELECT vendor, status, COUNT(*) AS n, "
            "       COALESCE(SUM(cost_usd),0) AS cost, "
            "       COALESCE(AVG(latency_ms),0) AS lat "
            "FROM vendor_call_log WHERE experiment_id = ? "
            "GROUP BY vendor, status",
            (experiment_id,),
        ).fetchall()
        for r in rows:
            v = r["vendor"]
            entry = by_vendor.setdefault(
                v, {"vendor": v, "calls": 0, "cost_usd": 0.0,
                     "avg_latency_ms": 0.0, "status_counts": {}}
            )
            entry["calls"] += r["n"]
            entry["cost_usd"] += r["cost"]
            # running avg (weighted)
            prev = entry["avg_latency_ms"]
            entry["avg_latency_ms"] = (
                (prev * (entry["calls"] - r["n"])) + (r["lat"] * r["n"])
            ) / max(1, entry["calls"])
            entry["status_counts"][r["status"]] = r["n"]
        total_cost = sum(v["cost_usd"] for v in by_vendor.values())
        total_calls = sum(v["calls"] for v in by_vendor.values())
    finally:
        conn.close()
    return {
        "experiment_id": experiment_id,
        "db_path": str(db_path),
        "total_cost_usd": round(total_cost, 6),
        "total_calls": total_calls,
        "vendors": sorted(by_vendor.values(), key=lambda x: -x["cost_usd"]),
    }


def _recent_calls(db_path: Path, limit: int = 50) -> list[dict]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT call_id, persona_id, sim_day, vendor, model_id, status, "
            "       cost_usd, latency_ms, tokens_in, tokens_out "
            "FROM vendor_call_log ORDER BY rowid DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


# -------- File preview + download --------

_ALLOWED_ROOTS = (
    PAPER_ROOT / "experiments",
    PAPER_ROOT / "runs",
    PAPER_ROOT / "data",
)


def _resolve_safe(rel_path: str) -> Path:
    """Resolve ``rel_path`` against PAPER_ROOT and reject paths outside allowed
    roots (no ``../`` escape into user's home or system files)."""
    full = (PAPER_ROOT / rel_path).resolve()
    root_resolved = PAPER_ROOT.resolve()
    if not str(full).startswith(str(root_resolved) + os.sep):
        raise HTTPException(403, "path outside workspace")
    if not any(
        str(full).startswith(str(r.resolve()) + os.sep) or str(full) == str(r.resolve())
        for r in _ALLOWED_ROOTS
    ):
        raise HTTPException(403, "path outside allowed roots (experiments / runs / data)")
    if not full.exists():
        raise HTTPException(404, f"not found: {rel_path}")
    if not full.is_file():
        raise HTTPException(400, "not a regular file")
    return full


@app.get("/api/file")
def download_file(path: str) -> FileResponse:
    full = _resolve_safe(path)
    # Serve raw bytes; browser decides download vs inline via Content-Disposition.
    return FileResponse(
        str(full),
        filename=full.name,
        media_type="application/octet-stream",
    )


@app.get("/api/preview")
def preview_file(path: str, limit: int = 100) -> dict:
    """Parse first N rows of a CSV or JSONL file and return as JSON.

    CSV is read with UTF-8-BOM (Excel-friendly). JSONL is parsed line-by-line.
    Other formats return 415.
    """
    full = _resolve_safe(path)
    suffix = full.suffix.lower()
    size = full.stat().st_size

    if suffix == ".csv":
        rows: list[dict] = []
        truncated = False
        with full.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv_mod.DictReader(f)
            headers = list(reader.fieldnames or [])
            for i, row in enumerate(reader):
                if i >= limit:
                    truncated = True
                    break
                rows.append(row)
        return {
            "format": "csv", "path": path, "size": size,
            "headers": headers, "rows": rows,
            "row_count_shown": len(rows), "truncated": truncated,
        }

    if suffix == ".jsonl":
        rows = []
        headers_order: list[str] = []
        seen: set = set()
        truncated = False
        with full.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if len(rows) >= limit:
                    truncated = True
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
                for k in obj.keys():
                    if k not in seen:
                        seen.add(k)
                        headers_order.append(k)
                rows.append(obj)
        return {
            "format": "jsonl", "path": path, "size": size,
            "headers": headers_order, "rows": rows,
            "row_count_shown": len(rows), "truncated": truncated,
        }

    if suffix in (".txt", ".md", ".sha256", ".log"):
        text = full.read_text(encoding="utf-8", errors="replace")
        return {"format": "text", "path": path, "size": size, "text": text[:50_000]}

    if suffix == ".json":
        try:
            obj = json.loads(full.read_text(encoding="utf-8"))
            return {"format": "json", "path": path, "size": size, "data": obj}
        except json.JSONDecodeError as e:
            raise HTTPException(500, f"invalid JSON: {e}")

    raise HTTPException(415, f"unsupported preview format: {suffix}")


@app.get("/api/path-exists")
def path_exists(path: str) -> dict:
    """Cheap existence check — used by UI to decide whether to render a preview link."""
    try:
        full = _resolve_safe(path)
    except HTTPException as e:
        if e.status_code == 404:
            return {"exists": False, "path": path}
        raise
    return {
        "exists": True, "path": path,
        "size": full.stat().st_size, "mtime": full.stat().st_mtime,
    }


# -------- Labeling router (calibration CSV in-browser labeler) --------

labeling_mod.configure(path_resolver=_resolve_safe)
app.include_router(labeling_mod.router)


# -------- Static index --------

@app.get("/")
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.ico")
def favicon() -> JSONResponse:
    return JSONResponse({}, status_code=204)
