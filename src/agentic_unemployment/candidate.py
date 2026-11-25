from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+98|0)?9\d{9}(?!\d)")
_URL = re.compile(r"https?://\S+")
_DOC_SEPARATOR = "\n\n---\n\n"


class Weights(BaseModel):
    python_backend: float = 0.55
    fastapi: float = 0.15
    other_skills: float = 0.20
    experience: float = 0.10


class Profile(BaseModel):
    target_roles: list[str]
    seniority: Literal["junior", "mid", "senior"]
    years_experience: float
    weights: Weights = Weights()
    exclude_title_keywords: list[str] = []
    exclude_companies: list[str] = []
    resume_files: list[str] | None = None


@dataclass(frozen=True)
class Candidate:
    resume_text: str
    profile: Profile
    hash: str
    files: tuple[str, ...] = ()


def _check_no_contact_info(text: str, name: str = "resume") -> None:
    found = [
        kind
        for kind, rx in (("email", _EMAIL), ("phone", _PHONE), ("url", _URL))
        if rx.search(text)
    ]
    if found:
        raise ValueError(
            f"{name} still contains contact info ({', '.join(found)}). "
            "Remove it: this text is sent to an LLM API."
        )


def _select_files(directory: Path, selected: list[str] | None) -> list[Path]:
    if selected:
        paths = [directory / name for name in selected]
        missing = [
            p.relative_to(directory).as_posix() for p in paths if not p.is_file()
        ]
        if missing:
            raise FileNotFoundError(f"resume_files not found: {', '.join(missing)}")
        return paths

    files = [
        p
        for p in directory.rglob("*.md")
        if p.is_file() and not p.name.startswith("_") and p.name.lower() != "readme.md"
    ]
    if not files:
        raise FileNotFoundError(f"no resume markdown files found in {directory}")

    main = directory / "resume.md"
    if main.is_file():
        files = [main] + sorted(p for p in files if p != main)
    else:
        files = sorted(files)
    return files


def load_candidate(directory: Path = Path("resume")) -> Candidate:
    profile_raw = (directory / "profile.yaml").read_text(encoding="utf-8")
    profile = Profile.model_validate(yaml.safe_load(profile_raw))

    files = _select_files(directory, profile.resume_files)
    parts: list[str] = []
    names: list[str] = []
    digest = hashlib.sha256()

    for path in files:
        rel = path.relative_to(directory).as_posix()
        text = path.read_text(encoding="utf-8").strip()
        _check_no_contact_info(text, rel)
        parts.append(text)
        names.append(rel)
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")

    digest.update(profile_raw.encode("utf-8"))
    return Candidate(
        resume_text=_DOC_SEPARATOR.join(parts),
        profile=profile,
        hash=digest.hexdigest(),
        files=tuple(names),
    )
