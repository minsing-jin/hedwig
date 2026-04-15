"""
Storage dispatcher — picks SQLite (local) or Supabase based on env.

Default: SQLite local file at ~/.hedwig/hedwig.db (zero-config)
Override: set SUPABASE_URL + SUPABASE_KEY to use Supabase instead.
Force:    set HEDWIG_STORAGE=sqlite|supabase

All public functions mirror the same signature whichever backend is active.
"""
from __future__ import annotations

import importlib
import os
from typing import Any


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


def __getattr__(name: str) -> Any:
    # Only proxy non-dunder, non-submodule names
    if name.startswith("_") or name in ("local", "supabase"):
        raise AttributeError(name)
    b = _backend()
    if hasattr(b, name):
        return getattr(b, name)
    raise AttributeError(f"storage backend has no attribute '{name}'")
