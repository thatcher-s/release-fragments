"""Throwaway Git repositories for the check and release tests; runs real `git` in temp dirs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

PYPROJECT = """\
[project]
name = "demo"
version = "1.2.3"
dependencies = []

[tool.release-fragments]
lock_command = ["true"]
"""

CHANGELOG = """\
# Changelog

## [1.2.3] - 2026-01-01

### Added

- Initial release.
"""


@pytest.fixture
def git_env(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Shield tests from the developer's Git config (signing, hooks, default branch)."""
    empty = tmp_path_factory.mktemp("gitconfig") / "config"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")


def git(cwd: Path, *args: str) -> str:
    """Run git in `cwd`, fail the test on error, and return stripped stdout."""
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"
    return proc.stdout.strip()


def write(root: Path, rel: str, text: str) -> Path:
    """Write `text` to `root/rel`, creating parent directories."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def commit_all(root: Path, message: str) -> str:
    """Stage everything, commit, and return the new HEAD SHA."""
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def frag(slug: str, category: str, suffix: str = "abc123") -> str:
    """A valid fragment path under the default fragment dir."""
    return f"changelog/next/20260101-{slug}-{suffix}.{category}.md"


def init_repo(root: Path) -> Path:
    """Create a repo on `main` with a manifest, changelog and source file, committed."""
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    write(root, "pyproject.toml", PYPROJECT)
    write(root, "CHANGELOG.md", CHANGELOG)
    write(root, "src/demo/__init__.py", "")
    write(root, "README.md", "demo\n")
    commit_all(root, "initial")
    return root


def init_origin(tmp_path: Path) -> Path:
    """A bare `origin` seeded from `init_repo`; returns the bare repo path."""
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = init_repo(tmp_path / "seed")
    git(seed, "push", "-q", str(origin), "main")
    return origin


def clone(origin: Path, dest: Path) -> Path:
    """Clone `origin` into `dest` and return it."""
    git(dest.parent, "clone", "-q", str(origin), str(dest))
    return dest
