"""Fragment contract: names, bodies, discovery and slugs."""

from __future__ import annotations

from pathlib import Path

import pytest

from release_fragments.fragments import (
    Category,
    FragmentError,
    discover,
    load_all,
    parse_fragment,
    slugify,
)

VALID = "20260101-new-thing-abc123.added.md"


def test_parse_valid_fragment_trims_edges_only() -> None:
    fragment = parse_fragment(VALID, b"\n\n- one\n\n  - nested\n\n")
    assert (fragment.category, fragment.body) == (Category.ADDED, "- one\n\n  - nested")


@pytest.mark.parametrize(
    "name",
    [
        "20260101-new-thing-abc123.Added.md",
        "20260101-new-thing-abc123.feature.md",
        "20260101-New-thing-abc123.added.md",
        "20260101-new-thing-abc12.added.md",
        "20260101-new-thing-ABC123.added.md",
        "2026011-new-thing-abc123.added.md",
        "20260101--abc123.added.md",
        f"20260101-{'a' * 56}-abc123.added.md",
        "20260101-new-thing-abc123.added.MD",
    ],
)
def test_parse_rejects_bad_names(name: str) -> None:
    with pytest.raises(FragmentError):
        parse_fragment(name, b"- body")


@pytest.mark.parametrize("content", [b"", b" \n\t\n", b"\xff\xfe"])
def test_parse_rejects_empty_or_non_utf8_body(content: bytes) -> None:
    with pytest.raises(FragmentError):
        parse_fragment(VALID, content)


def test_discover_missing_dir_is_empty(tmp_path: Path) -> None:
    assert discover(tmp_path / "nope") == []


def test_discover_takes_only_immediate_visible_md_files(tmp_path: Path) -> None:
    for name in ("b.md", "a.md", ".hidden.md", "notes.txt", "upper.MD"):
        (tmp_path / name).write_text("x")
    (tmp_path / "nested.md").mkdir()
    (tmp_path / "nested.md" / "inner.md").write_text("x")
    assert [p.name for p in discover(tmp_path)] == ["a.md", "b.md"]


def test_load_all_reports_every_problem(tmp_path: Path) -> None:
    (tmp_path / "bad-name.md").write_text("- x")
    (tmp_path / VALID).write_text("  ")
    with pytest.raises(FragmentError) as exc:
        load_all(tmp_path)
    assert "bad-name.md" in str(exc.value)
    assert "body is empty" in str(exc.value)


@pytest.mark.parametrize(
    ("description", "slug"),
    [
        ("Add Shiny NEW thing!", "add-shiny-new-thing"),
        ("  --Fix: crash (on start)--  ", "fix-crash-on-start"),
        ("café über", "caf-ber"),
        ("a" * 60, "a" * 55),
        ("a" * 54 + " bcd", "a" * 54),
    ],
)
def test_slugify(description: str, slug: str) -> None:
    assert slugify(description) == slug


def test_slugify_rejects_empty_result() -> None:
    with pytest.raises(FragmentError):
        slugify("!!! ???")
