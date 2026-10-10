# release-fragments

News-fragment changelog and semver release automation for Python repositories.

## What it does

Each pull request that ships a behavior change adds a small Markdown fragment under
`changelog/next/` instead of hand-editing `CHANGELOG.md`. A PR gate validates the
fragments and refuses PRs that touch shipping code without one. Once the PR merges to
the default branch, release automation assembles the pending fragments into a new
`CHANGELOG.md` section, bumps the version, commits, tags and publishes a GitHub release.

The version bump is derived entirely from the fragment categories present in a release —
never from commit messages, PR labels or a hand-picked number. The largest bump among
the fragments being released wins:

| Category | Bump | Changelog heading |
|---|---|---|
| `breaking` | major | Breaking Changes |
| `removed` | major | Removed |
| `added` | minor | Added |
| `changed` | minor | Changed |
| `deprecated` | minor | Deprecated |
| `fixed` | patch | Fixed |
| `security` | patch | Security |

Flow: **PR adds fragments → gate validates them → merge to the default branch → release
assembles, tags and publishes.**

## Quick start (consumer repo)

1. Add a `[tool.release-fragments]` table to `pyproject.toml` only if you need a
   non-default setting — every key is optional (see Configuration below).

2. Add the pre-push hook to `.pre-commit-config.yaml`:

   ```yaml
   repos:
     - repo: https://github.com/thatcher-s/release-fragments
       rev: v0.1.0
       hooks:
         - id: release-check
   ```

3. Call the two reusable workflows from your own workflow files:

   ```yaml
   # .github/workflows/ci.yml
   on:
     pull_request:

   jobs:
     fragment-gate:
       uses: thatcher-s/release-fragments/.github/workflows/gate.yml@v0.1.0
       with:
         tool-spec: "git+https://github.com/thatcher-s/release-fragments@v0.1.0"
   ```

   ```yaml
   # .github/workflows/auto-release.yml
   on:
     push:
       branches: [main]
       paths: ["changelog/next/**"]

   jobs:
     release:
       permissions:
         contents: write
       uses: thatcher-s/release-fragments/.github/workflows/release.yml@v0.1.0
       with:
         tool-spec: "git+https://github.com/thatcher-s/release-fragments@v0.1.0"
       secrets: inherit
   ```

   `gate.yml` must be called from a `pull_request`-triggered workflow — it reads the PR's
   base and head SHAs from the event and otherwise has nothing to check. Pass
   `tool-spec` so the consumer repo doesn't need `release-fragments` as a dependency;
   omit it only when the tool is installed in the calling repo itself. `secrets: inherit`
   passes an optional `RELEASE_TOKEN` repository secret through (see GitHub requirements
   below).

4. Add a `just`/shell helper so contributors don't have to remember the fragment
   filename contract:

   ```just
   fragment category description:
       uvx --from git+https://github.com/thatcher-s/release-fragments@v0.1.0 \
           release add {{ category }} "{{ description }}"
   ```

   ```console
   $ just fragment fixed "Handle empty release notes"
   ```

## Commands

- **`release add <category> <description> [--dry-run]`** — creates a pending
  fragment. Prints the absolute path to the new file as the last stdout line (with
  `--dry-run`, the path it *would* create; nothing is written). With a missing
  category or description, it prints usage and exits 0.
- **`release check [base] [head] [--assume-shipping]`** — validates a branch against
  the release policy (hand-edited history, hand-edited version, new fragments, fragment
  required for shipping changes). Each violation goes to stderr as
  `release check: <message>`; exits 1 if there are any, 0 otherwise.
- **`release build [--dry-run]`** — assembles all pending fragments into a release.
  Prints `new-version=X.Y.Z` as the last stdout line (`new-version=` with no pending
  fragments). With `--dry-run`, prints the rendered section followed by
  `would-release=X.Y.Z` (or `no pending fragments`), and writes nothing.
- **`release publish [--dry-run] [--max-attempts N]`** — builds, commits, pushes,
  tags and publishes (CI only). Prints `released=vX.Y.Z` as the last stdout line
  (`released=` if nothing was released). `--dry-run` builds in dry-run mode and prints
  `would-release=vX.Y.Z` instead, without pushing anything.
- **`release notes <version>`** — prints one version's release notes extracted from
  `CHANGELOG.md`. The version may be given with or without a leading `v`.

## Configuration

Settings live under `[tool.release-fragments]` in `pyproject.toml`; every key is
optional and unknown keys are an error. See `docs/design.md` §2 for the full key
reference and defaults.

## GitHub requirements

- **Branch protection:** if the default branch requires pull requests, the built-in
  `GITHUB_TOKEN` cannot push the release commit past that protection. Supply a GitHub
  App (or other) token with `contents: write` as the `RELEASE_TOKEN` secret, or add a
  ruleset bypass for the release actor.
- **`RELEASE_TOKEN`:** optional; falls back to `github.token` when not supplied. Only
  needed when branch protection would otherwise block the release push.

## Developing this repo

```console
$ just init    # uv sync, then install the pre-push hook
$ just test    # pytest
$ just lint    # ruff check, ruff format --check, mypy
```

Every behavior-changing PR adds a fragment:

```console
$ just fragment <category> "<description>"
```

## License

MIT — see [LICENSE](LICENSE).
