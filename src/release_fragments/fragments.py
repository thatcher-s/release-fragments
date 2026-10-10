"""The fragment contract: categories, bumps, filename and body rules, and discovery.

Pure rules plus directory listing and file reads; `check` applies the same rules to Git
content, `build` and `add` apply them to the working tree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import IntEnum, StrEnum
from pathlib import Path

from release_fragments.errors import ReleaseFragmentsError


class Category(StrEnum):
    """Fragment categories, declared in release-section rendering order."""

    BREAKING = "breaking"
    ADDED = "added"
    CHANGED = "changed"
    DEPRECATED = "deprecated"
    REMOVED = "removed"
    FIXED = "fixed"
    SECURITY = "security"


class Bump(IntEnum):
    """Semver bump size; larger value wins when fragments are combined."""

    PATCH = 1
    MINOR = 2
    MAJOR = 3


BUMPS: dict[Category, Bump] = {
    Category.BREAKING: Bump.MAJOR,
    Category.ADDED: Bump.MINOR,
    Category.CHANGED: Bump.MINOR,
    Category.DEPRECATED: Bump.MINOR,
    Category.REMOVED: Bump.MAJOR,
    Category.FIXED: Bump.PATCH,
    Category.SECURITY: Bump.PATCH,
}

HEADINGS: dict[Category, str] = {
    Category.BREAKING: "Breaking Changes",
    Category.ADDED: "Added",
    Category.CHANGED: "Changed",
    Category.DEPRECATED: "Deprecated",
    Category.REMOVED: "Removed",
    Category.FIXED: "Fixed",
    Category.SECURITY: "Security",
}

SLUG_MAX = 55
_CATEGORIES = "|".join(c.value for c in Category)
FILENAME_RE = re.compile(
    rf"^(?P<date>[0-9]{{8}})-(?P<slug>[a-z0-9-]{{1,{SLUG_MAX}}})-(?P<suffix>[0-9a-f]{{6}})"
    rf"\.(?P<category>{_CATEGORIES})\.md$"
)


class FragmentError(ReleaseFragmentsError):
    """One or more fragments break the filename or body contract."""


@dataclass(frozen=True)
class Fragment:
    """A validated fragment: its filename, category and trimmed Markdown body."""

    name: str
    category: Category
    body: str

    @property
    def bump(self) -> Bump:
        """The version bump this fragment's category requires."""
        return BUMPS[self.category]


def parse_name(name: str) -> Category:
    """Return the category encoded in a fragment filename, or raise `FragmentError`."""
    match = FILENAME_RE.fullmatch(name)
    if match is None:
        raise FragmentError(
            f"{name}: fragment names must look like "
            f"YYYYMMDD-<slug>-<6 hex>.<category>.md with category one of: {_CATEGORIES}"
        )
    return Category(match["category"])


def parse_fragment(name: str, content: bytes) -> Fragment:
    """Validate a fragment's filename and body; the body is UTF-8 and trimmed."""
    category = parse_name(name)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FragmentError(f"{name}: body is not valid UTF-8") from exc
    body = text.strip()
    if not body:
        raise FragmentError(f"{name}: body is empty")
    return Fragment(name=name, category=category, body=body)


def is_candidate_name(name: str) -> bool:
    """True for names build consumes: non-hidden, lowercase `.md` extension."""
    return not name.startswith(".") and name.endswith(".md")


def discover(fragment_dir: Path) -> list[Path]:
    """List immediate, non-hidden regular `.md` files, sorted by name; missing dir means none."""
    if not fragment_dir.is_dir():
        return []
    return sorted(
        (p for p in fragment_dir.iterdir() if is_candidate_name(p.name) and p.is_file()),
        key=lambda p: p.name,
    )


def load_all(fragment_dir: Path) -> list[tuple[Path, Fragment]]:
    """Discover and parse every fragment, reporting all problems together before any write."""
    loaded: list[tuple[Path, Fragment]] = []
    problems: list[str] = []
    for path in discover(fragment_dir):
        try:
            loaded.append((path, parse_fragment(path.name, path.read_bytes())))
        except FragmentError as exc:
            problems.append(str(exc))
    if problems:
        raise FragmentError("invalid fragments:\n  " + "\n  ".join(problems))
    return loaded


def slugify(description: str) -> str:
    """Turn a free-text description into a fragment slug, or raise if nothing is left."""
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower()).strip("-")
    slug = slug[:SLUG_MAX].rstrip("-")
    if not slug:
        raise FragmentError(f"description {description!r} yields an empty slug")
    return slug


def fragment_filename(day: date, slug: str, suffix: str, category: Category) -> str:
    """Assemble a fragment filename from its parts."""
    return f"{day:%Y%m%d}-{slug}-{suffix}.{category.value}.md"
