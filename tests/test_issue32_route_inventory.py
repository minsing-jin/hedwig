from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "hedwig" / "dashboard" / "app.py"
BASE_TEMPLATE_PATH = ROOT / "hedwig" / "dashboard" / "templates" / "base.html"
INVENTORY_PATH = ROOT / "docs" / "issue32-user-facing-route-inventory.md"
TEMPLATES_DIR = ROOT / "hedwig" / "dashboard" / "templates"


def _html_page_routes_from_app() -> dict[str, str]:
    source = APP_PATH.read_text(encoding="utf-8")
    routes: dict[str, str] = {}
    blocks = re.split(r"(?=    @app\.)", source)
    for block in blocks:
        decorator = re.match(
            r"    @app\.get\(\"([^\"]+)\"([^\n]*)\)",
            block,
        )
        if not decorator:
            continue

        route, decorator_tail = decorator.groups()
        before_next_route = block.split("\n    @app.", 1)[0]
        if (
            "HTMLResponse" not in decorator_tail
            and "TemplateResponse" not in before_next_route
        ):
            continue

        template_match = re.search(
            r"TemplateResponse\(\s*(?:request,\s*)?\"([^\"]+)\"",
            before_next_route,
        )
        routes[route] = template_match.group(1) if template_match else ""
    return routes


def _inventory_page_routes() -> dict[str, list[str]]:
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    rows: dict[str, list[str]] = {}
    for line in inventory.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        route = cells[0].strip("`")
        if not route.startswith("/"):
            continue
        rows[route] = cells
    return rows


def _documented_route_refs() -> set[str]:
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"`(/[^`]*)`", inventory))


def _normalize_internal_ref(value: str) -> str | None:
    value = value.strip()
    if (
        not value.startswith("/")
        or value.startswith(("/static/", "/assets/"))
        or "{{" in value
        or "${" in value
    ):
        return None
    return re.split(r"[?#]", value, maxsplit=1)[0]


def _literal_internal_template_refs() -> set[str]:
    refs: set[str] = set()
    attr_pattern = re.compile(
        r"""(?:href|action|hx-get|hx-post)=["']([^"']+)["']"""
    )
    js_redirect_pattern = re.compile(
        r"""window\.location\.href\s*=\s*["']([^"']+)["']"""
    )
    for template_path in TEMPLATES_DIR.glob("*.html"):
        source = template_path.read_text(encoding="utf-8")
        for match in [*attr_pattern.findall(source), *js_redirect_pattern.findall(source)]:
            normalized = _normalize_internal_ref(match)
            if normalized:
                refs.add(normalized)
    return refs


def _base_header_links() -> dict[str, str]:
    source = BASE_TEMPLATE_PATH.read_text(encoding="utf-8")
    nav_match = re.search(
        r"<div class=\"nav-links\">(?P<body>.*?)</div>",
        source,
        flags=re.S,
    )
    assert nav_match is not None
    links: dict[str, str] = {}
    for href, label_html in re.findall(r"<a href=\"([^\"]+)\"[^>]*>(.*?)</a>", nav_match.group("body")):
        label = re.sub(r"<[^>]+>", "", label_html).strip()
        links[href] = label
    return links


def _route_path_is_registered(path: str, registered_route_paths: set[str]) -> bool:
    if path in registered_route_paths:
        return True
    return any(
        "{" in route_path
        and re.fullmatch(re.sub(r"\{[^/]+\}", r"[^/]+", route_path), path)
        for route_path in registered_route_paths
    )


def _static_server_redirects() -> set[tuple[str, str]]:
    source = APP_PATH.read_text(encoding="utf-8")
    redirects: set[tuple[str, str]] = set()
    for block in re.split(r"(?=    @app\.)", source):
        decorator = re.match(r"    @app\.(?:get|post)\(\"([^\"]+)\"", block)
        if not decorator:
            continue
        route = decorator.group(1)
        for target in re.findall(r"RedirectResponse\(url=\"([^\"]+)\"", block):
            redirects.add((route, target))
    return redirects


def _markdown_section(title: str) -> str:
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    marker = f"## {title}"
    assert marker in inventory
    return inventory.split(marker, 1)[1].split("\n## ", 1)[0]


