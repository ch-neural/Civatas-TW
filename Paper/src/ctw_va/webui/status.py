"""Step-completion detection for the webui sidebar / banner.

For each CLI step we answer: "is this already done?"

Four states:
  - done      : evidence exists (output file and/or successful job)
  - ready     : prereqs met, no evidence of prior run
  - blocked   : missing env var or upstream step not done
  - stub      : not yet implemented (spec marked is_stub)
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from . import jobs as jobs_mod
from . import spec as spec_mod


PAPER_ROOT = jobs_mod.PAPER_ROOT


def _env_is_set(key: str) -> bool:
    v = os.environ.get(key, "").strip()
    return bool(v and v not in ("sk_xxx", "changeme"))


def _check_env_label(label: str) -> tuple[bool, list[str]]:
    """Map a human 'what' label to concrete env var checks.

    Returns (all_present, missing_keys).
    """
    # Aliases
    if label == "SERPER_API_KEY":
        return (_env_is_set("SERPER_API_KEY"), [] if _env_is_set("SERPER_API_KEY") else ["SERPER_API_KEY"])
    if "5 家 vendor" in label or "vendor API" in label:
        vendor_keys = [
            "OPENAI_API_KEY", "GEMINI_API_KEY",
            "XAI_API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY",
        ]
        missing = [k for k in vendor_keys if not _env_is_set(k)]
        return (len(missing) == 0, missing)
    return (True, [])


def _file_evidence(path_str: str) -> dict | None:
    """Check if an output path (possibly templated) exists."""
    if path_str.startswith("(") or path_str == "(stdout)":
        return None  # non-file output — ignore for detection
    p = PAPER_ROOT / path_str
    # Handle templated paths like slate_seed{SEED}_n{N}.jsonl → glob parent.
    if "{" in path_str:
        parent = p.parent
        if not parent.exists():
            return None
        # Use the filename template to build a glob pattern.
        import re
        pattern = re.sub(r"\{[^}]+\}", "*", p.name)
        candidates = sorted(
            (m for m in parent.glob(pattern) if m.is_file() and m.stat().st_size > 0),
            key=lambda m: m.stat().st_mtime, reverse=True,
        )
        if candidates:
            return {
                "path": str(candidates[0].relative_to(PAPER_ROOT)),
                "size": candidates[0].stat().st_size,
                "mtime": candidates[0].stat().st_mtime,
            }
        return None
    if p.exists() and p.is_file() and p.stat().st_size > 0:
        return {
            "path": path_str,
            "size": p.stat().st_size,
            "mtime": p.stat().st_mtime,
        }
    return None


def _has_any_data_db() -> dict | None:
    """Any runs/<id>/data.db with at least one vendor_call_log row?"""
    runs = PAPER_ROOT / "runs"
    if not runs.exists():
        return None
    for sub in runs.iterdir():
        db = sub / "data.db"
        if not db.exists():
            continue
        try:
            conn = sqlite3.connect(str(db))
            row = conn.execute(
                "SELECT COUNT(*) FROM vendor_call_log"
            ).fetchone()
            conn.close()
            if row and row[0] > 0:
                return {"experiment_id": sub.name, "calls": row[0]}
        except sqlite3.Error:
            continue
    return None


def _last_successful_job(group: str, subcommand: str, jobs: list[dict]) -> dict | None:
    """Find the most recent done job for this command."""
    for j in jobs:  # already sorted desc by list_jobs
        if (j.get("group") == group
                and j.get("subcommand") == subcommand
                and j.get("status") == "done"):
            return {
                "job_id": j["job_id"],
                "ended_at": j.get("ended_at"),
                "duration_s": j.get("duration_s"),
            }
    return None


def compute_all_statuses() -> dict[str, dict]:
    """Return {"group/subcommand": {state, evidence, blocked_by, ...}} for all steps."""
    out: dict[str, dict] = {}
    # Pull full job history once.
    all_jobs = jobs_mod.list_jobs(limit=500)

    # Pass 1: file evidence + job evidence + env check (no upstream step deps yet)
    for c in spec_mod.COMMANDS:
        key = f"{c['group']}/{c['subcommand']}"
        if c.get("is_stub"):
            out[key] = {"state": "stub", "evidence": [], "blocked_by": []}
            continue

        evidence: list[dict] = []
        # Output-file presence
        for o in c.get("outputs", []):
            fe = _file_evidence(o.get("path", ""))
            if fe:
                evidence.append({"kind": "file", **fe})

        # Successful job in history
        lj = _last_successful_job(c["group"], c["subcommand"], all_jobs)
        if lj:
            evidence.append({"kind": "job", **lj})

        # For cost/* — evidence is "any data.db exists"
        if c["group"] == "cost":
            db_info = _has_any_data_db()
            if db_info and not evidence:
                # We can run cost, but haven't literally run it yet → ready, not done
                pass

        # env-level blocked_by
        blocked_by: list[dict] = []
        for dep in c.get("depends_on", []):
            if dep.get("kind") == "env":
                ok, missing = _check_env_label(dep.get("what", ""))
                if not ok:
                    blocked_by.append({
                        "kind": "env", "what": dep["what"],
                        "missing": missing,
                        "note": dep.get("note", ""),
                    })

        out[key] = {
            "state": "done" if evidence else "ready",
            "evidence": evidence,
            "blocked_by": blocked_by,
        }

    # Pass 2: propagate upstream step blockage
    # A step is blocked if any of its depends_on{kind:step} target is not done.
    for c in spec_mod.COMMANDS:
        key = f"{c['group']}/{c['subcommand']}"
        if out[key]["state"] in ("done", "stub"):
            continue
        step_blocks: list[dict] = []
        for dep in c.get("depends_on", []):
            if dep.get("kind") != "step":
                continue
            dep_key = dep.get("what", "")
            dep_state = out.get(dep_key, {}).get("state")
            if dep_state != "done":
                step_blocks.append({
                    "kind": "step",
                    "what": dep_key,
                    "state": dep_state or "unknown",
                    "note": dep.get("note", ""),
                })
        if step_blocks:
            out[key]["blocked_by"].extend(step_blocks)
            out[key]["state"] = "blocked"
        elif out[key]["blocked_by"]:
            # Still has env blocks
            out[key]["state"] = "blocked"

    return out
