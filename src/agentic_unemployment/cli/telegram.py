from __future__ import annotations

from typing import Annotated

import typer

from agentic_unemployment.cli.app import telegram_app
from agentic_unemployment.cli.common import describe_proxy
from agentic_unemployment.config import settings
from agentic_unemployment.notify import TelegramNotifier


@telegram_app.command("test")
def telegram_test(
    text: Annotated[
        str, typer.Option("--text")
    ] = "✅ agentic-unemployment: Telegram is working",
) -> None:
    """Send one test message through the configured bot/proxy."""
    notifier = TelegramNotifier.from_settings(settings)
    proxy = settings.telegram_proxy or settings.outbound_proxy or settings.http_proxy
    typer.echo(f"telegram proxy: {describe_proxy(proxy)}")
    if not notifier.enabled:
        typer.echo(
            "telegram is not configured (TELEGRAM_TOKEN / TELEGRAM_CHAT_ID)", err=True
        )
        raise typer.Exit(2)
    if not notifier.send(text):
        raise typer.Exit(1)
    typer.echo("sent")