def test_issue32_inventory_covers_every_dashboard_html_page_route():
    app_routes = _html_page_routes_from_app()
    inventory_routes = _inventory_page_routes()

    missing = sorted(set(app_routes) - set(inventory_routes))
    assert missing == []

    extra = sorted(set(inventory_routes) - set(app_routes))
    allowed_non_page_references = {
        "/algorithm/export",
        "/algorithm/import",
        "/algorithm/import/dry-run",
        "/dashboard/stats",
        "/health",
        "/policy/natural-language",
        "/policy/personal-algorithm",
        "/policy/rollback",
        "/settings/model-backend/save",
        "/setup/source-settings/save",
        "/signals/{signal_id}/trace",
    }
    assert set(extra) <= allowed_non_page_references

    for route, template in app_routes.items():
        row = inventory_routes[route]
        assert template in row[1]
        assert row[2] and row[2] != "Primary visible features"
        assert row[3] and row[3] != "Setup layering / preservation note"


def test_issue32_inventory_covers_global_header_navigation():
    header_links = _base_header_links()
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    header_section = inventory.split("## Global Header Navigation", 1)[1].split(
        "\n## ",
        1,
    )[0]

    expected_links = {
        "/chat",
        "/demo",
        "/",
        "/ambient/pwa",
        "/feed",
        "/brief",
        "/profile",
        "/signals",
        "/evolution",
        "/sandbox",
        "/meta",
        "/status",
        "/sovereignty",
        "/sources",
        "/settings",
        "/criteria",
        "/setup",
        "/onboarding",
        "/onboarding/auto",
        "/admin",
    }
    assert set(header_links) == expected_links

    missing_from_inventory = [
        href for href in header_links if f"`{href}`" not in header_section
    ]
    assert missing_from_inventory == []


