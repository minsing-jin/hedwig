"""Test hedwig.saas.oauth — verify 12 providers registered."""

from hedwig.saas.oauth import SUPPORTED_PROVIDERS, list_providers, get_provider_metadata


EXPECTED_PROVIDERS = {
    "google", "github", "twitter", "discord",
    "linkedin_oidc", "facebook", "apple", "azure",
    "spotify", "slack_oidc", "twitch", "notion",
}


def test_twelve_providers_registered():
    """SUPPORTED_PROVIDERS must contain exactly 12 entries."""
    assert len(SUPPORTED_PROVIDERS) == 12, (
        f"Expected 12 providers, got {len(SUPPORTED_PROVIDERS)}: "
        f"{sorted(SUPPORTED_PROVIDERS.keys())}"
    )


def test_expected_provider_ids_present():
    """All 12 expected provider IDs must be present."""
    assert set(SUPPORTED_PROVIDERS.keys()) == EXPECTED_PROVIDERS


def test_each_provider_has_required_metadata():
    """Every provider entry must have label, icon, and color."""
    for pid, meta in SUPPORTED_PROVIDERS.items():
        for key in ("label", "icon", "color"):
            assert key in meta, f"Provider '{pid}' missing '{key}'"
        assert meta["color"].startswith("#"), (
            f"Provider '{pid}' color should be a hex string"
        )


def test_list_providers_returns_all():
    """list_providers() returns a list of dicts with 'id' key."""
    providers = list_providers()
    assert len(providers) == 12
    ids = {p["id"] for p in providers}
    assert ids == EXPECTED_PROVIDERS


def test_get_provider_metadata_known():
    """get_provider_metadata returns dict for known provider."""
    meta = get_provider_metadata("google")
    assert meta is not None
    assert meta["label"] == "Google"


def test_get_provider_metadata_unknown():
    """get_provider_metadata returns None for unknown provider."""
    assert get_provider_metadata("myspace") is None
