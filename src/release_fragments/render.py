"""Changelog text: render a release section, insert it, and extract one version's notes.

Pure text, no I/O; `build` reads and writes `CHANGELOG.md`, the CLI and `release` read notes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import HEADINGS, Category, Fragment

INTRO = """\
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
"""

_SECTION_MARKER = re.compile(r"^## \[", re.MULTILINE)


def render_section(version: str, day: date, fragments: Sequence[Fragment]) -> str:
    """Render `## [X.Y.Z] - YYYY-MM-DD` with non-empty categories in order, bodies by filename."""
    parts = [f"## [{version}] - {day.isoformat()}"]
    for category in Category:
        bodies = [f.body for f in sorted(fragments, key=lambda f: f.name) if f.category is category]
        if bodies:
            parts += ["", f"### {HEADINGS[category]}", "", "\n\n".join(bodies)]
    return "\n".join(parts) + "\n"


def insert_section(existing: str | None, section: str) -> str:
    """Put a section above the newest release, or after the intro; `None` means a new file."""
    if existing is None:
        return f"{INTRO}\n{section}"
    # Anchored at line start so a "## [" quoted inside intro prose is not mistaken for history.
    marker = _SECTION_MARKER.search(existing)
    if marker is None:
        return f"{existing.rstrip(chr(10))}\n\n{section}"
    return f"{existing[: marker.start()]}{section}\n{existing[marker.start() :]}"


def extract_notes(changelog_text: str, version: str) -> str:
    """Return the body under `## [version]` up to the next `## ` heading, blank edges trimmed."""
    lines = changelog_text.splitlines()
    heading = f"## [{version}]"
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith(heading)) + 1
    except StopIteration:
        raise ReleaseFragmentsError(f"no {heading} section in the changelog") from None
    end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = lines[start:end]
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        raise ReleaseFragmentsError(f"the {heading} section has no notes")
    return "\n".join(body)
