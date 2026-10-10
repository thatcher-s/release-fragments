"""Tests for `release check` against real temp Git repositories."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitrepo import commit_all, frag, git, git_env, init_repo, write

from release_fragments.check import check, is_shipping_path
from release_fragments.config import Config, load_config
from release_fragments.errors import ReleaseFragmentsError

__all__ = ["git_env"]
pytestmark = pytest.mark.usefixtures("git_env")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repo with `main` committed and `feature` checked out from it."""
    root = init_repo(tmp_path / "repo")
    git(root, "checkout", "-q", "-b", "feature")
    return root


def run(root: Path, *, assume_shipping: bool = False) -> list[str]:
    config: Config = load_config(root)
    return check(config, "main", "feature", assume_shipping=assume_shipping)


def test_shipping_change_without_fragment_fails(repo: Path) -> None:
    write(repo, "src/demo/core.py", "x = 1\n")
    commit_all(repo, "feat")
    [violation] = run(repo)
    assert "need a new fragment" in violation


def test_shipping_change_with_fragment_passes(repo: Path) -> None:
    write(repo, "src/demo/core.py", "x = 1\n")
    write(repo, frag("core", "added"), "- Core.\n")
    commit_all(repo, "feat")
    assert run(repo) == []


@pytest.mark.parametrize("path", ["docs/guide.md", "tests/test_x.py", "README.md"])
def test_non_shipping_change_passes(repo: Path, path: str) -> None:
    write(repo, path, "text\n")
    commit_all(repo, "docs")
    assert run(repo) == []


def test_assume_shipping_requires_fragment(repo: Path) -> None:
    write(repo, "docs/guide.md", "text\n")
    commit_all(repo, "docs")
    assert len(run(repo, assume_shipping=True)) == 1
    write(repo, frag("guide", "changed"), "- Guide.\n")
    commit_all(repo, "fragment")
    assert run(repo, assume_shipping=True) == []


def test_existing_or_modified_fragment_does_not_count(repo: Path) -> None:
    git(repo, "checkout", "-q", "main")
    write(repo, frag("old", "fixed"), "- Old.\n")
    commit_all(repo, "pending fragment")
    git(repo, "checkout", "-q", "feature")
    git(repo, "reset", "-q", "--hard", "main")
    write(repo, "src/demo/core.py", "x = 1\n")
    write(repo, frag("old", "fixed"), "- Old, reworded.\n")
    commit_all(repo, "feat")
    [violation] = run(repo)
    assert "need a new fragment" in violation


def test_renamed_fragment_counts_as_added(repo: Path) -> None:
    git(repo, "checkout", "-q", "main")
    write(repo, frag("old", "fixed"), "- Old.\n")
    commit_all(repo, "pending fragment")
    git(repo, "checkout", "-q", "feature")
    git(repo, "reset", "-q", "--hard", "main")
    git(repo, "mv", frag("old", "fixed"), frag("renamed", "fixed"))
    write(repo, "src/demo/core.py", "x = 1\n")
    commit_all(repo, "feat")
    assert run(repo) == []


def test_changelog_edit_fails(repo: Path) -> None:
    write(repo, "CHANGELOG.md", "# Changelog\n\nhand edit\n")
    commit_all(repo, "edit")
    [violation] = run(repo)
    assert "CHANGELOG.md" in violation


def test_manual_version_change_fails(repo: Path) -> None:
    pyproject = (repo / "pyproject.toml").read_text()
    write(repo, "pyproject.toml", pyproject.replace('"1.2.3"', '"2.0.0"'))
    write(repo, frag("bump", "breaking"), "- Bump.\n")
    commit_all(repo, "bump")
    [violation] = run(repo)
    assert "1.2.3 -> 2.0.0" in violation


def test_release_on_base_does_not_fail_pr_touching_manifest(repo: Path) -> None:
    pyproject = (repo / "pyproject.toml").read_text()
    write(repo, "pyproject.toml", pyproject.replace("dependencies = []", 'dependencies = ["x"]'))
    write(repo, frag("dep", "changed"), "- Depend on x.\n")
    commit_all(repo, "add dependency")
    git(repo, "checkout", "-q", "main")
    write(repo, "pyproject.toml", pyproject.replace('"1.2.3"', '"1.3.0"'))
    write(repo, "CHANGELOG.md", "# Changelog\n\n## [1.3.0] - 2026-02-01\n\n- x\n")
    commit_all(repo, "chore(release): v1.3.0 [skip ci]")
    assert run(repo) == []


def test_base_advancing_does_not_contaminate_diff(repo: Path) -> None:
    write(repo, "docs/guide.md", "text\n")
    commit_all(repo, "docs")
    git(repo, "checkout", "-q", "main")
    write(repo, "src/demo/core.py", "x = 1\n")
    write(repo, "CHANGELOG.md", "# Changelog\n\nchanged on main\n")
    commit_all(repo, "main moves on")
    assert run(repo) == []


@pytest.mark.parametrize(
    ("path", "body", "expected"),
    [
        ("changelog/next/notes.md", "- x\n", "fragment names must look like"),
        ("changelog/next/20260101-x-abc123.feature.md", "- x\n", "fragment names must look like"),
        (frag("empty", "added"), "  \n\n", "body is empty"),
    ],
)
def test_invalid_added_fragment_fails(repo: Path, path: str, body: str, expected: str) -> None:
    write(repo, path, body)
    commit_all(repo, "bad fragment")
    violations = run(repo)
    assert any(expected in v for v in violations)


@pytest.mark.parametrize(
    "path",
    [
        "changelog/next/sub/20260101-x-abc123.added.md",
        "changelog/next/.20260101-x-abc123.added.md",
        "changelog/next/20260101-x-abc123.added.txt",
    ],
)
def test_unconsumable_added_file_fails(repo: Path, path: str) -> None:
    write(repo, path, "- x\n")
    write(repo, frag("ok", "added"), "- Ok.\n")
    commit_all(repo, "odd file")
    [violation] = run(repo)
    assert path in violation


def test_gitkeep_is_allowed(repo: Path) -> None:
    write(repo, "changelog/next/.gitkeep", "")
    commit_all(repo, "keep")
    assert run(repo) == []


def test_bodies_are_read_from_head_not_worktree(repo: Path) -> None:
    write(repo, "src/demo/core.py", "x = 1\n")
    write(repo, frag("good", "added"), "- Good.\n")
    write(repo, frag("bad", "added", "def456"), "\n")
    commit_all(repo, "feat")
    write(repo, frag("good", "added"), "")
    write(repo, frag("bad", "added", "def456"), "- Fixed only on disk.\n")
    [violation] = run(repo)
    assert "body is empty" in violation and "bad" in violation


def test_bad_ref_raises(repo: Path) -> None:
    with pytest.raises(ReleaseFragmentsError, match="no-such-ref"):
        check(load_config(repo), "no-such-ref", "feature")


def test_shipping_path_matching() -> None:
    paths = ("src/", "pyproject.toml")
    assert is_shipping_path("src/a.py", paths)
    assert is_shipping_path("pyproject.toml", paths)
    assert not is_shipping_path("srcx/a.py", paths)
    assert not is_shipping_path("sub/pyproject.toml", paths)
