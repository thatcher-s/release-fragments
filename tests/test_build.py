"""Building a release from fragments, including the transactional lock refresh."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from release_fragments.build import build
from release_fragments.config import Config
from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import FragmentError

DAY = date(2026, 3, 4)


def _fragment(config: Config, slug: str, category: str, body: str = "- change\n") -> Path:
    directory = config.path(config.fragment_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"20260301-{slug}-abc123.{category}.md"
    path.write_text(body, encoding="utf-8")
    return path


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_missing_fragment_dir_is_a_noop(project: Config) -> None:
    before = _snapshot(project.root)
    marker = project.root / "lock-ran"
    assert build(replace(project, lock_command=("touch", str(marker)))) is None
    assert _snapshot(project.root) == before


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        ("breaking", "2.0.0"),
        ("added", "1.3.0"),
        ("changed", "1.3.0"),
        ("deprecated", "1.3.0"),
        ("removed", "2.0.0"),
        ("fixed", "1.2.4"),
        ("security", "1.2.4"),
    ],
)
def test_each_category_bump(project: Config, category: str, expected: str) -> None:
    _fragment(project, "x", category)
    result = build(project, dry_run=True)
    assert result is not None and result.version == expected


def test_mixed_categories_pick_largest(project: Config) -> None:
    _fragment(project, "a", "fixed")
    _fragment(project, "b", "deprecated")
    _fragment(project, "c", "security")
    result = build(project, dry_run=True)
    assert result is not None and result.version == "1.3.0"


def test_dry_run_writes_and_runs_nothing(project: Config) -> None:
    _fragment(project, "a", "fixed")
    before = _snapshot(project.root)
    result = build(replace(project, lock_command=("false",)), dry_run=True, today=DAY)
    assert result is not None
    assert result.section == "## [1.2.4] - 2026-03-04\n\n### Fixed\n\n- change\n"
    assert _snapshot(project.root) == before


def test_success_writes_release_and_removes_only_consumed(project: Config) -> None:
    consumed = [_fragment(project, "a", "added"), _fragment(project, "b", "fixed")]
    fragment_dir = project.path(project.fragment_dir)
    (fragment_dir / ".gitkeep").write_text("")
    (fragment_dir / "nested").mkdir()
    (fragment_dir / "nested" / "keep.md").write_text("x")

    result = build(project, today=DAY)

    assert result is not None
    assert (result.previous_version, result.version) == ("1.2.3", "1.3.0")
    assert result.consumed == tuple(consumed)
    assert 'version = "1.3.0"' in project.path("pyproject.toml").read_text()
    assert result.section in project.path("CHANGELOG.md").read_text()
    assert sorted(p.name for p in fragment_dir.iterdir()) == [".gitkeep", "nested"]
    assert (fragment_dir / "nested" / "keep.md").exists()


def test_success_removes_emptied_fragment_dir(project: Config) -> None:
    _fragment(project, "a", "fixed")
    assert build(project) is not None
    assert not project.path(project.fragment_dir).exists()


def test_invalid_fragments_fail_before_any_change(project: Config) -> None:
    _fragment(project, "a", "fixed")
    _fragment(project, "b", "added", body="   ")
    before = _snapshot(project.root)
    with pytest.raises(FragmentError):
        build(project)
    assert _snapshot(project.root) == before


@pytest.mark.parametrize("manifest", ['[project]\nname = "x"\n', 'version = "1.2.3-rc.1"\n'])
def test_bad_manifest_version_fails_before_any_change(project: Config, manifest: str) -> None:
    project.path("pyproject.toml").write_text(manifest)
    _fragment(project, "a", "fixed")
    before = _snapshot(project.root)
    with pytest.raises(ReleaseFragmentsError):
        build(replace(project, lock_command=()))
    assert _snapshot(project.root) == before


@pytest.mark.parametrize(
    "command",
    [
        ("sh", "-c", "echo broken > uv.lock; exit 3"),
        ("definitely-not-a-real-lock-tool-xyz",),
    ],
)
@pytest.mark.parametrize("had_files", [True, False])
def test_failed_lock_refresh_restores_everything(
    project: Config, command: tuple[str, ...], had_files: bool
) -> None:
    if had_files:
        project.path("CHANGELOG.md").write_text("# Log\r\n\r\n## [1.2.3] - 2025\r\n\r\n- old\r\n")
        project.path("uv.lock").write_text("original lock\n")
    _fragment(project, "a", "fixed")
    before = _snapshot(project.root)
    with pytest.raises(ReleaseFragmentsError, match="exited 3|could not run"):
        build(replace(project, lock_command=command))
    assert _snapshot(project.root) == before
