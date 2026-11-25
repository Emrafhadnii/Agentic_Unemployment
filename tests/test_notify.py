import json
from datetime import datetime

import httpx

from agentic_unemployment.matcher import MatchResult, SubScores
from agentic_unemployment.models.job import Job
from agentic_unemployment.notify import TelegramNotifier
from agentic_unemployment.storage import Storage


def _db(score=88, title="Backend Developer", key="jobinja:1", candidate_hash="h"):
    db = Storage(":memory:")
    job = Job(
        source="jobinja",
        source_id=key.split(":")[1],
        url="https://jobinja.ir/job/1",
        title=title,
        company="ACME",
        location_raw="Tehran",
        employment_type_raw="تمام وقت، دورکاری",
        salary_raw="۳۰,۰۰۰,۰۰۰",
        posted_raw="۲ روز پیش",
        posted_at=None,
        fetched_at=datetime(2026, 11, 24),
    )
    job.experience_raw = "سه تا شش سال"
    job.skills = ["Python", "FastAPI", "PostgreSQL"]
    db.insert_new([job])
    db.save_detail(job)
    result = MatchResult(
        sub_scores=SubScores(
            python_backend=90, fastapi=100, other_skills=60, experience=70
        ),
        summary="good fit",
        reasons=["real Python work", "FastAPI"],
        missing_requirements=["Kafka"],
        score=score,
        verdict="strong",
    )
    db.save_match(job.key, candidate_hash, "fake", result)
    return db, job


def _ok_handler(calls):
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True})

    return handler


def test_sends_once_per_job():
    db, _ = _db()
    calls = []
    notifier = TelegramNotifier(
        "t", 1, transport=httpx.MockTransport(_ok_handler(calls))
    )

    assert notifier.notify_matches(db, "h") == (1, 0)
    assert notifier.notify_matches(db, "h") == (0, 0)
    assert len(calls) == 1
    assert calls[0]["chat_id"] == 1
    text = calls[0]["text"]
    assert "Backend Developer" in text
    assert "ACME" in text
    assert "88/100" in text
    assert "۳۰,۰۰۰,۰۰۰" in text
    assert "سه تا شش سال" in text
    assert "Python, FastAPI, PostgreSQL" in text
    assert "https://jobinja.ir/job/1" in text


def test_score_must_be_strictly_above_threshold():
    db, _ = _db(score=50)
    calls = []
    notifier = TelegramNotifier(
        "t", 1, min_score=50, transport=httpx.MockTransport(_ok_handler(calls))
    )
    assert notifier.notify_matches(db, "h") == (0, 0)
    assert calls == []


def test_failed_send_is_retried_next_time():
    db, _ = _db()
    failing = TelegramNotifier(
        "t",
        1,
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")),
    )
    assert failing.notify_matches(db, "h") == (0, 1)
    assert db.count_notified() == 0

    calls = []
    working = TelegramNotifier(
        "t", 1, transport=httpx.MockTransport(_ok_handler(calls))
    )
    assert working.notify_matches(db, "h") == (1, 0)
    assert db.count_notified() == 1


def test_disabled_without_token():
    calls = []
    notifier = TelegramNotifier(
        None, 1, transport=httpx.MockTransport(_ok_handler(calls))
    )
    assert notifier.enabled is False
    assert notifier.send("hi") is False
    assert calls == []


def test_html_is_escaped():
    db, _ = _db(title="<b>Backend</b>")
    calls = []
    notifier = TelegramNotifier(
        "t", 1, transport=httpx.MockTransport(_ok_handler(calls))
    )
    assert notifier.notify_matches(db, "h") == (1, 0)
    assert "&lt;b&gt;Backend&lt;/b&gt;" in calls[0]["text"]


def test_any_candidate_uses_best_match_and_sends_once():
    db, _ = _db(score=60, candidate_hash="old")
    db.save_match(
        "jobinja:1",
        "new",
        "fake",
        MatchResult(
            sub_scores=SubScores(
                python_backend=90, fastapi=100, other_skills=60, experience=70
            ),
            summary="better",
            reasons=["r"],
            missing_requirements=[],
            score=95,
            verdict="strong",
        ),
    )
    calls = []
    notifier = TelegramNotifier(
        "t", 1, transport=httpx.MockTransport(_ok_handler(calls))
    )

    assert notifier.notify_matches(db, None, any_candidate=True) == (1, 0)
    assert "95/100" in calls[0]["text"]
    assert notifier.notify_matches(db, None, any_candidate=True) == (0, 0)


def test_dry_run_prints_without_sending_or_marking(capsys):
    db, _ = _db()
    calls = []
    notifier = TelegramNotifier(
        None, None, transport=httpx.MockTransport(_ok_handler(calls))
    )

    assert notifier.notify_matches(db, "h", dry_run=True) == (1, 0)
    assert "Backend Developer" in capsys.readouterr().out
    assert calls == []
    assert db.count_notified() == 0


def test_abort_alert():
    calls = []
    notifier = TelegramNotifier(
        "t", 1, transport=httpx.MockTransport(_ok_handler(calls))
    )
    assert notifier.send_abort_alert("LLM down") is True
    assert "Scoring stopped" in calls[0]["text"]
