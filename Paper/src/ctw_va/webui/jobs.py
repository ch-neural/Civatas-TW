"""Subprocess job manager for civatas-exp webui.

Each button press spawns one subprocess (``python -m ctw_va.cli <group>
<subcommand> ...``) running in the Paper/ working directory so relative
paths (experiments/, runs/) resolve as the CLI expects. Stdout + stderr
are teed to a per-job log file. Jobs persist on disk so the history
survives server restarts.
"""
from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


# Paper/ root (the package lives at Paper/src/ctw_va/webui)
PAPER_ROOT = Path(__file__).resolve().parents[3]
JOBS_DIR = PAPER_ROOT / "runs" / "webui" / "jobs"
JOBS_INDEX = PAPER_ROOT / "runs" / "webui" / "jobs.jsonl"


@dataclass
class Job:
    job_id: str
    group: str
    subcommand: str
    cmd: list[str]
    vendor: Optional[str] = None        # explicit single-vendor tag
    status: str = "pending"              # pending / running / done / error / cancelled
    return_code: Optional[int] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    log_path: str = ""
    params: dict = field(default_factory=dict)
    pid: Optional[int] = None
    label: str = ""                      # short UI label

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_s"] = (
            (self.ended_at or time.time()) - self.started_at
            if self.started_at else None
        )
        return d


# In-memory registry (job_id -> Job). Populated from disk on startup.
_JOBS: dict[str, Job] = {}
_JOBS_LOCK = threading.Lock()
_PROCS: dict[str, subprocess.Popen] = {}


def _ensure_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _persist(job: Job) -> None:
    """Append the job's current state to jobs.jsonl (simple audit log)."""
    _ensure_dirs()
    with JOBS_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(job.to_dict(), ensure_ascii=False) + "\n")


def load_existing_jobs() -> None:
    """Rebuild _JOBS from jobs.jsonl so history survives restarts."""
    _ensure_dirs()
    if not JOBS_INDEX.exists():
        return
    latest: dict[str, dict] = {}
    for line in JOBS_INDEX.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            latest[rec["job_id"]] = rec
        except Exception:
            continue
    with _JOBS_LOCK:
        for jid, rec in latest.items():
            rec.pop("duration_s", None)
            # Any job still marked running at startup is dead — mark as error.
            if rec.get("status") in ("pending", "running"):
                rec["status"] = "error"
                rec["return_code"] = -1
            _JOBS[jid] = Job(**rec)


def list_jobs(limit: int = 100) -> list[dict]:
    with _JOBS_LOCK:
        items = sorted(
            _JOBS.values(),
            key=lambda j: j.started_at or 0,
            reverse=True,
        )[:limit]
    return [j.to_dict() for j in items]


def get_job(job_id: str) -> Optional[dict]:
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
    return j.to_dict() if j else None


def get_log(job_id: str, offset: int = 0, max_bytes: int = 200_000) -> dict:
    """Return a chunk of the job's log starting at ``offset``."""
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
    if not j or not j.log_path:
        return {"offset": offset, "next_offset": offset, "chunk": "", "size": 0}
    p = Path(j.log_path)
    if not p.exists():
        return {"offset": offset, "next_offset": offset, "chunk": "", "size": 0}
    size = p.stat().st_size
    if offset >= size:
        return {"offset": offset, "next_offset": size, "chunk": "", "size": size}
    with p.open("rb") as f:
        f.seek(offset)
        data = f.read(max_bytes)
    # If we truncated mid-utf8, trim trailing bytes until decodable.
    text = ""
    for trim in range(min(4, len(data))):
        try:
            text = data[: len(data) - trim].decode("utf-8") if trim else data.decode("utf-8")
            break
        except UnicodeDecodeError:
            continue
    return {
        "offset": offset,
        "next_offset": offset + len(text.encode("utf-8")),
        "chunk": text,
        "size": size,
    }


