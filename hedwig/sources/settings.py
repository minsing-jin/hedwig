from __future__ import annotations

import json
from pathlib import Path

from hedwig.config import PROJECT_ROOT
from hedwig.sources.base import get_registered_sources

SOURCE_SETTINGS_PATH = PROJECT_ROOT / "source_settings.json"


def load_source_settings(
    path: Path | None = None,
    registry: dict[str, object] | None = None,
) -> dict[str, bool]:
    """Load persisted source enablement flags, defaulting unknown state to enabled."""
    available = registry or get_registered_sources()
    enabled = {plugin_id: True for plugin_id in available}
    config_path = path or SOURCE_SETTINGS_PATH

    if not config_path.exists():
        return enabled

    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return enabled

    saved_sources = payload.get("sources", {})
    if not isinstance(saved_sources, dict):
        return enabled

    for plugin_id in enabled:
        if plugin_id in saved_sources:
            enabled[plugin_id] = bool(saved_sources[plugin_id])

    return enabled


def save_source_settings(
    enabled: dict[str, bool],
    path: Path | None = None,
) -> dict[str, dict[str, bool]]:
    """Persist source enablement flags to disk."""
    config_path = path or SOURCE_SETTINGS_PATH
    payload = {
        "sources": {
            plugin_id: bool(enabled[plugin_id])
            for plugin_id in sorted(enabled)
        }
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def filter_registered_sources(path: Path | None = None) -> dict[str, object]:
    """Return only the registered sources currently enabled in local settings."""
    registry = get_registered_sources()
    enabled = load_source_settings(path=path, registry=registry)
    return {
        plugin_id: cls
        for plugin_id, cls in registry.items()
        if enabled.get(plugin_id, True)
    }
