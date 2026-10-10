# Design

**Flow:** a PR adds release-note fragments → a PR gate validates them → merging to the
default branch triggers release assembly → automation commits the generated files, tags
the commit and publishes a GitHub release.

Versions come from fragment categories only, never from commit messages, PR labels or a
hand-picked number.

## 1. Files and who writes them

| File | Purpose | Written by |
|---|---|---|
| `changelog/next/` | Pending Markdown fragments | Contributors (`release add`) |
| `CHANGELOG.md` | Release history, newest first | Release automation |
| `pyproject.toml` `version` | Current version | Release automation (contributors may edit other parts) |
| `uv.lock` | Lockfile, refreshed after the version changes | Release automation, dependency updates |

All paths are relative to the current working directory, which must be the repo root.

## 2. Configuration

Settings live in `[tool.release-fragments]` in `pyproject.toml`; see `config.py`. Every key
is optional, and unknown keys are an error.

| Key | Default | Meaning |
|---|---|---|
| `fragment-dir` | `changelog/next` | Pending-fragment directory |
| `changelog` | `CHANGELOG.md` | Release history |
| `manifest` | `pyproject.toml` | File holding `version = "X.Y.Z"` |
| `lockfile` | `uv.lock` | Staged with the release when it exists |
| `lock-command` | `["uv", "lock"]` | Run after the version changes; `[]` skips it |
| `shipping-paths` | `src/`, `.github/workflows/`, `.github/actions/`, `pyproject.toml`, `uv.lock` | Paths whose change requires a fragment. Trailing `/` means a directory prefix, otherwise an exact path |
| `base-ref` | `origin/main` | Default base for `release check` |
| `remote` | `origin` | Remote that `release publish` pushes to |
| `branch` | `main` | Branch that `release publish` pushes to |
| `major-version-zero` | `false` | Below 1.0, a major bump becomes a minor bump (see §5) |

## 3. Fragment contract (`fragments.py`)

- **Name:** `<YYYYMMDD>-<slug>-<6 lowercase hex>.<category>.md`. The slug is 1–55 of
  `[a-z0-9-]`. Only the date's shape is checked.
- **Body:** UTF-8 Markdown that is non-empty after trimming. It is trimmed at the edges and
  the interior is kept as written. The category is never inferred from the prose.
- **Categories:** listed below in rendering order. Names are case-sensitive.

  | Category | Bump | Heading |
  |---|---|---|
  | `breaking` | major | Breaking Changes |
  | `added` | minor | Added |
  | `changed` | minor | Changed |
  | `deprecated` | minor | Deprecated |
  | `removed` | major | Removed |
  | `fixed` | patch | Fixed |
  | `security` | patch | Security |

- **Discovery:** immediate, non-hidden regular files with a lowercase `.md` extension. There
  is no recursion, and a missing directory means no fragments. Every fragment is parsed
  before anything is written, and all problems are reported together.

## 4. Commands

The CLI is `release` (`cli.py`). It exits 0 on success and 1 on a `ReleaseFragmentsError`.

### `release add <category> <description> [--dry-run]` (`add.py`)

1. **Slug:** lowercase the description, turn each run of non-`[a-z0-9]` characters into one
   `-`, strip edge hyphens, truncate to 55 characters, then strip a trailing hyphen.
   Reject an empty result.
2. **Name:** use the UTC date and a random 6-hex suffix. Create the directory if needed.
   The file is created exclusively, so an existing file is never overwritten; on a
   collision, retry with a new suffix, up to 5 attempts in total.
3. **Body:** `- <description>\n`.
4. **Output:** print the absolute path as the last stdout line. `--dry-run` prints the path
   it would create and writes nothing, not even the directory.

If the category or description is missing, print usage and exit 0.

### `release build [--dry-run]` (`build.py`)

1. Load and validate all fragments. If there are none, write nothing, skip the lock refresh
   and print `new-version=`.
