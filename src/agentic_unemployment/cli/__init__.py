from __future__ import annotations

from agentic_unemployment.cli import (  # noqa: F401
    crawl,
    github,
    notify,
    resume,
    run,
    score,
    stats,
    telegram,
)
from agentic_unemployment.cli.app import app

__all__ = ["app"]
