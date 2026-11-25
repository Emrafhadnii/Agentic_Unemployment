import json
from contextlib import nullcontext
from datetime import datetime

from agentic_unemployment import pipeline
from agentic_unemployment.candidate import Candidate, Profile
from agentic_unemployment.config import SearchSpec
from agentic_unemployment.llm import LLMError
from agentic_unemployment.models.job import Job
from agentic_unemployment.pipeline import score_pending
from agentic_unemployment.storage import Storage

GOOD = json.dumps(
    {
        "sub_scores": {
            "python_backend": 90,
            "fastapi": 100,
            "other_skills": 60,
            "experience": 70,
        },
        "summary": "ok",
        "reasons": ["r"],
        "missing_requirements": [],
    }
)


class FakeLLM:
    model = "fake"

    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, messages, **kw):
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _candidate(resume="R"):
    p = Profile(target_roles=["b"], seniority="junior", years_experience=2)
    return Candidate(resume_text=resume, profile=p, hash=f"h-{resume}")


def _job(source: str, source_id: str) -> Job:
    return Job(
        source=source,
        source_id=source_id,
        url=f"https://example.com/{source}/{source_id}",
        title=f"{source} job",
        company=None,
        location_raw=None,
        employment_type_raw=None,
        salary_raw=None,
        posted_raw=None,
        posted_at=None,
        fetched_at=datetime(2026, 11, 22),
    )


class FakeSource:
    def __init__(self, job: Job) -> None:
        self.job = job
        self.calls: list[tuple[list[str], bool]] = []

    def make_client(self):
        return nullcontext(object())

    def crawl_list(
        self, client, keywords, remote=False, max_pages=5, delay=1.5
    ) -> list[Job]:
        self.calls.append((keywords, remote))
        return [self.job]


def test_crawl_dispatches_each_source(monkeypatch):
    db = Storage(":memory:")
    jobinja = FakeSource(_job("jobinja", "1"))
    jobvision = FakeSource(_job("jobvision", "2"))
    monkeypatch.setattr(
        pipeline,
        "SOURCES",
        {"jobinja": jobinja, "jobvision": jobvision},
    )

    stats = pipeline.crawl_searches(
        db,
        [
            SearchSpec(source="jobinja", keywords=["python"]),
            SearchSpec(source="jobvision", keywords=["backend"], remote=True),
        ],
        fetch_details=False,
    )

    assert (stats.searches, stats.search_failures) == (2, 0)
    assert (stats.found, stats.new) == (2, 2)
    assert db.count_by_source() == {"jobinja": 1, "jobvision": 1}
    assert jobinja.calls == [(["python"], False)]
    assert jobvision.calls == [(["backend"], True)]


def _db(n=1):
    db = Storage(":memory:")
    jobs = [
        Job(
            source="jobinja",
            source_id=f"id{i}",
            url="u",
            title=f"T{i}",
            company=None,
            location_raw=None,
            employment_type_raw=None,
            salary_raw=None,
            posted_raw=None,
            posted_at=None,
            fetched_at=datetime(2026, 11, 22),
        )
        for i in range(n)
    ]
    db.insert_new(jobs)
    for j in jobs:
        db.save_detail(j)
    return db


def test_stops_after_consecutive_transient_errors():
    db = _db(5)
    llm = FakeLLM([LLMError("down", transient=True)] * 3)
    ok, failed, aborted = score_pending(db, llm, _candidate())
    assert (ok, failed, aborted) == (0, 0, True)
    assert len(db.pending_match("h-R", 50, 3)) == 5  # nothing lost, nothing penalised


def test_unexpected_error_is_recorded_not_raised():
    db = _db(1)
    ok, failed, aborted = score_pending(
        db, FakeLLM([KeyError("choices")]), _candidate(), max_attempts=1
    )
    assert (ok, failed, aborted) == (0, 1, False)
    assert db.pending_match("h-R", 50, 1) == []


def test_bad_output_is_skipped_after_max_attempts():
    db = _db(1)
    for _ in range(3):  # score_job makes 2 calls per attempt
        score_pending(db, FakeLLM(["junk", "junk"]), _candidate())
    assert db.pending_match("h-R", 50, 3) == []


def test_success_is_stored_and_not_repeated_until_resume_changes():
    db = _db(1)
    assert score_pending(db, FakeLLM([GOOD]), _candidate())[0] == 1
    assert db.pending_match("h-R", 50, 3) == []
    assert len(db.pending_match("h-R2", 50, 3)) == 1  # new resume hash: score again
