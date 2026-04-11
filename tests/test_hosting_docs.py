"""Tests for the SaaS hosting guide."""

from __future__ import annotations

import pathlib


ROOT = pathlib.Path(__file__).resolve().parent.parent
HOSTING_DOC = ROOT / "docs" / "HOSTING.md"


def _read_hosting_doc() -> str:
    return HOSTING_DOC.read_text(encoding="utf-8")


def test_hosting_doc_exists():
    """docs/HOSTING.md must exist for deployment instructions."""
    assert HOSTING_DOC.is_file(), "docs/HOSTING.md is missing"


def test_hosting_doc_covers_core_services():
    """Hosting guide should cover the SaaS deployment stack."""
    content = _read_hosting_doc()
    for keyword in ("Railway", "Supabase", "Stripe", "Docker"):
        assert keyword in content, f"docs/HOSTING.md must mention {keyword}"


def test_hosting_doc_mentions_repo_deployment_files():
    """Hosting guide should point operators to the checked-in deployment files."""
    content = _read_hosting_doc()
    for filename in ("Procfile", "Dockerfile", "railway.toml", "nixpacks.toml"):
        assert filename in content, f"docs/HOSTING.md must mention {filename}"

    assert "python -m hedwig --dashboard --saas --port $PORT" in content
    assert "/landing" in content, "Hosting guide should mention the healthcheck route"


def test_hosting_doc_lists_required_env_vars():
    """Hosting guide should document the required deployment environment variables."""
    content = _read_hosting_doc()
    for env_var in (
        "OPERATOR_OPENAI_KEY",
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_PRO",
        "STRIPE_PRICE_TEAM",
    ):
        assert env_var in content, f"docs/HOSTING.md must document {env_var}"
