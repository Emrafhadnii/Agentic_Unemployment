from datetime import datetime

import pytest
import typer
from typer.testing import CliRunner

from agentic_unemployment import cli
from agentic_unemployment.cli.common import build_searches
from agentic_unemployment.config import settings
from agentic_unemployment.matcher import MatchResult, SubScores
from agentic_unemployment.models.job import Job
from agentic_unemployment.storage import Storage

runner = CliRunner()

PROFILE = """
target_roles: [backend developer]
seniority: junior
years_experience: 2
"""


def _resume(tmp_path):
    (tmp_path / "resume.md").write_text(
        "# Test\n\n## Skills\n- Python", encoding="utf-8"
    )
    (tmp_path / "profile.yaml").write_text(PROFILE, encoding="utf-8")
    return tmp_path


def _db(tmp_path):
    path = tmp_path / "jobs.db"
    db = Storage(path)
    job = Job(
        source="jobinja",
        source_id="1",
        url="https://jobinja.ir/job/1",
        title="Backend Developer",
        company="ACME",
        location_raw="Tehran",
        employment_type_raw=None,
        salary_raw=None,
        posted_raw=None,
        posted_at=None,
        fetched_at=datetime(2026, 11, 24),
    )
    db.insert_new([job])
    db.save_detail(job)
    db.save_match(
        job.key,
        "h",
        "fake",
        MatchResult(
            sub_scores=SubScores(
                python_backend=90, fastapi=100, other_skills=60, experience=70
            ),
            summary="good fit",
            reasons=["python"],
            missing_requirements=[],
            score=88,
            verdict="strong",
        ),
    )
    db.close()
    return path


def test_build_searches_filters_by_source():
    specs = build_searches(["python"], remote=True, onsite=False, sources=["jobvision"])
    assert len(specs) == 1
    assert specs[0].source == "jobvision"
    assert specs[0].remote is True


def test_build_searches_rejects_unknown_source():
    with pytest.raises(typer.BadParameter):
        build_searches(["python"], remote=False, onsite=False, sources=["linkedin"])


def test_help_lists_commands():
    result = runner.invoke(cli.app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "crawl",
        "score",
        "notify",
        "run",
        "stats",
        "resume",
        "github",
        "telegram",
    ):
        assert command in result.output


def test_resume_check(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "resume_dir", _resume(tmp_path))
    result = runner.invoke(cli.app, ["resume", "check"])
    assert result.exit_code == 0
    assert "resume.md" in result.output
    assert "hash:" in result.output


def test_notify_dry_run_with_any_candidate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", _db(tmp_path))
    monkeypatch.setattr(settings, "telegram_token", None)
    monkeypatch.setattr(settings, "telegram_chat_id", None)

    result = runner.invoke(cli.app, ["notify", "--dry-run", "--any-candidate"])
    assert result.exit_code == 0
    assert "Backend Developer" in result.output
    assert "88/100" in result.output
    assert "dry run: would send 1" in result.output


def test_notify_without_telegram_config_exits_2(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", _db(tmp_path))
    monkeypatch.setattr(settings, "telegram_token", None)
    monkeypatch.setattr(settings, "telegram_chat_id", None)

    result = runner.invoke(cli.app, ["notify", "--any-candidate"])
    assert result.exit_code == 2
    assert "not configured" in result.output


def test_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", _db(tmp_path))
    monkeypatch.setattr(settings, "resume_dir", _resume(tmp_path))

    result = runner.invoke(cli.app, ["stats"])
    assert result.exit_code == 0
    assert "jobs: 1" in result.output
    assert "notified: 0" in result.output
