from datetime import datetime
from pathlib import Path

from agentic_unemployment.sources.jobinja import parse_detail, parse_list

SAMPLES = Path(__file__).parent.parent / "samples" / "jobinja"
NOW = datetime(2026, 11, 22, 12, 0)


def test_card_fields():
    jobs = parse_list((SAMPLES / "card_1.html").read_text(encoding="utf-8"), NOW)
    assert len(jobs) == 1
    j = jobs[0]
    assert j.key == "jobinja:t1E1"
    assert "?" not in j.url
    assert j.company == "لرن فایلز | Learnfiles"
    assert j.location_raw == "تهران، تهران"
    assert j.employment_type_raw == "قرارداد دورکاری"
    assert j.is_remote is True
    assert j.salary_raw is None
    assert j.posted_at == datetime(2026, 11, 15, 12, 0)


def test_full_list_page():
    jobs = parse_list((SAMPLES / "list_p1.html").read_text(encoding="utf-8"), NOW)
    assert len(jobs) > 5
    assert all(j.title and j.source_id for j in jobs)
    assert len({j.key for j in jobs}) == len(jobs)


def test_detail_fields():
    card = (SAMPLES / "card_1.html").read_text(encoding="utf-8")
    job = parse_list(card, NOW)[0]
    parse_detail((SAMPLES / "job_1.html").read_text(encoding="utf-8"), job)

    assert job.is_remote is True
    assert job.location_raw == "تهران، تهران"
    assert job.experience_raw == "سه تا شش سال"
    assert "۳۰,۰۰۰,۰۰۰" in job.salary_raw
    assert job.skills == ["تحلیل", "Linux", "Python"]
    assert "Malware Analysis" in job.description
    assert "ثبت آگهی استخدام در جابینجا" not in job.description
    assert "• " in job.description
