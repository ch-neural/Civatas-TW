"""Fan-out prompt × vendor calls and persist responses for annotation.

For each selected prompt, call each selected vendor with a fixed
(neutral) system prompt. Persist one JSONL row per (prompt, vendor)
pair. Downstream: CSV export → human annotate → train classifier.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Iterable

from ..adapter.client import VendorResponse
from ..adapter.clients import register_default_clients
from .prompts import PromptSpec, stratified_sample


SYSTEM_PROMPT = (
    "You are a helpful assistant. Please answer the user's question in "
    "Traditional Chinese (繁體中文). Keep your reply under 150 Chinese "
    "characters."
)


async def _call_one(client, system: str, user: str, seed: int) -> VendorResponse:
    # Vendor client already handles retries + error mapping.
    return await client.chat(system, user, seed)


def _row_from_response(p: PromptSpec, v: str, resp) -> dict:
    """Build a JSONL row from either a VendorResponse or an Exception."""
    if isinstance(resp, Exception):
        return {
            "prompt_id": p.prompt_id, "vendor": v,
            "prompt_text": p.text, "expected": p.expected, "topic": p.topic,
            "status": "error", "response_text": "",
            "error_detail": f"{type(resp).__name__}: {resp}",
            "model_id": "", "cost_usd": 0.0, "latency_ms": 0,
            "tokens_in": 0, "tokens_out": 0,
            "label": "",
        }
    return {
        "prompt_id": p.prompt_id, "vendor": v,
        "prompt_text": p.text, "expected": p.expected, "topic": p.topic,
        "status": resp.status, "response_text": resp.raw_text,
        "error_detail": resp.error_detail or "",
        "model_id": resp.model_id, "cost_usd": resp.cost_usd,
        "latency_ms": resp.latency_ms,
        "tokens_in": resp.input_tokens, "tokens_out": resp.output_tokens,
        "label": "",
    }


def _flush_rows(rows: list[dict], path: Path) -> None:
    """Atomic flush: write to .tmp then rename. Kill-safe — partial file
    never shown to external readers."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(path)


