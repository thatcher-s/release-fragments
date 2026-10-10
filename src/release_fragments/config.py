"""Load the `[tool.release-fragments]` table from `pyproject.toml` into a `Config`.

Reads one file; every other module receives the resulting `Config` instead of reading settings.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from release_fragments.errors import ReleaseFragmentsError

DEFAULT_SHIPPING_PATHS: tuple[str, ...] = (
    "src/",
    ".github/workflows/",
    ".github/actions/",
    "pyproject.toml",
    "uv.lock",
)


@dataclass(frozen=True)
class Config:
    """Repository settings; relative paths are POSIX strings relative to `root`, as Git uses."""

    root: Path
    fragment_dir: str = "changelog/next"
    changelog: str = "CHANGELOG.md"
    manifest: str = "pyproject.toml"
    lockfile: str = "uv.lock"
    # Empty means "no lockfile refresh".
    lock_command: tuple[str, ...] = ("uv", "lock")
    # An entry ending in "/" matches everything under that directory; otherwise an exact path.
    shipping_paths: tuple[str, ...] = DEFAULT_SHIPPING_PATHS
    base_ref: str = "origin/main"
    remote: str = "origin"
    branch: str = "main"
    # Below 1.0, a major bump becomes minor (the Cargo/npm-caret convention for 0.y.z).
    major_version_zero: bool = False

    def path(self, relative: str) -> Path:
        """Return the absolute filesystem path for a repo-relative setting."""
        return self.root / relative


_STR_KEYS = {"fragment_dir", "changelog", "manifest", "lockfile", "base_ref", "remote", "branch"}
_LIST_KEYS = {"lock_command", "shipping_paths"}
_BOOL_KEYS = {"major_version_zero"}


def load_config(root: Path | None = None) -> Config:
    """Read `[tool.release-fragments]` from `<root>/pyproject.toml`; defaults when absent."""
    root = (root or Path.cwd()).resolve()
    pyproject = root / "pyproject.toml"
    table: dict[str, Any] = {}
    if pyproject.is_file():
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ReleaseFragmentsError(f"{pyproject}: invalid TOML: {exc}") from exc
        raw = data.get("tool", {}).get("release-fragments", {})
        table = {key.replace("-", "_"): value for key, value in raw.items()}

    known = {f.name for f in fields(Config)} - {"root"}
    unknown = sorted(set(table) - known)
    if unknown:
        raise ReleaseFragmentsError(f"unknown [tool.release-fragments] keys: {', '.join(unknown)}")

    values: dict[str, Any] = {}
    for key, value in table.items():
        if key in _STR_KEYS:
            if not isinstance(value, str) or not value:
                raise ReleaseFragmentsError(f"[tool.release-fragments] {key} must be a string")
            values[key] = value.strip("/") if key == "fragment_dir" else value
        elif key in _LIST_KEYS:
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ReleaseFragmentsError(
                    f"[tool.release-fragments] {key} must be a list of strings"
                )
            values[key] = tuple(value)
        elif key in _BOOL_KEYS:
            if not isinstance(value, bool):
                raise ReleaseFragmentsError(f"[tool.release-fragments] {key} must be a boolean")
            values[key] = value
    return Config(root=root, **values)
