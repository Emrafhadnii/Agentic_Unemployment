from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import urlsplit

import typer

from agentic_unemployment.candidate import Candidate, load_candidate
from agentic_unemployment.config import SearchSpec, settings
from agentic_unemployment.sources import SOURCE_NAMES
from agentic_unemployment.storage import Storage


@contextmanager
def open_db():
    db = Storage(settings.db_path)
    try:
        yield db
    finally:
        db.close()


def current_candidate() -> Candidate:
    return load_candidate(settings.resume_dir)


def describe_proxy(url: str | None) -> str:
    if not url:
        return "none"
    parts = urlsplit(url)
    if not parts.hostname:
        return "configured (could not parse)"
    return f"{parts.scheme}://{parts.hostname}:{parts.port or '-'}"


def validate_sources(sources: list[str] | None) -> list[str] | None:
    if not sources:
        return None
    unknown = sorted(set(sources) - set(SOURCE_NAMES))
    if unknown:
        raise typer.BadParameter(
            f"unknown source(s): {', '.join(unknown)}; "
            f"choose from {', '.join(SOURCE_NAMES)}"
        )
    return list(dict.fromkeys(sources))


def build_searches(
    keywords: list[str] | None,
    remote: bool,
    onsite: bool,
    sources: list[str] | None = None,
) -> list[SearchSpec]:
    if remote and onsite:
        raise typer.BadParameter("use either --remote or --onsite, not both")

    selected = validate_sources(sources)
    if keywords:
        modes = [True] if remote else [False] if onsite else [True, False]
        targets = selected or list(SOURCE_NAMES)
        return [
            SearchSpec(source=source, keywords=list(keywords), remote=mode)
            for source in targets
            for mode in modes
        ]

    specs = list(settings.searches)
    if selected:
        specs = [spec for spec in specs if spec.source in selected]
    if remote:
        specs = [spec for spec in specs if spec.remote]
    elif onsite:
        specs = [spec for spec in specs if not spec.remote]
    if not specs:
        raise typer.BadParameter(
            "no searches matched; configure SEARCHES or pass -k/--keyword"
        )
    return specs


def print_crawl(stats) -> None:
    typer.echo(
        f"searches: {stats.searches} ({stats.search_failures} failed), "
        f"found: {stats.found}, new: {stats.new}"
    )
    if stats.details_ok or stats.details_failed:
        typer.echo(f"details: {stats.details_ok} ok, {stats.details_failed} failed")
