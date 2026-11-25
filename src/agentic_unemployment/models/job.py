from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Job:
    source: str
    source_id: str
    url: str
    title: str
    company: str | None
    location_raw: str | None
    employment_type_raw: str | None
    salary_raw: str | None
    posted_raw: str | None
    posted_at: datetime | None
    fetched_at: datetime

    is_remote: bool = False
    description: str | None = None
    category_raw: str | None = None
    experience_raw: str | None = None
    education_raw: str | None = None
    military_raw: str | None = None
    skills: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"
