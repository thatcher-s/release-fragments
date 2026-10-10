"""The PR gate: compare a branch against its base and list release-policy violations.

Reads Git history only (never the working tree); `fragments` owns the contract it applies,
`build` consumes what this gate lets through.
"""

from __future__ import annotations

import posixpath

from release_fragments.config import Config
from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import FragmentError, is_candidate_name, parse_fragment
from release_fragments.git import changed_paths, rev_parse, run_git, show_file
from release_fragments.version import read_version


def is_shipping_path(path: str, shipping_paths: tuple[str, ...]) -> bool:
    """True if `path` matches an entry: trailing `/` is a directory prefix, else exact."""
    return any(
        path.startswith(entry) if entry.endswith("/") else path == entry for entry in shipping_paths
    )


def check(config: Config, base: str, head: str, *, assume_shipping: bool = False) -> list[str]:
    """Return the violations of `head` relative to `base`; an empty list means the PR passes."""
    root = config.root
    base_sha = rev_parse(root, base)
    head_sha = rev_parse(root, head)
    changed = changed_paths(root, base_sha, head_sha)
    violations: list[str] = []

    if config.changelog in changed:
        violations.append(f"{config.changelog} is written by release automation; revert it")

    if config.manifest in changed:
        violations.extend(_version_violations(config, base_sha, head_sha))

    prefix = config.fragment_dir + "/"
    added = changed_paths(root, base_sha, head_sha, added_under=prefix)
    valid = 0
    for path in added:
        rest = path.removeprefix(prefix)
        name = posixpath.basename(path)
        if "/" in rest:
            violations.append(f"{path}: fragments must sit directly in {config.fragment_dir}")
        elif name == ".gitkeep":
            continue
        elif not is_candidate_name(name):
            violations.append(f"{path}: not a fragment (hidden or not .md); build would skip it")
        else:
            content = show_file(root, head_sha, path) or b""
            try:
                parse_fragment(name, content)
            except FragmentError as exc:
                violations.append(str(exc))
            else:
                valid += 1

    shipping = assume_shipping or any(is_shipping_path(p, config.shipping_paths) for p in changed)
    if shipping and valid == 0:
        violations.append(
            f"shipping changes need a new fragment in {config.fragment_dir} "
            "(run `release add <category> <description>`)"
        )
    return violations


def _version_violations(config: Config, base_sha: str, head_sha: str) -> list[str]:
    # Compare against the merge-base, not the base tip: a release landing on the base after
    # branching changes the base version without this PR touching it.
    merge_base = run_git(config.root, "merge-base", base_sha, head_sha).stdout.strip()
    before = show_file(config.root, merge_base, config.manifest)
    after = show_file(config.root, head_sha, config.manifest)
    if before is None or after is None:
        return []
    try:
        old = read_version(before.decode("utf-8"))
        new = read_version(after.decode("utf-8"))
    except (UnicodeDecodeError, ReleaseFragmentsError) as exc:
        return [f"{config.manifest}: cannot read version: {exc}"]
    if old != new:
        return [
            f"{config.manifest} version changed {old} -> {new}; "
            "versions are set by release automation"
        ]
    return []
