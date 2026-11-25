from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from agentic_unemployment.models.job import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key                 TEXT PRIMARY KEY,
    source              TEXT NOT NULL,
    source_id           TEXT NOT NULL,
    url                 TEXT NOT NULL,
    title               TEXT NOT NULL,
    company             TEXT,
    location_raw        TEXT,
    employment_type_raw TEXT,
    salary_raw          TEXT,
    posted_raw          TEXT,
    posted_at           TEXT,
    fetched_at          TEXT NOT NULL,
    is_remote           INTEGER NOT NULL DEFAULT 0,
    description         TEXT,
    category_raw        TEXT,
    experience_raw      TEXT,
    education_raw       TEXT,
    military_raw        TEXT,
    skills              TEXT NOT NULL DEFAULT '[]',
    first_seen_at       TEXT NOT NULL,
    detail_fetched_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_pending ON jobs(detail_fetched_at);
CREATE TABLE IF NOT EXISTS matches (
    job_key              TEXT NOT NULL,
    candidate_hash       TEXT NOT NULL,
    score                INTEGER NOT NULL,
    verdict              TEXT NOT NULL,
    sub_scores           TEXT NOT NULL,
    summary              TEXT NOT NULL,
    reasons              TEXT NOT NULL,
    missing_requirements TEXT NOT NULL,
    model                TEXT NOT NULL,
    scored_at            TEXT NOT NULL,
    PRIMARY KEY (job_key, candidate_hash)
);
CREATE TABLE IF NOT EXISTS match_failures (
    job_key        TEXT NOT NULL,
    candidate_hash TEXT NOT NULL,
    attempts       INTEGER NOT NULL,
    last_error     TEXT,
    last_at        TEXT,
    PRIMARY KEY (job_key, candidate_hash)
);
CREATE TABLE IF NOT EXISTS notifications (
    job_key        TEXT PRIMARY KEY,
    candidate_hash TEXT NOT NULL,
    score          INTEGER NOT NULL,
    sent_at        TEXT NOT NULL
);
"""

_DETAIL_COLUMNS = (
    "location_raw",
    "employment_type_raw",
    "salary_raw",
    "category_raw",
    "experience_raw",
    "education_raw",
    "military_raw",
    "description",
)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class Storage:
    def __init__(self, path: str | Path = "data/jobs.db") -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=30.0)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA busy_timeout = 30000")
        if str(path) != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def insert_new(self, jobs: list[Job]) -> list[Job]:
        """Insert jobs we haven't seen. Returns only the newly inserted ones."""
        new: list[Job] = []
        now = datetime.now().isoformat()
        with self.conn:
            for j in jobs:
                cur = self.conn.execute(
                    """INSERT OR IGNORE INTO jobs
                       (key, source, source_id, url, title, company, location_raw,
                        employment_type_raw, salary_raw, posted_raw, posted_at,
                        fetched_at, is_remote, category_raw, experience_raw,
                        first_seen_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        j.key,
                        j.source,
                        j.source_id,
                        j.url,
                        j.title,
                        j.company,
                        j.location_raw,
                        j.employment_type_raw,
                        j.salary_raw,
                        j.posted_raw,
                        _iso(j.posted_at),
                        _iso(j.fetched_at),
                        int(j.is_remote),
                        j.category_raw,
                        j.experience_raw,
                        now,
                    ),
                )
                if cur.rowcount:
                    new.append(j)
        return new

    def pending_detail(self, source: str | None = None) -> list[Job]:
        sql = "SELECT * FROM jobs WHERE detail_fetched_at IS NULL"
        args: tuple = ()
        if source:
            sql += " AND source = ?"
            args = (source,)
        return [self._to_job(r) for r in self.conn.execute(sql, args)]

    def save_detail(self, job: Job) -> None:
        sets = ", ".join(f"{c} = ?" for c in _DETAIL_COLUMNS)
        with self.conn:
            self.conn.execute(
                f"""UPDATE jobs SET {sets}, is_remote = ?, skills = ?,
                    detail_fetched_at = ? WHERE key = ?""",
                (
                    *(getattr(job, c) for c in _DETAIL_COLUMNS),
                    int(job.is_remote),
                    json.dumps(job.skills, ensure_ascii=False),
                    datetime.now().isoformat(),
                    job.key,
                ),
            )

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def count_by_source(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT source, COUNT(*) FROM jobs GROUP BY source ORDER BY source"
        ).fetchall()
        return {row[0]: row[1] for row in rows}

    def count_pending_detail(self, source: str | None = None) -> int:
        sql = "SELECT COUNT(*) FROM jobs WHERE detail_fetched_at IS NULL"
        args: tuple = ()
        if source:
            sql += " AND source = ?"
            args = (source,)
        return self.conn.execute(sql, args).fetchone()[0]

    def count_pending_match(self, candidate_hash: str, max_attempts: int) -> int:
        return self.conn.execute(
            """SELECT COUNT(*) FROM jobs j
               WHERE j.detail_fetched_at IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM matches m
                                 WHERE m.job_key = j.key AND m.candidate_hash = ?)
                 AND COALESCE((SELECT attempts FROM match_failures f
                               WHERE f.job_key = j.key AND f.candidate_hash = ?), 0) < ?""",
            (candidate_hash, candidate_hash, max_attempts),
        ).fetchone()[0]

    def count_matches(self, candidate_hash: str | None = None) -> int:
        if candidate_hash:
            return self.conn.execute(
                "SELECT COUNT(*) FROM matches WHERE candidate_hash = ?",
                (candidate_hash,),
            ).fetchone()[0]
        return self.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]

    @staticmethod
    def _to_job(r: sqlite3.Row) -> Job:
        return Job(
            source=r["source"],
            source_id=r["source_id"],
            url=r["url"],
            title=r["title"],
            company=r["company"],
            location_raw=r["location_raw"],
            employment_type_raw=r["employment_type_raw"],
            salary_raw=r["salary_raw"],
            posted_raw=r["posted_raw"],
            posted_at=_dt(r["posted_at"]),
            fetched_at=datetime.fromisoformat(r["fetched_at"]),
            is_remote=bool(r["is_remote"]),
            description=r["description"],
            category_raw=r["category_raw"],
            experience_raw=r["experience_raw"],
            education_raw=r["education_raw"],
            military_raw=r["military_raw"],
            skills=json.loads(r["skills"]),
        )

    def pending_match(
        self, candidate_hash: str, limit: int, max_attempts: int
    ) -> list[Job]:
        rows = self.conn.execute(
            """SELECT j.* FROM jobs j
               WHERE j.detail_fetched_at IS NOT NULL
                 AND NOT EXISTS (SELECT 1 FROM matches m
                                 WHERE m.job_key = j.key AND m.candidate_hash = ?)
                 AND COALESCE((SELECT attempts FROM match_failures f
                               WHERE f.job_key = j.key AND f.candidate_hash = ?), 0) < ?
               ORDER BY j.first_seen_at DESC
               LIMIT ?""",
            (candidate_hash, candidate_hash, max_attempts, limit),
        ).fetchall()
        return [self._to_job(r) for r in rows]

    def save_match(self, job_key: str, candidate_hash: str, model: str, r) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT OR REPLACE INTO matches
                   (job_key, candidate_hash, score, verdict, sub_scores, summary,
                    reasons, missing_requirements, model, scored_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_key,
                    candidate_hash,
                    r.score,
                    r.verdict,
                    json.dumps(r.sub_scores.model_dump()),
                    r.summary,
                    json.dumps(r.reasons, ensure_ascii=False),
                    json.dumps(r.missing_requirements, ensure_ascii=False),
                    model,
                    datetime.now().isoformat(),
                ),
            )

    def record_match_failure(
        self, job_key: str, candidate_hash: str, error: str
    ) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO match_failures (job_key, candidate_hash, attempts, last_error, last_at)
                   VALUES (?,?,1,?,?)
                   ON CONFLICT(job_key, candidate_hash) DO UPDATE SET
                     attempts = attempts + 1,
                     last_error = excluded.last_error,
                     last_at = excluded.last_at""",
                (job_key, candidate_hash, error[:500], datetime.now().isoformat()),
            )

    def unnotified_high_matches(
        self,
        candidate_hash: str | None,
        min_score: int,
        limit: int = 50,
        any_candidate: bool = False,
    ) -> list[tuple[Job, sqlite3.Row]]:
        """Matches above the threshold that were never sent to any channel.

        Notifications are keyed by job, not by candidate: editing the resume
        should not re-send jobs the user has already seen. With
        ``any_candidate`` the best match per job across every resume version
        is considered instead of only the current candidate hash.
        """
        if any_candidate:
            rows = self.conn.execute(
                """WITH best AS (
                       SELECT m.*, ROW_NUMBER() OVER (
                           PARTITION BY m.job_key
                           ORDER BY m.score DESC, m.scored_at DESC
                       ) AS rn
                       FROM matches m
                   )
                   SELECT j.*, b.candidate_hash, b.score, b.verdict, b.summary,
                          b.reasons, b.missing_requirements, b.scored_at
                   FROM best b
                   JOIN jobs j ON j.key = b.job_key
                   WHERE b.rn = 1
                     AND b.score > ?
                     AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.job_key = j.key)
                   ORDER BY b.score DESC, b.scored_at DESC
                   LIMIT ?""",
                (min_score, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """SELECT j.*, m.candidate_hash, m.score, m.verdict, m.summary,
                          m.reasons, m.missing_requirements, m.scored_at
                   FROM matches m
                   JOIN jobs j ON j.key = m.job_key
                   WHERE m.candidate_hash = ?
                     AND m.score > ?
                     AND NOT EXISTS (SELECT 1 FROM notifications n WHERE n.job_key = j.key)
                   ORDER BY m.score DESC, m.scored_at DESC
                   LIMIT ?""",
                (candidate_hash, min_score, limit),
            ).fetchall()
        return [(self._to_job(r), r) for r in rows]

    def mark_notified(self, job_key: str, candidate_hash: str, score: int) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO notifications
                   (job_key, candidate_hash, score, sent_at)
                   VALUES (?,?,?,?)""",
                (job_key, candidate_hash, score, datetime.now().isoformat()),
            )

    def count_notified(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
