from __future__ import annotations

import logging
import re
from importlib import metadata
from pathlib import Path
from typing import Final

import httpx

logger = logging.getLogger(__name__)

GITHUB_REPOSITORY: Final[str] = "minsing-jin/hedwig"
GITHUB_LATEST_RELEASE_URL: Final[str] = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest"
)
REQUEST_TIMEOUT_SECONDS: Final[float] = 5.0


def resolve_current_version() -> str:
    """Return the current Hedwig version for local and installed runs."""
    try:
        return metadata.version("hedwig")
    except metadata.PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
        if pyproject_path.exists():
            match = re.search(
                r'^version\s*=\s*"(?P<version>[^"]+)"',
                pyproject_path.read_text(encoding="utf-8"),
                re.MULTILINE,
            )
            if match:
                return match.group("version")
        return "0.0.0"


def _normalize_version(version: str) -> str:
    match = re.search(r"(\d+(?:\.\d+)*)", version or "")
    return match.group(1) if match else "0.0.0"


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in _normalize_version(version).split("."))


def check_latest_version(current_version: str | None = None) -> tuple[str, str, bool]:
    """Compare the current version with the latest GitHub release tag."""
    resolved_current = _normalize_version(current_version or resolve_current_version())

    try:
        response = httpx.get(
            GITHUB_LATEST_RELEASE_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"hedwig/{resolved_current}",
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        latest_version = _normalize_version(response.json().get("tag_name", resolved_current))
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("Failed to check latest Hedwig release: %s", exc)
        latest_version = resolved_current

    return (
        resolved_current,
        latest_version,
        _version_tuple(latest_version) > _version_tuple(resolved_current),
    )
