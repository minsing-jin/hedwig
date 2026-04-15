"""
Quickstart — zero-config local mode.

Goal: from `pip install` to receiving signals in under 3 minutes with
only an OpenAI key required. No Supabase, no Slack, no Discord setup.

Flow:
  1. Prompt for OpenAI key (save to .env)
  2. Prompt for interest in one sentence
  3. Auto-generate criteria.yaml
  4. Initialize SQLite DB
  5. Run dry collection to verify sources
  6. Start dashboard + open browser

Run: python -m hedwig --quickstart
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CRITERIA_PATH = PROJECT_ROOT / "criteria.yaml"


GREETING = """
╭──────────────────────────────────────────────────╮
│  🦉 Hedwig Quickstart                            │
│                                                  │
│  Zero-config local mode. SQLite storage.         │
│  No Supabase, Slack, or Discord required.        │
│  Only needs an OpenAI API key.                   │
╰──────────────────────────────────────────────────╯
"""


def _read_env() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    result = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip()
    return result


def _write_env(values: dict[str, str]):
    existing = _read_env()
    existing.update({k: v for k, v in values.items() if v})
    lines = ["# Hedwig quickstart configuration", "HEDWIG_STORAGE=sqlite", ""]
    for k, v in existing.items():
        if k == "HEDWIG_STORAGE":
            continue
        lines.append(f"{k}={v}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


def _prompt_openai_key(existing: dict[str, str]) -> str:
    current = existing.get("OPENAI_API_KEY", "")
    if current and current.startswith("sk-"):
        print(f"✓ OPENAI_API_KEY already set (ending ...{current[-6:]})")
        try:
            ans = input("  Use existing? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans in ("", "y", "yes"):
            return current

    print("")
    print("Step 1: OpenAI API key")
    print("  Get one at https://platform.openai.com/api-keys")
    try:
        key = input("  OPENAI_API_KEY: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)

    if not key.startswith("sk-"):
        print("  ⚠️  Warning: doesn't start with sk-. Saving anyway.")
    return key


def _prompt_interest() -> str:
    print("")
    print("Step 2: What AI signals are you interested in?")
    print("  Example: 'AI agent frameworks, LLM tooling, and new ML papers'")
    try:
        interest = input("  Interest (one sentence): ").strip()
    except (EOFError, KeyboardInterrupt):
        interest = ""
    if not interest:
        interest = "AI agents, LLM tooling, and research papers"
        print(f"  Using default: {interest}")
    return interest


def _generate_criteria(interest: str) -> dict:
    """Generate a minimal but useful criteria.yaml from a single interest sentence."""
    return {
        "identity": {
            "role": "AI builder",
            "focus": [interest],
        },
        "signal_preferences": {
            "care_about": [
                interest,
                "Real adoption signals (not hype)",
                "Practical applicability of papers",
                "New tool releases with benchmarks",
            ],
            "ignore": [
                "Pure marketing fluff",
                "Unsubstantiated predictions",
                "Repeated old news",
                "Brand-driven hype without substance",
            ],
        },
        "urgency_rules": {
            "alert": [
                "Major model release or significant update",
                "Breaking API change affecting developers",
                "Critical security issue",
            ],
            "digest": [
                "Interesting technical discussion",
                "Emerging trend with multiple signals",
                "Useful new tool or library",
            ],
            "skip": [
                "Opinion without data",
                "Hype-driven speculation",
            ],
        },
        "context": {
            "interests": [interest],
        },
        "metadata": {
            "generated_by": "quickstart",
            "source": "single-sentence interest",
        },
    }


def _save_criteria(data: dict):
    with open(CRITERIA_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def _init_db():
    from hedwig.storage import local as local_storage
    local_storage.init_db()
    db_path = local_storage._db_path()
    print(f"✓ SQLite DB initialized: {db_path}")


async def _dry_test():
    """Quick source check — just list registered plugins."""
    from hedwig.sources import get_registered_sources
    sources = get_registered_sources()
    print(f"✓ {len(sources)} source plugins ready")


def _start_dashboard_and_open():
    port = 8765
    print("")
    print(f"🚀 Starting dashboard at http://127.0.0.1:{port}")
    print("   Ctrl+C to stop.")
    print("")

    def open_browser():
        time.sleep(2.0)
        webbrowser.open(f"http://127.0.0.1:{port}")

    threading.Thread(target=open_browser, daemon=True).start()

    from hedwig.dashboard.app import run as run_dashboard
    run_dashboard(host="127.0.0.1", port=port, saas=False)


def run_quickstart():
    print(GREETING)
    existing = _read_env()

    # Step 1: OpenAI key
    openai_key = _prompt_openai_key(existing)

    # Step 2: Interest
    if CRITERIA_PATH.exists() and existing.get("HEDWIG_STORAGE") == "sqlite":
        print("")
        print(f"✓ criteria.yaml already exists at {CRITERIA_PATH}")
        interest = None
    else:
        interest = _prompt_interest()

    # Step 3: Save .env
    _write_env({
        "OPENAI_API_KEY": openai_key,
        "HEDWIG_STORAGE": "sqlite",
    })
    print(f"✓ .env saved: {ENV_PATH}")

    # Step 4: Generate criteria if needed
    if interest is not None:
        criteria = _generate_criteria(interest)
        _save_criteria(criteria)
        print(f"✓ criteria.yaml generated: {CRITERIA_PATH}")

    # Step 5: Initialize DB
    os.environ["OPENAI_API_KEY"] = openai_key
    os.environ["HEDWIG_STORAGE"] = "sqlite"
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_KEY", None)
    _init_db()

    # Step 6: Source check
    asyncio.run(_dry_test())

    # Step 7: Start dashboard + open browser
    print("")
    print("━" * 50)
    print("Setup complete. Starting dashboard…")
    print("━" * 50)
    _start_dashboard_and_open()


if __name__ == "__main__":
    run_quickstart()
