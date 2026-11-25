from __future__ import annotations

from typing import Annotated

import typer

from agentic_unemployment.cli.app import app
from agentic_unemployment.cli.common import current_candidate, open_db
from agentic_unemployment.config import settings
from agentic_unemployment.llm import LLMClient
from agentic_unemployment.pipeline import score_pending


@app.command()
def score(
    limit: Annotated[
        int | None, typer.Option("--limit", help="Max jobs to score.")
    ] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts")] = None,
    model: Annotated[
        str | None, typer.Option("--model", help="Override the LLM model.")
    ] = None,
) -> None:
    """Score pending jobs against the combined resume and store matches."""
    limit = settings.score_limit if limit is None else limit
    max_attempts = settings.max_match_attempts if max_attempts is None else max_attempts

    try:
        candidate = current_candidate()
        llm = LLMClient.from_settings(settings, model)
    except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
        typer.echo(f"cannot score: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(
        f"resume: {len(candidate.files)} file(s), {len(candidate.resume_text)} chars"
    )
    with open_db() as db:
        ok, failed, aborted = score_pending(db, llm, candidate, limit, max_attempts)
    typer.echo(f"scored: {ok}, failed: {failed}")
    if aborted:
        typer.echo("scoring aborted: the LLM kept failing; jobs stay pending", err=True)
        raise typer.Exit(2)
