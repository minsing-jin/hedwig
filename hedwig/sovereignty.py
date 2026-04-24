"""Sovereignty boundary — expresses + enforces the v3 core moat.

Closes G4 in docs/phase_reports/interview_gap_audit.md. seed.yaml ontology
calls out ``sovereignty`` as a first-class entity declaring which paths
the user can edit vs. the system can mutate vs. readonly history.
Without this boundary the 'algorithm sovereignty' moat is just a
tagline. With it, nl_editor / nl_algo_editor / meta-evolution all
consult the same list before overwriting.

Usage:
    from hedwig.sovereignty import can_edit, enforce

    if not can_edit('algorithm', 'retrieval.top_n', actor='user'):
        return JSONResponse({'error': 'path locked'}, status_code=403)

    # Or raise on violation:
    enforce('algorithm', 'version', actor='user')  # raises SovereigntyError
"""
from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

SOVEREIGNTY_PATH = Path(__file__).resolve().parent.parent / "sovereignty.yaml"

VALID_DOMAINS = ("criteria", "algorithm", "memory")
VALID_ACTORS = ("user", "system")


class SovereigntyError(PermissionError):
    """Raised when an actor attempts to write a path they don't own."""


def load_sovereignty() -> dict:
    try:
        return yaml.safe_load(SOVEREIGNTY_PATH.read_text()) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.warning("sovereignty.yaml parse failed: %s", e)
        return {}


def _match(path: str, patterns: list[str]) -> bool:
    """Check whether ``path`` matches any of the glob patterns."""
    for pat in patterns or []:
        if fnmatch.fnmatchcase(path, pat):
            return True
    return False


def can_edit(domain: str, path: str, actor: str = "user") -> bool:
    """Return True when ``actor`` is allowed to write ``path`` under ``domain``.

    Rules:
      - readonly_history is forbidden for everyone.
      - user_editable is allowed for actor='user' (and for actor='system').
      - system_mutable is allowed for actor='system' (and for actor='user'
        when the path is also listed under user_editable).
      - Paths not mentioned at all default to actor='system' write-allowed
        but actor='user' write-denied (conservative default — if you want
        NL editors to touch something new, add it to user_editable).
    """
    if domain not in VALID_DOMAINS:
        raise ValueError(f"unknown sovereignty domain {domain!r}")
    if actor not in VALID_ACTORS:
        raise ValueError(f"unknown actor {actor!r}")

    spec = load_sovereignty().get(domain) or {}
    readonly = spec.get("readonly_history") or []
    user_editable = spec.get("user_editable") or []
    system_mutable = spec.get("system_mutable") or []

    if _match(path, readonly):
        return False
    if actor == "user":
        return _match(path, user_editable)
    if actor == "system":
        return _match(path, user_editable) or _match(path, system_mutable) or (
            not _match(path, readonly)
        )
    return False


def enforce(domain: str, path: str, actor: str = "user") -> None:
    """Raise :class:`SovereigntyError` when ``actor`` cannot write ``path``."""
    if not can_edit(domain, path, actor=actor):
        raise SovereigntyError(
            f"sovereignty: actor={actor!r} may not write {domain}.{path}"
        )


def filter_allowed_changes(
    domain: str, changes: list[dict], actor: str = "user",
) -> tuple[list[dict], list[dict]]:
    """Split a list of {op, path, value} into (allowed, rejected).

    NL editor endpoints use this to apply the allowed subset and return the
    rejected paths to the UI so the user sees why something didn't happen.
    """
    allowed, rejected = [], []
    for ch in changes or []:
        path = str(ch.get("path", ""))
        if not path:
            rejected.append({**ch, "reason": "missing path"})
            continue
        if can_edit(domain, path, actor=actor):
            allowed.append(ch)
        else:
            rejected.append({**ch, "reason": "sovereignty: path not user_editable"})
    return allowed, rejected
