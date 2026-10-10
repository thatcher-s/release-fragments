"""Thin `git` subprocess wrappers that turn failures into `ReleaseFragmentsError`.

Does I/O (runs `git`); `check` and `release` decide what to ask Git, this module only asks.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from release_fragments.errors import ReleaseFragmentsError

_STDERR_TAIL = 5


def _fail(args: tuple[str, ...], stderr: str) -> ReleaseFragmentsError:
    tail = "\n".join(stderr.strip().splitlines()[-_STDERR_TAIL:])
    return ReleaseFragmentsError(f"`git {' '.join(args)}` failed:\n{tail}")


def run_git(
    root: Path, *args: str, input: str | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run `git <args>` in `root`; with `check`, a non-zero exit raises `ReleaseFragmentsError`."""
    try:
        proc = subprocess.run(
            ["git", *args], cwd=root, input=input, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise ReleaseFragmentsError(f"cannot run git: {exc}") from exc
    if check and proc.returncode != 0:
        raise _fail(args, proc.stderr)
    return proc


def rev_parse(root: Path, rev: str) -> str:
    """Resolve `rev` to a full commit SHA, raising on a bad ref."""
    return run_git(root, "rev-parse", "--verify", f"{rev}^{{commit}}").stdout.strip()


def show_file(root: Path, commit: str, path: str) -> bytes | None:
    """Return the raw bytes of `path` at `commit`, or None if the path doesn't exist there."""
    args = ("cat-file", "blob", f"{commit}:{path}")
    exists = run_git(root, "cat-file", "-e", f"{commit}:{path}", check=False)
    if exists.returncode != 0:
        return None
    try:
        proc = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
    except OSError as exc:
        raise ReleaseFragmentsError(f"cannot run git: {exc}") from exc
    if proc.returncode != 0:
        raise _fail(args, proc.stderr.decode("utf-8", "replace"))
    return proc.stdout


def changed_paths(root: Path, base: str, head: str, *, added_under: str | None = None) -> list[str]:
    """Paths changed by a three-dot `base...head` diff, without rename pairing.

    With `added_under`, only paths added under that directory.
    """
    args = ["diff", "--name-only", "-z", "--no-renames"]
    if added_under is not None:
        args.append("--diff-filter=A")
    args.append(f"{base}...{head}")
    if added_under is not None:
        args += ["--", added_under]
    out = run_git(root, *args).stdout
    return [p for p in out.split("\0") if p]
