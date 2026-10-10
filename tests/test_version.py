"""Semver parsing, bumping and manifest version rewriting."""

from __future__ import annotations

import pytest

from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import Bump
from release_fragments.version import bump_version, parse_version, read_version, replace_version


def test_parse_version() -> None:
    assert parse_version("10.0.27") == (10, 0, 27)


@pytest.mark.parametrize(
    "text", ["1.2.3-rc.1", "1.2.3+build", "v1.2.3", "1.2", "1.2.3.4", "01.2.3", " 1.2.3", ""]
)
def test_parse_version_rejects_non_plain(text: str) -> None:
    with pytest.raises(ReleaseFragmentsError):
        parse_version(text)


@pytest.mark.parametrize(
    ("version", "bump", "expected"),
    [
        ("1.2.3", Bump.PATCH, "1.2.4"),
        ("1.2.3", Bump.MINOR, "1.3.0"),
        ("1.2.3", Bump.MAJOR, "2.0.0"),
        ("0.4.7", Bump.MAJOR, "1.0.0"),
        ("0.4.7", Bump.MINOR, "0.5.0"),
    ],
)
def test_bump_version(version: str, bump: Bump, expected: str) -> None:
    assert bump_version(version, bump) == expected


def test_bump_rejects_prerelease() -> None:
    with pytest.raises(ReleaseFragmentsError):
        bump_version("1.2.3-beta.1", Bump.PATCH)


MANIFEST = (
    '[project]\r\nname = "x"  # keep\r\nversion = "1.2.3"\r\n\r\n[tool.x]\r\n  version = "9"\r\n'
)


def test_read_version_ignores_indented_lines() -> None:
    assert read_version(MANIFEST) == "1.2.3"


def test_replace_version_keeps_every_other_byte() -> None:
    assert replace_version(MANIFEST, "2.0.0") == MANIFEST.replace('"1.2.3"', '"2.0.0"')


@pytest.mark.parametrize(
    "text",
    [
        '[project]\nname = "x"\n',
        "version = '1.2.3'\n",
        'version = "1.2.3"\n[tool.y]\nversion = "4.5.6"\n',
    ],
)
def test_missing_or_ambiguous_manifest_version_fails(text: str) -> None:
    with pytest.raises(ReleaseFragmentsError, match="exactly one"):
        read_version(text)
