"""CLI commands for statistical analysis (Phase C7 — stub)."""
import click


@click.group("analyze")
def analyze():
    """Statistical analysis (JSD / NEMD / refusal pipeline) (Phase C7)."""
    pass


@analyze.command("placeholder")
def placeholder():
    """Not yet implemented (see spec Phase C7)."""
    click.echo("Not yet implemented (see spec Phase C7).")
