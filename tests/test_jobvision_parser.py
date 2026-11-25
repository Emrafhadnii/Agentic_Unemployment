import json
from datetime import UTC, datetime
from pathlib import Path

from agentic_unemployment.sources.jobvision import parse_detail, parse_list

SAMPLES = Path(__file__).parent.parent / "samples" / "jobvision"
NOW = datetime(2026, 11, 25, 9, 30)


def _load(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def test_list_fields():
    jobs = parse_list(_load("list_p1.json"), NOW)
    assert len(jobs) == 10

    job = jobs[0]
    assert job.key == "jobvision:1607787"
    assert job.url == "https://jobvision.ir/jobs/1607787"
    assert job.title == "برنامه‌نویس Python"
    assert job.company == "غزال اکسین مهرگان"
    assert job.location_raw == "البرز، کرج، گلشهر"
    assert job.employment_type_raw == "تمام وقت"
    assert job.is_remote is False
    assert job.experience_raw == "بدون نیاز به سابقه"
    assert job.posted_raw == "دیروز"
    expected = datetime(2026, 11, 24, 11, 42, 19, tzinfo=UTC).astimezone()
    assert job.posted_at == expected.replace(tzinfo=None)


def test_list_keeps_salary_and_remote_flag():
    jobs = parse_list(_load("list_p1.json"), NOW)
    salaried = next(job for job in jobs if job.source_id == "1626936")
    assert salaried.salary_raw == "60 - 70 میلیون تومان"
    assert salaried.experience_raw == "5 سال"


def test_detail_fields():
    job = parse_list(_load("list_p1.json"), NOW)[0]
    parse_detail(_load("detail_1.json"), job)

    assert job.description.startswith("مسلط به Python")
    assert "<div" not in job.description
    assert "Visual Studio" in job.description
    assert job.is_remote is False
    assert job.location_raw == "البرز، کرج، گلشهر"
    assert job.experience_raw == "بدون نیاز به سابقه"
    assert job.education_raw == "کاردانی کامپیوتر / فناوری اطلاعات"
    assert job.military_raw == "نیاز به پایان خدمت"
    assert job.skills == [
        "Python",
        "Microsoft Visual Studio",
        "Microsoft SQL Server",
        "MySQL",
        "AI Chatbots & General Assistants",
    ]


def test_detail_preserves_list_salary_when_detail_hides_it():
    job = next(
        job
        for job in parse_list(_load("list_p1.json"), NOW)
        if job.source_id == "1626936"
    )
    parse_detail({"description": "short detail page"}, job)
    assert job.salary_raw == "60 - 70 میلیون تومان"
    assert job.experience_raw == "5 سال"
