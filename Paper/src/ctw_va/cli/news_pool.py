"""CLI commands for news pool management (Phase A1)."""
from __future__ import annotations

from pathlib import Path

import click

from ..news import serper_fetch, merge as merge_module


@click.group("news-pool")
def news_pool():
    """News pool management (Phase A1)."""
    pass


@news_pool.command("fetch-a")
@click.option("--output", type=click.Path(), required=True,
              help="Path to write stage_a_output.jsonl")
@click.option("--max-pages", type=int, default=10, show_default=True,
              help="Max Serper pages per keyword")
def fetch_a(output: str, max_pages: int):
    """Stage A: generic 7-keyword Serper search."""
    from dotenv import load_dotenv
    load_dotenv()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    n = serper_fetch.fetch_stage_a(output_path=output, max_pages=max_pages)
    click.echo(f"Stage A: {n} articles written to {output}")


@news_pool.command("fetch-b")
@click.option("--output", type=click.Path(), required=True,
              help="Path to write stage_b_output.jsonl")
@click.option("--max-pages", type=int, default=5, show_default=True,
              help="Max Serper pages per domain/keyword pair")
def fetch_b(output: str, max_pages: int):
    """Stage B: site-scoped blue-leaning media."""
    from dotenv import load_dotenv
    load_dotenv()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    n = serper_fetch.fetch_stage_b(output_path=output, max_pages=max_pages)
    click.echo(f"Stage B: {n} articles written to {output}")


@news_pool.command("fetch-c")
@click.option("--output", type=click.Path(), required=True,
              help="Path to write stage_c_output.jsonl")
@click.option("--max-pages", type=int, default=5, show_default=True,
              help="Max Serper pages per domain/keyword pair")
def fetch_c(output: str, max_pages: int):
    """Stage C: site-scoped deep-spectrum media."""
    from dotenv import load_dotenv
    load_dotenv()
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    n = serper_fetch.fetch_stage_c(output_path=output, max_pages=max_pages)
    click.echo(f"Stage C: {n} articles written to {output}")


@news_pool.command("merge")
@click.option(
    "--inputs-dir",
    type=click.Path(exists=True),
    default="experiments/news_pool_2024_jan",
    show_default=True,
    help="Directory containing stage_a/b/c_output.jsonl",
)
@click.option(
    "--output",
    type=click.Path(),
    default="experiments/news_pool_2024_jan/merged_pool.jsonl",
    show_default=True,
    help="Path to write merged_pool.jsonl",
)
def merge_cmd(inputs_dir: str, output: str):
    """A1: merge stage A/B/C outputs, dedup, compute SHA-256."""
    result = merge_module.merge_pool(inputs_dir, output)
    click.echo(f"Merged {result['count']} articles to {output}")
    click.echo(f"  Excluded (non-news): {result['excluded_count']}")
    click.echo(f"  SHA-256: {result['sha256']}")
    click.echo(f"  Leaning distribution: {result['leaning_distribution']}")


@news_pool.command("stats")
@click.argument(
    "pool_path",
    type=click.Path(exists=True),
    default="experiments/news_pool_2024_jan/merged_pool.jsonl",
)
def stats_cmd(pool_path: str):
    """Print leaning / stage / domain statistics for a merged pool."""
    merge_module.print_stats(pool_path)
