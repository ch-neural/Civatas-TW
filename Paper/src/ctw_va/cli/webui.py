"""CLI: civatas-exp webui — launch the FastAPI test harness."""
from __future__ import annotations

import click


@click.group("webui")
def webui():
    """Web UI for running CLI commands + tracking results (Paper-only)."""
    pass


@webui.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8765, type=int, show_default=True)
@click.option("--reload", is_flag=True, help="auto-reload on file change (dev)")
def serve_cmd(host: str, port: int, reload: bool):
    """Launch uvicorn serving the single-page test harness.

    Open http://HOST:PORT/ in a browser. Stop with Ctrl-C.
    """
    try:
        import uvicorn
    except ImportError as e:
        raise click.ClickException(
            "uvicorn 未安裝。請先：pip install 'fastapi>=0.110' 'uvicorn>=0.27'"
        ) from e

    # Load .env so child processes inherit API keys.
    from dotenv import load_dotenv
    load_dotenv()

    click.echo(f"▶ CTW-VA-2026 webui on http://{host}:{port}/")
    click.echo("  Ctrl-C to stop.")
    uvicorn.run(
        "ctw_va.webui.app:app",
        host=host, port=port, reload=reload, log_level="info",
    )
