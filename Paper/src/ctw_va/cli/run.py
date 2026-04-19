"""CLI: civatas-exp run ..."""
from __future__ import annotations

import asyncio

import click

from ..adapter.router import VendorRouter
from ..adapter.clients import register_default_clients
from ..storage import db as storage_db


@click.group("run")
def run():
    """Experiment execution (Phase C4-C5)."""
    pass


@run.command("smoke-test")
@click.option("--experiment-id", default="smoke-test")
@click.option("--vendors", default="openai,gemini,grok,deepseek,kimi")
def smoke_test_cmd(experiment_id, vendors):
    """Make ONE multivendor call (~USD 0.001) to verify all clients work."""
    from dotenv import load_dotenv
    load_dotenv()

    vendors_list = [v.strip() for v in vendors.split(",") if v.strip()]
    storage_db.set_db_path(f"runs/{experiment_id}/data.db")

    async def _run():
        registered = register_default_clients()
        missing = [v for v in vendors_list if v not in registered]
        if missing:
            click.echo(f"Warning: Missing API keys for: {missing}. Will skip.")
            vendors_list[:] = [v for v in vendors_list if v in registered]
        if not vendors_list:
            click.echo("No vendors available (check .env)")
            return

        router = VendorRouter(clients=registered)
        result = await router.chat_multivendor(
            vendors=vendors_list,
            system_prompt="You are a test assistant.",
            user_prompt="Reply with exactly: 'Smoke test passed.'",
            seed=42,
            experiment_id=experiment_id,
            persona_id="smoke",
            sim_day=0,
        )

        click.echo(f"prompt_hash: {result.prompt_hash}")
        for v, r in result.results.items():
            marker = "OK" if r.status == "ok" else "FAIL"
            click.echo(f"  [{marker}] {v}: status={r.status}, "
                       f"cost=${r.cost_usd:.5f}, "
                       f"reply={r.raw_text[:60]!r}")
            if r.status == "error":
                click.echo(f"     error: {r.error_detail}")

    asyncio.run(_run())
