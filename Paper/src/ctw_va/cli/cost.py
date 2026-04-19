"""CLI commands for cost estimation (Phase B5 — stub)."""
import click


@click.group("cost")
def cost():
    """Cost estimation and budget tracking (Phase B5)."""
    pass


@cost.command("placeholder")
def placeholder():
    """Not yet implemented (see spec Phase B5)."""
    click.echo("Not yet implemented (see spec Phase B5).")
