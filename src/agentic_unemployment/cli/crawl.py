from __future__ import annotations

from typing import Annotated

import typer

from agentic_unemployment.cli.app import app
from agentic_unemployment.cli.common import (
    build_searches,
    open_db,
    print_crawl,
    validate_sources,
)
from agentic_unemployment.config import settings
from agentic_unemployment.pipeline import crawl_pending_details, crawl_searches


@app.command()
def crawl(
    keyword: Annotated[
        list[str] | None,
        typer.Option("-k", "--keyword", help="Keyword to search; repeatable."),
    ] = None,
    remote: Annotated[bool, typer.Option("--remote", help="Remote jobs only.")] = False,
    onsite: Annotated[
        bool, typer.Option("--onsite", help="On-site jobs only.")
    ] = False,
    source: Annotated[
        list[str] | None,
        typer.Option("--source", help="Only these sources; repeatable."),
    ] = None,
    max_pages: Annotated[int | None, typer.Option("--max-pages")] = None,
    delay: Annotated[
        float | None, typer.Option("--delay", help="Delay between requests (s).")
    ] = None,
    no_details: Annotated[
        bool, typer.Option("--no-details", help="Only crawl list pages.")
    ] = False,
    details_only: Annotated[
        bool, typer.Option("--details-only", help="Only fetch pending detail pages.")
    ] = False,
) -> None:
    """Crawl Jobinja and JobVision and store jobs and details."""
    if no_details and details_only:
        raise typer.BadParameter(
            "--no-details and --details-only are mutually exclusive"
        )
    max_pages = settings.max_pages if max_pages is None else max_pages
    delay = settings.request_delay if delay is None else delay
    selected = validate_sources(source)

    with open_db() as db:
        if details_only:
            ok, failed = crawl_pending_details(db, delay=delay, sources=selected)
            typer.echo(f"details: {ok} ok, {failed} failed")
            return

        specs = build_searches(keyword, remote, onsite, selected)
        stats = crawl_searches(
            db, specs, max_pages=max_pages, delay=delay, fetch_details=not no_details
        )
        print_crawl(stats)
        if stats.search_failures:
            raise typer.Exit(1)
