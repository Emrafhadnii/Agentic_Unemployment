from __future__ import annotations

from typing import Annotated

import typer

from agentic_unemployment.candidate import Candidate
from agentic_unemployment.cli.app import app
from agentic_unemployment.cli.common import current_candidate, open_db, print_crawl
from agentic_unemployment.cli.notify import notify_in_run
from agentic_unemployment.config import settings
from agentic_unemployment.llm import LLMClient
from agentic_unemployment.notify import TelegramNotifier
from agentic_unemployment.pipeline import crawl_searches, score_pending


@app.command()
def run(
    max_pages: Annotated[int | None, typer.Option("--max-pages")] = None,
    delay: Annotated[float | None, typer.Option("--delay")] = None,
    no_details: Annotated[bool, typer.Option("--no-details")] = False,
    limit: Annotated[int | None, typer.Option("--limit")] = None,
    max_attempts: Annotated[int | None, typer.Option("--max-attempts")] = None,
    min_score: Annotated[int | None, typer.Option("--min-score")] = None,
    any_candidate: Annotated[bool, typer.Option("--any-candidate")] = False,
    skip_crawl: Annotated[bool, typer.Option("--skip-crawl")] = False,
    skip_score: Annotated[bool, typer.Option("--skip-score")] = False,
    skip_notify: Annotated[bool, typer.Option("--skip-notify")] = False,
) -> None:
    """Run crawl, score and notify in one process (cron/worker convenience)."""
    max_pages = settings.max_pages if max_pages is None else max_pages
    delay = settings.request_delay if delay is None else delay
    limit = settings.score_limit if limit is None else limit
    max_attempts = settings.max_match_attempts if max_attempts is None else max_attempts
    min_score = settings.telegram_min_score if min_score is None else min_score

    candidate: Candidate | None = None
    aborted = False
    exit_code = 0

    with open_db() as db:
        if not skip_crawl:
            stats = crawl_searches(
                db,
                settings.searches,
                max_pages=max_pages,
                delay=delay,
                fetch_details=not no_details,
            )
            print_crawl(stats)
            if stats.search_failures:
                exit_code = 1

        if not skip_score:
            try:
                candidate = current_candidate()
                llm = LLMClient.from_settings(settings)
            except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
                typer.echo(f"cannot score: {e}", err=True)
                raise typer.Exit(2)
            ok, failed, aborted = score_pending(db, llm, candidate, limit, max_attempts)
            typer.echo(f"scored: {ok}, failed: {failed}")

        if not skip_notify:
            if candidate is None and not any_candidate:
                try:
                    candidate = current_candidate()
                except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
                    typer.echo(f"cannot notify: {e}", err=True)
                    raise typer.Exit(2)
            exit_code = max(
                exit_code,
                notify_in_run(
                    db, candidate, min_score=min_score, any_candidate=any_candidate
                ),
            )

    if aborted:
        notifier = TelegramNotifier.from_settings(settings)
        if settings.telegram_alert_on_abort:
            notifier.send_abort_alert(
                "The LLM kept failing, so scoring was stopped early."
            )
        typer.echo("scoring aborted: the LLM kept failing", err=True)
        raise typer.Exit(2)
    if exit_code:
        raise typer.Exit(exit_code)
