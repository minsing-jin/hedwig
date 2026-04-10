"""
API key validator — test keys against real endpoints.
"""
from __future__ import annotations

import httpx


async def test_openai(key: str) -> tuple[bool, str]:
    if not key or not key.startswith("sk-"):
        return False, "Invalid format (should start with sk-)"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"},
            )
            if resp.status_code == 200:
                models = resp.json().get("data", [])
                return True, f"OK ({len(models)} models accessible)"
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Connection error: {e}"


async def test_supabase(url: str, key: str) -> tuple[bool, str]:
    if not url or not key:
        return False, "URL and key required"
    if not url.startswith("https://"):
        return False, "URL should start with https://"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{url.rstrip('/')}/rest/v1/",
                headers={"apikey": key, "Authorization": f"Bearer {key}"},
            )
            if resp.status_code in (200, 404):  # 404 is fine - means API is reachable
                return True, "OK (Supabase reachable)"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Connection error: {e}"


async def test_slack_webhook(url: str) -> tuple[bool, str]:
    if not url:
        return False, "URL required"
    if not url.startswith("https://hooks.slack.com/"):
        return False, "Should start with https://hooks.slack.com/"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={"text": "🦉 Hedwig test message — ignore."},
            )
            if resp.status_code == 200 and resp.text == "ok":
                return True, "OK (test message sent)"
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
    except Exception as e:
        return False, f"Connection error: {e}"


async def test_discord_webhook(url: str) -> tuple[bool, str]:
    if not url:
        return False, "URL required"
    if "discord.com/api/webhooks" not in url:
        return False, "Should contain discord.com/api/webhooks"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                url,
                json={"content": "🦉 Hedwig test message — ignore."},
            )
            if resp.status_code in (200, 204):
                return True, "OK (test message sent)"
            return False, f"HTTP {resp.status_code}"
    except Exception as e:
        return False, f"Connection error: {e}"


async def test_all(values: dict[str, str]) -> dict[str, tuple[bool, str]]:
    """Test all provided keys. Returns dict of key_name → (ok, message)."""
    results: dict[str, tuple[bool, str]] = {}

    if values.get("OPENAI_API_KEY"):
        results["OPENAI_API_KEY"] = await test_openai(values["OPENAI_API_KEY"])

    if values.get("SUPABASE_URL") and values.get("SUPABASE_KEY"):
        results["SUPABASE"] = await test_supabase(
            values["SUPABASE_URL"], values["SUPABASE_KEY"]
        )

    for key in ("SLACK_WEBHOOK_ALERTS", "SLACK_WEBHOOK_DAILY"):
        if values.get(key):
            results[key] = await test_slack_webhook(values[key])

    for key in ("DISCORD_WEBHOOK_ALERTS", "DISCORD_WEBHOOK_DAILY", "DISCORD_WEBHOOK_WEEKLY"):
        if values.get(key):
            results[key] = await test_discord_webhook(values[key])

    return results
