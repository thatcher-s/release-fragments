"""Release-section rendering, changelog insertion and notes extraction."""

from __future__ import annotations

from datetime import date

import pytest

from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import Category, Fragment
from release_fragments.render import INTRO, extract_notes, insert_section, render_section

DAY = date(2026, 3, 4)


def _frag(name: str, category: Category, body: str) -> Fragment:
    return Fragment(name=name, category=category, body=body)


def test_section_orders_categories_and_filenames_and_omits_empty() -> None:
    fragments = [
        _frag("b", Category.FIXED, "- fix b"),
        _frag("z", Category.BREAKING, "- break"),
        _frag("a", Category.FIXED, "- fix a\n\n  ```py\n  x = 1\n  ```"),
        _frag("c", Category.ADDED, "- add"),
    ]
    assert render_section("2.0.0", DAY, fragments) == (
        "## [2.0.0] - 2026-03-04\n"
        "\n### Breaking Changes\n\n- break\n"
        "\n### Added\n\n- add\n"
        "\n### Fixed\n\n- fix a\n\n  ```py\n  x = 1\n  ```\n\n- fix b\n"
    )


SECTION = "## [1.1.0] - 2026-03-04\n\n### Added\n\n- new\n"


def test_insert_into_missing_file_writes_intro() -> None:
    text = insert_section(None, SECTION)
    assert text == INTRO + "\n" + SECTION
    assert "Keep a Changelog" in text and "Semantic Versioning" in text


def test_insert_keeps_intro_and_history() -> None:
    existing = "# Log\n\nIntro text.\n\n## [1.0.0] - 2025-01-01\n\n- old\n"
    assert insert_section(existing, SECTION) == (
        "# Log\n\nIntro text.\n\n" + SECTION + "\n## [1.0.0] - 2025-01-01\n\n- old\n"
    )


def test_insert_without_history_appends_after_blank_line() -> None:
    assert insert_section("# Log\n\nIntro.\n", SECTION) == "# Log\n\nIntro.\n\n" + SECTION


CHANGELOG = "# Log\n\n## [1.1.0] - 2026\n\n\n### Added\n\n- new\n\n\n## [1.0.0] - 2025\n\n- old\n"


@pytest.mark.parametrize(
    ("version", "notes"),
    [("1.1.0", "### Added\n\n- new"), ("1.0.0", "- old")],
)
def test_extract_notes(version: str, notes: str) -> None:
    assert extract_notes(CHANGELOG, version) == notes


@pytest.mark.parametrize(
    ("text", "match"),
    [(CHANGELOG.replace("1.0.0", "0.9.0"), "no ## \\[1.0.0\\]"), ("## [1.0.0]\n\n\n", "no notes")],
)
def test_extract_notes_failures(text: str, match: str) -> None:
    with pytest.raises(ReleaseFragmentsError, match=match):
        extract_notes(text, "1.0.0")
