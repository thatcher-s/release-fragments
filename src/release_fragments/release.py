"""CI release: build, commit, push with race retry, tag, and publish a GitHub release.

Does I/O (Git, the changelog, `gh`); `build` produces the release files, this module ships them.
"""

from __future__ import annotations

import re
import subprocess
from typing import Protocol

from release_fragments.build import build
from release_fragments.config import Config
from release_fragments.errors import ReleaseFragmentsError
from release_fragments.git import rev_parse, run_git
from release_fragments.render import extract_notes

_NEWEST_VERSION_RE = re.compile(r"^## \[([^\]]+)\]", re.MULTILINE)


class Publisher(Protocol):
    """Where release notes are published, keyed by tag."""

    def release_exists(self, tag: str) -> bool:
        """True if a release for `tag` already exists."""
        ...

    def create_release(self, tag: str, notes: str) -> None:
        """Publish a release for `tag` with `notes` as its body."""
        ...


class GhPublisher:
    """Publishes GitHub releases through the `gh` CLI in the current directory."""

    def release_exists(self, tag: str) -> bool:
        """True if `gh release view <tag>` finds the release; other `gh` failures raise."""
        proc = _gh("release", "view", tag)
        if proc.returncode == 0:
            return True
        if "release not found" in proc.stderr.lower():
            return False
        raise _gh_error(("release", "view", tag), proc)

    def create_release(self, tag: str, notes: str) -> None:
        """Create the release, passing the notes on stdin."""
        args = ("release", "create", tag, "--title", tag, "--notes-file", "-")
        proc = _gh(*args, input=notes)
        if proc.returncode != 0:
            raise _gh_error(args, proc)


def _gh(*args: str, input: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args], input=input, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise ReleaseFragmentsError(f"cannot run gh: {exc}") from exc


def _gh_error(
    args: tuple[str, ...], proc: subprocess.CompletedProcess[str]
) -> ReleaseFragmentsError:
    return ReleaseFragmentsError(f"`gh {' '.join(args)}` failed:\n{proc.stderr.strip()}")


def release(
    config: Config, *, publisher: Publisher, max_attempts: int = 3, dry_run: bool = False
) -> str | None:
    """Release pending fragments and return the tag, or None if there was nothing to do.

    With `dry_run`, only builds in dry-run mode and returns the would-be tag.
    """
    if dry_run:
        result = build(config, dry_run=True)
        return f"v{result.version}" if result else None
    if max_attempts < 1:
        raise ReleaseFragmentsError("max attempts must be at least 1")

    root = config.root
    for attempt in range(1, max_attempts + 1):
        result = build(config)
        if result is None:
            return _recover(config, publisher) if attempt == 1 else None
        tag = f"v{result.version}"
        commit = _commit(config, tag)
        if _push(config, commit):
            notes = extract_notes(_read_changelog(config), result.version)
            _ensure_tag(config, tag, commit)
            _ensure_published(publisher, tag, notes)
            return tag
        run_git(root, "reset", "--hard", "FETCH_HEAD")
    raise ReleaseFragmentsError(
        f"lost the push race {max_attempts} times; rerun the release workflow"
    )


def _commit(config: Config, tag: str) -> str:
    root = config.root
    files = [config.changelog, config.manifest]
    if config.path(config.lockfile).exists():
        files.append(config.lockfile)
    run_git(root, "add", "--", *files)
    run_git(root, "add", "-A", "--", config.fragment_dir)
    if run_git(root, "diff", "--cached", "--quiet", check=False).returncode == 0:
        raise ReleaseFragmentsError("build produced no staged changes; nothing to commit")
    run_git(root, "commit", "-m", f"chore(release): {tag} [skip ci]")
    return rev_parse(root, "HEAD")


def _push(config: Config, commit: str) -> bool:
    """Push the release commit; False means we lost a race and should rebuild on FETCH_HEAD."""
    root = config.root
    push = run_git(root, "push", config.remote, f"HEAD:refs/heads/{config.branch}", check=False)
    if push.returncode == 0:
        return True
    run_git(root, "fetch", config.remote, config.branch)
    tip = rev_parse(root, "FETCH_HEAD")
    if tip == commit:
        # The push landed even though the client reported failure (e.g. a dropped connection).
        return True
    if tip == rev_parse(root, f"{commit}^"):
        tail = "\n".join(push.stderr.strip().splitlines()[-5:])
        raise ReleaseFragmentsError(f"push to {config.remote} failed:\n{tail}")
    return False


def _read_changelog(config: Config) -> str:
    try:
        return config.path(config.changelog).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _ensure_tag(config: Config, tag: str, commit: str) -> None:
    root = config.root
    ref = f"refs/tags/{tag}"
    out = run_git(root, "ls-remote", "--tags", config.remote, ref, f"{ref}^{{}}").stdout
    # ls-remote patterns match ref-name tails, so keep only exact names. An annotated tag's
    # target is its `^{}` entry; a lightweight tag has only the plain entry.
    remote = {name: sha for sha, name in (line.split("\t", 1) for line in out.splitlines())}
    target = remote.get(f"{ref}^{{}}", remote.get(ref))
    if target is not None:
        if target != commit:
            raise ReleaseFragmentsError(
                f"remote tag {tag} points at {target}, not release commit {commit}"
            )
        return
    run_git(root, "tag", "-a", tag, "-m", tag, commit)
    run_git(root, "push", config.remote, ref)


def _ensure_published(publisher: Publisher, tag: str, notes: str) -> None:
    if not notes.strip():
        raise ReleaseFragmentsError(f"no release notes for {tag}")
    if not publisher.release_exists(tag):
        publisher.create_release(tag, notes)


def _recover(config: Config, publisher: Publisher) -> str | None:
    """Create a missing tag or release for the newest changelog version, if it was committed."""
    text = _read_changelog(config)
    match = _NEWEST_VERSION_RE.search(text)
    if match is None:
        return None
    version = match[1]
    tag = f"v{version}"
    commit = run_git(
        config.root,
        "log",
        "-1",
        "--format=%H",
        "--fixed-strings",
        "--grep",
        f"chore(release): {tag} [skip ci]",
    ).stdout.strip()
    if not commit:
        return None
    notes = extract_notes(text, version)
    _ensure_tag(config, tag, commit)
    _ensure_published(publisher, tag, notes)
    return tag
