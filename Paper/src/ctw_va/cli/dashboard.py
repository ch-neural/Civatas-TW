"""CLI commands for HTML dashboard generation (Phase D — stub)."""
import click


@click.group("dashboard")
def dashboard():
    """Single-file HTML + Chart.js dashboard generation (Phase D)."""
    pass


@dashboard.command("placeholder")
def placeholder():
    """Not yet implemented (see spec Phase D)."""
    click.echo("Not yet implemented (see spec Phase D).")
