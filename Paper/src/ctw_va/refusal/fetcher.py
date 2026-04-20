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


async def _fetch_responses_async(
    prompts: list[PromptSpec],
    vendors: list[str],
    seed: int,
    on_progress=None,
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
            if isinstance(resp, Exception):
                rows.append({
                    "prompt_id": p.prompt_id, "vendor": v,
                    "prompt_text": p.text, "expected": p.expected, "topic": p.topic,
                    "status": "error", "response_text": "",
                    "error_detail": f"{type(resp).__name__}: {resp}",
                    "model_id": "", "cost_usd": 0.0, "latency_ms": 0,
                    "tokens_in": 0, "tokens_out": 0,
                    "label": "",  # human fills this
                })
            else:
                rows.append({
                    "prompt_id": p.prompt_id, "vendor": v,
                    "prompt_text": p.text, "expected": p.expected, "topic": p.topic,
                    "status": resp.status, "response_text": resp.raw_text,
                    "error_detail": resp.error_detail or "",
                    "model_id": resp.model_id, "cost_usd": resp.cost_usd,
                    "latency_ms": resp.latency_ms,
                    "tokens_in": resp.input_tokens, "tokens_out": resp.output_tokens,
                    "label": "",
                })
            print(f"[{done}/{total}] {p.prompt_id} × {v}: "
                  f"{rows[-1]['status']} · ${rows[-1]['cost_usd']:.5f} · "
                  f"{rows[-1]['latency_ms']}ms", flush=True)
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

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    rows = asyncio.run(_fetch_responses_async(prompts, vendors, seed))
    elapsed = time.monotonic() - t0

    with open(output_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

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
    return {
        "count": len(rows), "cost_usd": total_cost,
        "ok": ok, "err": err, "elapsed_s": elapsed,
    }
