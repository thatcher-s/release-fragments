"""Assemble pending fragments into a release: changelog, manifest version and lockfile.

Reads and writes the working tree and runs the lock command; `release` commits the result,
`render` and `version` supply the pure text transforms.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from release_fragments.config import Config
from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import Bump, load_all
from release_fragments.render import insert_section, render_section
from release_fragments.version import bump_version, parse_version, read_version, replace_version

_STDERR_TAIL = 500


@dataclass(frozen=True)
class BuildResult:
    """What a build produced (or, in a dry run, would produce)."""

    version: str
    previous_version: str
    section: str
    consumed: tuple[Path, ...]


def build(
    config: Config, *, dry_run: bool = False, today: date | None = None
) -> BuildResult | None:
    """Consume pending fragments into a release; `None` when there are none to consume."""
    fragment_dir = config.path(config.fragment_dir)
    loaded = load_all(fragment_dir)
    if not loaded:
        return None

    manifest_path = config.path(config.manifest)
    changelog_path = config.path(config.changelog)
    manifest_text = _read_text(manifest_path)
    previous = read_version(manifest_text)
    fragments = [fragment for _, fragment in loaded]
    bump = max(fragment.bump for fragment in fragments)
    if config.major_version_zero and bump is Bump.MAJOR and parse_version(previous)[0] == 0:
        bump = Bump.MINOR
    version = bump_version(previous, bump)
    section = render_section(version, today or datetime.now(UTC).date(), fragments)
    result = BuildResult(
        version=version,
        previous_version=previous,
        section=section,
        consumed=tuple(path for path, _ in loaded),
    )
    if dry_run:
        return result

    existing = _read_text(changelog_path) if changelog_path.exists() else None
    new_changelog = insert_section(existing, section)
    new_manifest = replace_version(manifest_text, version)

    tracked = (changelog_path, manifest_path, config.path(config.lockfile))
    snapshots = {path: path.read_bytes() if path.exists() else None for path in tracked}
    try:
        changelog_path.write_bytes(new_changelog.encode("utf-8"))
        manifest_path.write_bytes(new_manifest.encode("utf-8"))
        _refresh_lock(config)
    except BaseException:
        for path, original in snapshots.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise

    for path in result.consumed:
        path.unlink()
    if not any(fragment_dir.iterdir()):
        fragment_dir.rmdir()
    return result


def _read_text(path: Path) -> str:
    # Bytes, not read_text: universal-newline decoding would silently rewrite CRLF files.
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReleaseFragmentsError(f"cannot read {path}: {exc}") from exc


def _refresh_lock(config: Config) -> None:
    if not config.lock_command:
        return
    command = list(config.lock_command)
    try:
        proc = subprocess.run(
            command,
            cwd=config.root,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise ReleaseFragmentsError(f"lock command {command[0]!r} could not run: {exc}") from exc
    if proc.returncode != 0:
        tail = proc.stderr.strip()[-_STDERR_TAIL:]
        raise ReleaseFragmentsError(
            f"lock command {' '.join(command)!r} exited {proc.returncode}; "
            f"release files restored. stderr tail:\n{tail}"
        )
