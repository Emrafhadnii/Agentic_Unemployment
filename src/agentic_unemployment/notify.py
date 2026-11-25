from __future__ import annotations

import html
import json
import logging

import httpx

log = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 3900


class TelegramNotifier:
    """Small Telegram Bot API client that never raises on send failures."""

    def __init__(
        self,
        token: str | None,
        chat_id: int | str | None,
        min_score: int = 50,
        timeout: float = 15.0,
        proxy: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.token = token or None
        self.chat_id = chat_id
        self.min_score = min_score
        self._client: httpx.Client | None = None
        if self.token:
            try:
                self._client = httpx.Client(
                    base_url=f"https://api.telegram.org/bot{self.token}/",
                    timeout=timeout,
                    proxy=None if transport else proxy,
                    transport=transport,
                )
            except Exception:
                log.exception(
                    "telegram disabled: could not create HTTP client "
                    "(check TELEGRAM_PROXY and install httpx[socks] for SOCKS5)"
                )

    @property
    def enabled(self) -> bool:
        return self._client is not None and self.chat_id not in (None, "")

    @classmethod
    def from_settings(cls, settings) -> TelegramNotifier:
        token = (
            settings.telegram_token.get_secret_value()
            if settings.telegram_token is not None
            else None
        )
        return cls(
            token,
            settings.telegram_chat_id,
            min_score=settings.telegram_min_score,
            timeout=settings.telegram_timeout,
            proxy=settings.telegram_proxy
            or settings.outbound_proxy
            or settings.http_proxy,
        )

    def send(self, text: str) -> bool:
        if not self.enabled:
            return False
        if len(text) > MAX_MESSAGE_CHARS:
            text = text[: MAX_MESSAGE_CHARS - 1] + "…"
        try:
            resp = self._client.post(
                "sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
        except httpx.HTTPError as e:
            log.error("telegram send failed: %s", e)
            return False
        except Exception:
            log.exception("unexpected telegram error")
            return False

        if resp.status_code >= 400:
            log.error("telegram HTTP %s: %s", resp.status_code, resp.text[:300])
            return False
        log.info("telegram: message sent")
        return True

    def send_abort_alert(self, detail: str) -> bool:
        return self.send(
            "⚠️ <b>Scoring stopped</b>\n"
            f"{html.escape(detail)}\n"
            "Unscored jobs stay pending."
        )

    def format_match(self, job, row) -> str:
        reasons = _load_list(row["reasons"])[:3]
        missing = _load_list(row["missing_requirements"])[:2]
        meta = " · ".join(
            x
            for x in (
                job.company,
                job.location_raw,
                job.employment_type_raw,
                "Remote" if job.is_remote else None,
            )
            if x
        )

        lines = [
            f"🎯 <b>{row['score']}/100</b> · {html.escape(row['verdict'])} match",
            f"<b>{html.escape(job.title)}</b>",
        ]
        if meta:
            lines.append(html.escape(meta))
        if job.salary_raw:
            lines.append(f"💰 {html.escape(job.salary_raw)}")
        if job.experience_raw:
            lines.append(f"🧠 Experience: {html.escape(job.experience_raw)}")
        if job.skills:
            lines.append(f"🛠 {html.escape(', '.join(job.skills[:6]))}")
        if job.posted_raw:
            lines.append(f"🕒 {html.escape(job.posted_raw)}")
        if row["summary"]:
            lines += ["", html.escape(row["summary"])]
        if reasons:
            lines += ["", "<b>Why:</b>"] + [f"• {html.escape(r)}" for r in reasons]
        if missing:
            lines += ["", "<b>Missing:</b>"] + [f"• {html.escape(m)}" for m in missing]
        lines += ["", f'<a href="{html.escape(job.url, quote=True)}">Open job</a>']
        return "\n".join(lines)

    def notify_matches(
        self,
        db,
        candidate_hash: str | None,
        *,
        min_score: int | None = None,
        limit: int = 50,
        any_candidate: bool = False,
        dry_run: bool = False,
    ) -> tuple[int, int]:
        """Send every unsent match above the threshold. Returns (sent, failed)."""
        threshold = self.min_score if min_score is None else min_score
        rows = db.unnotified_high_matches(
            candidate_hash, threshold, limit=limit, any_candidate=any_candidate
        )
        if not rows:
            return 0, 0
        if not dry_run and not self.enabled:
            log.error(
                "telegram is not configured; %d match(es) left pending", len(rows)
            )
            return 0, len(rows)

        sent = failed = 0
        for job, row in rows:
            text = self.format_match(job, row)
            if dry_run:
                print(f"\n--- {job.key} ---\n{text}")
                sent += 1
                continue
            if self.send(text):
                db.mark_notified(job.key, row["candidate_hash"], int(row["score"]))
                sent += 1
            else:
                failed += 1
        if sent and not dry_run:
            log.info("telegram: %d new job notification(s) sent", sent)
        return sent, failed


def _load_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
    except ValueError:
        return []
    return [str(x) for x in value] if isinstance(value, list) else []
