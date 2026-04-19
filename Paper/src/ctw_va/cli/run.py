"""CLI commands for running experiments (Phase C4-C5 — stub)."""
import click


@click.group("run")
def run():
    """Run experiment (Phase C4-C5)."""
    pass


@run.command("placeholder")
def placeholder():
    """Not yet implemented (see spec Phase C4-C5)."""
    click.echo("Not yet implemented (see spec Phase C4-C5).")
