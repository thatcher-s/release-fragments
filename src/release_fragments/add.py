"""Create one pending fragment file from a category and a description.

Writes a single new file under the fragment directory; `fragments` owns the naming rules.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

from release_fragments.config import Config
from release_fragments.fragments import Category, FragmentError, fragment_filename, slugify

MAX_ATTEMPTS = 5


def add_fragment(
    config: Config,
    category: str,
    description: str,
    *,
    dry_run: bool = False,
    today: date | None = None,
    suffix: Callable[[], str] | None = None,
) -> Path:
    """Write `- <description>` to a new fragment and return its absolute path; never overwrite."""
    try:
        kind = Category(category)
    except ValueError:
        valid = ", ".join(c.value for c in Category)
        raise FragmentError(f"unknown category {category!r}; choose one of: {valid}") from None
    slug = slugify(description)
    day = today or datetime.now(UTC).date()
    make_suffix = suffix or (lambda: secrets.token_hex(3))
    directory = config.path(config.fragment_dir).resolve()

    if dry_run:
        return directory / fragment_filename(day, slug, make_suffix(), kind)

    directory.mkdir(parents=True, exist_ok=True)
    for _ in range(MAX_ATTEMPTS):
        path = directory / fragment_filename(day, slug, make_suffix(), kind)
        try:
            with path.open("x", encoding="utf-8") as handle:
                handle.write(f"- {description}\n")
        except FileExistsError:
            continue
        return path
    raise FragmentError(f"could not find a free fragment name after {MAX_ATTEMPTS} attempts")
