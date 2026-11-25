from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)
API = "https://api.github.com"
MAX_README_CHARS = 4000


class GitHubError(RuntimeError):
    pass


def make_client(
    token: str | None = None,
    proxy: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> httpx.Client:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "agentic-unemployment",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return httpx.Client(
        base_url=API,
        headers=headers,
        timeout=20.0,
        follow_redirects=True,
        proxy=None if transport else proxy,
        transport=transport,
    )


def _get(client: httpx.Client, path: str, **params) -> httpx.Response:
    resp = client.get(path, params=params)
    if resp.status_code == 404:
        raise GitHubError(f"not found: {path}")
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise GitHubError("GitHub API rate limit exceeded (set GITHUB_TOKEN)")
    if resp.status_code >= 400:
        raise GitHubError(f"GitHub HTTP {resp.status_code}: {resp.text[:300]}")
    return resp


def fetch_user(client: httpx.Client, username: str) -> dict:
    return _get(client, f"/users/{username}").json()


def fetch_repos(client: httpx.Client, username: str, max_repos: int = 12) -> list[dict]:
    """Public, non-fork, non-archived repos, most interesting first."""
    raw = _get(
        client,
        f"/users/{username}/repos",
        sort="pushed",
        per_page=100,
        type="owner",
    ).json()
    repos = [
        r for r in raw if not r.get("fork") and not r.get("archived") and r.get("name")
    ]
    repos.sort(
        key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at") or ""),
        reverse=True,
    )
    return repos[:max_repos]


def fetch_readme(client: httpx.Client, username: str, repo: str) -> str | None:
    resp = client.get(
        f"/repos/{username}/{repo}/readme",
        headers={"Accept": "application/vnd.github.raw"},
    )
    if resp.status_code == 404:
        return None
    if resp.status_code >= 400:
        log.warning(
            "README fetch failed for %s/%s: HTTP %s", username, repo, resp.status_code
        )
        return None
    return resp.text[:MAX_README_CHARS]


def render_evidence(
    user: dict,
    repos: list[dict],
    readmes: dict[str, str] | None = None,
) -> str:
    readmes = readmes or {}
    lines = [
        "=== GITHUB PROFILE ===",
        f"Username: {user.get('login', '-')}",
        f"Name: {user.get('name') or '-'}",
        f"Bio: {user.get('bio') or '-'}",
        f"Company: {user.get('company') or '-'}",
        f"Location: {user.get('location') or '-'}",
        f"Public repos: {user.get('public_repos', '-')}",
        f"Followers: {user.get('followers', '-')}",
        "",
        "=== REPOSITORIES ===",
    ]
    for repo in repos:
        topics = ", ".join(repo.get("topics") or []) or "-"
        lines += [
            "",
            (
                f"## {repo['name']} ({repo.get('language') or 'unknown language'}, "
                f"{repo.get('stargazers_count', 0)} stars)"
            ),
            f"Description: {repo.get('description') or '-'}",
            f"Topics: {topics}",
            f"Last push: {repo.get('pushed_at') or '-'}",
        ]
        readme = readmes.get(repo["name"])
        if readme:
            lines += ["README:", readme.strip()]
    return "\n".join(lines)
