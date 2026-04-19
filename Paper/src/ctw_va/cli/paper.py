"""CLI commands for paper figure generation (Phase C9 — stub)."""
import click


@click.group("paper")
def paper():
    """Paper figure and table generation (Phase C9)."""
    pass


@paper.command("placeholder")
def placeholder():
    """Not yet implemented (see spec Phase C9)."""
    click.echo("Not yet implemented (see spec Phase C9).")
