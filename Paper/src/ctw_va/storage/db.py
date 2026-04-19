"""SQLite storage for experiment_run / vendor_call_log / agent_day_vendor."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from ..adapter.client import VendorResponse


_DB_PATH: Path | None = None


def set_db_path(path: str | Path) -> None:
    global _DB_PATH
    _DB_PATH = Path(path)
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_db_path() -> Path:
    if _DB_PATH is None:
        # Default: runs/default/data.db (user should override)
        default = Path("runs/default/data.db")
        default.parent.mkdir(parents=True, exist_ok=True)
        return default
    return _DB_PATH


@contextmanager
def connection():
    """Context-managed SQLite connection with schema auto-init."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    # Auto-init schema if empty
    schema_path = Path(__file__).parent / "schema.sql"
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    try:
        yield conn
    finally:
        conn.commit()
        conn.close()


def log_vendor_call(
    *, call_id: str, experiment_id: str, persona_id: str, sim_day: int,
    vendor: str, model_id: str, articles_shown: list, prompt_hash: str,
    response: VendorResponse,
) -> None:
    """Insert a row into vendor_call_log. Creates experiment_run row if missing."""
    with connection() as conn:
        # Ensure experiment_run exists (minimal row; real metadata written by run.py)
        conn.execute(
            "INSERT OR IGNORE INTO experiment_run "
            "(experiment_id, persona_slate_id, news_pool_id, scenario, replication_seed, pipeline_version) "
            "VALUES (?, '', '', '', 0, 'dev')",
            (experiment_id,),
        )
        conn.execute(
            "INSERT INTO vendor_call_log "
            "(call_id, experiment_id, persona_id, sim_day, vendor, model_id, "
            " articles_shown, prompt_hash, response_raw, refusal_status, "
            " latency_ms, tokens_in, tokens_out, cost_usd, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                call_id, experiment_id, persona_id, sim_day, vendor, model_id,
                json.dumps(articles_shown, ensure_ascii=False),
                prompt_hash,
                response.raw_text,
                None,  # refusal_status filled by refusal pipeline (Phase C2)
                response.latency_ms,
                response.input_tokens,
                response.output_tokens,
                response.cost_usd,
                response.status,
            ),
        )


def total_cost(experiment_id: str) -> float:
    """Return cumulative USD spent on an experiment."""
    with connection() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM vendor_call_log WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        return float(row["s"])


def cost_by_vendor(experiment_id: str) -> dict[str, float]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT vendor, COALESCE(SUM(cost_usd), 0) AS s "
            "FROM vendor_call_log WHERE experiment_id = ? GROUP BY vendor",
            (experiment_id,),
        ).fetchall()
        return {r["vendor"]: float(r["s"]) for r in rows}


def call_count(experiment_id: str) -> dict[str, int]:
    """Counts by status."""
    with connection() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS c FROM vendor_call_log WHERE experiment_id = ? GROUP BY status",
            (experiment_id,),
        ).fetchall()
        return {r["status"]: int(r["c"]) for r in rows}
