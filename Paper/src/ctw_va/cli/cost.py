"""CLI: civatas-exp cost ..."""
from __future__ import annotations

import click

from ..storage import db as storage_db
from ..adapter.router import VendorRouter


@click.group("cost")
def cost():
    """Cost estimation and budget tracking (Phase B5)."""
    pass


@cost.command("burn")
@click.option("--experiment-id", required=True)
@click.option("--db", type=click.Path(), default=None,
              help="SQLite DB path (default: runs/<experiment_id>/data.db)")
def burn_cmd(experiment_id, db):
    """Print current cost burn + budget status."""
    if db:
        storage_db.set_db_path(db)
    else:
        storage_db.set_db_path(f"runs/{experiment_id}/data.db")
    spent = storage_db.total_cost(experiment_id)
    by_v = storage_db.cost_by_vendor(experiment_id)
    counts = storage_db.call_count(experiment_id)
    cap = VendorRouter.HARD_BUDGET_USD
    click.echo(f"Experiment: {experiment_id}")
    click.echo(f"  Spent:     ${spent:.4f}")
    click.echo(f"  Budget:    ${cap:.2f}")
    click.echo(f"  Remaining: ${cap - spent:.2f} ({100 * spent / cap:.1f}% used)")
    click.echo(f"\nBy vendor:")
    for v, s in sorted(by_v.items(), key=lambda x: -x[1]):
        click.echo(f"  {v}: ${s:.4f}")
    click.echo(f"\nCall status:")
    for st, c in sorted(counts.items()):
        click.echo(f"  {st}: {c}")


@cost.command("forecast")
@click.option("--experiment-id", required=True)
@click.option("--total-calls-planned", type=int, required=True)
def forecast_cmd(experiment_id, total_calls_planned):
    """Estimate remaining cost from average-so-far."""
    storage_db.set_db_path(f"runs/{experiment_id}/data.db")
    spent = storage_db.total_cost(experiment_id)
    counts = storage_db.call_count(experiment_id)
    done = sum(counts.values())
    if done == 0:
        click.echo("No calls yet — can't forecast.")
        return
    avg = spent / done
    remaining = total_calls_planned - done
    forecast = avg * remaining
    click.echo(f"Done: {done} calls, avg ${avg:.5f}/call")
    click.echo(f"Remaining: {remaining} calls × ${avg:.5f} = ${forecast:.2f}")
    click.echo(f"Projected total: ${spent + forecast:.2f}")
