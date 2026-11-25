from __future__ import annotations

from typing import Annotated

import typer

from agentic_unemployment.cli.app import github_app
from agentic_unemployment.cli.common import describe_proxy
from agentic_unemployment.config import settings
from agentic_unemployment.github_enrich import (
    check_github,
    enrich_github,
    proxy_for_github,
)


@github_app.command("enrich")
def github_enrich(
    username: Annotated[str | None, typer.Option("--username")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print without writing files.")
    ] = False,
    max_repos: Annotated[int | None, typer.Option("--max-repos")] = None,
    readme_repos: Annotated[int | None, typer.Option("--readme-repos")] = None,
) -> None:
    """Generate resume/github.md and profile suggestions from GitHub."""
    username = username or settings.github_username
    if not username:
        typer.echo("set GITHUB_USERNAME or pass --username", err=True)
        raise typer.Exit(2)

    typer.echo(f"github proxy: {describe_proxy(proxy_for_github(settings))}")
    try:
        docs = enrich_github(
            settings,
            username,
            dry_run=dry_run,
            max_repos=max_repos,
            readme_repos=readme_repos,
        )
    except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
        typer.echo(f"github enrichment failed: {e}", err=True)
        raise typer.Exit(2)

    if dry_run:
        typer.echo(docs.bullets)
        typer.echo("")
        typer.echo(docs.suggestions)
        return
    typer.echo(f"wrote {docs.bullets_path}")
    typer.echo(f"wrote {docs.suggestions_path}")


@github_app.command("test")
def github_test(
    username: Annotated[str | None, typer.Option("--username")] = None,
) -> None:
    """Check GitHub API connectivity through the configured proxy."""
    username = username or settings.github_username
    if not username:
        typer.echo("set GITHUB_USERNAME or pass --username", err=True)
        raise typer.Exit(2)

    token = settings.github_token.get_secret_value() if settings.github_token else None
    typer.echo(f"github proxy: {describe_proxy(proxy_for_github(settings))}")
    typer.echo(f"github token: {'set' if token else 'not set'}")
    try:
        user, repos, readme = check_github(settings, username)
    except Exception as e:  # noqa: BLE001 - CLI boundary: report, do not traceback
        typer.echo(f"github request failed: {e}", err=True)
        raise typer.Exit(2)

    typer.echo(f"ok: {user.get('login')} ({user.get('name') or 'no name'})")
    typer.echo(f"public repos: {user.get('public_repos')}, sampled: {len(repos)}")
    for repo in repos:
        typer.echo(
            f"  - {repo['name']} ({repo.get('language') or 'unknown'}, "
            f"{repo.get('stargazers_count', 0)} stars)"
        )
    typer.echo(f"readme: {'ok' if readme else 'none'}")
