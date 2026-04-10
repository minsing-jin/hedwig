"""Tests for the Hedwig source plugin registry.

Verifies that:
- At least 16 source plugins are registered
- Each source has required metadata (plugin_id, platform, display_name)
- All expected builtin sources are present
- The registry API (get_source, create_source) works correctly
"""

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