async def _fetch_responses_async(
    prompts: list[PromptSpec],
    vendors: list[str],
    seed: int,
    on_progress=None,
    flush_path: Path | None = None,
) -> list[dict]:
    registered = register_default_clients()
    clients = {v: registered[v] for v in vendors if v in registered}
    missing = [v for v in vendors if v not in clients]
    if missing:
        print(f"[warn] skipping vendors with missing API key: {missing}", flush=True)
    if not clients:
        raise RuntimeError("No vendors available — check API keys in .env")

    total = len(prompts) * len(clients)
    done = 0
    rows: list[dict] = []

    for p in prompts:
        # Fan out to all vendors in parallel per-prompt (preserves prompt order in output).
        tasks = {
            v: asyncio.create_task(_call_one(c, SYSTEM_PROMPT, p.text, seed))
            for v, c in clients.items()
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for (v, _), resp in zip(tasks.items(), results):
            done += 1
            row = _row_from_response(p, v, resp)
            rows.append(row)
            print(f"[{done}/{total}] {p.prompt_id} × {v}: "
                  f"{row['status']} · ${row['cost_usd']:.5f} · "
                  f"{row['latency_ms']}ms", flush=True)
        # Incremental flush: after every prompt's fan-out (5 rows), write to
        # disk so ^C / crash / network drop doesn't lose hours of API spend.
        if flush_path is not None:
            _flush_rows(rows, flush_path)
    return rows


def fetch(
    n: int,
    vendors: Iterable[str],
    output_path: str,
    seed: int = 20240113,
) -> dict:
    """Synchronous entry point used by the CLI."""
    from dotenv import load_dotenv
    load_dotenv()

    vendors = [v.strip() for v in vendors if v.strip()]
    prompts = stratified_sample(n=n, seed=seed)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    rows = asyncio.run(_fetch_responses_async(
        prompts, vendors, seed, flush_path=out,
    ))
    elapsed = time.monotonic() - t0
    _flush_rows(rows, out)  # final flush ensures last partial batch is written

    total_cost = sum(r["cost_usd"] for r in rows)
    ok = sum(1 for r in rows if r["status"] == "ok")
    err = sum(1 for r in rows if r["status"] == "error")
    print(
        f"\n✓ Fetched {len(rows)} responses in {elapsed:.1f}s, "
        f"total cost ${total_cost:.4f} ({ok} ok / {err} err)\n"
        f"  Output: {output_path}\n"
        f"  Next: civatas-exp calibration export --input {output_path} "
        f"--output <csv>",
        flush=True,
    )
    if err > 0:
        print(f"  Or first: civatas-exp calibration retry-errors "
              f"--input {output_path}  # 重抓 {err} 筆 error",
              flush=True)
    return {
        "count": len(rows), "cost_usd": total_cost,
        "ok": ok, "err": err, "elapsed_s": elapsed,
    }


async def _retry_errors_async(
    error_rows: list[dict],
    seed: int,
    flush_callback=None,
) -> tuple[list[dict], list[dict]]:
    """Re-call each errored row. Returns (recovered_rows, still_errored_rows)."""
    registered = register_default_clients()
    # Group vendors we actually need (from error_rows) and check availability.
    needed_vendors = sorted({r["vendor"] for r in error_rows})
    clients = {v: registered[v] for v in needed_vendors if v in registered}
    missing = [v for v in needed_vendors if v not in clients]
    if missing:
        print(f"[warn] skipping vendors with missing API key: {missing}", flush=True)

    total = len(error_rows)
    recovered: list[dict] = []
    still_err: list[dict] = []

    for i, orig in enumerate(error_rows, 1):
        v = orig["vendor"]
        if v not in clients:
            still_err.append(orig)
            print(f"[{i}/{total}] {orig['prompt_id']} × {v}: skipped "
                  f"(no API key)", flush=True)
            continue
        p = PromptSpec(
            prompt_id=orig["prompt_id"],
            text=orig["prompt_text"],
            expected=orig.get("expected", ""),
            topic=orig.get("topic", ""),
        )
        try:
            resp = await _call_one(clients[v], SYSTEM_PROMPT, p.text, seed)
        except Exception as e:
            resp = e
        new_row = _row_from_response(p, v, resp)
        # Preserve pre-existing human label (defensive — errors usually have
        # no label, but if a later step backfilled, don't wipe it).
        if orig.get("label"):
            new_row["label"] = orig["label"]
        if new_row["status"] == "ok":
            recovered.append(new_row)
        else:
            still_err.append(new_row)
        status = new_row["status"]
        badge = "✓" if status == "ok" else "✗"
        print(f"[{i}/{total}] {p.prompt_id} × {v}: {badge} {status} · "
              f"${new_row['cost_usd']:.5f} · {new_row['latency_ms']}ms",
              flush=True)
        if flush_callback is not None:
            flush_callback(recovered, still_err)
    return recovered, still_err


def retry_errors(
    input_path: str,
    output_path: str | None = None,
    seed: int = 20240113,
) -> dict:
    """Re-fetch only rows with status='error' from an existing JSONL.

    Output preserves order: rows that were ok stay put; error rows are
    replaced in-place by their retry outcome (success row OR updated error).
    """
    from dotenv import load_dotenv
    load_dotenv()

    in_path = Path(input_path)
    out_path = Path(output_path) if output_path else in_path

    # Load all rows preserving order
    all_rows: list[dict] = []
    with in_path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                all_rows.append(json.loads(line))

    # Indexes of error rows (original positions)
    err_indices = [i for i, r in enumerate(all_rows) if r.get("status") == "error"]
    if not err_indices:
        print(f"✓ No status=error rows in {in_path} — nothing to retry.",
              flush=True)
        return {"retried": 0, "recovered": 0, "still_err": 0, "cost_usd": 0.0}

    # Per-vendor breakdown
    from collections import Counter
    by_vendor = Counter(all_rows[i]["vendor"] for i in err_indices)
    print(f"Found {len(err_indices)} errored rows across {len(by_vendor)} vendors:",
          flush=True)
    for v in ["openai", "gemini", "grok", "deepseek", "kimi"]:
        if by_vendor.get(v):
            print(f"  {v:9} {by_vendor[v]:4}", flush=True)
    print(flush=True)

    err_rows_in_order = [all_rows[i] for i in err_indices]

    # Flush callback: replace errored rows in all_rows with latest attempts,
    # persist incrementally so ^C preserves progress.
    attempted_so_far: dict[tuple[str, str], dict] = {}  # (pid, vendor) -> new row

    def _flush(recovered, still_err):
        # Merge both lists; index by (prompt_id, vendor) so latest wins
        for r in recovered + still_err:
            attempted_so_far[(r["prompt_id"], r["vendor"])] = r
        # Reconstruct full row list with updates applied
        merged = list(all_rows)
        for i in err_indices:
            key = (merged[i]["prompt_id"], merged[i]["vendor"])
            if key in attempted_so_far:
                merged[i] = attempted_so_far[key]
        _flush_rows(merged, out_path)

    t0 = time.monotonic()
    recovered, still_err = asyncio.run(_retry_errors_async(
        err_rows_in_order, seed, flush_callback=_flush,
    ))
    elapsed = time.monotonic() - t0
    _flush(recovered, still_err)  # final persist

    cost = sum(r.get("cost_usd", 0.0) for r in recovered + still_err)
    print(
        f"\n✓ Retried {len(err_rows_in_order)} rows in {elapsed:.1f}s, "
        f"cost ${cost:.4f}\n"
        f"  Recovered: {len(recovered)} ({len(recovered)/len(err_rows_in_order):.0%})\n"
        f"  Still error: {len(still_err)}  "
        f"(likely permanent — content filter / auth / etc)\n"
        f"  Output: {out_path}",
        flush=True,
    )
    if still_err:
        # Show a per-vendor breakdown of permanent failures — usually Kimi
        # content-policy rejections, which themselves ARE data for the paper.
        from collections import Counter
        still_by_v = Counter(r["vendor"] for r in still_err)
        print("  Permanent failures per vendor:", flush=True)
        for v, n in still_by_v.most_common():
            print(f"    {v}: {n}", flush=True)
    return {
        "retried": len(err_rows_in_order),
        "recovered": len(recovered),
        "still_err": len(still_err),
        "cost_usd": cost,
        "elapsed_s": elapsed,
    }
