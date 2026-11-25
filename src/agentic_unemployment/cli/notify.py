from __future__ import annotations

from typing import Annotated

import typer

from agentic_unemployment.candidate import Candidate
from agentic_unemployment.cli.app import app
from agentic_unemployment.cli.common import current_candidate, open_db
from agentic_unemployment.config import settings
from agentic_unemployment.notify import TelegramNotifier


@app.command()
def notify(
    min_score: Annotated[
        int | None,
        typer.Option("--min-score", help="Only notify matches above this score."),
    ] = None,
    limit: Annotated[
        int, typer.Option("--limit", help="Max notifications to send.")
    ] = 50,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print instead of sending.")
    ] = False,
    any_candidate: Annotated[
        bool,
        typer.Option(
            "--any-candidate",
            help="Use the best match across all resume versions.",
        ),
    ] = False,
) -> None:
    """Send scored jobs above the threshold to Telegram."""
    min_score = settings.telegram_min_score if min_score is None else min_score
    notifier = TelegramNotifier.from_settings(settings)
    if not dry_run and not notifier.enabled:
        typer.echo(
            "telegram is not configured (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)", err=True
        )
        raise typer.Exit(2)

    candidate_hash = None
    if not any_candidate:
        try:
            candidate_hash = current_candidate().hash
        except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
            typer.echo(f"cannot load resume: {e}", err=True)
            raise typer.Exit(2)

    with open_db() as db:
        sent, failed = notifier.notify_matches(
            db,
            candidate_hash,
            min_score=min_score,
            limit=limit,
            any_candidate=any_candidate,
            dry_run=dry_run,
        )

    if dry_run:
        typer.echo(f"dry run: would send {sent} notification(s)")
    else:
        typer.echo(f"telegram: sent {sent}, failed {failed}")
    if failed:
        raise typer.Exit(1)


def notify_in_run(
    db,
    candidate: Candidate | None,
    *,
    min_score: int,
    any_candidate: bool,
) -> int:
    notifier = TelegramNotifier.from_settings(settings)
    if not notifier.enabled:
        typer.echo("telegram is not configured; skipping notifications")
        return 0
    candidate_hash = candidate.hash if candidate else None
    if candidate_hash is None and not any_candidate:
        typer.echo(
            "no resume loaded; use --any-candidate to notify old matches", err=True
        )
        return 1
    sent, failed = notifier.notify_matches(
        db, candidate_hash, min_score=min_score, any_candidate=any_candidate
    )
    typer.echo(f"telegram: sent {sent}, failed {failed}")
    return 1 if failed else 0
