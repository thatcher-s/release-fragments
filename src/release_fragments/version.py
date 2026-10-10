"""Semver arithmetic and the manifest `version = "..."` line; pure text, no I/O.

`build` reads and writes the manifest file; this module only parses and rewrites its text.
"""

from __future__ import annotations

import re

from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import Bump

_VERSION_RE = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_MANIFEST_RE = re.compile(r'^version\s*=\s*"([^"]*)"\s*$', re.MULTILINE)


def parse_version(text: str) -> tuple[int, int, int]:
    """Parse a plain `X.Y.Z` version; prerelease and build suffixes are rejected."""
    match = _VERSION_RE.fullmatch(text)
    if match is None:
        raise ReleaseFragmentsError(f"version {text!r} is not a plain X.Y.Z semver version")
    major, minor, patch = (int(part) for part in match.groups())
    return major, minor, patch


def bump_version(version: str, bump: Bump) -> str:
    """Apply a semver bump; there is no special case below 1.0."""
    major, minor, patch = parse_version(version)
    if bump is Bump.MAJOR:
        return f"{major + 1}.0.0"
    if bump is Bump.MINOR:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _only_match(manifest_text: str) -> re.Match[str]:
    matches = list(_MANIFEST_RE.finditer(manifest_text))
    if len(matches) != 1:
        raise ReleaseFragmentsError(
            f'manifest must contain exactly one unindented version = "..." line, '
            f"found {len(matches)}"
        )
    return matches[0]


def read_version(manifest_text: str) -> str:
    """Return the manifest's single version string."""
    return _only_match(manifest_text)[1]


def replace_version(manifest_text: str, new_version: str) -> str:
    """Swap the quoted version value, keeping every other byte of the manifest."""
    match = _only_match(manifest_text)
    return manifest_text[: match.start(1)] + new_version + manifest_text[match.end(1) :]
