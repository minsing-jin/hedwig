from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import dotenv_values, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv()


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    return Path(value).expanduser() if value else default


CRITERIA_PATH = _path_from_env("HEDWIG_CRITERIA_PATH", PROJECT_ROOT / "criteria.yaml")
ALGORITHM_PATH = PROJECT_ROOT / "algorithm.yaml"
EVOLUTION_LOG_PATH = PROJECT_ROOT / "evolution_log.jsonl"
ALGORITHM_LOG_PATH = PROJECT_ROOT / "algorithm_log.jsonl"
USER_MEMORY_PATH = PROJECT_ROOT / "user_memory.jsonl"


_RUNTIME_CONFIG_DEFAULTS = {
    "OPENAI_API_KEY": "",
    "OPENAI_MODEL_FAST": "gpt-4o-mini",
    "OPENAI_MODEL_DEEP": "gpt-4o",
    "SLACK_WEBHOOK_ALERTS": "",
    "SLACK_WEBHOOK_DAILY": "",
    "SLACK_BOT_TOKEN": "",
    "DISCORD_WEBHOOK_ALERTS": "",
    "DISCORD_WEBHOOK_DAILY": "",
    "DISCORD_WEBHOOK_WEEKLY": "",
    "SMTP_HOST": "",
    "SMTP_PORT": "587",
    "SMTP_USER": "",
    "SMTP_PASS": "",
    "SMTP_FROM": "",
    "SUPABASE_URL": "",
    "SUPABASE_KEY": "",
    "REDDIT_CLIENT_ID": "",
    "REDDIT_CLIENT_SECRET": "",
    "EXA_API_KEY": "",
    "SCRAPECREATORS_API_KEY": "",
}


def _candidate_env_paths(env_path: Path | str | None = None) -> list[Path]:
    """Return likely local .env paths without requiring process env mutation."""
    paths: list[Path] = []
    if env_path is not None:
        paths.append(Path(env_path).expanduser())
    paths.extend([Path.cwd() / ".env", PROJECT_ROOT / ".env"])

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve() if path.exists() else path.absolute()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _load_persisted_env(env_path: Path | str | None = None) -> dict[str, str]:
    """Read persisted .env values directly; empty values are preserved."""
    values: dict[str, str] = {}
    for path in _candidate_env_paths(env_path):
        if not path.exists():
            continue
        parsed = dotenv_values(path)
        for key, value in parsed.items():
            if value is not None:
                values[key] = value
    return values


def _runtime_value(
    key: str,
    default: str = "",
    *,
    persisted: dict[str, str] | None = None,
    prefer_persisted: bool = False,
) -> str:
    persisted = persisted or {}
    if prefer_persisted and key in persisted:
        return persisted.get(key, "") or default

    env_value = os.getenv(key)
    if env_value:
        return env_value
    if key in persisted:
        return persisted.get(key, "") or default
    return default


def refresh_runtime_config(
    env_path: Path | str | None = None,
    *,
    prefer_persisted: bool = False,
    update_process_env: bool = False,
) -> dict[str, str]:
    """Refresh module-level runtime settings from process env and persisted .env.

    The dashboard setup flow writes OPENAI_API_KEY to the managed .env while the
    FastAPI process is already running. Refreshing these globals lets existing
    ``from hedwig.config import OPENAI_API_KEY`` call sites read the persisted
    setup value without requiring a process restart or an os.environ mutation.
    """
    persisted = _load_persisted_env(env_path)
    refreshed: dict[str, str] = {}
    for key, default in _RUNTIME_CONFIG_DEFAULTS.items():
        value = _runtime_value(
            key,
            default,
            persisted=persisted,
            prefer_persisted=prefer_persisted,
        )
        globals()[key] = value
        refreshed[key] = value
        if update_process_env:
            if value:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
    return refreshed


def load_criteria() -> dict:
    if not CRITERIA_PATH.exists():
        return {}
    with open(CRITERIA_PATH) as f:
        return yaml.safe_load(f) or {}


_ALGORITHM_VERSION_SEEDED = False


def load_algorithm_config() -> dict:
    """Load algorithm.yaml — user-owned recommendation algorithm definition.

    Peer to criteria.yaml. Defines the Hybrid Ensemble (retrieval + ranking)
    and Meta-Evolution settings. See docs/VISION_v3.md.

    Side effect: on first call with a non-empty algorithm.yaml, seed the
    ``algorithm_versions`` table with the baseline v1 so the Evolution
    timeline has an origin marker even before Meta-Evolution runs.
    """
    if not ALGORITHM_PATH.exists():
        return {}
    with open(ALGORITHM_PATH) as f:
        cfg = yaml.safe_load(f) or {}

    _seed_algorithm_version_once(cfg)
    return cfg


def _seed_algorithm_version_once(cfg: dict) -> None:
    global _ALGORITHM_VERSION_SEEDED
    if _ALGORITHM_VERSION_SEEDED or not cfg:
        return
    _ALGORITHM_VERSION_SEEDED = True
    try:
        from hedwig.storage import get_algorithm_history, save_algorithm_version
        if get_algorithm_history(limit=1):
            return
        save_algorithm_version(
            version=int(cfg.get("version", 1)),
            config=cfg,
            created_by="seed",
            origin=str(cfg.get("origin", "initial_default")),
        )
    except Exception:
        # Never let version-seeding failure block the pipeline
        pass


# Runtime settings
refresh_runtime_config()


def smtp_alerts_configured() -> bool:
    """SMTP is usable for alert delivery when host and sender are configured."""
    return bool(SMTP_HOST and SMTP_FROM)


def _alert_delivery_configured() -> bool:
    return bool(SLACK_WEBHOOK_ALERTS or DISCORD_WEBHOOK_ALERTS or smtp_alerts_configured())


def _daily_delivery_configured() -> bool:
    return bool(SLACK_WEBHOOK_DAILY or DISCORD_WEBHOOK_DAILY or smtp_alerts_configured())


def check_required_keys(mode: str = "full") -> list[str]:
    """Check which truly-required keys are missing.

    Only OPENAI_API_KEY is strictly required — it powers the LLM scorer,
    briefer, and evolution engine, all of which are the core value.

    Supabase and delivery (Slack/Discord/SMTP) are *optional*: without them,
    the pipeline still collects, scores, stores locally (SQLite), and shows
    results in the dashboard. Their absence is surfaced via warnings in
    ``check_optional_keys``, not as a hard failure.
    """
    missing = []
    if mode in ("full", "score", "evolve", "daily"):
        if not OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
    return missing


def check_optional_keys(mode: str = "full") -> list[str]:
    """Return a list of optional capability gaps for user-facing warnings."""
    gaps: list[str] = []
    if mode in ("full", "daily"):
        if not _alert_delivery_configured():
            gaps.append("alert delivery (set SLACK_WEBHOOK_ALERTS / DISCORD_WEBHOOK_ALERTS / SMTP_*)")
        if not _daily_delivery_configured():
            gaps.append("daily-brief delivery (set SLACK_WEBHOOK_DAILY / DISCORD_WEBHOOK_DAILY / SMTP_*)")
    return gaps
