from datetime import datetime
from pathlib import Path

from agentic_unemployment.models.job import Job
from agentic_unemployment.sources.jobinja import parse_detail, parse_list
from agentic_unemployment.storage import Storage

SAMPLES = Path(__file__).parent.parent / "samples" / "jobinja"
NOW = datetime(2026, 11, 22, 12, 0)


def _jobs():
    return parse_list((SAMPLES / "card_1.html").read_text(encoding="utf-8"), NOW)


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
        fetched_at=NOW,
    )


def test_dedup():
    db = Storage(":memory:")
    assert len(db.insert_new(_jobs())) == 1
    assert db.insert_new(_jobs()) == []
    assert db.count() == 1


def test_same_id_on_different_sources_is_distinct():
    db = Storage(":memory:")
    jobs = [_job("jobinja", "42"), _job("jobvision", "42")]
    assert db.insert_new(jobs) == jobs
    assert db.count() == 2
    assert db.count_by_source() == {"jobinja": 1, "jobvision": 1}


def test_detail_roundtrip():
    db = Storage(":memory:")
    db.insert_new(_jobs())

    pending = db.pending_detail()
    assert len(pending) == 1
    job = parse_detail((SAMPLES / "job_1.html").read_text(encoding="utf-8"), pending[0])
    db.save_detail(job)

    assert db.pending_detail() == []
    saved = db._to_job(db.conn.execute("SELECT * FROM jobs").fetchone())
    assert saved.skills == ["تحلیل", "Linux", "Python"]
    assert "Malware Analysis" in saved.description
    assert saved.is_remote is True
