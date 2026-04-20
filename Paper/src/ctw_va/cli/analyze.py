"""CLI: civatas-exp analyze ... (Phase C7)."""
from __future__ import annotations

import json
from pathlib import Path

import click

from ..analytics import pipelines


def _default_db(experiment_id: str) -> str:
    return f"runs/{experiment_id}/data.db"


@click.group("analyze")
def analyze():
    """Statistical analysis (JSD / NEMD / refusal + bootstrap CI)."""
    pass


@analyze.command("distribution")
@click.option("--experiment-id", required=True, help="experiment_id (需存在 data.db)")
@click.option("--db", "db_path", default="", help="SQLite 路徑（預設 runs/<id>/data.db）")
@click.option("--sim-day", type=int, default=None,
              help="指定某天；不填則每個 persona×vendor 取最後一天")
@click.option("--output", default="", help="metric JSON 輸出（預設 metrics/<id>/distribution.json）")
@click.option("--n-resamples", type=int, default=10_000, show_default=True,
              help="bootstrap resample 次數")
@click.option("--confidence", type=float, default=0.95, show_default=True)
@click.option("--seed", type=int, default=20240113, show_default=True)
@click.option("--no-bootstrap", is_flag=True, help="跳過 bootstrap CI（加速，但無 CI/p-value）")
def distribution_cmd(experiment_id, db_path, sim_day, output, n_resamples, confidence, seed, no_bootstrap):
    """Party-choice + party_lean_5 distribution metrics (JSD vs CEC + pairwise + NEMD)."""
    db = db_path or _default_db(experiment_id)
    if not Path(db).exists():
        raise click.ClickException(f"DB not found: {db}")

    result = pipelines.pipeline_distribution(
        db, experiment_id, sim_day=sim_day,
        confidence=confidence, n_resamples=n_resamples, seed=seed,
        bootstrap=not no_bootstrap,
    )

    out = output or f"metrics/{experiment_id}/distribution.json"
    path = pipelines.write_json(out, result)
    click.echo(f"Wrote {path}")
    click.echo(f"  n_rows={result.get('n_rows')} n_personas={result.get('n_personas')}")
    click.echo(f"  vendors: {', '.join(result.get('vendors', []))}")
    if result.get("jsd_vs_truth"):
        click.echo("  JSD vs CEC 2024:")
        for v, d in result["jsd_vs_truth"].items():
            ci = f"  [{d.get('ci_low', float('nan')):.4f}, {d.get('ci_high', float('nan')):.4f}]" if "ci_low" in d else ""
            click.echo(f"    {v}: {d['value']:.4f}{ci}")


@analyze.command("refusal")
@click.option("--classifier", required=True, help="refusal_clf_n*.pkl 路徑")
@click.option("--experiment-id", default="", help="若給就讀 vendor_call_log")
@click.option("--db", "db_path", default="", help="SQLite 路徑覆寫")
@click.option("--labeled", default="", help="改為分析 labeled_n*.jsonl 或 responses_n*.jsonl")
@click.option("--output", default="", help="metric JSON 輸出")
def refusal_cmd(classifier, experiment_id, db_path, labeled, output):
    """Refusal rate by vendor (× topic 若 input 帶有 topic 欄)."""
    if labeled:
        result = pipelines.pipeline_refusal(classifier_path=classifier, labeled_path=labeled)
        default_out = Path(labeled).with_name(Path(labeled).stem + "_refusal.json")
    elif experiment_id:
        db = db_path or _default_db(experiment_id)
        if not Path(db).exists():
            raise click.ClickException(f"DB not found: {db}")
        result = pipelines.pipeline_refusal(
            classifier_path=classifier, db_path=db, experiment_id=experiment_id,
        )
        default_out = Path(f"metrics/{experiment_id}/refusal.json")
    else:
        raise click.ClickException("provide --experiment-id OR --labeled PATH")

    out = output or str(default_out)
    path = pipelines.write_json(out, result)
    click.echo(f"Wrote {path}")
    click.echo(f"  source: {result['source']}")
    click.echo(f"  n_rows: {result['n_rows']}")
    for vendor, block in (result.get("by_vendor") or {}).items():
        click.echo(
            f"    {vendor}: total={block['total']} "
            f"hard={block['hard_refusal']} soft={block['soft_refusal']} "
            f"on_task={block['on_task']} "
            f"refusal_rate={block['refusal_rate']:.3f}"
        )


@analyze.command("all")
@click.option("--experiment-id", required=True)
@click.option("--db", "db_path", default="")
@click.option("--classifier", default="", help="若給則順便跑 refusal pipeline")
@click.option("--sim-day", type=int, default=None)
@click.option("--output-dir", default="", help="預設 metrics/<experiment_id>/")
@click.option("--n-resamples", type=int, default=10_000)
@click.option("--confidence", type=float, default=0.95)
@click.option("--seed", type=int, default=20240113)
@click.option("--no-bootstrap", is_flag=True)
def all_cmd(experiment_id, db_path, classifier, sim_day, output_dir, n_resamples, confidence, seed, no_bootstrap):
    """Run distribution + (optional) refusal + write a combined summary."""
    db = db_path or _default_db(experiment_id)
    if not Path(db).exists():
        raise click.ClickException(f"DB not found: {db}")

    out_dir = Path(output_dir or f"metrics/{experiment_id}")
    out_dir.mkdir(parents=True, exist_ok=True)

    dist = pipelines.pipeline_distribution(
        db, experiment_id, sim_day=sim_day,
        confidence=confidence, n_resamples=n_resamples, seed=seed,
        bootstrap=not no_bootstrap,
    )
    pipelines.write_json(out_dir / "distribution.json", dist)
    click.echo(f"Wrote {out_dir / 'distribution.json'}")

    refusal = None
    if classifier:
        refusal = pipelines.pipeline_refusal(
            classifier_path=classifier, db_path=db, experiment_id=experiment_id,
        )
        pipelines.write_json(out_dir / "refusal.json", refusal)
        click.echo(f"Wrote {out_dir / 'refusal.json'}")

    summary = {
        "experiment_id": experiment_id,
        "computed_at": pipelines.now_iso(),
        "distribution_metrics_path": "distribution.json",
        "refusal_path": "refusal.json" if refusal else None,
        "vendors": dist.get("vendors", []),
        "n_personas": dist.get("n_personas", 0),
        "headline": {
            "jsd_vs_truth": {v: d["value"] for v, d in dist.get("jsd_vs_truth", {}).items()},
            "refusal_rate": {v: b["refusal_rate"] for v, b in (refusal or {}).get("by_vendor", {}).items()} if refusal else None,
        },
    }
    pipelines.write_json(out_dir / "summary.json", summary)
    click.echo(f"Wrote {out_dir / 'summary.json'}")
