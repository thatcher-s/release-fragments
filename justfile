# Task runner. Requires `just` and `uv`.

default:
    @just --list

# One-time setup after cloning: environment and pre-push hooks
init:
    uv sync
    prek install --hook-type pre-push

# Run the test suite
test *args:
    uv run pytest {{ args }}

# Lint, format-check and type-check
lint:
    uv run ruff check . && uv run ruff format --check . && uv run mypy

# Auto-fix lint findings and reformat
fmt:
    uv run ruff check --fix . && uv run ruff format .

# Add a release-note fragment, e.g. `just fragment fixed "Handle empty notes"`
fragment category description:
    uv run release add {{ category }} "{{ description }}"
