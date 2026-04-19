"""CLI commands for persona slate management (Phase A3 — stub)."""
import click


@click.group("persona-slate")
def persona_slate():
    """Persona slate management (Phase A3)."""
    pass


@persona_slate.command("placeholder")
def placeholder():
    """Not yet implemented (see spec Phase A3)."""
    click.echo("Not yet implemented (see spec Phase A3).")
