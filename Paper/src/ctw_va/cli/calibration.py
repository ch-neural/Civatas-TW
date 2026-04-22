"""CLI: civatas-exp calibration ... (Phase A5 — refusal calibration)."""
from __future__ import annotations

import json as _json

import click

from ..refusal import fetcher, csv_io, classifier, stats as stats_mod, blind as blind_mod
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


@calibration.command("retry-errors")
@click.option("--input", "input_path", type=click.Path(exists=True), required=True,
              help="Responses JSONL containing status=error rows to re-fetch")
@click.option("--output", type=click.Path(), default=None,
              help="Output JSONL path. Default: rewrite --input in place.")
@click.option("--seed", type=int, default=20240113, show_default=True,
              help="Per-call seed (match original fetch for reproducibility)")
def retry_errors_cmd(input_path, output, seed):
    """Re-fetch only rows where status=='error' — recovers transient network
    failures cheaply without re-running the full 1000-call sweep. Rows that
    were already ok stay untouched; permanent errors (content filter, auth)
    will stay error after retry."""
    fetcher.retry_errors(input_path=input_path, output_path=output, seed=seed)


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


@calibration.command("stats")
@click.option("--csv", "csv_path", type=click.Path(exists=True), required=True,
              help="Responses CSV (with or without hand-labels)")
@click.option("--sidecar", type=click.Path(), default=None,
              help="AI suggestion JSONL sidecar. Default: <csv_stem>.ai_suggest.jsonl")
@click.option("--json", "as_json", is_flag=True,
              help="Emit machine-readable JSON instead of the text report")
def stats_cmd(csv_path, sidecar, as_json):
    """Report labeling progress + label distribution + AI-sidecar overlap."""
    s = stats_mod.compute(csv_path, sidecar_path=sidecar)
    if as_json:
        click.echo(_json.dumps(s, ensure_ascii=False, indent=2))
    else:
        click.echo(stats_mod.format_text(s, csv_path=csv_path))


@calibration.command("blind-sample")
@click.option("--csv", "csv_path", type=click.Path(exists=True), required=True,
              help="Primary labeled CSV (e.g. responses_n200.csv)")
@click.option("--n", type=int, default=50, show_default=True,
              help="Blind subset size (stratified across vendor × expected)")
@click.option("--seed", type=int, default=20260422, show_default=True,
              help="Deterministic seed — same seed produces the same subset")
@click.option("--output", type=click.Path(), default=None,
              help="Output CSV (default: <input_stem>_blind.csv; filename must match "
                   "responses_n*_*.csv so the webui labeler accepts it)")
def blind_sample_cmd(csv_path, n, seed, output):
    """Sample a blind-validation subset for rater reliability (Cohen's κ).

    Output CSV has the label column cleared. Open in webui under blind mode
    (AI suggestions hidden) and re-label from scratch. Then run
    `calibration agreement` to compute κ.
    """
    from pathlib import Path
    if output is None:
        p = Path(csv_path)
        output = str(p.with_name(p.stem + "_blind" + p.suffix))
    result = blind_mod.sample_blind_subset(
        input_csv=csv_path, output_csv=output, n=n, seed=seed,
    )
    click.echo(f"✓ Sampled {result['sampled']} rows from "
               f"{result['eligible']} eligible → {result['output']}")
    click.echo(f"  seed={result['seed']}")
    click.echo(f"  stratum breakdown (vendor|expected):")
    for k in sorted(result["by_stratum"]):
        click.echo(f"    {k}: {result['by_stratum'][k]}")
    click.echo()
    click.echo("  Next: open the output CSV in the webui labeler. Blind mode "
               "auto-activates (AI suggestions hidden) when filename ends with _blind.csv.")


@calibration.command("agreement")
@click.option("--primary", "primary_csv", type=click.Path(exists=True), required=True,
              help="Primary labeled CSV (original human labels)")
@click.option("--blind", "blind_csv", type=click.Path(exists=True), required=True,
              help="Blind re-labeled CSV (same rows, re-labeled without AI assist)")
@click.option("--json", "as_json", type=bool, default=False, is_flag=True,
              help="Emit JSON instead of text report")
@click.option("--output-json", type=click.Path(), default=None,
              help="Optional: write JSON report to this path (for paper §3.5 citation)")
def agreement_cmd(primary_csv, blind_csv, as_json, output_json):
    """Compute Cohen's κ between primary and blind labels on the blind subset.

    Reports overall κ + per-vendor κ + 3×3 confusion matrix. Writes optional
    JSON for downstream paper figures.
    """
    from ..refusal import agreement as agreement_mod
    result = agreement_mod.compute(primary_csv=primary_csv, blind_csv=blind_csv)
    if output_json:
        import json as _j
        from pathlib import Path
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(
            _j.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if as_json:
        click.echo(_json.dumps(result, ensure_ascii=False, indent=2))
    else:
        click.echo(agreement_mod.format_text(result))


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
