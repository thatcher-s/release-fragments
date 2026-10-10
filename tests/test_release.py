"""Tests for `release publish` against a local bare `origin` and a fake publisher."""

from __future__ import annotations

from pathlib import Path

import pytest
from gitrepo import clone, commit_all, frag, git, git_env, init_origin, write

from release_fragments.config import load_config
from release_fragments.errors import ReleaseFragmentsError
from release_fragments.release import release

__all__ = ["git_env"]
pytestmark = pytest.mark.usefixtures("git_env")


class FakePublisher:
    """Records releases; `existing` tags report as already published."""

    def __init__(self, existing: set[str] | None = None, fail: bool = False) -> None:
        self.existing = existing or set()
        self.fail = fail
        self.created: list[tuple[str, str]] = []

    def release_exists(self, tag: str) -> bool:
        return tag in self.existing

    def create_release(self, tag: str, notes: str) -> None:
        if self.fail:
            raise ReleaseFragmentsError("publish failed")
        self.created.append((tag, notes))


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    """A bare origin with one pending `added` fragment on main."""
    origin = init_origin(tmp_path)
    dev = clone(origin, tmp_path / "dev")
    write(dev, frag("widget", "added"), "- Add widget.\n")
    commit_all(dev, "feat: widget")
    git(dev, "push", "-q", "origin", "main")
    return origin


