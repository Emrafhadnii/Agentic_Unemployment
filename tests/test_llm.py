import httpx
import pytest

from agentic_unemployment.llm import LLMClient, LLMError


def _client(handler):
    return LLMClient(
        "k",
        "https://x.test/v4/",
        "m",
        transport=httpx.MockTransport(handler),
        min_interval=0,
    )


@pytest.mark.parametrize(
    "body",
    [
        {"error": {"message": "quota exceeded"}},
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
    ],
)
def test_broken_200_response_becomes_transient_llm_error(body):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=body)

    with pytest.raises(LLMError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "hi"}], retries=2, backoff=0)
    assert excinfo.value.transient is True
    assert len(calls) == 2


def test_non_json_200_is_retried_then_raises_llm_error():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(LLMError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "hi"}], retries=3, backoff=0)
    assert excinfo.value.transient is True
    assert len(calls) == 3


def test_exhausted_server_errors_raise_transient_llm_error():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="down")

    with pytest.raises(LLMError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "hi"}], retries=4, backoff=0)
    assert excinfo.value.transient is True
    assert len(calls) == 4


def test_auth_error_is_not_retried_and_not_transient():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(401, text="bad key")

    with pytest.raises(LLMError) as excinfo:
        _client(handler).chat([{"role": "user", "content": "hi"}], retries=4, backoff=0)
    assert excinfo.value.transient is False
    assert len(calls) == 1


def test_rejects_invalid_retry_count():
    with pytest.raises(ValueError):
        _client(lambda r: httpx.Response(200)).chat([], retries=0)
