"""Creating fragment files with `add_fragment`."""

from __future__ import annotations

from datetime import UTC, date, datetime
from itertools import count

import pytest

from release_fragments.add import add_fragment
from release_fragments.config import Config
from release_fragments.fragments import FragmentError, parse_fragment

DAY = date(2026, 3, 4)


def test_creates_valid_fragment(project: Config) -> None:
    path = add_fragment(project, "fixed", "Fix the crash!", today=DAY, suffix=lambda: "a1b2c3")
    assert path == project.root / "changelog/next/20260304-fix-the-crash-a1b2c3.fixed.md"
    assert path.is_absolute()
    assert path.read_text() == "- Fix the crash!\n"
    assert parse_fragment(path.name, path.read_bytes()).body == "- Fix the crash!"


def test_default_name_uses_utc_date_and_random_hex(project: Config) -> None:
    path = add_fragment(project, "added", "thing")
    assert parse_fragment(path.name, path.read_bytes())
    assert path.name.startswith(datetime.now(UTC).strftime("%Y%m%d-thing-"))


def test_invalid_category_lists_valid_ones(project: Config) -> None:
    with pytest.raises(FragmentError, match="breaking, added, changed.*security"):
        add_fragment(project, "Added", "thing")


def test_empty_slug_is_rejected(project: Config) -> None:
    with pytest.raises(FragmentError, match="empty slug"):
        add_fragment(project, "added", "!!!")


def test_collision_retries_with_new_suffix(project: Config) -> None:
    suffixes = iter(["aaaaaa", "bbbbbb"])
    first = add_fragment(project, "added", "x", today=DAY, suffix=lambda: "aaaaaa")
    second = add_fragment(project, "added", "x", today=DAY, suffix=lambda: next(suffixes))
    assert (first.name, second.name) == (
        "20260304-x-aaaaaa.added.md",
        "20260304-x-bbbbbb.added.md",
    )


def test_five_collisions_fail_without_overwriting(project: Config) -> None:
    existing = add_fragment(project, "added", "x", today=DAY, suffix=lambda: "aaaaaa")
    existing.write_text("original")
    calls = count()

    def same() -> str:
        next(calls)
        return "aaaaaa"

    with pytest.raises(FragmentError, match="5 attempts"):
        add_fragment(project, "added", "x", today=DAY, suffix=same)
    assert next(calls) == 5
    assert existing.read_text() == "original"


def test_dry_run_creates_nothing(project: Config) -> None:
    path = add_fragment(project, "added", "x", dry_run=True, today=DAY, suffix=lambda: "abcdef")
    assert path == project.root / "changelog/next/20260304-x-abcdef.added.md"
    assert not path.parent.exists()
