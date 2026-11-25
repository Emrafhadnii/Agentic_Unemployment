import httpx

from agentic_unemployment.sources.github import (
    fetch_readme,
    fetch_repos,
    make_client,
    render_evidence,
)


def test_filters_forks_and_archived_and_sorts_by_stars():
    def handler(request):
        return httpx.Response(
            200,
            json=[
                {
                    "name": "forked",
                    "fork": True,
                    "archived": False,
                    "stargazers_count": 100,
                },
                {
                    "name": "old",
                    "fork": False,
                    "archived": True,
                    "stargazers_count": 100,
                },
                {
                    "name": "low",
                    "fork": False,
                    "archived": False,
                    "stargazers_count": 1,
                    "pushed_at": "2026-01-01",
                },
                {
                    "name": "high",
                    "fork": False,
                    "archived": False,
                    "stargazers_count": 10,
                    "pushed_at": "2025-01-01",
                },
            ],
        )

    client = make_client(transport=httpx.MockTransport(handler))
    repos = fetch_repos(client, "me", max_repos=10)
    assert [r["name"] for r in repos] == ["high", "low"]


def test_readme_missing_returns_none():
    client = make_client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    assert fetch_readme(client, "me", "repo") is None


def test_evidence_contains_profile_repos_and_readme():
    user = {"login": "me", "name": "Me", "public_repos": 3, "followers": 1}
    repos = [
        {
            "name": "api",
            "language": "Python",
            "stargazers_count": 5,
            "description": "FastAPI service",
            "topics": ["fastapi"],
            "pushed_at": "2026-01-01",
        }
    ]
    text = render_evidence(user, repos, {"api": "Runs with Docker."})
    assert "Username: me" in text
    assert "Python" in text
    assert "FastAPI service" in text
    assert "Runs with Docker." in text
