"""Loading `[tool.release-fragments]` settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from release_fragments.config import DEFAULT_SHIPPING_PATHS, Config, load_config
from release_fragments.errors import ReleaseFragmentsError


def _load(tmp_path: Path, table: str) -> Config:
    (tmp_path / "pyproject.toml").write_text(f"[tool.release-fragments]\n{table}\n")
    return load_config(tmp_path)


def test_defaults_without_pyproject(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert config == Config(root=tmp_path.resolve())
    assert config.shipping_paths == DEFAULT_SHIPPING_PATHS


def test_hyphenated_keys_and_list_values(tmp_path: Path) -> None:
    config = _load(
        tmp_path,
        'fragment-dir = "notes/pending/"\nlock-command = []\nbase-ref = "upstream/dev"\n'
        "major-version-zero = true",
    )
    assert (
        config.fragment_dir,
        config.lock_command,
        config.base_ref,
        config.major_version_zero,
    ) == ("notes/pending", (), "upstream/dev", True)


def test_unknown_key_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ReleaseFragmentsError, match="unknown .* keys: color"):
        _load(tmp_path, 'color = "red"')


@pytest.mark.parametrize(
    "table",
    [
        "changelog = 3",
        'changelog = ""',
        'lock-command = "uv lock"',
        "shipping-paths = [1]",
        'major-version-zero = "yes"',
    ],
)
def test_wrong_type_is_an_error(tmp_path: Path, table: str) -> None:
    with pytest.raises(ReleaseFragmentsError, match="must be"):
        _load(tmp_path, table)


def test_invalid_toml_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ReleaseFragmentsError, match="invalid TOML"):
        _load(tmp_path, "this is = = not toml")
