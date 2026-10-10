"""The `release` command line: parsing and output only; the work lives in sibling modules.

Stdout lines named here (`new-version=`, the fragment path) are an automation interface.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from release_fragments.add import add_fragment
from release_fragments.build import build
from release_fragments.check import check
from release_fragments.config import load_config
from release_fragments.errors import ReleaseFragmentsError
from release_fragments.fragments import Category
from release_fragments.release import GhPublisher, release
from release_fragments.render import extract_notes

ADD_USAGE = f"usage: release add <{'|'.join(c.value for c in Category)}> <description>"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="release", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add", help="create a pending release-note fragment")
    add.add_argument("category", nargs="?")
    add.add_argument("description", nargs="?")
    add.add_argument("--dry-run", action="store_true", help="print the path, write nothing")

    chk = sub.add_parser("check", help="validate a branch's fragments and release policy")
    chk.add_argument("base", nargs="?", help="base ref (default: config base_ref)")
    chk.add_argument("head", nargs="?", default="HEAD", help="head ref (default: HEAD)")
    chk.add_argument(
        "--assume-shipping",
        action="store_true",
        help="require a new fragment regardless of which paths changed",
    )

    bld = sub.add_parser("build", help="assemble pending fragments into a release")
    bld.add_argument("--dry-run", action="store_true", help="print the section, write nothing")

    rel = sub.add_parser("publish", help="build, commit, push, tag and publish (CI only)")
    rel.add_argument("--dry-run", action="store_true", help="build and report, push nothing")
    rel.add_argument("--max-attempts", type=int, default=3)

    notes = sub.add_parser("notes", help="print one version's release notes")
    notes.add_argument("version", help="X.Y.Z, with or without a leading v")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    args = _parser().parse_args(argv)
    try:
        return _dispatch(args)
    except ReleaseFragmentsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _dispatch(args: argparse.Namespace) -> int:
    config = load_config()

    if args.command == "add":
        if not args.category or not args.description:
            print(ADD_USAGE)
            return 0
        path = add_fragment(config, args.category, args.description, dry_run=args.dry_run)
        print(path)
        return 0

    if args.command == "check":
        violations = check(
            config,
            args.base or config.base_ref,
            args.head,
            assume_shipping=args.assume_shipping,
        )
        for violation in violations:
            print(f"release check: {violation}", file=sys.stderr)
        return 1 if violations else 0

    if args.command == "build":
        result = build(config, dry_run=args.dry_run)
        if args.dry_run:
            if result is not None:
                print(result.section, end="")
                print(f"would-release={result.version}")
            else:
                print("no pending fragments")
            return 0
        print(f"new-version={result.version if result else ''}")
        return 0

    if args.command == "publish":
        tag = release(
            config,
            publisher=GhPublisher(),
            max_attempts=args.max_attempts,
            dry_run=args.dry_run,
        )
        print(f"{'would-release' if args.dry_run else 'released'}={tag or ''}")
        return 0

    if args.command == "notes":
        changelog = config.path(config.changelog)
        if not changelog.is_file():
            raise ReleaseFragmentsError(f"{config.changelog} does not exist")
        text = changelog.read_text(encoding="utf-8")
        print(extract_notes(text, args.version.removeprefix("v")))
        return 0

    raise AssertionError(f"unhandled command {args.command}")


if __name__ == "__main__":
    sys.exit(main())
