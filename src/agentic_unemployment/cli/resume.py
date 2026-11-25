from __future__ import annotations

import typer

from agentic_unemployment.cli.app import resume_app
from agentic_unemployment.cli.common import current_candidate


@resume_app.command("check")
def resume_check() -> None:
    """Show which markdown files are combined and the resulting hash."""
    try:
        candidate = current_candidate()
    except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
        typer.echo(f"resume is invalid: {e}", err=True)
        raise typer.Exit(2)

    typer.echo("resume files:")
    for name in candidate.files:
        typer.echo(f"  - {name}")
    typer.echo(f"combined: {len(candidate.resume_text)} chars")
    typer.echo(f"hash: {candidate.hash}")
