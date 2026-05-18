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
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
CRITERIA_PATH = PROJECT_ROOT / "criteria.yaml"
DEFAULT_INTEREST = "AI agents, LLM tooling, and research papers"


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
    interest = normalize_interest(interest)
    if interest == DEFAULT_INTEREST:
        print(f"  Using default: {interest}")
    return interest


def normalize_interest(interest: str | None) -> str:
    """Return the one-shot setup default when the user skips interest input."""
    value = " ".join((interest or "").split())
    return value or DEFAULT_INTEREST


def validate_generated_criteria(criteria: dict) -> dict:
    """Ensure quickstart/setup criteria can be safely persisted as criteria.yaml."""
    required_sections = (
        "identity",
        "signal_preferences",
        "urgency_rules",
        "context",
        "metadata",
    )
    missing = [
        section
        for section in required_sections
        if not isinstance(criteria.get(section), dict)
    ]
    if missing:
        raise ValueError(f"Generated criteria missing sections: {', '.join(missing)}")

    list_paths = (
        ("identity", "focus"),
        ("signal_preferences", "care_about"),
        ("signal_preferences", "ignore"),
        ("urgency_rules", "alert"),
        ("urgency_rules", "digest"),
        ("urgency_rules", "skip"),
        ("context", "interests"),
    )
    for section, key in list_paths:
        values = criteria[section].get(key)
        if not isinstance(values, list) or not all(
            isinstance(item, str) and item.strip() for item in values
        ):
            raise ValueError(
                f"Generated criteria field {section}.{key} "
                "must be a non-empty string list"
            )

    role = criteria["identity"].get("role")
    if not isinstance(role, str) or not role.strip():
        raise ValueError(
            "Generated criteria field identity.role must be a non-empty string"
        )
    if criteria["metadata"].get("generated_by") != "quickstart":
        raise ValueError("Generated criteria metadata.generated_by must remain quickstart")
    return criteria


def generate_criteria_from_interest(interest: str | None) -> dict:
    """Generate a minimal but useful criteria.yaml from a single interest sentence."""
    interest = normalize_interest(interest)
    criteria = {
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
    return validate_generated_criteria(criteria)


def persist_generated_criteria(criteria: dict, path: Path | None = None) -> Path:
    """Persist generated setup criteria to the project criteria.yaml path."""
    criteria_path = path or CRITERIA_PATH
    criteria_path.parent.mkdir(parents=True, exist_ok=True)
    criteria_path.write_text(
        yaml.safe_dump(
            validate_generated_criteria(criteria),
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return criteria_path


def persist_initial_profile(criteria: dict, interest: str | None, *, created_by: str = "quickstart") -> dict:
    """Seed the versioned profile and memory paths used by profile/feed startup."""
    normalized_interest = normalize_interest(interest)
    result = {
        "criteria_version": None,
        "criteria_version_persisted": False,
        "user_memory_persisted_db": False,
        "user_memory_persisted_jsonl": False,
    }

    try:
        from hedwig.models import CriteriaVersion
        from hedwig.storage import get_criteria_versions, save_criteria_version

        latest = get_criteria_versions(limit=1) or []
        latest_version = int(latest[0]["version"]) if latest else 0
        next_version = latest_version + 1
        result["criteria_version"] = next_version
        result["criteria_version_persisted"] = bool(
            save_criteria_version(
                CriteriaVersion(
                    version=next_version,
                    criteria=criteria,
                    created_by=created_by,
                    diff_from_previous=f"Initial {created_by} criteria profile.",
                )
            )
        )
    except Exception:
        result["criteria_version"] = None

    try:
        from hedwig import config as hedwig_config
        from hedwig.memory.store import MemoryStore
        from hedwig.models import UserMemory
        from hedwig.storage import save_user_memory

        now = datetime.utcnow()
        iso = now.isocalendar()
        memory = UserMemory(
            snapshot_week=f"{iso.year}-W{iso.week:02d}",
            confirmed_interests=[normalized_interest],
            rejected_topics=criteria.get("signal_preferences", {}).get("ignore", []) or [],
            taste_trajectory=(
                f"Initial {created_by} profile seeded from the quickstart "
                f"interest: {normalized_interest}"
            ),
            context={
                "source": created_by,
                "role": criteria.get("identity", {}).get("role", "AI builder"),
                "criteria_interests": criteria.get("context", {}).get("interests", []),
            },
            natural_language_feedback=[normalized_interest],
        )
        result["user_memory_persisted_db"] = bool(save_user_memory(memory))
        user_memory_path = hedwig_config.USER_MEMORY_PATH
        user_memory_path.parent.mkdir(parents=True, exist_ok=True)
        MemoryStore(path=user_memory_path).save_snapshot(memory)
        result["user_memory_persisted_jsonl"] = True
    except Exception:
        pass

    return result


def _generate_criteria(interest: str) -> dict:
    return generate_criteria_from_interest(interest)


def _save_criteria(data: dict):
    persist_generated_criteria(data)


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


def _init_source_settings():
    """Persist first-run source settings from the registered default source set."""
    from hedwig.sources import get_registered_sources
    from hedwig.sources import settings as source_settings

    registry = get_registered_sources()
    state = source_settings.initialize_source_settings_from_registry(registry=registry)
    action = "initialized" if state["created"] else "already configured"
    print(f"✓ source_settings.json {action}: {state['path']}")


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
    generated_criteria = None
    if interest is not None:
        generated_criteria = _generate_criteria(interest)
        _save_criteria(generated_criteria)
        print(f"✓ criteria.yaml generated: {CRITERIA_PATH}")

    # Step 5: Initialize DB
    os.environ["OPENAI_API_KEY"] = openai_key
    os.environ["HEDWIG_STORAGE"] = "sqlite"
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_KEY", None)
    _init_db()
    if generated_criteria is not None:
        persist_initial_profile(generated_criteria, interest)
    _init_source_settings()

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
