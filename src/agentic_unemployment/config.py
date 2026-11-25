from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

SourceName = Literal["jobinja", "jobvision"]


class SearchSpec(BaseModel):
    source: SourceName = "jobinja"
    keywords: list[str]
    remote: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_ignore_empty=True
    )

    db_path: Path = Path("data/jobs.db")
    log_level: str = "INFO"
    telegram_token: SecretStr | None = None
    telegram_chat_id: int | None = None
    telegram_min_score: int = 50
    telegram_alert_on_abort: bool = True
    telegram_timeout: float = 15.0

    outbound_proxy: str | None = None

    telegram_proxy: str | None = None
    github_proxy: str | None = None
    llm_api_key: SecretStr | None = None
    resume_dir: Path = Path("resume")
    http_proxy: str | None = None
    llm_base_url: str = "https://api.z.ai/api/paas/v4/"
    llm_model: str = "GLM-4.7-Flash"
    llm_timeout: float = 120.0
    llm_extra: dict = {"thinking": {"type": "disabled"}}
    score_limit: int = 50
    max_match_attempts: int = 3
    llm_min_interval: float = 2.0

    max_pages: int = 5
    request_delay: float = 1.5

    github_username: str | None = None
    github_token: SecretStr | None = None
    github_max_repos: int = 12
    github_readme_repos: int = 5

    searches: list[SearchSpec] = [
        SearchSpec(source="jobinja", keywords=["python"], remote=True),
        SearchSpec(source="jobinja", keywords=["python"], remote=False),
        SearchSpec(source="jobinja", keywords=["backend"], remote=True),
        SearchSpec(source="jobinja", keywords=["backend"], remote=False),
        SearchSpec(source="jobvision", keywords=["python"], remote=True),
        SearchSpec(source="jobvision", keywords=["python"], remote=False),
        SearchSpec(source="jobvision", keywords=["backend"], remote=True),
        SearchSpec(source="jobvision", keywords=["backend"], remote=False),
    ]


settings = Settings()
