"""
Storage dispatcher — picks SQLite (local) or Supabase based on env.

Default: SQLite local file at ~/.hedwig/hedwig.db (zero-config)
Override: set SUPABASE_URL + SUPABASE_KEY to use Supabase instead.
Force:    set HEDWIG_STORAGE=sqlite|supabase

All public functions mirror the same signature whichever backend is active.
"""
from __future__ import annotations

import importlib
import inspect
import os
from typing import Any

from hedwig.models import ScoredSignal


def _backend_name() -> str:
    forced = os.getenv("HEDWIG_STORAGE", "").strip().lower()
    if forced in ("sqlite", "local"):
        return "local"
    if forced == "supabase":
        return "supabase"
    if os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        return "supabase"
    return "local"


def _backend():
    # importlib.import_module bypasses __getattr__ recursion
    return importlib.import_module(f"hedwig.storage.{_backend_name()}")


def get_backend_name() -> str:
    return _backend_name()


def save_signals(signals: list[ScoredSignal], user_id: str | None = None) -> int:
    """Persist feed signals through the currently selected backend.

    Keep this as an explicit wrapper instead of relying on module ``__getattr__``:
    tests and long-running dashboard processes may import or patch this symbol
    before one-shot setup forces ``HEDWIG_STORAGE=sqlite``.
    """
    save = _backend().save_signals
    signature = inspect.signature(save)
    accepts_user_id = "user_id" in signature.parameters or any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in signature.parameters.values()
    )
    if accepts_user_id:
        return save(signals, user_id=user_id)
    return save(signals)


def __getattr__(name: str) -> Any:
    # Only proxy non-dunder, non-submodule names
    if name.startswith("_") or name in ("local", "supabase"):
        raise AttributeError(name)
    b = _backend()
    if hasattr(b, name):
        return getattr(b, name)
    raise AttributeError(f"storage backend has no attribute '{name}'")
