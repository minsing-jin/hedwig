from __future__ import annotations

import json
from pathlib import Path

from hedwig.config import PROJECT_ROOT
from hedwig.sources.base import get_registered_sources

SOURCE_SETTINGS_PATH = PROJECT_ROOT / "source_settings.json"

SOURCE_PRESETS = {
    "registry_default": {
        "label": "Registry defaults",
        "description": (
            "Use the currently enabled source set from registry/source_settings. "
            "This is the one-shot setup default."
        ),
        "source_ids": None,
    },
    "local_ai_builder": {
        "label": "Local AI-builder signal mix",
        "description": (
            "Balanced first-run coverage for agents, LLM tooling, research, "
            "engineering news, and AI lab updates."
        ),
        "source_ids": (
            "ai_labs",
            "arxiv",
            "arxiv_recsys",
            "geeknews",
            "github_trending",
            "hackernews",
            "linkedin",
            "newsletter",
            "papers_with_code",
            "semantic_scholar",
            "twitter",
            "youtube",
        ),
    },
    "research_papers": {
        "label": "Research papers",
        "description": (
            "Paper-first setup for arXiv, recommender-system papers, "
            "Semantic Scholar, and daily paper curation."
        ),
        "source_ids": (
            "arxiv",
            "arxiv_recsys",
            "papers_with_code",
            "semantic_scholar",
        ),
    },
    "builder_news": {
        "label": "Builder news",
        "description": (
            "Engineering and product signals from GitHub, Hacker News, "
            "AI labs, newsletters, and technical blogs."
        ),
        "source_ids": (
            "ai_labs",
            "geeknews",
            "github_trending",
            "hackernews",
            "linkedin",
            "newsletter",
            "twitter",
        ),
    },
    "social_video": {
        "label": "Social and video",
        "description": (
            "Public social, community, and video discovery sources for "
            "broader algorithm exploration."
        ),
        "source_ids": (
            "bluesky",
            "instagram",
            "reddit",
            "threads",
            "tiktok",
            "youtube",
        ),
    },
    "all_sources": {
        "label": "All registered sources",
        "description": (
            "Enable every registered source plugin. Best for power users "
            "who will tune source settings later."
        ),
        "source_ids": "__all__",
    },
}

DEFAULT_SOURCE_PRESET = "registry_default"


def normalize_source_preset_id(preset_id: str | None) -> str:
    """Return a known setup source preset id."""
    normalized = (preset_id or DEFAULT_SOURCE_PRESET).strip()
    if normalized in SOURCE_PRESETS:
        return normalized
    return DEFAULT_SOURCE_PRESET


def load_source_settings(
    path: Path | None = None,
    registry: dict[str, object] | None = None,
) -> dict[str, bool]:
    """Load persisted source enablement flags, defaulting unknown state to enabled."""
    available = registry or get_registered_sources()
    enabled = default_enabled_source_settings(registry=available)
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


def default_enabled_source_settings(
    registry: dict[str, object] | None = None,
) -> dict[str, bool]:
    """Return the registry-defined default source enablement map."""
    available = registry or get_registered_sources()
    return {plugin_id: True for plugin_id in available}


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


def initialize_source_settings_from_registry(
    path: Path | None = None,
    registry: dict[str, object] | None = None,
    *,
    overwrite: bool = False,
) -> dict:
    """Create first-run source_settings from registry defaults.

    Existing source_settings are preserved unless ``overwrite`` is requested.
    """
    available = registry or get_registered_sources()
    config_path = path or SOURCE_SETTINGS_PATH
    if config_path.exists() and not overwrite:
        return {
            "created": False,
            "path": str(config_path),
            "sources": load_source_settings(path=config_path, registry=available),
        }

    payload = save_source_settings(
        default_enabled_source_settings(registry=available),
        path=config_path,
    )
    return {
        "created": True,
        "path": str(config_path),
        "sources": payload["sources"],
    }


def enabled_sources_for_preset(
    preset_id: str | None,
    path: Path | None = None,
    registry: dict[str, object] | None = None,
) -> dict[str, bool]:
    """Return source enablement for a setup preset.

    The default preset intentionally delegates to ``load_source_settings`` so
    first-run setup preserves the existing registry/source_settings default.
    """
    available = registry or get_registered_sources()
    normalized_preset = normalize_source_preset_id(preset_id)
    preset = SOURCE_PRESETS[normalized_preset]
    source_ids = preset.get("source_ids")

    if source_ids is None:
        return load_source_settings(path=path, registry=available)
    if source_ids == "__all__":
        return {plugin_id: True for plugin_id in available}

    selected = set(source_ids)
    return {
        plugin_id: plugin_id in selected
        for plugin_id in available
    }


def get_source_presets(
    path: Path | None = None,
    registry: dict[str, object] | None = None,
) -> list[dict]:
    """Return render-ready setup source preset definitions."""
    available = registry or get_registered_sources()
    total = len(available)
    presets = []

    for preset_id, preset in SOURCE_PRESETS.items():
        enabled = enabled_sources_for_preset(
            preset_id,
            path=path,
            registry=available,
        )
        enabled_source_ids = [
            plugin_id
            for plugin_id in sorted(available)
            if enabled.get(plugin_id, True)
        ]
        declared_ids = preset.get("source_ids")
        if declared_ids in (None, "__all__"):
            unavailable_source_ids: list[str] = []
        else:
            unavailable_source_ids = [
                plugin_id
                for plugin_id in declared_ids
                if plugin_id not in available
            ]

        presets.append(
            {
                "id": preset_id,
                "label": preset["label"],
                "description": preset["description"],
                "source_ids": enabled_source_ids,
                "preview_source_ids": enabled_source_ids[:8],
                "enabled_count": len(enabled_source_ids),
                "total_count": total,
                "unavailable_source_ids": unavailable_source_ids,
                "is_default": preset_id == DEFAULT_SOURCE_PRESET,
            }
        )

    return presets


def filter_registered_sources(path: Path | None = None) -> dict[str, object]:
    """Return only the registered sources currently enabled in local settings."""
    registry = get_registered_sources()
    enabled = load_source_settings(path=path, registry=registry)
    return {
        plugin_id: cls
        for plugin_id, cls in registry.items()
        if enabled.get(plugin_id, True)
    }
