"""Tests for the Hedwig source plugin registry.

Verifies that:
- At least 16 source plugins are registered
- Each source has required metadata (plugin_id, platform, display_name)
- All expected builtin sources are present
- The registry API (get_source, create_source) works correctly
"""

import pytest

from hedwig.sources import get_registered_sources, get_source, create_source
from hedwig.sources.base import Source


EXPECTED_SOURCES = [
    "arxiv",
    "bluesky",
    "geeknews",
    "hackernews",
    "instagram",
    "linkedin",
    "newsletter",
    "papers_with_code",
    "polymarket",
    "reddit",
    "semantic_scholar",
    "threads",
    "tiktok",
    "twitter",
    "web_search",
    "youtube",
]


def test_registry_contains_at_least_16_sources():
    """AC-10: Source plugin registry contains at least 16 sources."""
    sources = get_registered_sources()
    assert len(sources) >= 16, (
        f"Expected at least 16 registered sources, got {len(sources)}: "
        f"{sorted(sources.keys())}"
    )


def test_all_expected_sources_registered():
    """Every expected builtin source is present in the registry."""
    sources = get_registered_sources()
    for name in EXPECTED_SOURCES:
        assert name in sources, f"Missing expected source: {name}"


def test_each_source_is_subclass_of_base():
    """Every registered source inherits from Source."""
    for plugin_id, cls in get_registered_sources().items():
        assert issubclass(cls, Source), (
            f"Source {plugin_id} ({cls}) is not a subclass of Source"
        )


def test_each_source_has_metadata():
    """Every registered source exposes valid metadata."""
    for plugin_id, cls in get_registered_sources().items():
        meta = cls.metadata()
        assert "plugin_id" in meta, f"{plugin_id} metadata missing plugin_id"
        assert "platform" in meta, f"{plugin_id} metadata missing platform"
        assert "display_name" in meta, f"{plugin_id} metadata missing display_name"
        assert "plugin_type" in meta, f"{plugin_id} metadata missing plugin_type"
        assert "fetch_method" in meta, f"{plugin_id} metadata missing fetch_method"


def test_get_source_returns_correct_class():
    """get_source() returns the right class for known plugin IDs."""
    for name in EXPECTED_SOURCES:
        cls = get_source(name)
        assert cls is not None, f"get_source('{name}') returned None"
        assert issubclass(cls, Source)


def test_get_source_returns_none_for_unknown():
    """get_source() returns None for unregistered plugin IDs."""
    assert get_source("nonexistent_source_xyz") is None


def test_create_source_returns_instance():
    """create_source() returns a Source instance for known plugin IDs."""
    for name in EXPECTED_SOURCES:
        instance = create_source(name)
        assert instance is not None, f"create_source('{name}') returned None"
        assert isinstance(instance, Source)


def test_create_source_returns_none_for_unknown():
    """create_source() returns None for unregistered plugin IDs."""
    assert create_source("nonexistent_source_xyz") is None


def test_each_source_has_fetch_method():
    """Every registered source has a callable fetch() method."""
    for plugin_id, cls in get_registered_sources().items():
        instance = cls()
        assert hasattr(instance, "fetch"), f"{plugin_id} missing fetch() method"
        assert callable(instance.fetch), f"{plugin_id}.fetch is not callable"


def test_source_presets_include_registry_default_and_known_setup_choices(tmp_path):
    """Setup source presets are render-ready and keep registry defaults first."""
    from hedwig.sources import settings as source_settings

    presets = source_settings.get_source_presets(path=tmp_path / "missing.json")
    preset_ids = [preset["id"] for preset in presets]

    assert preset_ids[0] == source_settings.DEFAULT_SOURCE_PRESET
    assert "local_ai_builder" in preset_ids
    assert "research_papers" in preset_ids
    assert "builder_news" in preset_ids
    assert "social_video" in preset_ids
    assert "all_sources" in preset_ids
    assert all(preset["enabled_count"] > 0 for preset in presets)
    assert all(
        preset["total_count"] == len(get_registered_sources())
        for preset in presets
    )


