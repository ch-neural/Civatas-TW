"""CLI commands for refusal calibration (Phase A5 — stub)."""
import click


@click.group("calibration")
def calibration():
    """Refusal calibration dataset management (Phase A5)."""
    pass


@calibration.command("placeholder")
def placeholder():
    """Not yet implemented (see spec Phase A5)."""
    click.echo("Not yet implemented (see spec Phase A5).")
