"""Tests for Docker build context exclusions."""

from __future__ import annotations

import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCKERIGNORE = ROOT / ".dockerignore"


def _read_entries() -> set[str]:
    entries = set()
    for raw_line in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        entry = raw_line.strip()
        if entry and not entry.startswith("#"):
            entries.add(entry)
    return entries


def test_dockerignore_exists():
    """Project root must include a .dockerignore file."""
    assert DOCKERIGNORE.is_file(), ".dockerignore is missing from project root"


def test_dockerignore_excludes_virtualenv():
    """Docker build context should exclude the local virtual environment."""
    entries = _read_entries()
    assert {".venv", ".venv/", "/.venv/"}.intersection(entries), (
        ".dockerignore must exclude .venv from the Docker build context"
    )


def test_dockerignore_excludes_tests_directory():
    """Docker build context should exclude local test files."""
    entries = _read_entries()
    assert {"tests", "tests/", "/tests/"}.intersection(entries), (
        ".dockerignore must exclude tests from the Docker build context"
    )