def test_source_preset_enablement_preserves_source_settings_default(tmp_path):
    """The default preset derives from persisted source_settings."""
    from hedwig.sources import settings as source_settings

    path = tmp_path / "source_settings.json"
    source_settings.save_source_settings(
        {
            plugin_id: plugin_id != "arxiv"
            for plugin_id in get_registered_sources()
        },
        path=path,
    )

    enabled = source_settings.enabled_sources_for_preset(
        "registry_default",
        path=path,
    )

    assert enabled["arxiv"] is False
    assert enabled["hackernews"] is True


def test_initialize_source_settings_from_registry_creates_first_run_defaults(tmp_path):
    """First-run setup persists the registry default enabled source map."""
    from hedwig.sources import settings as source_settings

    registry = get_registered_sources()
    path = tmp_path / "source_settings.json"

    state = source_settings.initialize_source_settings_from_registry(
        path=path,
        registry=registry,
    )

    assert state["created"] is True
    assert state["path"] == str(path)
    assert set(state["sources"]) == set(registry)
    assert all(state["sources"].values())

    saved = source_settings.load_source_settings(path=path, registry=registry)
    assert saved == state["sources"]


def test_initialize_source_settings_from_registry_preserves_existing_defaults(tmp_path):
    """Default initialization is first-run only and does not erase user toggles."""
    from hedwig.sources import settings as source_settings

    registry = get_registered_sources()
    path = tmp_path / "source_settings.json"
    source_settings.save_source_settings(
        {
            plugin_id: plugin_id != "arxiv"
            for plugin_id in registry
        },
        path=path,
    )

    state = source_settings.initialize_source_settings_from_registry(
        path=path,
        registry=registry,
    )

    assert state["created"] is False
    assert state["sources"]["arxiv"] is False
    assert state["sources"]["hackernews"] is True


def test_research_source_preset_maps_to_research_plugins_only():
    """Preset selection returns a full source_settings-compatible boolean map."""
    from hedwig.sources import settings as source_settings

    enabled = source_settings.enabled_sources_for_preset("research_papers")
    active = {
        plugin_id
        for plugin_id, is_enabled in enabled.items()
        if is_enabled
    }

    assert active == {
        "arxiv",
        "arxiv_recsys",
        "papers_with_code",
        "semantic_scholar",
    }
    assert enabled["hackernews"] is False
    assert enabled["reddit"] is False


@pytest.mark.asyncio
async def test_collect_all_defaults_to_enabled_source_settings(tmp_path, monkeypatch):
    """First-run collection uses enabled registry/source_settings sources by default."""
    from hedwig import main as main_mod
    from hedwig.sources import settings as source_settings

    calls: list[str] = []

    class EnabledSource:
        async def fetch(self):
            calls.append("enabled")
            return ["enabled-post"]

    class DisabledSource:
        async def fetch(self):
            calls.append("disabled")
            return ["disabled-post"]

    registry = {
        "enabled": EnabledSource,
        "disabled": DisabledSource,
    }
    settings_path = tmp_path / "source_settings.json"
    source_settings.save_source_settings(
        {"enabled": True, "disabled": False},
        path=settings_path,
    )
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", settings_path)
    monkeypatch.setattr(source_settings, "get_registered_sources", lambda: registry)

    posts = await main_mod.collect_all()

    assert posts == ["enabled-post"]
    assert calls == ["enabled"]


@pytest.mark.asyncio
async def test_collect_all_can_include_all_registered_sources(monkeypatch):
    """Explicit collection override preserves the existing all-source behavior."""
    import hedwig.sources as sources_mod
    from hedwig import main as main_mod

    calls: list[str] = []

    class EnabledSource:
        async def fetch(self):
            calls.append("enabled")
            return ["enabled-post"]

    class DisabledSource:
        async def fetch(self):
            calls.append("disabled")
            return ["disabled-post"]

    monkeypatch.setattr(
        sources_mod,
        "get_registered_sources",
        lambda: {
            "enabled": EnabledSource,
            "disabled": DisabledSource,
        },
    )

    posts = await main_mod.collect_all(enabled_only=False)

    assert posts == ["enabled-post", "disabled-post"]
    assert calls == ["enabled", "disabled"]
