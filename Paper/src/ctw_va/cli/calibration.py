"""CLI: civatas-exp calibration ... (Phase A5 — refusal calibration)."""
from __future__ import annotations

import click

from ..refusal import fetcher, csv_io, classifier
from ..refusal.prompts import VALID_LABELS


@click.group("calibration")
def calibration():
    """Refusal calibration: fetch responses → label → train classifier (Phase A5)."""
    pass


@calibration.command("fetch")
@click.option("--n", type=int, default=200, show_default=True,
              help="Number of prompts to sample (stratified across 3 expected categories)")
@click.option("--vendors", default="openai,gemini,grok,deepseek,kimi", show_default=True,
              help="Comma-separated vendors to query")
@click.option("--output", type=click.Path(), required=True,
              help="JSONL output path (one row per prompt×vendor)")
@click.option("--seed", type=int, default=20240113, show_default=True,
              help="Seed for prompt sampling + per-call seed")
def fetch_cmd(n, vendors, output, seed):
    """Fan-out prompt bank to selected vendors and save responses for annotation."""
    vendors_list = [v.strip() for v in vendors.split(",") if v.strip()]
    fetcher.fetch(n=n, vendors=vendors_list, output_path=output, seed=seed)


@calibration.command("export")
@click.option("--input", "input_path", type=click.Path(exists=True), required=True,
              help="Responses JSONL produced by `calibration fetch`")
@click.option("--output", type=click.Path(), required=True,
              help="CSV output path (Excel/Numbers-friendly, UTF-8 BOM)")
def export_cmd(input_path, output):
    """Dump responses JSONL to a CSV with an empty `label` column for hand annotation."""
    result = csv_io.export_to_csv(input_path, output)
    click.echo(f"✓ Exported {result['count']} rows → {result['output']}")
    click.echo()
    click.echo(result["hint"])


@calibration.command("import-labels")
@click.option("--csv", "csv_path", type=click.Path(exists=True), required=True,
              help="Hand-labeled CSV (the `label` column filled)")
@click.option("--output", type=click.Path(), required=True,
              help="Labeled JSONL output path (feeds `calibration train`)")
def import_labels_cmd(csv_path, output):
    """Parse hand-labeled CSV back into a JSONL ready for classifier training."""
    result = csv_io.import_labels_from_csv(csv_path, output)
    click.echo(f"✓ Imported {result['labeled']} labeled rows → {result['output']}")
    click.echo(f"  Skipped {result['skipped']} unlabeled / invalid rows.")
    click.echo(f"  Distribution: {result['by_label']}")
    if result["bad_labels"]:
        click.echo()
        click.echo(f"  ⚠ {len(result['bad_labels'])} rows had invalid labels "
                   f"(valid: {VALID_LABELS}):")
        for bad in result["bad_labels"][:5]:
            click.echo(f"    - {bad}")
        if len(result["bad_labels"]) > 5:
            click.echo(f"    ... and {len(result['bad_labels']) - 5} more")


@calibration.command("train")
@click.option("--input", "input_path", type=click.Path(exists=True), required=True,
              help="Labeled JSONL (from `calibration import-labels`)")
@click.option("--output", type=click.Path(), required=True,
              help="Trained classifier pickle output")
@click.option("--test-ratio", type=float, default=0.2, show_default=True)
@click.option("--seed", type=int, default=20240113, show_default=True)
def train_cmd(input_path, output, test_ratio, seed):
    """Train TF-IDF + LogisticRegression refusal classifier on labeled rows."""
    classifier.train(
        input_jsonl=input_path, output_pkl=output,
        test_ratio=test_ratio, seed=seed,
    )
