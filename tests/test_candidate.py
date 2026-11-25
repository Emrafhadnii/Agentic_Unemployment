import pytest

from agentic_unemployment.candidate import load_candidate

PROFILE = """
target_roles: [backend developer]
seniority: junior
years_experience: 2
"""


def _write(tmp_path, resume="# Test\n\n## Skills\n- Python", profile=PROFILE):
    (tmp_path / "resume.md").write_text(resume, encoding="utf-8")
    (tmp_path / "profile.yaml").write_text(profile, encoding="utf-8")
    return tmp_path


def _write_docs(tmp_path, docs, profile=PROFILE):
    for name, text in docs.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    (tmp_path / "profile.yaml").write_text(profile, encoding="utf-8")
    return tmp_path


def test_loads(tmp_path):
    c = load_candidate(_write(tmp_path))
    assert c.profile.seniority == "junior"
    assert "Python" in c.resume_text
    assert len(c.hash) == 64


def test_hash_changes_with_resume_and_profile(tmp_path):
    h1 = load_candidate(_write(tmp_path)).hash
    h2 = load_candidate(
        _write(tmp_path, resume="# Test\n\n## Skills\n- Python, Go")
    ).hash
    h3 = load_candidate(_write(tmp_path, profile=PROFILE + "cities: [تهران]\n")).hash
    assert len({h1, h2, h3}) == 3


@pytest.mark.parametrize(
    "leak", ["me@example.com", "09123456789", "https://github.com/x"]
)
def test_rejects_contact_info(tmp_path, leak):
    with pytest.raises(ValueError, match="contact info"):
        load_candidate(_write(tmp_path, resume=f"# Test\n{leak}"))


def test_rejects_bad_profile(tmp_path):
    with pytest.raises(ValueError):
        load_candidate(_write(tmp_path, profile=PROFILE.replace("junior", "juinor")))


def test_combines_every_markdown_document(tmp_path):
    c = load_candidate(
        _write_docs(
            tmp_path,
            {
                "resume.md": "# Main\nBackend engineer",
                "experience.md": "## Experience\nBuilt APIs",
                "skills.md": "## Skills\nPython, Redis",
            },
        )
    )
    assert c.resume_text.startswith("# Main")
    assert "Built APIs" in c.resume_text
    assert "Python, Redis" in c.resume_text
    assert "\n\n---\n\n" in c.resume_text


def test_skips_underscore_files_and_readme(tmp_path):
    c = load_candidate(
        _write_docs(
            tmp_path,
            {
                "resume.md": "MAIN",
                "_draft.md": "DRAFT",
                "README.md": "DOCS",
            },
        )
    )
    assert "MAIN" in c.resume_text
    assert "DRAFT" not in c.resume_text
    assert "DOCS" not in c.resume_text


def test_resume_files_selects_and_orders(tmp_path):
    profile = PROFILE + "resume_files: [skills.md, resume.md]\n"
    c = load_candidate(
        _write_docs(
            tmp_path,
            {
                "resume.md": "MAIN",
                "skills.md": "SKILLS",
                "ignored.md": "IGNORED",
            },
            profile=profile,
        )
    )
    assert c.resume_text == "SKILLS\n\n---\n\nMAIN"


def test_contact_info_error_names_the_file(tmp_path):
    with pytest.raises(ValueError, match="experience.md"):
        load_candidate(
            _write_docs(
                tmp_path,
                {
                    "resume.md": "MAIN",
                    "experience.md": "mail me at me@example.com",
                },
            )
        )


def test_hash_changes_when_an_extra_document_changes(tmp_path):
    docs = {"resume.md": "MAIN", "skills.md": "Python"}
    h1 = load_candidate(_write_docs(tmp_path, docs)).hash
    h2 = load_candidate(_write_docs(tmp_path, {**docs, "skills.md": "Python, Go"})).hash
    assert h1 != h2
