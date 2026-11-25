from __future__ import annotations

import logging
from typing import Annotated

import typer

from agentic_unemployment.config import settings

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Crawl Jobinja and JobVision, score jobs against your resume, and send Telegram alerts.",
)
resume_app = typer.Typer(no_args_is_help=True, help="Inspect the combined resume.")
github_app = typer.Typer(
    no_args_is_help=True, help="GitHub enrichment and connectivity."
)
telegram_app = typer.Typer(no_args_is_help=True, help="Telegram notifications.")
app.add_typer(resume_app, name="resume")
app.add_typer(github_app, name="github")
app.add_typer(telegram_app, name="telegram")


@app.callback()
def main(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Enable debug logging.")
    ] = False,
    log_level: Annotated[str, typer.Option("--log-level", help="Logging level.")] = "",
) -> None:
    level = "DEBUG" if verbose else (log_level or settings.log_level)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        force=True,
    )