def ci_clone(origin: Path, dest: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh CI checkout of origin, used as the cwd."""
    root = clone(origin, dest)
    monkeypatch.chdir(root)
    return root


def push_fragment(origin: Path, tmp_path: Path, name: str, category: str, body: str) -> None:
    """Simulate another merged PR landing a fragment on origin."""
    other = clone(origin, tmp_path / f"other-{name}")
    write(other, frag(name, category, "fed456"), body)
    commit_all(other, f"feat: {name}")
    git(other, "push", "-q", "origin", "main")


def run(root: Path, publisher: FakePublisher, **kwargs: object) -> str | None:
    return release(load_config(root), publisher=publisher, **kwargs)  # type: ignore[arg-type]


def remote_tag_target(origin: Path, tag: str) -> str:
    return git(origin, "rev-parse", f"refs/tags/{tag}^{{commit}}")


def test_happy_path(origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    write(root, "stray.txt", "untracked\n")
    write(root, "README.md", "dirty but unrelated\n")
    publisher = FakePublisher()

    assert run(root, publisher) == "v1.3.0"

    tip = git(origin, "rev-parse", "main")
    assert git(origin, "log", "-1", "--format=%s", "main") == "chore(release): v1.3.0 [skip ci]"
    changed = git(origin, "show", "--name-only", "--format=", "main").splitlines()
    assert sorted(changed) == sorted(["CHANGELOG.md", "pyproject.toml", frag("widget", "added")])
    assert git(origin, "cat-file", "-t", "refs/tags/v1.3.0") == "tag"
    assert remote_tag_target(origin, "v1.3.0") == tip
    [(tag, notes)] = publisher.created
    assert tag == "v1.3.0"
    assert "- Add widget." in notes and "## [" not in notes


def test_push_race_rebuilds_on_winning_tip(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    push_fragment(origin, tmp_path, "gadget", "breaking", "- Replace gadget.\n")
    publisher = FakePublisher()

    assert run(root, publisher) == "v2.0.0"

    changelog = git(origin, "show", "main:CHANGELOG.md")
    assert "- Add widget." in changelog and "- Replace gadget." in changelog
    assert "## [1.3.0]" not in changelog
    assert [tag for tag, _ in publisher.created] == ["v2.0.0"]


def test_winner_consumed_everything_returns_none(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loser = clone(origin, tmp_path / "loser")
    winner = ci_clone(origin, tmp_path / "winner", monkeypatch)
    assert run(winner, FakePublisher()) == "v1.3.0"
    monkeypatch.chdir(loser)
    # Otherwise the loser's release commit can be byte-identical to the winner's.
    monkeypatch.setenv("GIT_COMMITTER_DATE", "2001-01-01T00:00:00Z")
    publisher = FakePublisher()

    assert run(loser, publisher) is None

    assert publisher.created == []
    assert git(origin, "log", "-1", "--format=%s", "main") == "chore(release): v1.3.0 [skip ci]"


def test_broken_remote_raises_immediately(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    git(root, "remote", "set-url", "origin", str(tmp_path / "missing.git"))
    publisher = FakePublisher()
    with pytest.raises(ReleaseFragmentsError):
        run(root, publisher)
    assert publisher.created == []


def test_rejected_push_with_unchanged_tip_raises(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    before = git(origin, "rev-parse", "main")
    hook = write(origin, "hooks/pre-receive", "#!/bin/sh\necho 'policy says no' >&2\nexit 1\n")
    hook.chmod(0o755)
    with pytest.raises(ReleaseFragmentsError, match="policy says no"):
        run(root, FakePublisher(), max_attempts=3)
    assert git(origin, "rev-parse", "main") == before
    assert git(root, "log", "-1", "--format=%s") == "chore(release): v1.3.0 [skip ci]"


def test_attempts_exhausted_raises(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    push_fragment(origin, tmp_path, "gadget", "fixed", "- Fix gadget.\n")
    with pytest.raises(ReleaseFragmentsError, match="lost the push race"):
        run(root, FakePublisher(), max_attempts=1)
    assert git(origin, "log", "-1", "--format=%s", "main") == "feat: gadget"


def test_remote_tag_on_wrong_commit_raises(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    git(root, "tag", "-a", "v1.3.0", "-m", "squatter")
    git(root, "push", "-q", "origin", "v1.3.0")
    publisher = FakePublisher()
    with pytest.raises(ReleaseFragmentsError, match="not release commit"):
        run(root, publisher)
    assert publisher.created == []


def test_existing_github_release_is_skipped(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    publisher = FakePublisher(existing={"v1.3.0"})
    assert run(root, publisher) == "v1.3.0"
    assert publisher.created == []
    assert remote_tag_target(origin, "v1.3.0") == git(origin, "rev-parse", "main")


def test_recovery_publishes_missing_release_and_skips_good_tag(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = ci_clone(origin, tmp_path / "first", monkeypatch)
    with pytest.raises(ReleaseFragmentsError, match="publish failed"):
        run(first, FakePublisher(fail=True))
    tag_object = git(origin, "rev-parse", "refs/tags/v1.3.0")
    second = ci_clone(origin, tmp_path / "second", monkeypatch)
    publisher = FakePublisher()

    assert run(second, publisher) == "v1.3.0"

    assert git(origin, "rev-parse", "refs/tags/v1.3.0") == tag_object
    [(tag, notes)] = publisher.created
    assert tag == "v1.3.0" and "- Add widget." in notes


def test_recovery_creates_missing_tag(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = ci_clone(origin, tmp_path / "first", monkeypatch)
    assert run(first, FakePublisher()) == "v1.3.0"
    git(origin, "tag", "-d", "v1.3.0")
    second = ci_clone(origin, tmp_path / "second", monkeypatch)
    publisher = FakePublisher(existing={"v1.3.0"})

    assert run(second, publisher) == "v1.3.0"

    assert remote_tag_target(origin, "v1.3.0") == git(origin, "rev-parse", "main")
    assert publisher.created == []


def test_nothing_to_release_or_recover_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = init_origin(tmp_path)
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    publisher = FakePublisher()
    assert run(root, publisher) is None
    assert publisher.created == []
    assert git(origin, "tag") == ""


def test_dry_run_pushes_nothing(
    origin: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = ci_clone(origin, tmp_path / "ci", monkeypatch)
    before = git(origin, "rev-parse", "main")
    publisher = FakePublisher()

    assert run(root, publisher, dry_run=True) == "v1.3.0"

    assert git(origin, "rev-parse", "main") == before
    assert git(origin, "tag") == ""
    assert git(root, "status", "--porcelain") == ""
    assert publisher.created == []