2. Read the version, apply the largest bump, and render the section dated today (UTC).
3. **Transactional (deliberate improvement):** compute the new changelog and manifest
   contents in memory, then write both as bytes so line endings are kept. Run the lock
   command.
   - **On any failure:** put back the original bytes of the changelog, manifest and
     lockfile (deleting files that didn't exist before), leave the fragments in place, and
     raise. The error carries the return code and the end of stderr.
   - **On success:** only after the lock refresh succeeds, delete exactly the consumed
     fragments. Remove the fragment directory if it is then empty; discovery treats a
     missing directory as empty.
4. **Output:** `new-version=X.Y.Z` is the last stdout line, printed only on success.
5. **`--dry-run` (deliberate improvement; the original ignored the flag):** print the
   section and `would-release=X.Y.Z`. Write nothing and run nothing.

### `release check [base] [head] [--assume-shipping]` (`check.py`)

`base` defaults to config `base-ref` and `head` to `HEAD`. Changed files come from a
**three-dot** diff with renames off (`git diff --name-only --no-renames base...head`),
never two-dot, so moving a file out of a shipping path still counts as a shipping change.
Checks run in this order; violations are collected and returned as a list of strings.

1. **Hand-edited history:** `CHANGELOG.md` changed → violation.
2. **Hand-edited version (deliberate change):** if the manifest changed, read its version at
   `merge-base(base, head)` and at `head`. If they differ, or either can't be read, it's a
   violation. The original compared the base *tip* with head, which falsely fails every
   open PR that touched `pyproject.toml` once a release lands on the base branch.
3. **New fragments:** take the added files under the fragment dir
   (`--diff-filter=A --no-renames`). Because renames are off, a fragment renamed to a new
   valid name counts as newly added; a test pins this.
   - **Unconsumable files (deliberate improvement):** an added file that build would never
     consume is a violation, because check and build must agree on scope. That covers
     nested paths, hidden files other than `.gitkeep`, and non-`.md` files.
   - **Read from head (deliberate improvement):** bodies are read from the head commit's
     blobs, not from the working tree, so the result doesn't depend on what is checked
     out.
   - Validate each name and body with `fragments.parse_fragment`.
4. **Fragment required:** if any changed path is a shipping path (or `--assume-shipping`)
   and no valid fragment was added → violation.

Bad refs or git failures raise `ReleaseFragmentsError`; they are not violations.

### `release publish [--dry-run] [--max-attempts N]` (`release.py`)

The original kept this in workflow shell. Here it is Python, so it can be tested against
real temp repos. It assumes a disposable CI checkout on `branch`, with the Git identity
and push credentials already configured by the workflow.

1. `build(config)`.
   - **No result on attempt 1:** run **publication recovery** (below) and return its tag
     or `None`.
   - **No result on a later attempt:** the winner already consumed everything, so return
     `None` without publishing.
2. **Stage only** the changelog, manifest, lockfile (if it exists) and
   `git add -A -- <fragment_dir>` (the deletions). If nothing is staged, raise.
3. **Commit** with message `chore(release): vX.Y.Z [skip ci]`.
4. **Push** `HEAD:refs/heads/<branch>` to `remote`. If it fails, `git fetch remote branch`.
   - If the fetched tip is our own commit, the push landed anyway: continue.
   - If the tip is no longer our commit's parent, we lost a race: `git reset --hard
     FETCH_HEAD` and go back to step 1. Recompute the release; never rebase a stale one.
   - Otherwise the failure is unrelated: raise immediately.
   - Give up after `max_attempts` attempts.
5. **Notes:** `extract_notes`; empty notes raise.
6. **Tag:** if `refs/tags/vX.Y.Z` exists on the remote, check that it peels to the release
   commit and raise if it doesn't (deliberate improvement). Otherwise create the annotated
   tag `vX.Y.Z` and push it.
7. **Publish:** if `publisher.release_exists(tag)` is true, skip. Otherwise
   `publisher.create_release(tag, notes)`.
8. Print `released=vX.Y.Z`, or `released=` when nothing was released.

**Publication recovery (deliberate improvement):** this repairs a release whose commit
landed but whose tag or publication failed.

1. Take the newest version in the changelog (the first `## [X.Y.Z]`); if there is none,
   return `None`.
2. Find the commit whose full subject is `chore(release): vX.Y.Z [skip ci]`. Matching the
   full subject keeps v1.2.3 from matching v1.2.30. If there is none, return `None`.
3. Ensure the tag and release exist, as in steps 6–7.

`--dry-run` builds in dry-run mode and prints `would-release=vX.Y.Z`. It never commits,
pushes, tags or publishes.

**Publisher seam:** `class Publisher(Protocol)` with `release_exists(tag) -> bool` and
`create_release(tag, notes) -> None`. `GhPublisher` shells out to `gh release view` and
`gh release create <tag> --title <tag> --notes-file -`, passing the notes on stdin. Tests
inject a fake and never call `gh`.

### `release notes <version>`

Prints `extract_notes(CHANGELOG text, version)`.

## 5. Version and rendering rules (`version.py`, `render.py`)

- **Version format:** exactly `X.Y.Z` in decimal, without leading zeros. Prerelease and
  build suffixes are rejected.
  - Patch: `X.Y.(Z+1)`. Minor: `X.(Y+1).0`. Major: `(X+1).0.0`.
  - **Below 1.0:** by default, no special case: a `breaking` or `removed` fragment takes
    0.4.2 to 1.0.0. With `major-version-zero = true`, a major bump becomes a minor bump
    while the major version is 0 (0.4.2 → 0.5.0), following SemVer §4 and the Cargo and npm
    caret convention that the minor number signals breaking changes in 0.y.z. Patch and
    minor bumps are unchanged. To release 1.0.0, turn the setting off; the next major
    bump then lands on 1.0.0.
- **Manifest:** exactly one line matching `^version\s*=\s*"([^"]*)"\s*$` (multiline mode,
  unindented, double-quoted). If there are zero or several, raise. Replace only the quoted
  value and keep every other byte.
- **Section:** `## [X.Y.Z] - YYYY-MM-DD`, then for each non-empty category in order a
  blank line, `### <Heading>`, a blank line, and the fragment bodies sorted by filename and
  separated by blank lines. The section ends with a single `\n`.
- **Insertion:**
  - **Missing file:** write the standard intro (`# Changelog`, plus a paragraph naming
    Keep a Changelog and Semantic Versioning, with links), then the section.
  - **Existing file:** insert before the first line that starts with `## [`, separated by
    one blank line. A `## [` quoted mid-line in the intro doesn't count.
  - **No marker:** append the section after exactly one blank line. Keep all other text.
- **`extract_notes(text, version)`:** the lines after `## [version]` up to the next line
  starting with `## `, with blank lines trimmed at both ends. Raise if the heading is
  missing or the notes are empty.

## 6. GitHub integration (`.github/`)

- **`ci.yml`:** lint, type-check and test on PRs and pushes, and call the gate on PRs.
- **`gate.yml`** (reusable `workflow_call`):
  - **Always reports a status.** The job always runs and its steps are conditional,
    because a skipped required job can block branch protection.
  - **Dependabot exemption:** the PR author **and** `github.actor` are both
    `dependabot[bot]` → success without validation.
  - **Otherwise:** fetch full history, then `release check <base.sha> <head.sha>`. The CLI
    decides whether shipping paths changed, so the path list lives in one place.
  - **Skip-marker guard:** reject the PR title, body or commit messages if they contain
    `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]`, `[actions skip]` or
    `skip-checks: true` (with or without the space). These survive squash merges and suppress the release. Pass the
    values through `env:`, never `${{ }}` inline in a script.
- **`release.yml`** (reusable; this repo's `auto-release.yml` calls it on push to `main`
  under `changelog/next/**`, and on `workflow_dispatch` for recovery):
  - Only the release job asks for `contents: write`.
  - `concurrency: release`, `cancel-in-progress: false`.
  - Checkout uses `fetch-depth: 0` and `persist-credentials: false`, then configures push
    auth from an optional `RELEASE_TOKEN` secret, falling back to `github.token`.
  - Sets the bot Git identity, then runs `release publish`.
  - **Install:** the tool comes from the `tool-spec` input. A consumer passes a pinned git
    URL; when the input is empty (this repo), it runs from the checkout with `uv run`.
- **Pre-push:** `.pre-commit-hooks.yaml` exports a `release-check` hook that runs
  `release check` with config defaults.

## 7. Known limits

- **Recovery doesn't check notes:** publication recovery checks that the tag exists and
  points at the right commit. It doesn't check that an existing GitHub release's notes
  match the changelog.
- **Branch protection:** with required PRs on the branch, `GITHUB_TOKEN` can't push the
  release commit. Provide a GitHub App token as `RELEASE_TOKEN` or add a ruleset bypass.
- **No submodule sync:** the original's submodule pointer sync was workspace-specific and
  is not included.
