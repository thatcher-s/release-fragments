"""The `add`, `build` and `notes` subcommands' stdout contracts and exit codes."""

from __future__ import annotations

from pathlib import Path

import pytest

from release_fragments.cli import ADD_USAGE, main
from release_fragments.config import Config


def _last_line(capsys: pytest.CaptureFixture[str]) -> str:
    return capsys.readouterr().out.splitlines()[-1]


def test_add_prints_absolute_path(project: Config, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["add", "fixed", "A fix"]) == 0
    path = Path(_last_line(capsys))
    assert path.is_absolute() and path.read_text() == "- A fix\n"


def test_add_without_description_prints_usage(
    project: Config, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["add", "fixed"]) == 0
    assert _last_line(capsys) == ADD_USAGE


def test_add_bad_category_exits_1(project: Config) -> None:
    assert main(["add", "nope", "x"]) == 1


def test_build_without_fragments(project: Config, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build"]) == 0
    assert _last_line(capsys) == "new-version="


def test_build_prints_new_version(project: Config, capsys: pytest.CaptureFixture[str]) -> None:
    main(["add", "added", "feature"])
    assert main(["build"]) == 0
    assert _last_line(capsys) == "new-version=1.3.0"


def test_build_dry_run(project: Config, capsys: pytest.CaptureFixture[str]) -> None:
    main(["add", "fixed", "bug"])
    assert main(["build", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[-1] == "would-release=1.2.4"
    assert "new-version" not in out


def test_failed_build_emits_no_marker(project: Config, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = project.path("pyproject.toml")
    pyproject.write_text(pyproject.read_text().replace('["true"]', '["false"]'))
    main(["add", "fixed", "bug"])
    capsys.readouterr()
    assert main(["build"]) == 1
    captured = capsys.readouterr()
    assert "new-version" not in captured.out
    assert "exited 1" in captured.err


def test_notes(project: Config, capsys: pytest.CaptureFixture[str]) -> None:
    main(["add", "fixed", "bug"])
    main(["build"])
    capsys.readouterr()
    assert main(["notes", "v1.2.4"]) == 0
    assert capsys.readouterr().out == "### Fixed\n\n- bug\n"
