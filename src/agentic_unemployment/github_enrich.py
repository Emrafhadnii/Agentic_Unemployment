from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from agentic_unemployment.llm import LLMClient
from agentic_unemployment.sources.github import (
    fetch_readme,
    fetch_repos,
    fetch_user,
    make_client,
    render_evidence,
)

log = logging.getLogger(__name__)

BULLETS_PROMPT = """You turn public GitHub evidence into truthful resume material for ONE candidate.

Rules:
- Use ONLY facts present in the evidence below. Never invent technologies, metrics, impact, users or dates.
- Prefer concrete engineering details: what each project does, the stack, and notable implementation choices.
- Ignore forks, trivial/tutorial repos, and abandoned experiments unless the evidence clearly shows real work.
- Do not include links, emails or phone numbers.
- Write in English. Reply with markdown ONLY, no code fences.

Format:
# GitHub Projects

## <repository name> — <main language>
- <one or two specific bullets>

Use at most 8 repositories and at most 2 bullets each. Omit repositories you cannot describe factually.

=== GITHUB EVIDENCE ===
{evidence}
"""

SUGGESTIONS_PROMPT = """You review a developer's public GitHub presence and suggest concrete improvements.

Rules:
- Base every suggestion on the evidence below. Be specific, not generic.
- Focus on things the developer can change: profile bio/headline, pinned repositories,
  repository descriptions and topics, README structure, missing tests/CI/docker/docs,
  and which projects to showcase for backend/Python roles.
- Do not invent facts. Do not include links.
- Write in English. Reply with a short markdown checklist ONLY, no code fences.

Format:
# GitHub profile suggestions

## Profile
- [ ] ...

## Repositories to showcase
- [ ] ...

## Per-repository improvements
- [ ] ...

=== GITHUB EVIDENCE ===
{evidence}
"""

_URL = re.compile(r"https?://\S+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+98|0)?9\d{9}(?!\d)")


@dataclass(frozen=True)
class GitHubDocs:
    bullets: str
    suggestions: str
    bullets_path: Path | None = None
    suggestions_path: Path | None = None


def proxy_for_github(settings) -> str | None:
    return settings.github_proxy or settings.outbound_proxy or settings.http_proxy


def _strip_fences(text: str) -> str:
    text = re.sub(r"^\s*```(?:markdown|md)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _sanitize(text: str) -> str:
    """Never let generated links/contact details reach the resume corpus."""
    text = _URL.sub("", text)
    text = _EMAIL.sub("", text)
    text = _PHONE.sub("", text)
    return re.sub(r"[ \t]+\n", "\n", text).strip()


def _fetch_github(settings, username: str, max_repos: int, readme_repos: int):
    token = settings.github_token.get_secret_value() if settings.github_token else None
    with make_client(token, proxy_for_github(settings)) as client:
        user = fetch_user(client, username)
        repos = fetch_repos(client, username, max_repos)
        readmes: dict[str, str] = {}
        for repo in repos[:readme_repos]:
            readme = fetch_readme(client, username, repo["name"])
            if readme:
                readmes[repo["name"]] = readme
    return user, repos, readmes


def check_github(settings, username: str) -> tuple[dict, list[dict], str | None]:
    user, repos, readmes = _fetch_github(
        settings, username, max_repos=3, readme_repos=1
    )
    readme = next(iter(readmes.values()), None)
    return user, repos, readme


def enrich_github(
    settings,
    username: str,
    *,
    dry_run: bool = False,
    max_repos: int | None = None,
    readme_repos: int | None = None,
) -> GitHubDocs:
    max_repos = settings.github_max_repos if max_repos is None else max_repos
    readme_repos = (
        settings.github_readme_repos if readme_repos is None else readme_repos
    )

    user, repos, readmes = _fetch_github(settings, username, max_repos, readme_repos)
    log.info("github: %d repos, %d README(s)", len(repos), len(readmes))
    evidence = render_evidence(user, repos, readmes)

    llm = LLMClient.from_settings(settings)
    bullets = _sanitize(
        _strip_fences(
            llm.chat(
                [
                    {
                        "role": "system",
                        "content": BULLETS_PROMPT.format(evidence=evidence),
                    },
                    {"role": "user", "content": "Write the resume projects section."},
                ]
            )
        )
    )
    suggestions = _sanitize(
        _strip_fences(
            llm.chat(
                [
                    {
                        "role": "system",
                        "content": SUGGESTIONS_PROMPT.format(evidence=evidence),
                    },
                    {
                        "role": "user",
                        "content": "Write the GitHub improvement checklist.",
                    },
                ]
            )
        )
    )

    if dry_run:
        return GitHubDocs(bullets, suggestions)

    resume_dir = Path(settings.resume_dir)
    resume_dir.mkdir(parents=True, exist_ok=True)
    bullets_path = resume_dir / "github.md"
    suggestions_path = resume_dir / "_github_suggestions.md"
    bullets_path.write_text(
        "<!-- generated by au github enrich; edit freely -->\n\n" + bullets + "\n",
        encoding="utf-8",
    )
    suggestions_path.write_text(suggestions + "\n", encoding="utf-8")
    log.info("wrote %s and %s", bullets_path, suggestions_path)
    return GitHubDocs(bullets, suggestions, bullets_path, suggestions_path)
