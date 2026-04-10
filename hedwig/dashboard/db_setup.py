"""
Supabase table auto-setup — creates all required tables via SQL REST endpoint.
"""
from __future__ import annotations

import httpx

from hedwig.storage.supabase import SCHEMA_SQL


async def create_tables(url: str, key: str) -> tuple[bool, str]:
    """Execute SCHEMA_SQL against Supabase via pg-meta or REST endpoint.

    Note: Supabase REST doesn't allow arbitrary SQL via anon key.
    This function attempts best-effort via the pg-meta endpoint if available,
    or returns instructions for manual setup.
    """
    if not url or not key:
        return False, "Supabase URL and key required"

    # Try the pg-meta API (requires service_role key)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{url.rstrip('/')}/rest/v1/rpc/exec_sql",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"sql": SCHEMA_SQL},
            )
            if resp.status_code in (200, 204):
                return True, "Tables created successfully"
    except Exception:
        pass

    # Fallback: provide the SQL for manual execution
    return False, "auto_setup_unavailable"


def get_schema_sql() -> str:
    """Return the SQL schema for manual execution."""
    return SCHEMA_SQL
