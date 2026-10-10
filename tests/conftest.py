"""Shared fixtures: a throwaway project directory with a manifest and a no-op lock command."""

from __future__ import annotations

from pathlib import Path

import pytest

from release_fragments.config import Config, load_config

PYPROJECT = """\
[project]
name = "demo"
version = "1.2.3"

[tool.release-fragments]
lock_command = ["true"]
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """A project root at `tmp_path` (also the cwd) whose lock refresh is a no-op."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return load_config(tmp_path)
