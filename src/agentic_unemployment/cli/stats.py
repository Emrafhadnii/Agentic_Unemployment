from __future__ import annotations

import typer

from agentic_unemployment.cli.app import app
from agentic_unemployment.cli.common import current_candidate, open_db
from agentic_unemployment.config import settings


@app.command()
def stats() -> None:
    """Show database, resume and notification counts."""
    with open_db() as db:
        typer.echo(f"jobs: {db.count()}")
        by_source = db.count_by_source()
        if by_source:
            typer.echo(
                "jobs by source: "
                + ", ".join(f"{source}={count}" for source, count in by_source.items())
            )
        typer.echo(f"details pending: {db.count_pending_detail()}")
        typer.echo(f"matches (all resumes): {db.count_matches()}")
        typer.echo(f"notified: {db.count_notified()}")

        try:
            candidate = current_candidate()
        except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
            typer.echo(f"resume: unavailable ({e})")
            return

        typer.echo(
            f"resume: {len(candidate.files)} file(s), "
            f"{len(candidate.resume_text)} chars, hash {candidate.hash[:12]}"
        )
        typer.echo(f"matches (current resume): {db.count_matches(candidate.hash)}")
        typer.echo(
            f"unscored (current resume): "
            f"{db.count_pending_match(candidate.hash, settings.max_match_attempts)}"
        )
        pending = db.unnotified_high_matches(
            None, settings.telegram_min_score, limit=10000, any_candidate=True
        )
        typer.echo(
            f"notifications pending (>{settings.telegram_min_score}): {len(pending)}"
        )
