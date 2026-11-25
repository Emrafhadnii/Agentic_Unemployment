from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger(__name__)
_RETRY = {429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    def __init__(self, msg: str, transient: bool = False) -> None:
        super().__init__(msg)
        self.transient = transient


def _parse_content(resp: httpx.Response) -> tuple[str, dict]:
    """Extract the assistant message, turning every malformed shape into LLMError."""
    try:
        data = resp.json()
    except ValueError as e:
        raise LLMError(
            f"response is not JSON: {resp.text[:300]}", transient=True
        ) from e

    if not isinstance(data, dict):
        raise LLMError(
            f"unexpected response type: {type(data).__name__}", transient=True
        )

    if data.get("error"):
        raise LLMError(f"API error: {str(data['error'])[:300]}", transient=True)

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError(f"response has no choices: {str(data)[:300]}", transient=True)

    choice = choices[0]
    if not isinstance(choice, dict):
        raise LLMError(
            f"unexpected choice type: {type(choice).__name__}", transient=True
        )

    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not content:
        raise LLMError(
            f"empty response (finish_reason={choice.get('finish_reason')})",
            transient=True,
        )
    usage = data.get("usage")
    return content, usage if isinstance(usage, dict) else {}


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 120.0,
        proxy: str | None = None,
        extra: dict | None = None,
        transport: httpx.BaseTransport | None = None,
        min_interval: float = 0.0,
    ) -> None:
        self.model = model
        self.extra = extra or {}
        self.min_interval = min_interval
        self._last_call = 0.0
        self._client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
            proxy=None if transport else proxy,
            transport=transport,
        )

    @classmethod
    def from_settings(cls, settings, model: str | None = None) -> LLMClient:
        if settings.llm_api_key is None:
            raise ValueError("LLM_API_KEY is not set")
        return cls(
            settings.llm_api_key.get_secret_value(),
            settings.llm_base_url,
            model or settings.llm_model,
            settings.llm_timeout,
            settings.http_proxy,
            settings.llm_extra,
            min_interval=settings.llm_min_interval,
        )

    def _throttle(self) -> None:
        wait = self._last_call + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        retries: int = 4,
        backoff: float = 5.0,
    ) -> str:
        if retries < 1:
            raise ValueError("retries must be at least 1")
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **self.extra,
        }
        for attempt in range(1, retries + 1):
            self._throttle()
            wait = backoff * attempt
            try:
                resp = self._client.post("chat/completions", json=payload)
            except httpx.HTTPError as e:
                if attempt == retries:
                    raise LLMError(f"network error: {e}", transient=True) from e
                log.warning(
                    "LLM network error (attempt %d/%d): %s", attempt, retries, e
                )
                time.sleep(wait)
                continue

            if resp.status_code in _RETRY:
                log.warning(
                    "LLM HTTP %s (attempt %d/%d): %s",
                    resp.status_code,
                    attempt,
                    retries,
                    resp.text[:300],
                )
                if attempt == retries:
                    raise LLMError(
                        f"HTTP {resp.status_code}: {resp.text[:300]}", transient=True
                    )
                retry_after = resp.headers.get("retry-after", "")
                if retry_after.isdigit():
                    wait = max(wait, int(retry_after))
                time.sleep(wait)
                continue

            if resp.status_code >= 400:
                raise LLMError(f"HTTP {resp.status_code}: {resp.text[:300]}")

            try:
                content, usage = _parse_content(resp)
            except LLMError as e:
                if not e.transient or attempt == retries:
                    raise
                log.warning("LLM bad response (attempt %d/%d): %s", attempt, retries, e)
                time.sleep(wait)
                continue

            log.info(
                "llm tokens: prompt=%s completion=%s",
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
            )
            return content

        raise LLMError("LLM call failed after all retries", transient=True)
