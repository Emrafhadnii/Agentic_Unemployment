import json
from datetime import datetime

import httpx
import pytest
from pydantic import ValidationError

from agentic_unemployment.candidate import Candidate, Profile, Weights
from agentic_unemployment.llm import LLMClient
from agentic_unemployment.matcher import (
    SubScores,
    build_system,
    combine,
    parse_output,
    render_job,
    score_job,
    verdict_for,
)
from agentic_unemployment.models.job import Job

GOOD = {
    "sub_scores": {
        "python_backend": 90,
        "fastapi": 100,
        "other_skills": 60,
        "experience": 70,
    },
    "summary": "ok",
    "reasons": ["FastAPI in production"],
    "missing_requirements": ["Kafka"],
}


def _client(replies):
    it = iter(replies)

    def handler(request):
        body = {
            "choices": [{"message": {"content": next(it)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        return httpx.Response(200, json=body)

    return LLMClient(
        "k", "https://x.test/v4/", "m", transport=httpx.MockTransport(handler)
    )


def _candidate():
    p = Profile(target_roles=["backend"], seniority="junior", years_experience=2)
    return Candidate(resume_text="MY-RESUME-TEXT", profile=p, hash="h")


def _job():
    return Job(
        source="jobinja",
        source_id="x",
        url="u",
        title="Backend",
        company="SECRET-CO",
        location_raw="SECRET-CITY",
        employment_type_raw=None,
        salary_raw="SECRET-PAY",
        posted_raw=None,
        posted_at=None,
        fetched_at=datetime(2026, 11, 22),
    )


def test_retry_on_bad_output():
    r = score_job(_client(["not json", json.dumps(GOOD)]), _candidate(), _job())
    assert r.score == combine(SubScores(**GOOD["sub_scores"]), Weights())
    assert r.verdict == verdict_for(r.score)


def test_rejects_out_of_range():
    bad = {**GOOD, "sub_scores": {**GOOD["sub_scores"], "fastapi": 150}}
    with pytest.raises(ValidationError):
        parse_output(json.dumps(bad))


def test_all_perfect_is_100():
    assert (
        combine(
            SubScores(
                python_backend=100, fastapi=100, other_skills=100, experience=100
            ),
            Weights(),
        )
        == 100
    )


def test_experience_has_low_effect():
    s = SubScores(python_backend=100, fastapi=100, other_skills=100, experience=0)
    assert combine(s, Weights()) == 90


def test_gate_caps_non_python_jobs():
    s = SubScores(python_backend=10, fastapi=100, other_skills=100, experience=100)
    assert combine(s, Weights()) <= 35


def test_location_and_company_never_reach_the_llm():
    text = render_job(_job()) + build_system(_candidate())
    assert "SECRET" not in text
    assert "MY-RESUME-TEXT" in text


def test_retries_on_429_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, text="rate limited")
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]},
        )

    llm = LLMClient(
        "k", "https://x.test/v4/", "m", transport=httpx.MockTransport(handler)
    )
    assert llm.chat([{"role": "user", "content": "hi"}], backoff=0) == "ok"
    assert len(calls) == 2