def spawn_job(
    group: str,
    subcommand: str,
    params: dict,
    vendor: Optional[str] = None,
    label: str = "",
) -> Job:
    """Build argv and fire-and-forget a subprocess.

    ``vendor``: if set, the command will receive ``--vendors <vendor>`` so
    it only calls that single endpoint. ``None`` means "don't inject vendor
    flag"; the spec decides if the command supports it.
    """
    _ensure_dirs()
    job_id = uuid.uuid4().hex[:12]

    argv = [sys.executable, "-m", "ctw_va.cli", group, subcommand]
    argv += _build_flags(params)
    if vendor:
        argv += ["--vendors", vendor]

    log_path = JOBS_DIR / f"{job_id}.log"
    job = Job(
        job_id=job_id, group=group, subcommand=subcommand, cmd=argv,
        vendor=vendor, status="running", started_at=time.time(),
        log_path=str(log_path), params=params, label=label,
    )
    with _JOBS_LOCK:
        _JOBS[job_id] = job

    # Launch asynchronously (Popen returns immediately).
    log_f = log_path.open("wb")
    log_f.write(
        f"$ {shlex.join(argv)}\n".encode("utf-8")
    )
    log_f.flush()
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    try:
        proc = subprocess.Popen(
            argv, cwd=str(PAPER_ROOT),
            stdout=log_f, stderr=subprocess.STDOUT,
            env=env, start_new_session=True,
        )
    except Exception as e:
        log_f.write(f"[spawn-error] {e}\n".encode("utf-8"))
        log_f.close()
        job.status = "error"
        job.return_code = -1
        job.ended_at = time.time()
        _persist(job)
        return job

    job.pid = proc.pid
    with _JOBS_LOCK:
        _PROCS[job_id] = proc
    _persist(job)

    # Reaper thread closes log + marks job done when process exits.
    t = threading.Thread(
        target=_reap, args=(job_id, proc, log_f), daemon=True,
    )
    t.start()
    return job


def _reap(job_id: str, proc: subprocess.Popen, log_f) -> None:
    rc = proc.wait()
    log_f.flush()
    log_f.close()
    with _JOBS_LOCK:
        j = _JOBS.get(job_id)
        if j is None:
            return
        j.return_code = rc
        j.ended_at = time.time()
        if j.status == "cancelled":
            pass
        else:
            j.status = "done" if rc == 0 else "error"
        _PROCS.pop(job_id, None)
    _persist(j)


def cancel_job(job_id: str) -> bool:
    with _JOBS_LOCK:
        proc = _PROCS.get(job_id)
        j = _JOBS.get(job_id)
    if not proc or not j:
        return False
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            return False
    with _JOBS_LOCK:
        j.status = "cancelled"
    return True


def _build_flags(params: dict) -> list[str]:
    """Convert params dict -> click-style argv chunks.

    Keys whose ``flag`` is empty are treated as positional. Empty strings
    and None are skipped (lets the CLI fall back to its own default).
    Booleans render as bare ``--flag`` when True, skip entirely when False.

    Defensive: the frontend *should* coerce bool-typed fields via
    ``_coerce`` before POSTing, but a stale browser spec cache can result
    in string ``"true"`` / ``"false"`` slipping through. We treat those
    case-insensitively as booleans here so the resulting argv is always
    click-compatible regardless of frontend state.

    The webui posts a list of ``{flag, value, positional}`` so we can
    preserve positional ordering; we honour that shape here.
    """
    argv: list[str] = []
    positionals: list[str] = []
    for item in params.get("fields", []):
        flag = item.get("flag", "")
        val = item.get("value", "")
        if val in (None, ""):
            continue
        # Defensive: stringly-typed "true"/"false" arrive when a stale
        # browser cache renders an is_flag field as a text/select without
        # coercion. Normalise before the bool branch below.
        if isinstance(val, str) and val.strip().lower() in ("true", "false"):
            val = (val.strip().lower() == "true")
        if flag == "":
            positionals.append(str(val))
        elif isinstance(val, bool):
            if val:
                argv.append(flag)
        else:
            argv.extend([flag, str(val)])
    return argv + positionals
