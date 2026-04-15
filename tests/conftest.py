from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _force_supabase_backend(monkeypatch):
    """Existing tests monkey-patch hedwig.storage.supabase attributes directly.

    The storage dispatcher routes to local SQLite when no Supabase credentials
    are set. Force the dispatcher to route to supabase for tests so their
    monkey-patches actually intercept the calls.
    """
    monkeypatch.setenv("HEDWIG_STORAGE", "supabase")
