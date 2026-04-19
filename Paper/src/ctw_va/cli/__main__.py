"""CTW-VA-2026 CLI entry point.

Entry point: civatas-exp  (configured in pyproject.toml [project.scripts])
"""
import click

from . import (
    news_pool,
    persona_slate,
    calibration,
    run,
    cost,
    analyze,
    dashboard,
    paper,
)

from ctw_va import __version__


@click.group()
@click.version_option(version=__version__)
def cli():
    """Civatas-TW Vendor Audit experimental CLI."""
    pass


cli.add_command(news_pool.news_pool)
cli.add_command(persona_slate.persona_slate)
cli.add_command(calibration.calibration)
cli.add_command(run.run)
cli.add_command(cost.cost)
cli.add_command(analyze.analyze)
cli.add_command(dashboard.dashboard)
cli.add_command(paper.paper)


if __name__ == "__main__":
    cli()