def test_issue32_preserved_global_navigation_routes_are_reachable(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    header_links = _base_header_links()
    registered_route_paths = {getattr(route, "path", "") for route in app.routes}

    missing_registered_paths = [
        path
        for path in header_links
        if not _route_path_is_registered(path, registered_route_paths)
    ]
    assert missing_registered_paths == []

    expected_statuses = {
        "/": {303},
        "/ambient/pwa": {200},
        "/feed": {200},
        "/brief": {200},
        "/profile": {200},
        "/signals": {200},
        "/evolution": {200},
        "/sandbox": {200},
        "/meta": {200},
        "/status": {200},
        "/sovereignty": {200},
        "/sources": {200},
        "/settings": {200},
        "/criteria": {200},
        "/setup": {200},
        "/onboarding": {200},
        "/onboarding/auto": {200},
        "/admin": {200},
        "/chat": {200},
        "/demo": {200},
    }

    assert set(expected_statuses) == set(header_links)
    for path, allowed_statuses in expected_statuses.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code in allowed_statuses, path
        if path == "/":
            assert response.headers["location"] == "/setup"
        else:
            assert "Hedwig" in response.text


def test_issue32_inventory_covers_literal_internal_template_links_and_forms():
    documented = {_normalize_internal_ref(ref) or ref for ref in _documented_route_refs()}
    template_refs = _literal_internal_template_refs()

    missing = sorted(template_refs - documented)
    assert missing == []


def test_issue32_inventory_covers_static_server_redirects():
    documented = INVENTORY_PATH.read_text(encoding="utf-8")
    redirects = _static_server_redirects()

    assert redirects == {
        ("/", "/setup"),
        ("/settings/save", "/settings?saved=1"),
        ("/settings/model-backend/save", "/settings?saved=model-backend"),
    }
    for source, target in redirects:
        assert f"| `{source}` | `{target}` |" in documented


def test_issue32_inventory_covers_setup_onboarding_empty_and_first_run_affordances():
    section = _markdown_section("Setup/Onboarding First-Run UX Inventory")

    expected_surfaces = {
        "`setup.html` essential card": [
            "OPENAI_API_KEY",
            "needs OpenAI key",
            "first_run_status=not_started",
            "HEDWIG_STORAGE=sqlite",
            "POST /setup/required/save",
            "POST /setup/one-shot",
        ],
        "`setup.html` criteria card": [
            "interest_text",
            "AI agents, LLM tooling, and research papers",
            "/criteria",
            "/onboarding",
            "/chat",
        ],
        "`setup.html` source card": [
            "registry/source_settings",
            "POST /setup/source-settings/save",
            "/sources",
            "/settings",
        ],
        "`setup.html` progress/completion cards": [
            "ready_to_run",
            "waiting_for_feed_items",
            "feed_items_available=false",
            "GET /setup/one-shot/status",
            "redirect_target=/feed",
        ],
        "`setup.html` advanced details": [
            "Supabase",
            "delivery",
            "source/API keys",
            "model/backend",
            "export/import",
            "/algorithm/import/dry-run",
            "/sovereignty",
        ],
        "`onboarding.html`": [
            "Socratic interview",
            "click Start",
            "POST /onboarding/start",
            "POST /onboarding/respond",
        ],
        "`onboarding_auto.html`": [
            "SNS handles",
            "Loading",
            "/onboarding/auto/infer",
            "/criteria",
        ],
        "`feed.html`": [
            "Empty feed",
            "waiting for first feed items",
            "no enabled sources",
            "/feed/api",
            "/events/beacon",
        ],
        "`profile.html`": [
            "Missing criteria",
            "/algorithm/export",
            "/algorithm/import/dry-run",
            "/sovereignty",
        ],
        "`status.html`": [
            "Missing source env keys",
            "zero recent source counts",
            "/setup",
            "/meta",
        ],
    }

    for surface, required_terms in expected_surfaces.items():
        assert f"| {surface} |" in section
        for term in required_terms:
            assert term in section

    setup_template = (TEMPLATES_DIR / "setup.html").read_text(encoding="utf-8")
    assert "first_run_status" in setup_template
    assert "setup_state.feed_items_available" in setup_template
    assert "data-advanced-setup-entrypoint" in setup_template

    feed_template = (TEMPLATES_DIR / "feed.html").read_text(encoding="utf-8")
    assert "Waiting for first feed items" in feed_template
    assert "Feed is empty because no sources are enabled" in feed_template


def test_issue32_inventory_documents_manual_verification_for_preserved_paths():
    section = _markdown_section("Manual Verification Checklist For Preserved Paths")

    assert "Automated tests cover the route inventory" in section
    assert "HEDWIG_DB_PATH=/tmp/hedwig-issue32-manual.db" in section
    assert "python -m hedwig --dashboard --port 8765" in section
    assert "python -m hedwig --dashboard --saas --port 8766" in section

    expected_paths = {
        "Setup progressive-disclosure shell (`/setup`)": [
            "Advanced setup sections are collapsed",
            "Supabase, delivery, source/API keys",
        ],
        "Setup one-shot progress and feed handoff (`/setup`)": [
            "AI agents, LLM tooling, and research papers",
            "/feed",
        ],
        "Global dashboard navigation after setup": [
            "/chat",
            "/feed",
            "/profile",
            "/status",
            "/settings",
            "/sources",
            "/criteria",
            "/onboarding",
            "/onboarding/auto",
            "/brief",
            "/ambient/pwa",
            "/evolution",
            "/meta",
            "/sandbox",
            "/sovereignty",
            "/admin",
            "/demo",
        ],
        "Natural-language steering paths": [
            "/chat",
            "/criteria",
            "/onboarding",
            "/onboarding/auto",
        ],
        "Source and backend power controls": [
            "/sources",
            "/settings",
            "model/backend",
        ],
        "Delivery surfaces": [
            "/feed",
            "/brief",
            "/ambient/pwa",
            "Slack, Discord, and SMTP",
        ],
        "Ownership, export/import, and sovereignty": [
            "/profile",
            "/sovereignty",
            "/algorithm/export",
        ],
        "Evolution and experimentation tools": [
            "/evolution",
            "/meta",
            "/sandbox",
        ],
        "SaaS/account/legal surfaces": [
            "/landing",
            "/signup",
            "/login",
            "/auth/callback",
            "/billing",
            "/invite",
            "/ko",
            "/zh",
            "/terms",
            "/privacy",
            "/about",
        ],
    }

    for path_group, required_terms in expected_paths.items():
        assert f"| {path_group} |" in section
        for term in required_terms:
            assert term in section


if __name__ == "__main__":
    test_issue32_inventory_covers_every_dashboard_html_page_route()
    test_issue32_inventory_covers_global_header_navigation()
    test_issue32_inventory_covers_literal_internal_template_links_and_forms()
    test_issue32_inventory_covers_static_server_redirects()
    test_issue32_inventory_covers_setup_onboarding_empty_and_first_run_affordances()
    test_issue32_inventory_documents_manual_verification_for_preserved_paths()
