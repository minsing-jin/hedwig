from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "hedwig" / "dashboard" / "app.py"
BASE_TEMPLATE_PATH = ROOT / "hedwig" / "dashboard" / "templates" / "base.html"
INVENTORY_PATH = ROOT / "docs" / "issue32-user-facing-route-inventory.md"
ISSUE34_NAV_GROUPS_PATH = ROOT / "docs" / "issue34-dashboard-navigation-groups.md"
STYLE_PATH = ROOT / "hedwig" / "dashboard" / "static" / "style.css"
V3_STYLE_PATH = ROOT / "hedwig" / "dashboard" / "static" / "v3.css"
SETUP_TEMPLATE_PATH = ROOT / "hedwig" / "dashboard" / "templates" / "setup.html"
FEED_TEMPLATE_PATH = ROOT / "hedwig" / "dashboard" / "templates" / "feed.html"
BRIEF_TEMPLATE_PATH = ROOT / "hedwig" / "dashboard" / "templates" / "brief.html"


def _base_template() -> str:
    return BASE_TEMPLATE_PATH.read_text(encoding="utf-8")


def _dashboard_nav_body(source: str) -> str:
    nav_match = re.search(
        r'<div\s+class="nav-links"[^>]*>(?P<body>.*?)\n    </div>\n  </nav>',
        source,
        flags=re.S,
    )
    assert nav_match is not None
    return nav_match.group("body")


def _dashboard_left_rail_body(source: str) -> str:
    left_rail_match = re.search(
        r'<div class="nav-left-rail">(?P<body>[\s\S]*?)\n    </div>\n    <div\n      class="nav-links"',
        source,
    )
    assert left_rail_match is not None
    return left_rail_match.group("body")


def _dashboard_language_selector(source: str) -> tuple[str, str]:
    selector_match = re.search(
        r'<div\s+class="language-rail"(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</select>\s*</div>',
        source,
    )
    assert selector_match is not None
    return selector_match.group("attrs"), selector_match.group("body")


def _dashboard_nav_routes(source: str) -> set[str]:
    return set(re.findall(r'href="([^"]+)"', _dashboard_nav_body(source)))


def _dashboard_nav_labeled_routes(source: str) -> dict[str, str]:
    routes: dict[str, str] = {}
    for href, label_html in re.findall(
        r'<a\s+href="([^"]+)"[^>]*>(.*?)</a>',
        _dashboard_nav_body(source),
        flags=re.S,
    ):
        label = re.sub(r"<[^>]+>", "", label_html).strip()
        routes[href] = label
    return routes


def _dashboard_nav_details_blocks(source: str) -> list[str]:
    return re.findall(r"<details[\s\S]*?</details>", _dashboard_nav_body(source))


def _dashboard_nav_anchor_tags(source: str) -> list[str]:
    return re.findall(r"<a\s+[^>]*>[^<]+</a>", _dashboard_nav_body(source))


def _dashboard_primary_list_body(source: str) -> str:
    primary_match = re.search(
        r'<ul\s+class="nav-primary-list"[^>]*>(?P<body>.*?)</ul>',
        _dashboard_nav_body(source),
        flags=re.S,
    )
    assert primary_match is not None
    return primary_match.group("body")


def _dashboard_secondary_surface_body(source: str) -> str:
    secondary_match = re.search(
        r'<div\s+class="nav-secondary-surface"[^>]*>(?P<body>.*?)\n      </div>',
        _dashboard_nav_body(source),
        flags=re.S,
    )
    assert secondary_match is not None
    return secondary_match.group("body")


def _dashboard_overflow_menu_body(source: str) -> str:
    overflow_match = re.search(
        r'<details\s+class="nav-overflow nav-group"[^>]*>(?P<body>.*?)</details>',
        _dashboard_nav_body(source),
        flags=re.S,
    )
    assert overflow_match is not None
    return overflow_match.group("body")


def _assert_single_active_navigation_state(
    source: str,
    active_path: str,
    owning_group_attr: str | None = None,
) -> None:
    nav = _dashboard_nav_body(source)
    active_link = rf'<a href="{re.escape(active_path)}"[^>]* aria-current="page"'

    assert re.search(active_link, nav), active_path
    assert nav.count('aria-current="page"') == 1

    details_blocks = _dashboard_nav_details_blocks(source)
    current_blocks = [
        block for block in details_blocks if 'data-current-navigation="true"' in block
    ]

    if owning_group_attr is None:
        assert current_blocks == []
        assert "data-current-navigation" not in nav
        return

    assert len(current_blocks) == 1
    assert owning_group_attr in current_blocks[0]
    assert "open" in current_blocks[0]
    assert re.search(active_link, current_blocks[0]), active_path


def _data_route_group(source: str, attr_name: str) -> set[str]:
    match = re.search(rf'{attr_name}="([^"]+)"', source)
    assert match is not None
    return set(match.group(1).split())


def _data_route_groups(source: str, attr_name: str) -> set[str]:
    values = re.findall(rf'{attr_name}="([^"]+)"', source)
    assert values != []
    return {route for value in values for route in value.split()}


def _media_block(source: str, max_width: int) -> str:
    marker = f"@media (max-width: {max_width}px)"
    start = source.index(marker)
    next_media = source.find("@media", start + len(marker))
    return source[start:] if next_media == -1 else source[start:next_media]


def _dashboard_app_route_paths() -> set[str]:
    source = APP_PATH.read_text(encoding="utf-8")
    return set(
        re.findall(
            r'@app\.(?:get|post|delete|put|patch)\("([^"]+)"',
            source,
        )
    )


def _dashboard_html_page_routes_from_app() -> dict[str, str]:
    source = APP_PATH.read_text(encoding="utf-8")
    routes: dict[str, str] = {}
    blocks = re.split(r"(?=    @app\.)", source)
    for block in blocks:
        decorator = re.match(
            r'    @app\.get\("([^"]+)"([^\n]*)\)',
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
            r'TemplateResponse\(\s*(?:request,\s*)?"([^"]+)"',
            before_next_route,
        )
        routes[route] = template_match.group(1) if template_match else ""
    return routes


def _issue34_audited_html_routes() -> dict[str, list[str]]:
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")
    html_section = taxonomy.split("### HTML Surfaces", 1)[1].split("\n### ", 1)[0]
    rows: dict[str, list[str]] = {}
    for line in html_section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        route = cells[0].strip("`")
        if route.startswith("/"):
            rows[route] = cells
    return rows


def _issue34_audited_supporting_routes() -> set[str]:
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")
    supporting_section = taxonomy.split("### Supporting Endpoints", 1)[1].split(
        "\n## ",
        1,
    )[0]
    routes: set[str] = set()
    for line in supporting_section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0].startswith("`/"):
            routes.update(re.findall(r"`(/[^`]*)`", cells[0]))
    return routes


def _issue34_documented_route_refs() -> set[str]:
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")
    return set(re.findall(r"`(/[^`]*)`", taxonomy))


def _markdown_table_routes(section: str) -> set[str]:
    routes: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and cells[0].startswith("`/"):
            routes.add(cells[0].strip("`"))
    return routes


def _issue34_routes_moved_out_of_primary_map() -> dict[str, tuple[str, str]]:
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")
    moved_section = taxonomy.split(
        "### Routes Moved Out Of Primary Navigation",
        1,
    )[1].split("\n## ", 1)[0]
    moved_routes: dict[str, tuple[str, str]] = {}
    for line in moved_section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        moved_routes[cells[0].strip("`")] = (cells[1], cells[2])
    return moved_routes


def _assert_group_summary_label(
    source: str,
    aria_label: str,
    tier_key: str,
    title_key: str,
) -> None:
    assert re.search(
        rf'<summary[^>]*data-i18n-aria-label="{re.escape(title_key)}_label"'
        rf'[^>]*aria-label="{re.escape(aria_label)}"[^>]*>'
        rf'[\s\S]*?<span class="nav-group-kicker" data-i18n="{re.escape(tier_key)}">'
        rf'[^<]+</span>'
        rf'[\s\S]*?<span class="nav-group-title" data-i18n="{re.escape(title_key)}">'
        rf'[^<]+</span>',
        source,
    ), aria_label


def _issue32_preserved_dashboard_nav_routes() -> set[str]:
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    section = inventory.split("## Global Header Navigation", 1)[1].split(
        "\n## ",
        1,
    )[0]
    routes: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 2 or not cells[1].startswith("`/"):
            continue
        routes.add(cells[1].strip("`"))
    return routes


def _issue32_inventory_html_routes() -> set[str]:
    inventory = INVENTORY_PATH.read_text(encoding="utf-8")
    section = inventory.split("## HTML Pages", 1)[1].split("\n## ", 1)[0]
    return _markdown_table_routes(section)


def _issue34_inventory_nav_routes_for_shell() -> set[str]:
    routes = set(_issue32_inventory_html_routes())
    routes.remove("/ambient/{surface}")
    routes.add("/ambient/pwa")
    return routes


def _issue34_saas_inventory_routes() -> set[str]:
    return {
        "/landing",
        "/ko",
        "/zh",
        "/signup",
        "/login",
        "/auth/callback",
        "/billing",
        "/invite",
        "/terms",
        "/privacy",
        "/about",
    }


def _route_path_is_registered(path: str, registered_route_paths: set[str]) -> bool:
    if path in registered_route_paths:
        return True
    return any(
        "{" in route_path
        and re.fullmatch(re.sub(r"\{[^/]+\}", r"[^/]+", route_path), path)
        for route_path in registered_route_paths
    )


def _registered_html_page_routes(registered_route_paths: set[str]) -> set[str]:
    return {
        route
        for route in _dashboard_html_page_routes_from_app()
        if route in registered_route_paths
    }


def _visible_nav_path_for_route(route: str) -> str:
    if route == "/ambient/{surface}":
        return "/ambient/pwa"
    return route


def _assert_issue32_inventory_routes_reachable_from_nav(
    client: TestClient,
    *,
    shell_path: str,
    inventory_routes: set[str],
) -> None:
    registered_route_paths = {
        getattr(route, "path", "") for route in client.app.routes
    }
    visible_nav_routes = _dashboard_nav_routes(client.get(shell_path).text)

    concrete_routes = {
        _visible_nav_path_for_route(route) for route in inventory_routes
    }
    missing_nav_routes = sorted(concrete_routes - visible_nav_routes)
    assert missing_nav_routes == []

    missing_registered_paths = sorted(
        path
        for path in concrete_routes
        if not _route_path_is_registered(path, registered_route_paths)
    )
    assert missing_registered_paths == []

    for path in sorted(concrete_routes):
        response = client.get(path, follow_redirects=False)
        if path == "/":
            assert response.status_code == 303, path
            assert response.headers["location"] == "/setup"
            continue

        assert response.status_code == 200, path
        assert "<html" in response.text.lower(), path


def test_issue34_navigation_groups_routes_without_removing_existing_links():
    source = _base_template()

    assert 'data-dashboard-nav-grouped="true"' in source
    assert 'aria-label="Dashboard navigation"' in source
    assert 'data-primary-navigation="/setup /feed /brief /chat"' in source
    assert 'class="nav-secondary-surface"' in source
    assert 'aria-label="Secondary dashboard access"' in source
    assert 'data-dashboard-secondary-surface="true"' in source
    assert 'data-secondary-access-surface="disclosure-menu"' in source
    assert 'data-navigation-tier="primary"' in source
    assert 'data-primary-navigation-group="most-used"' in source
    assert (
        'data-primary-navigation-routes="/setup /feed /brief /chat"'
    ) in source
    assert source.count('class="nav-primary"') == 4
    assert len(re.findall(r'<details\s+class="nav-group', source)) == 4
    assert source.count("data-secondary-navigation=") == 2
    assert source.count("data-advanced-navigation=") == 1
    assert source.count("data-saas-navigation=") == 1
    assert source.count('data-navigation-tier="secondary"') == 2
    assert source.count('data-navigation-tier="advanced"') == 1
    assert source.count('data-navigation-tier="saas"') == 1
    assert source.count('class="nav-group-label"') == 4
    assert source.count('class="nav-group-title"') == 4
    assert source.count('data-i18n="nav.tier.secondary"') == 2
    assert source.count('data-i18n="nav.tier.advanced"') == 1
    assert source.count('data-i18n="nav.tier.saas"') == 1
    assert source.count("data-i18n-aria-label=") >= 21
    assert 'data-i18n="nav.group.read"' in source
    assert 'data-i18n="nav.group.steer"' in source
    assert 'data-i18n="nav.group.tools"' in source
    assert 'data-i18n="nav.group.account"' in source

    secondary_routes = _data_route_groups(source, "data-secondary-navigation-routes")
    advanced_routes = _data_route_group(source, "data-advanced-navigation-routes")
    saas_routes = _data_route_group(source, "data-saas-navigation-routes")
    grouped_lower_frequency_routes = secondary_routes | advanced_routes
    primary_routes = _data_route_group(source, "data-primary-navigation-routes")
    assert primary_routes == {"/setup", "/feed", "/brief", "/chat"}
    assert "/setup" not in grouped_lower_frequency_routes
    assert "/feed" not in grouped_lower_frequency_routes
    assert "/brief" not in grouped_lower_frequency_routes
    assert "/chat" not in grouped_lower_frequency_routes

    expected_routes = _issue32_preserved_dashboard_nav_routes()
    linked_routes = _dashboard_nav_routes(source)
    assert expected_routes <= linked_routes
    assert "/dashboard/generative" in grouped_lower_frequency_routes
    assert _issue34_saas_inventory_routes() == saas_routes
    assert (
        expected_routes - {"/setup", "/feed", "/brief", "/chat"}
    ) <= grouped_lower_frequency_routes


def test_issue34_secondary_access_surface_links_routes_removed_from_primary():
    source = _base_template()
    nav = _dashboard_nav_body(source)
    primary_body = _dashboard_primary_list_body(source)
    secondary_surface = _dashboard_secondary_surface_body(source)

    primary_routes = _data_route_group(source, "data-primary-navigation-routes")
    moved_route_map = _issue34_routes_moved_out_of_primary_map()
    moved_routes = set(moved_route_map)
    primary_linked_routes = set(re.findall(r'href="([^"]+)"', primary_body))
    secondary_surface_routes = set(
        re.findall(r'href="([^"]+)"', secondary_surface)
    )
    secondary_access_routes = _data_route_group(source, "data-secondary-access-routes")
    expected_secondary_access_routes = moved_routes | {"/dashboard/generative"}

    assert nav.index('class="nav-primary-list"') < nav.index(
        'class="nav-secondary-surface"',
    )
    assert primary_linked_routes == primary_routes
    assert moved_routes.isdisjoint(primary_linked_routes)
    assert moved_routes <= secondary_surface_routes
    assert expected_secondary_access_routes <= secondary_surface_routes
    assert secondary_access_routes == expected_secondary_access_routes
    assert secondary_surface.count("<details") == 4
    assert 'data-navigation-tier="secondary"' in secondary_surface
    assert 'data-navigation-tier="advanced"' in secondary_surface
    assert 'data-navigation-tier="saas"' in secondary_surface


def test_issue34_navigation_group_route_ownership_is_explicit_and_non_overlapping():
    source = _base_template()
    nav = _dashboard_nav_body(source)

    grouped_route_sets = {
        "primary": _data_route_group(source, "data-primary-navigation-routes"),
        "secondary_read": _data_route_group(
            source,
            "data-secondary-navigation=\"read\"[^>]*data-secondary-navigation-routes",
        ),
        "secondary_steer": _data_route_group(
            source,
            "data-secondary-navigation=\"steer\"[^>]*data-secondary-navigation-routes",
        ),
        "advanced_tools": _data_route_group(
            source,
            "data-advanced-navigation=\"advanced\"[^>]*data-advanced-navigation-routes",
        ),
        "saas_account": _data_route_group(
            source,
            "data-saas-navigation=\"account\"[^>]*data-saas-navigation-routes",
        ),
    }

    assert grouped_route_sets == {
        "primary": {"/setup", "/feed", "/brief", "/chat"},
        "secondary_read": {
            "/",
            "/dashboard/generative",
            "/ambient/pwa",
            "/signals",
            "/profile",
            "/status",
        },
        "secondary_steer": {
            "/criteria",
            "/onboarding",
            "/onboarding/auto",
            "/sovereignty",
        },
        "advanced_tools": {
            "/sources",
            "/settings",
            "/evolution",
            "/sandbox",
            "/meta",
            "/demo",
            "/admin",
        },
        "saas_account": {
            "/landing",
            "/ko",
            "/zh",
            "/signup",
            "/login",
            "/auth/callback",
            "/billing",
            "/invite",
            "/terms",
            "/privacy",
            "/about",
        },
    }

    route_owners = {
        route: [
            group_name
            for group_name, route_set in grouped_route_sets.items()
            if route in route_set
        ]
        for route in set().union(*grouped_route_sets.values())
    }
    assert {
        route: owners for route, owners in route_owners.items() if len(owners) != 1
    } == {}
    assert set().union(*grouped_route_sets.values()) == _issue34_inventory_nav_routes_for_shell()
    assert nav.index('data-primary-navigation-group="most-used"') < nav.index(
        'data-secondary-navigation="read"',
    )
    assert nav.index('data-secondary-navigation="read"') < nav.index(
        'data-secondary-navigation="steer"',
    )
    assert nav.index('data-secondary-navigation="steer"') < nav.index(
        'data-advanced-navigation="advanced"',
    )
    assert nav.index('data-advanced-navigation="advanced"') < nav.index(
        'data-saas-navigation="account"',
    )
    assert nav.index('data-saas-navigation="account"') < nav.index(
        'data-overflow-navigation="more"',
    )


def test_issue34_local_dashboard_first_level_navigation_stays_scannable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    body = TestClient(create_app()).get("/setup").text
    nav = _dashboard_nav_body(body)
    primary_body = _dashboard_primary_list_body(body)
    secondary_surface = _dashboard_secondary_surface_body(body)
    overflow_body = _dashboard_overflow_menu_body(body)

    primary_links = re.findall(
        r'<a href="([^"]+)" class="nav-primary"[^>]*>([^<]+)</a>',
        primary_body,
    )
    group_summaries = re.findall(r"<summary[^>]*>(?P<body>.*?)</summary>", nav, re.S)
    group_titles = re.findall(
        r'<span class="nav-group-title"[^>]*>([^<]+)</span>',
        secondary_surface,
    )
    overflow_label = re.search(
        r'<span class="nav-overflow-label"[^>]*>([^<]+)</span>',
        overflow_body,
    )

    assert primary_links == [
        ("/setup", "Setup"),
        ("/feed", "Feed"),
        ("/brief", "Brief"),
        ("/chat", "Chat"),
    ]
    assert group_titles == ["Read", "Steer", "Tools"]
    assert overflow_label is not None
    assert overflow_label.group(1) == "More"
    assert "Account" not in group_titles

    top_level_labels = [
        label for _href, label in primary_links
    ] + group_titles + [overflow_label.group(1)]
    assert top_level_labels == [
        "Setup",
        "Feed",
        "Brief",
        "Chat",
        "Read",
        "Steer",
        "Tools",
        "More",
    ]
    assert len(top_level_labels) == 8
    assert len(primary_links) == 4
    assert all("href=" not in summary for summary in group_summaries)
    assert _issue34_saas_inventory_routes().isdisjoint(_dashboard_nav_routes(body))


def test_issue34_overflow_menu_links_same_routes_removed_from_primary():
    source = _base_template()
    nav = _dashboard_nav_body(source)
    primary_body = _dashboard_primary_list_body(source)
    overflow_body = _dashboard_overflow_menu_body(source)

    moved_routes = set(_issue34_routes_moved_out_of_primary_map())
    primary_linked_routes = set(re.findall(r'href="([^"]+)"', primary_body))
    overflow_linked_routes = set(re.findall(r'href="([^"]+)"', overflow_body))
    overflow_access_routes = _data_route_group(source, "data-overflow-access-routes")

    assert 'data-overflow-navigation="more"' in source
    assert 'data-overflow-access-surface="more-menu"' in source
    assert nav.index('class="nav-secondary-surface"') < nav.index(
        'class="nav-overflow nav-group"',
    )
    assert moved_routes.isdisjoint(primary_linked_routes)
    assert overflow_linked_routes == moved_routes
    assert overflow_access_routes == moved_routes
    assert 'id="nav-overflow-summary"' in overflow_body
    assert 'aria-controls="nav-overflow-menu"' in overflow_body
    assert 'data-i18n-aria-label="nav.overflow_label"' in overflow_body
    assert 'aria-label="Overflow navigation: all preserved routes"' in overflow_body
    assert 'id="nav-overflow-menu"' in overflow_body
    assert 'data-i18n-aria-label="nav.menu.overflow_label"' in overflow_body
    assert overflow_body.count("<li>") == len(moved_routes)
    assert 'aria-current="page"' not in overflow_body


def test_issue34_navigation_labels_and_accessible_names_are_preserved():
    source = _base_template()

    for href, label, key in (
        ("/setup", "Setup", "nav.setup"),
        ("/feed", "Feed", "nav.feed"),
        ("/brief", "Brief", "nav.brief"),
        ("/chat", "Chat", "nav.chat"),
    ):
        assert re.search(
            rf'<a href="{re.escape(href)}" class="nav-primary"'
            rf'[^>]*data-i18n="{re.escape(key)}"'
            rf'[^>]*data-i18n-aria-label="{re.escape(key)}"'
            rf'[^>]*aria-label="{re.escape(label)}"[^>]*>{re.escape(label)}</a>',
            source,
        ), href

    _assert_group_summary_label(
        source,
        "Secondary navigation: Read",
        "nav.tier.secondary",
        "nav.group.read",
    )
    _assert_group_summary_label(
        source,
        "Secondary navigation: Steer",
        "nav.tier.secondary",
        "nav.group.steer",
    )
    _assert_group_summary_label(
        source,
        "Advanced navigation: Tools",
        "nav.tier.advanced",
        "nav.group.tools",
    )
    _assert_group_summary_label(
        source,
        "SaaS navigation: Account",
        "nav.tier.saas",
        "nav.group.account",
    )

    for anchor in _dashboard_nav_anchor_tags(source):
        visible_label = re.search(r">([^<]+)</a>", anchor)
        assert visible_label is not None
        assert visible_label.group(1).strip() != ""
        assert 'aria-label="' in anchor
        assert 'data-i18n-aria-label="' in anchor

    assert 'data-i18n-aria-label="nav.menu.read_label" aria-label="Secondary navigation: read"' in source
    assert 'data-i18n-aria-label="nav.menu.steer_label" aria-label="Secondary navigation: steer"' in source
    assert 'data-i18n-aria-label="nav.menu.tools_label" aria-label="Advanced navigation"' in source
    assert 'data-i18n-aria-label="nav.menu.account_label" aria-label="SaaS navigation"' in source
    assert 'data-i18n-aria-label="nav.menu.overflow_label" aria-label="Overflow navigation"' in source
    assert 'node.setAttribute("aria-label", dictionary[key])' in source


def test_issue34_shared_navigation_labels_are_localized_for_supported_languages():
    source = _base_template()

    for key in (
        "nav.dashboard_label",
        "nav.dashboard_navigation_label",
        "nav.primary_navigation_label",
        "nav.secondary_surface_label",
        "nav.setup",
        "nav.feed",
        "nav.brief",
        "nav.chat",
        "nav.group.read_label",
        "nav.group.steer_label",
        "nav.group.tools_label",
        "nav.group.account_label",
        "nav.overflow_label",
    ):
        assert f'data-i18n-aria-label="{key}"' in source

    for key in ("nav.setup", "nav.feed", "nav.brief", "nav.chat"):
        assert f'data-i18n="{key}"' in source

    expected_translations = {
        "ko": {
            "nav.dashboard_label": "Hedwig 대시보드",
            "nav.dashboard_navigation_label": "대시보드 내비게이션",
            "nav.primary_navigation_label": "주요 대시보드 내비게이션",
            "nav.setup": "설정",
            "nav.feed": "피드",
            "nav.brief": "브리프",
            "nav.chat": "채팅",
        },
        "zh": {
            "nav.dashboard_label": "Hedwig 仪表盘",
            "nav.dashboard_navigation_label": "仪表盘导航",
            "nav.primary_navigation_label": "主要仪表盘导航",
            "nav.setup": "设置",
            "nav.feed": "信息流",
            "nav.brief": "简报",
            "nav.chat": "聊天",
        },
        "en": {
            "nav.dashboard_label": "Hedwig dashboard",
            "nav.dashboard_navigation_label": "Dashboard navigation",
            "nav.primary_navigation_label": "Primary dashboard navigation",
            "nav.setup": "Setup",
            "nav.feed": "Feed",
            "nav.brief": "Brief",
            "nav.chat": "Chat",
        },
    }
    for language, translations in expected_translations.items():
        language_block = source.split(f"{language}: {{", 1)[1].split("\n      }", 1)[0]
        for key, translation in translations.items():
            assert f'"{key}": "{translation}"' in language_block


def test_issue34_navigation_accessibility_semantics_and_group_relationships():
    source = _base_template()
    nav = _dashboard_nav_body(source)

    assert '<nav class="nav" role="navigation" aria-label="Hedwig dashboard"' in source
    assert 'class="nav-links"\n      aria-label="Dashboard navigation"' in source
    assert re.search(
        r'<ul\s+class="nav-primary-list"\s+role="list"'
        r'\s+aria-label="Primary dashboard navigation"'
        r'\s+data-navigation-tier="primary"'
        r'\s+data-primary-navigation-group="most-used"'
        r'\s+data-primary-navigation-routes="/setup /feed /brief /chat"',
        nav,
    )
    assert 'role="menu"' not in nav
    assert len(re.findall(r"<ul[^>]*class=\"nav-primary-list\"[\s\S]*?</ul>", nav)) == 1
    primary_list = re.search(
        r'<ul[^>]*class="nav-primary-list"[^>]*>(?P<body>[\s\S]*?)</ul>',
        nav,
    )
    assert primary_list is not None
    assert primary_list.group("body").count("<li>") == 4
    assert primary_list.group("body").count('class="nav-primary"') == 4
    assert nav.index('class="nav-primary-list"') < nav.index('data-secondary-navigation="read"')
    assert nav.index('class="nav-primary-list"') < nav.index('data-secondary-navigation="steer"')
    assert nav.index('class="nav-primary-list"') < nav.index('data-advanced-navigation="advanced"')

    expected_groups = {
        "read": ("nav-read-summary", "nav-read-menu", 6),
        "steer": ("nav-steer-summary", "nav-steer-menu", 4),
        "advanced": ("nav-tools-summary", "nav-tools-menu", 7),
        "account": ("nav-saas-summary", "nav-saas-menu", 11),
    }
    for group_name, (summary_id, menu_id, expected_link_count) in expected_groups.items():
        if group_name == "advanced":
            group_attr = f'data-advanced-navigation="{group_name}"'
        elif group_name == "account":
            group_attr = f'data-saas-navigation="{group_name}"'
        else:
            group_attr = f'data-secondary-navigation="{group_name}"'
        group_match = re.search(
            rf'<details[^>]*role="group"'
            rf'[^>]*aria-labelledby="{summary_id}"'
            rf'[^>]*{re.escape(group_attr)}[^>]*>'
            rf'(?P<body>[\s\S]*?)</details>',
            nav,
        )
        assert group_match is not None, group_name
        group_body = group_match.group("body")
        assert re.search(
            rf'<summary id="{summary_id}" aria-controls="{menu_id}"'
            rf'[^>]*data-i18n-aria-label="nav\.group\.[^"]+_label"',
            group_body,
        ), group_name
        assert re.search(
            rf'<ul id="{menu_id}" class="nav-menu" role="list"'
            rf' aria-labelledby="{summary_id}"'
            rf'[^>]*data-i18n-aria-label="nav\.menu\.[^"]+_label"',
            group_body,
        ), group_name
        assert group_body.count("<li>") == expected_link_count
        assert group_body.count("</li>") == expected_link_count


def test_issue34_navigation_taxonomy_documents_secondary_and_advanced_groups():
    source = _base_template()
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")

    assert "## Secondary Navigation" in taxonomy
    assert "## Advanced Navigation" in taxonomy
    assert "`/setup`, `/feed`, `/brief`, `/chat`" in taxonomy

    for route in _dashboard_nav_routes(source):
        assert f"`{route}`" in taxonomy


def test_issue34_inventory_identifies_most_used_primary_route_targets():
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")
    issue32_inventory = INVENTORY_PATH.read_text(encoding="utf-8")

    primary_section = taxonomy.split(
        "### Most-Used Primary Route Selection",
        1,
    )[1].split("\n## ", 1)[0]
    primary_routes = _markdown_table_routes(primary_section)
    expected_primary_routes = {"/setup", "/feed", "/brief", "/chat"}

    assert primary_routes == expected_primary_routes
    assert 'data-primary-navigation="/setup /feed /brief /chat"' in _base_template()

    for route in expected_primary_routes:
        assert f"`{route}`" in issue32_inventory
        assert f"`{route}`" in primary_section

    for required_rationale in (
        "First-run configuration",
        "Default post-setup delivery",
        "summary consumption surface",
        "Natural-language steering",
    ):
        assert required_rationale in primary_section

    issue32_header_routes = _issue32_preserved_dashboard_nav_routes()
    secondary_and_advanced_routes = _data_route_groups(
        _base_template(),
        "data-secondary-navigation-routes",
    ) | _data_route_group(_base_template(), "data-advanced-navigation-routes")

    assert expected_primary_routes <= issue32_header_routes
    assert issue32_header_routes <= expected_primary_routes | secondary_and_advanced_routes
    assert "/dashboard/generative" in secondary_and_advanced_routes
    assert "/dashboard/generative" not in issue32_header_routes


def test_issue34_inventory_maps_routes_removed_from_primary_to_secondary_destinations():
    source = _base_template()
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")

    primary_routes = _data_route_group(source, "data-primary-navigation-routes")
    read_routes = _data_route_group(source, "data-secondary-navigation-routes")
    secondary_routes = _data_route_groups(source, "data-secondary-navigation-routes")
    advanced_routes = _data_route_group(source, "data-advanced-navigation-routes")
    issue32_header_routes = _issue32_preserved_dashboard_nav_routes()
    moved_route_map = _issue34_routes_moved_out_of_primary_map()

    assert "### Routes Moved Out Of Primary Navigation" in taxonomy
    assert set(moved_route_map) == issue32_header_routes - primary_routes
    assert set(moved_route_map).isdisjoint(primary_routes)
    assert issue32_header_routes == primary_routes | set(moved_route_map)

    for route, (destination, tier) in moved_route_map.items():
        assert ">" in destination
        if route in advanced_routes:
            assert tier == "Advanced"
            assert destination.startswith("Tools > ")
            continue

        assert route in secondary_routes
        assert tier == "Secondary"
        if route in read_routes:
            assert destination.startswith("Read > ")
        else:
            assert destination.startswith("Steer > ")


def test_issue34_regrouped_shell_maps_each_inventory_html_route_to_visible_entry():
    source = _base_template()
    inventory_routes = _issue34_inventory_nav_routes_for_shell()
    nav_routes = _dashboard_nav_routes(source)
    primary_routes = _data_route_group(source, "data-primary-navigation-routes")
    grouped_routes = (
        _data_route_groups(source, "data-secondary-navigation-routes")
        | _data_route_group(source, "data-advanced-navigation-routes")
        | _data_route_group(source, "data-saas-navigation-routes")
    )

    assert inventory_routes <= nav_routes
    assert inventory_routes == primary_routes | grouped_routes
    assert primary_routes == {"/setup", "/feed", "/brief", "/chat"}
    assert _issue34_saas_inventory_routes() <= grouped_routes
    assert "/dashboard/generative" in grouped_routes


def test_issue34_route_audit_enumerates_all_registered_dashboard_routes():
    taxonomy = ISSUE34_NAV_GROUPS_PATH.read_text(encoding="utf-8")
    documented_route_refs = _issue34_documented_route_refs()
    audited_html_routes = _issue34_audited_html_routes()
    audited_supporting_routes = _issue34_audited_supporting_routes()
    app_route_paths = _dashboard_app_route_paths()
    html_page_routes = _dashboard_html_page_routes_from_app()
    supporting_route_paths = app_route_paths - set(html_page_routes)

    assert "## Preserved Dashboard Route Audit" in taxonomy
    assert "### HTML Surfaces" in taxonomy
    assert "### Supporting Endpoints" in taxonomy
    assert app_route_paths <= documented_route_refs
    assert set(html_page_routes) <= set(audited_html_routes)
    assert audited_supporting_routes == supporting_route_paths

    for route, template in html_page_routes.items():
        row = audited_html_routes[route]
        assert template in row[1], route
        assert row[2] and row[2] != "Navigation / reachability tier"
        assert row[3] and row[3] != "Preservation note"

    for route in _dashboard_nav_routes(_base_template()):
        assert route in documented_route_refs
        audited_route = "/ambient/{surface}" if route == "/ambient/pwa" else route
        assert audited_route in audited_html_routes
        assert "shell link" in audited_html_routes[audited_route][2]


def test_issue34_grouped_navigation_is_usable_on_desktop_and_mobile():
    css = STYLE_PATH.read_text(encoding="utf-8")
    v3_css = V3_STYLE_PATH.read_text(encoding="utf-8")

    assert ".nav-primary-list {" in css
    assert "margin: 0;" in css
    assert "padding: 0;" in css
    assert ".nav-secondary-surface {" in css
    assert ".nav-primary-list li,\n.nav-menu li" in css
    assert ".nav-menu {" in css
    assert "position: absolute;" in css
    assert "width: 210px;" in css
    assert ".nav-group[open] .nav-menu" in css
    assert '.nav-links a[aria-current="page"]' in css
    assert '.nav-group[data-current-navigation="true"] summary' in css
    assert '.nav-menu a[aria-current="page"]' in css
    assert ".nav-links a:focus-visible" in css
    assert ".nav-group summary:focus-visible" in css
    assert ".language-rail select:focus-visible" in css
    assert "outline: 3px solid rgba(124, 92, 255, 0.45);" in css
    assert ".nav-group-saas .nav-group-kicker" in css
    assert ".nav-overflow-label" in css
    assert ".nav-overflow-menu" in css
    assert ".nav-links a:focus-visible" in v3_css
    assert "outline: 3px solid rgba(37, 99, 235, 0.35) !important;" in v3_css
    assert ".nav-group-saas .nav-group-kicker" in v3_css
    assert ".nav-overflow-label" in v3_css

    tablet_css = _media_block(css, 768)
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in tablet_css
    assert "align-items: stretch;" in tablet_css
    assert "min-height: 44px;" in tablet_css
    assert ".nav-primary-list" in tablet_css
    assert "grid-column: 1 / -1;" in tablet_css
    assert ".nav-secondary-surface" in tablet_css
    assert ".nav-overflow" in tablet_css
    assert ".nav-group[open] {" in tablet_css
    assert "grid-column: 1 / -1;" in tablet_css
    assert "position: static;" in tablet_css
    assert "max-width: none;" in tablet_css
    assert ".nav-group-label" in tablet_css
    assert "flex-direction: column;" in tablet_css
    assert ".nav-group[open] .nav-menu" in tablet_css
    assert "box-shadow: none;" in tablet_css
    assert "border: 1px solid var(--border);" in tablet_css
    assert "background: rgba(124, 92, 255, 0.06);" in tablet_css

    phone_css = _media_block(css, 480)
    assert ".nav-links,\n  .nav-primary-list,\n  .nav-secondary-surface," in phone_css
    assert ".nav-secondary-surface" in phone_css
    assert ".nav-overflow" in phone_css
    assert "grid-template-columns: 1fr;" in phone_css


def test_issue34_grouped_navigation_preserves_active_state_for_all_tiers(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())

    setup_body = client.get("/setup").text
    _assert_single_active_navigation_state(setup_body, "/setup")
    assert re.search(
        r'<a href="/setup" class="nav-primary"[^>]*data-i18n="nav.setup"'
        r'[^>]*data-i18n-aria-label="nav.setup"[^>]*aria-label="Setup"'
        r'[^>]*aria-current="page">Setup</a>',
        setup_body,
    )
    assert 'aria-label="Secondary navigation: Read"' in setup_body
    assert 'aria-label="Secondary navigation: Steer"' in setup_body
    assert 'aria-label="Advanced navigation: Tools"' in setup_body

    signals_body = client.get("/signals").text
    _assert_single_active_navigation_state(
        signals_body,
        "/signals",
        'data-secondary-navigation="read"',
    )
    assert 'data-secondary-navigation="read"' in signals_body
    assert re.search(
        r'<a href="/signals"[^>]*data-i18n="nav.signals"'
        r'[^>]*data-i18n-aria-label="nav.signals"[^>]*aria-label="Signals"'
        r'[^>]*aria-current="page">Signals</a>',
        signals_body,
    )
    _assert_group_summary_label(
        signals_body,
        "Secondary navigation: Read",
        "nav.tier.secondary",
        "nav.group.read",
    )

    generative_body = client.get("/dashboard/generative").text
    _assert_single_active_navigation_state(
        generative_body,
        "/dashboard/generative",
        'data-secondary-navigation="read"',
    )
    assert 'data-secondary-navigation="read"' in generative_body
    assert re.search(
        r'<a href="/dashboard/generative"[^>]*data-i18n="nav.generative"'
        r'[^>]*data-i18n-aria-label="nav.generative"'
        r'[^>]*aria-label="Generative"[^>]*aria-current="page">Generative</a>',
        generative_body,
    )

    onboarding_body = client.get("/onboarding").text
    _assert_single_active_navigation_state(
        onboarding_body,
        "/onboarding",
        'data-secondary-navigation="steer"',
    )
    assert 'data-secondary-navigation="steer"' in onboarding_body
    assert re.search(
        r'data-secondary-navigation="steer"[\s\S]*?open '
        r'data-current-navigation="true"',
        onboarding_body,
    )
    assert re.search(
        r'<a href="/onboarding"[^>]*data-i18n="nav.onboarding"'
        r'[^>]*data-i18n-aria-label="nav.onboarding"'
        r'[^>]*aria-label="Onboarding"[^>]*aria-current="page">Onboarding</a>',
        onboarding_body,
    )
    _assert_group_summary_label(
        onboarding_body,
        "Secondary navigation: Steer",
        "nav.tier.secondary",
        "nav.group.steer",
    )

    evolution_body = client.get("/evolution").text
    _assert_single_active_navigation_state(
        evolution_body,
        "/evolution",
        'data-advanced-navigation="advanced"',
    )
    assert 'data-advanced-navigation="advanced"' in evolution_body
    assert re.search(
        r'data-advanced-navigation="advanced"[\s\S]*?open '
        r'data-current-navigation="true"',
        evolution_body,
    )
    assert re.search(
        r'<a href="/evolution"[^>]*data-i18n="nav.evolution"'
        r'[^>]*data-i18n-aria-label="nav.evolution"'
        r'[^>]*aria-label="Evolution"[^>]*aria-current="page">Evolution</a>',
        evolution_body,
    )
    _assert_group_summary_label(
        evolution_body,
        "Advanced navigation: Tools",
        "nav.tier.advanced",
        "nav.group.tools",
    )


def test_issue34_every_registered_html_route_has_visible_navigation_path(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    local_client = TestClient(create_app())
    local_registered_paths = {
        getattr(route, "path", "") for route in local_client.app.routes
    }
    local_expected_nav_paths = {
        _visible_nav_path_for_route(route)
        for route in _registered_html_page_routes(local_registered_paths)
    }
    local_visible_nav = _dashboard_nav_labeled_routes(
        local_client.get("/setup").text,
    )

    assert _issue34_saas_inventory_routes().isdisjoint(local_visible_nav)
    missing_local_nav_paths = sorted(
        local_expected_nav_paths - set(local_visible_nav),
    )
    assert missing_local_nav_paths == []
    assert [
        path for path in sorted(local_expected_nav_paths) if not local_visible_nav[path]
    ] == []

    saas_client = TestClient(create_app(saas_mode=True))
    saas_registered_paths = {
        getattr(route, "path", "") for route in saas_client.app.routes
    }
    saas_expected_nav_paths = {
        _visible_nav_path_for_route(route)
        for route in _registered_html_page_routes(saas_registered_paths)
    }
    saas_visible_nav = _dashboard_nav_labeled_routes(
        saas_client.get("/signup").text,
    )

    assert _issue34_saas_inventory_routes() <= set(saas_visible_nav)
    missing_saas_nav_paths = sorted(
        saas_expected_nav_paths - set(saas_visible_nav),
    )
    assert missing_saas_nav_paths == []
    assert [
        path for path in sorted(saas_expected_nav_paths) if not saas_visible_nav[path]
    ] == []


def test_issue34_dashboard_navigation_routes_are_registered_and_reachable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    registered_route_paths = {
        getattr(route, "path", "") for route in client.app.routes
    }
    nav_routes = _dashboard_nav_routes(client.get("/setup").text)
    preserved_issue32_routes = _issue32_preserved_dashboard_nav_routes()
    local_shell_routes = preserved_issue32_routes | {"/dashboard/generative"}

    assert nav_routes == local_shell_routes
    assert _issue34_saas_inventory_routes().isdisjoint(nav_routes)
    missing_registered_paths = sorted(
        path
        for path in local_shell_routes
        if not _route_path_is_registered(path, registered_route_paths)
    )
    assert missing_registered_paths == []

    expected_statuses = {
        "/": {303},
        "/ambient/pwa": {200},
        "/feed": {200},
        "/brief": {200},
        "/profile": {200},
        "/signals": {200},
        "/dashboard/generative": {200},
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
    assert set(expected_statuses) == local_shell_routes

    for path, allowed_statuses in expected_statuses.items():
        response = client.get(path, follow_redirects=False)
        assert response.status_code in allowed_statuses, path
        if response.status_code == 303:
            assert response.headers["location"] == "/setup"
        else:
            assert "Hedwig" in response.text


def test_issue34_issue32_inventory_html_routes_remain_reachable_after_regrouping(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    inventory_routes = _issue32_inventory_html_routes()
    saas_routes = _issue34_saas_inventory_routes()

    assert saas_routes < inventory_routes

    _assert_issue32_inventory_routes_reachable_from_nav(
        TestClient(create_app()),
        shell_path="/setup",
        inventory_routes=inventory_routes - saas_routes,
    )
    _assert_issue32_inventory_routes_reachable_from_nav(
        TestClient(create_app(saas_mode=True)),
        shell_path="/signup",
        inventory_routes=saas_routes,
    )


def test_issue34_saas_inventory_navigation_routes_are_visible_and_reachable(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app(saas_mode=True))
    registered_route_paths = {
        getattr(route, "path", "") for route in client.app.routes
    }
    signup_body = client.get("/signup").text
    nav_routes = _dashboard_nav_routes(signup_body)
    saas_routes = _issue34_saas_inventory_routes()

    assert saas_routes <= nav_routes
    assert _data_route_group(signup_body, "data-saas-navigation-routes") == saas_routes
    assert 'data-saas-navigation="account"' in signup_body
    _assert_single_active_navigation_state(
        signup_body,
        "/signup",
        'data-saas-navigation="account"',
    )

    missing_registered_paths = sorted(
        path
        for path in saas_routes
        if not _route_path_is_registered(path, registered_route_paths)
    )
    assert missing_registered_paths == []

    for path in sorted(saas_routes):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 200, path
        assert "<html" in response.text.lower(), path


def test_issue34_language_selector_supports_ko_zh_en_and_persists_locally():
    source = _base_template()
    left_rail_match = re.search(
        r'<div class="nav-left-rail">(?P<body>[\s\S]*?)\n    </div>\n    <div\n      class="nav-links"',
        source,
    )
    assert left_rail_match is not None
    left_rail = left_rail_match.group("body")

    assert 'data-dashboard-language-selector="left-rail"' in left_rail
    assert 'class="language-rail"' in left_rail
    assert 'role="group"' in left_rail
    assert 'aria-label="Language selector"' in left_rail
    assert 'data-i18n-aria-label="language.selector_label"' in left_rail
    assert 'id="hedwig-language-label" for="hedwig-language"' in left_rail
    assert 'data-language-selector' in left_rail
    assert 'data-language-storage-key="hedwig.language"' in left_rail
    assert re.findall(
        r'<option value="([^"]+)" data-i18n="(language\.[^"]+)">([^<]+)</option>',
        left_rail,
    ) == [
        ("ko", "language.ko", "한국어"),
        ("zh", "language.zh", "中文"),
        ("en", "language.en", "English"),
    ]
    assert 'const HEDWIG_SUPPORTED_LANGUAGES = ["ko", "zh", "en"];' in source
    assert "data-language-selector" not in _dashboard_nav_body(source)
    assert 'const HEDWIG_LANGUAGE_STORAGE_KEY = "hedwig.language";' in source
    assert "window.localStorage.setItem(HEDWIG_LANGUAGE_STORAGE_KEY, language)" in source
    assert "window.localStorage.getItem(HEDWIG_LANGUAGE_STORAGE_KEY)" in source
    assert 'document.documentElement.lang = language' in source
    assert "data-i18n-aria-label" in source
    assert 'node.setAttribute("aria-label", dictionary[key])' in source


def test_issue34_language_selector_renders_visibly_with_available_options(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    response = client.get("/setup")

    assert response.status_code == 200
    body = response.text
    left_rail_match = re.search(
        r'<div class="nav-left-rail">(?P<body>[\s\S]*?)\n    </div>\n    <div\n      class="nav-links"',
        body,
    )
    assert left_rail_match is not None
    left_rail = left_rail_match.group("body")
    selector_match = re.search(
        r'<div\s+class="language-rail"(?P<attrs>[^>]*)>(?P<body>[\s\S]*?)</select>\s*</div>',
        left_rail,
    )
    assert selector_match is not None

    selector_attrs = selector_match.group("attrs")
    selector_body = selector_match.group("body")
    assert "hidden" not in selector_attrs
    assert 'aria-hidden="true"' not in selector_attrs
    assert "display: none" not in selector_attrs
    assert "visibility: hidden" not in selector_attrs
    assert 'role="group"' in selector_attrs
    assert 'aria-label="Language selector"' in selector_attrs
    assert 'data-dashboard-language-selector="left-rail"' in selector_attrs
    assert 'for="hedwig-language"' in selector_body
    assert 'data-language-selector' in selector_body
    assert re.findall(
        r'<option value="([^"]+)" data-i18n="(language\.[^"]+)">([^<]+)</option>',
        selector_body,
    ) == [
        ("ko", "language.ko", "한국어"),
        ("zh", "language.zh", "中文"),
        ("en", "language.en", "English"),
    ]

    css = STYLE_PATH.read_text(encoding="utf-8")
    assert re.search(r"\.language-rail\s*\{[\s\S]*?display: flex;", css)
    assert re.search(r"\.language-rail select\s*\{[\s\S]*?min-width: 92px;", css)


def test_issue34_language_selector_remains_visible_on_first_time_routes(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())

    for route in ("/setup", "/feed", "/brief"):
        response = client.get(route)

        assert response.status_code == 200, route
        body = response.text
        left_rail = _dashboard_left_rail_body(body)
        selector_attrs, selector_body = _dashboard_language_selector(left_rail)
        selector_markup = selector_attrs + selector_body

        assert body.count('data-dashboard-language-selector="left-rail"') == 1, route
        assert body.index('class="nav-left-rail"') < body.index('class="nav-links"')
        assert "data-language-selector" not in _dashboard_nav_body(body)
        assert "hidden" not in selector_attrs
        assert 'aria-hidden="true"' not in selector_attrs
        assert "display: none" not in selector_attrs
        assert "visibility: hidden" not in selector_attrs
        assert "disabled" not in selector_markup
        assert 'role="group"' in selector_attrs
        assert 'aria-label="Language selector"' in selector_attrs
        assert 'data-dashboard-language-selector="left-rail"' in selector_attrs
        assert 'id="hedwig-language-label" for="hedwig-language"' in selector_body
        assert 'id="hedwig-language"' in selector_body
        assert 'data-language-storage-key="hedwig.language"' in selector_body


def test_issue34_language_selector_css_preserves_mobile_visibility():
    css = STYLE_PATH.read_text(encoding="utf-8")
    language_blocks = re.findall(
        r"\.language-rail(?:\s+(?:label|select))?\s*\{[^}]*\}",
        css,
    )

    assert language_blocks != []
    for block in language_blocks:
        assert "display: none" not in block
        assert "visibility: hidden" not in block
        assert "opacity: 0" not in block

    tablet_css = _media_block(css, 768)
    phone_css = _media_block(css, 480)

    assert ".language-rail { border-left: 0; padding-left: 0; }" in tablet_css
    assert re.search(
        r"\.language-rail\s*\{[\s\S]*?justify-content: space-between;"
        r"[\s\S]*?width: 100%;[\s\S]*?\}",
        phone_css,
    )
    assert re.search(
        r"\.language-rail select\s*\{[\s\S]*?flex: 1;[\s\S]*?\}",
        phone_css,
    )


def test_issue34_selected_language_restores_from_local_storage_and_change_persists():
    source = _base_template()

    assert re.search(
        r"function loadHedwigLanguagePreference\(\) \{[\s\S]*?"
        r"window\.localStorage\.getItem\(HEDWIG_LANGUAGE_STORAGE_KEY\)"
        r"[\s\S]*?catch \{[\s\S]*?return \"\";",
        source,
    )
    assert re.search(
        r"function persistHedwigLanguagePreference\(language\) \{[\s\S]*?"
        r"window\.localStorage\.setItem\(HEDWIG_LANGUAGE_STORAGE_KEY, language\)"
        r"[\s\S]*?catch \{[\s\S]*?browser storage is unavailable",
        source,
    )
    assert re.search(
        r"const languageFromQuery = new URLSearchParams\(window\.location\.search\)"
        r"\.get\(\"lang\"\);\s*"
        r"const savedLanguage = loadHedwigLanguagePreference\(\);\s*"
        r"applyHedwigLanguage\(normalizeHedwigLanguage\(languageFromQuery\) "
        r"\|\| savedLanguage \|\| \"ko\"\);",
        source,
    )
    assert re.search(
        r'document\.querySelector\("\[data-language-selector\]"\)\?'
        r'\.addEventListener\("change", \(event\) => \{\s*'
        r"applyHedwigLanguage\(event\.target\.value\);",
        source,
    )
    assert re.search(
        r"function normalizeHedwigLanguage\(nextLanguage\) \{\s*"
        r"return HEDWIG_SUPPORTED_LANGUAGES\.includes\(nextLanguage\) "
        r'\? nextLanguage : "";',
        source,
    )


def test_issue34_selected_language_change_survives_reload_or_shell_remount():
    source = _base_template()

    assert 'data-language-storage-key="hedwig.language"' in source
    assert 'const HEDWIG_LANGUAGE_STORAGE_KEY = "hedwig.language";' in source
    assert source.index("function loadHedwigLanguagePreference()") < source.index(
        "const savedLanguage = loadHedwigLanguagePreference();",
    )
    assert source.index("function persistHedwigLanguagePreference(language)") < source.index(
        "document.querySelector(\"[data-language-selector]\")?.addEventListener",
    )
    assert re.search(
        r'document\.querySelector\("\[data-language-selector\]"\)\?'
        r'\.addEventListener\("change", \(event\) => \{\s*'
        r"applyHedwigLanguage\(event\.target\.value\);",
        source,
    )
    assert re.search(
        r"function applyHedwigLanguage\(nextLanguage\) \{[\s\S]*?"
        r"persistHedwigLanguagePreference\(language\);",
        source,
    )
    assert source.index("persistHedwigLanguagePreference(language);") < source.index(
        'window.dispatchEvent(new CustomEvent("hedwig:languagechange"',
    )
    assert re.search(
        r"const savedLanguage = loadHedwigLanguagePreference\(\);\s*"
        r"applyHedwigLanguage\(normalizeHedwigLanguage\(languageFromQuery\) "
        r"\|\| savedLanguage \|\| \"ko\"\);",
        source,
    )
    assert re.search(
        r"function renderHedwigLocalizedShell\(\) \{[\s\S]*?"
        r"document\.documentElement\.lang = language;[\s\S]*?"
        r'const selector = document\.querySelector\("\[data-language-selector\]"\);'
        r"[\s\S]*?if \(selector\) selector\.value = language;",
        source,
    )


def test_issue34_language_state_drives_shell_rerender_on_selector_change():
    source = _base_template()

    assert re.search(
        r"const HEDWIG_LANGUAGE_STATE = \{\s*"
        r'current: "ko",\s*'
        r"dictionary: HEDWIG_I18N\.ko",
        source,
    )
    assert re.search(
        r"function renderHedwigLocalizedShell\(\) \{[\s\S]*?"
        r"const language = HEDWIG_LANGUAGE_STATE\.current;[\s\S]*?"
        r"const dictionary = HEDWIG_LANGUAGE_STATE\.dictionary;[\s\S]*?"
        r"document\.documentElement\.lang = language;[\s\S]*?"
        r'document\.querySelectorAll\("\[data-i18n\]"\)[\s\S]*?'
        r"node\.textContent = dictionary\[key\];[\s\S]*?"
        r'document\.querySelectorAll\("\[data-i18n-aria-label\]"\)[\s\S]*?'
        r'node\.setAttribute\("aria-label", dictionary\[key\]\);[\s\S]*?'
        r'const selector = document\.querySelector\("\[data-language-selector\]"\);'
        r"[\s\S]*?selector\.value = language;",
        source,
    )
    assert re.search(
        r"function applyHedwigLanguage\(nextLanguage\) \{[\s\S]*?"
        r"const language = normalizeHedwigLanguage\(nextLanguage\) \|\| \"ko\";"
        r"[\s\S]*?HEDWIG_LANGUAGE_STATE\.current = language;"
        r"[\s\S]*?HEDWIG_LANGUAGE_STATE\.dictionary = HEDWIG_I18N\[language\] "
        r"\|\| HEDWIG_I18N\.ko;"
        r"[\s\S]*?renderHedwigLocalizedShell\(\);"
        r"[\s\S]*?persistHedwigLanguagePreference\(language\);"
        r"[\s\S]*?window\.dispatchEvent\(new CustomEvent"
        r'\("hedwig:languagechange", \{ detail: \{ language \} \}\)\);',
        source,
    )
    assert re.search(
        r'document\.querySelector\("\[data-language-selector\]"\)\?'
        r'\.addEventListener\("change", \(event\) => \{\s*'
        r"applyHedwigLanguage\(event\.target\.value\);",
        source,
    )


def test_issue34_language_state_is_wired_into_setup_page_rendering():
    source = SETUP_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'data-setup-language-renderer="HEDWIG_LANGUAGE_STATE"' in source
    assert "const SETUP_PAGE_I18N = {" in source
    for language in ("ko", "zh", "en"):
        assert f"{language}: {{" in source

    assert re.search(
        r"function setupPageLanguage\(\) \{[\s\S]*?"
        r"return HEDWIG_LANGUAGE_STATE\.current \|\| 'ko';",
        source,
    )
    assert re.search(
        r"function setupPageText\(key, fallback, replacements = \{\}\) \{[\s\S]*?"
        r"setupPageDictionary\(\)\[key\] \|\| fallback[\s\S]*?"
        r"text\.replaceAll\(`\{\$\{name\}\}`, String\(value\)\)",
        source,
    )
    assert re.search(
        r"function renderLocalizedSetupPage\(\) \{[\s\S]*?"
        r"updateSetupClientState\(\);[\s\S]*?"
        r"renderSetupState\(setupClientState\.latestSetupState\);[\s\S]*?"
        r"renderCollectionProgressLifecycle\(setupClientState\.latestCollectionProgress\);",
        source,
    )
    assert re.search(
        r"window\.addEventListener\('hedwig:languagechange', \(\) => \{\s*"
        r"renderLocalizedSetupPage\(\);",
        source,
    )

    dynamic_render_hooks = [
        "setup.status.openai_missing",
        "setup.feedback.not_started",
        "setup.progress.save_key_message",
        "setup.completion.message.waiting",
        "setup.collection.status",
    ]
    for hook in dynamic_render_hooks:
        assert f"setupPageText('{hook}'" in source


def test_issue34_setup_instructional_copy_uses_selected_language():
    source = SETUP_TEMPLATE_PATH.read_text(encoding="utf-8")

    instructional_hooks = [
        "setup.primary_path.start",
        "setup.primary_path.instructions",
        "setup.step.essential.eyebrow",
        "setup.step.essential.title",
        "setup.step.essential.badge",
        "setup.step.essential.instructions",
        "setup.step.criteria.eyebrow",
        "setup.step.criteria.title",
        "setup.step.criteria.instructions",
        "setup.step.sources.eyebrow",
        "setup.step.sources.title",
        "setup.step.sources.instructions",
        "setup.step.progress.eyebrow",
        "setup.step.progress.title",
        "setup.step.progress.instructions",
        "setup.step.feed.eyebrow",
        "setup.step.feed.title",
        "setup.step.feed.instructions",
        "setup.step.completion.eyebrow",
        "setup.step.completion.title",
        "setup.step.advanced.eyebrow",
        "setup.step.advanced.title",
        "setup.step.advanced.instructions",
    ]
    for hook in instructional_hooks:
        assert f'data-setup-i18n="{hook}"' in source
        assert f"'{hook}':" in source

    expected_localized_copy = {
        "ko": [
            "'setup.primary_path.start': '필수 설정 시작'",
            "'setup.step.essential.instructions': '이 단계만 차단 조건입니다.",
            "'setup.step.feed.title': '피드 우선 대시보드'",
        ],
        "zh": [
            "'setup.primary_path.start': '开始必需设置'",
            "'setup.step.essential.instructions': '这是唯一阻塞步骤。",
            "'setup.step.feed.title': '信息流优先仪表盘'",
        ],
        "en": [
            "'setup.primary_path.start': 'Start required setup'",
            "'setup.step.essential.instructions': 'This is the only blocking step.",
            "'setup.step.feed.title': 'Feed-first dashboard'",
        ],
    }
    for language, snippets in expected_localized_copy.items():
        language_block = source.split(f"{language}: {{", 1)[1].split("\n  },", 1)[0]
        for snippet in snippets:
            assert snippet in language_block

    assert re.search(
        r"function renderSetupStaticInstructionCopy\(\) \{[\s\S]*?"
        r"document\.querySelectorAll\('\[data-setup-i18n\]'\)\.forEach"
        r"\(\(node\) => \{[\s\S]*?"
        r"const key = node\.dataset\.setupI18n;[\s\S]*?"
        r"node\.textContent = setupPageText\(key, node\.textContent\.trim\(\)\);",
        source,
    )
    assert re.search(
        r"function renderLocalizedSetupPage\(\) \{\s*"
        r"renderSetupStaticInstructionCopy\(\);[\s\S]*?"
        r"updateSetupClientState\(\);",
        source,
    )


def test_issue34_setup_controls_and_action_labels_use_selected_language():
    source = SETUP_TEMPLATE_PATH.read_text(encoding="utf-8")

    required_control_hooks = {
        "setup.action.save_required_inputs",
        "setup.action.continue_optional_interests",
        "setup.action.skip_default_criteria",
        "setup.action.continue_with_interests",
        "setup.action.enter_key_continue",
        "setup.action.start_first_collection",
        "setup.action.enter_key_start_collection",
        "setup.action.retry_first_collection",
        "setup.action.refresh_status",
        "setup.action.configure_delivery",
        "setup.action.configure_source_keys",
        "setup.action.open_detailed_source_settings",
        "setup.action.save_source_toggles",
        "setup.action.create_supabase_tables",
        "setup.action.save_delivery_settings",
        "setup.action.test_delivery_settings",
        "setup.action.save_source_api_keys",
        "setup.action.save_model_backend_settings",
        "setup.action.download_algorithm_bundle",
        "setup.action.dry_run_import",
        "setup.action.confirm_import",
        "setup.action.test_all_keys",
        "setup.action.save_all",
        "setup.control.import_algorithm_bundle",
    }
    wired_hooks = set(
        re.findall(
            r'data-(?:setup-i18n|ready-i18n|missing-key-i18n|unsaved-i18n)="([^"]+)"',
            source,
        )
    )
    assert required_control_hooks <= wired_hooks

    for hook in wired_hooks:
        if hook.startswith(("setup.action.", "setup.control.")):
            assert f"'{hook}':" in source

    expected_localized_controls = {
        "ko": [
            "'setup.action.save_required_inputs': '필수 입력 저장'",
            "'setup.action.start_first_collection': '첫 수집 시작'",
            "'setup.action.configure_delivery': 'Delivery 채널 설정'",
            "'setup.control.import_algorithm_bundle': '알고리즘 번들 가져오기'",
        ],
        "zh": [
            "'setup.action.save_required_inputs': '保存必需输入'",
            "'setup.action.start_first_collection': '启动首次收集'",
            "'setup.action.configure_delivery': '配置 delivery 渠道'",
            "'setup.control.import_algorithm_bundle': '导入算法包'",
        ],
        "en": [
            "'setup.action.save_required_inputs': 'Save required inputs'",
            "'setup.action.start_first_collection': 'Start first collection'",
            "'setup.action.configure_delivery': 'Configure delivery channels'",
            "'setup.control.import_algorithm_bundle': 'Import algorithm bundle'",
        ],
    }
    for language, snippets in expected_localized_controls.items():
        language_block = source.split(f"{language}: {{", 1)[1].split("\n  },", 1)[0]
        for snippet in snippets:
            assert snippet in language_block

    assert re.search(
        r"const readyLabel = button\.dataset\.readyI18n[\s\S]*?"
        r"setupPageText\(button\.dataset\.readyI18n,[\s\S]*?"
        r"const missingKeyLabel = button\.dataset\.missingKeyI18n[\s\S]*?"
        r"setupPageText\(button\.dataset\.missingKeyI18n,[\s\S]*?"
        r"button\.textContent = enabled \? readyLabel : missingKeyLabel;",
        source,
    )


def test_issue34_i18n_hooks_cover_shell_setup_feed_and_brief_entrypoints():
    templates = {
        "base": _base_template(),
        "setup": SETUP_TEMPLATE_PATH.read_text(encoding="utf-8"),
        "feed": FEED_TEMPLATE_PATH.read_text(encoding="utf-8"),
        "brief": BRIEF_TEMPLATE_PATH.read_text(encoding="utf-8"),
    }

    required_hooks = {
        "base": ["nav.setup", "nav.feed", "nav.brief", "nav.chat", "footer.tagline"],
        "setup": ["setup.title", "setup.subtitle", "setup.primary", "setup.advanced"],
        "feed": ["feed.title", "feed.subtitle", "feed.controls"],
        "brief": ["brief.title", "brief.subtitle", "brief.empty"],
    }
    for template_name, hooks in required_hooks.items():
        for hook in hooks:
            assert f'data-i18n="{hook}"' in templates[template_name]

    for language in ("ko", "zh", "en"):
        assert f"{language}: {{" in templates["base"]


def test_issue34_feed_entrypoint_labels_and_descriptions_are_localized():
    base = _base_template()
    feed = FEED_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'data-feed-entrypoint-i18n="HEDWIG_LANGUAGE_STATE"' in feed
    assert 'data-i18n-aria-label="feed.entry.nav_label"' in feed

    entrypoint_keys = {
        "feed.entry.nav_label": {
            "ko": "피드 이후 주요 경로",
            "zh": "信息流后的主要路径",
            "en": "Post-setup feed navigation",
        },
        "feed.entry.chat.label": {
            "ko": "채팅",
            "zh": "聊天",
            "en": "Chat",
        },
        "feed.entry.chat.description": {
            "ko": "자연어로 Hedwig의 방향을 조정합니다.",
            "zh": "用自然语言调校 Hedwig。",
            "en": "Steer Hedwig in natural language.",
        },
        "feed.entry.profile.label": {
            "ko": "프로필",
            "zh": "个人资料",
            "en": "Profile",
        },
        "feed.entry.profile.description": {
            "ko": "선호도와 내보내기 화면을 확인합니다.",
            "zh": "查看偏好和导出界面。",
            "en": "Review preferences and export surfaces.",
        },
        "feed.entry.status.label": {
            "ko": "상태",
            "zh": "状态",
            "en": "Status",
        },
        "feed.entry.status.description": {
            "ko": "준비 상태와 런타임 상태를 확인합니다.",
            "zh": "检查准备情况和运行状态。",
            "en": "Check readiness and runtime health.",
        },
    }

    for key, translations in entrypoint_keys.items():
        assert f'data-i18n="{key}"' in feed or f'data-i18n-aria-label="{key}"' in feed
        for language, translation in translations.items():
            language_block = base.split(f"{language}: {{", 1)[1].split(
                "\n      }",
                1,
            )[0]
            assert f'"{key}": "{translation}"' in language_block


def test_issue34_feed_entrypoint_actions_are_localized():
    base = _base_template()
    feed = FEED_TEMPLATE_PATH.read_text(encoding="utf-8")

    action_keys = {
        "feed.actions_label": {"ko": "피드 작업", "zh": "信息流操作", "en": "Feed actions"},
        "feed.mode.grid": {"ko": "그리드", "zh": "网格", "en": "Grid"},
        "feed.mode.detail_swipe": {
            "ko": "상세 스와이프",
            "zh": "滑动详情",
            "en": "Detail Swipe",
        },
        "feed.mode.dense_reader": {
            "ko": "Dense Reader",
            "zh": "Dense Reader",
            "en": "Dense Reader",
        },
        "feed.action.refresh_sync": {
            "ko": "지금 새로고침/동기화",
            "zh": "立即刷新/同步",
            "en": "Refresh / sync now",
        },
        "feed.action.reload": {
            "ko": "피드 다시 불러오기",
            "zh": "重新加载信息流",
            "en": "Reload feed",
        },
        "feed.item.open": {"ko": "열기", "zh": "打开", "en": "Open"},
        "feed.item.open_label": {
            "ko": "항목 원본 열기",
            "zh": "打开条目来源",
            "en": "Open item source",
        },
        "feed.item.read": {"ko": "읽음 표시", "zh": "标记已读", "en": "Mark read"},
        "feed.item.read_label": {
            "ko": "항목을 읽음으로 표시",
            "zh": "将条目标记为已读",
            "en": "Mark item as read",
        },
        "feed.item.save": {
            "ko": "왼쪽: 저장/나중에",
            "zh": "左滑：保存/稍后",
            "en": "Left: save/later",
        },
        "feed.item.save_label": {
            "ko": "나중에 볼 항목으로 저장",
            "zh": "保存条目稍后查看",
            "en": "Save item for later",
        },
        "feed.item.dismiss": {"ko": "숨기기", "zh": "忽略", "en": "Dismiss"},
        "feed.item.dismiss_label": {
            "ko": "항목 숨기기",
            "zh": "忽略条目",
            "en": "Dismiss item",
        },
        "feed.item.next": {
            "ko": "오른쪽/다음: 건너뛰기",
            "zh": "右滑/下一个：跳过",
            "en": "Right/next: skip",
        },
        "feed.item.not_interested": {
            "ko": "관심 없음",
            "zh": "不感兴趣",
            "en": "Not interested",
        },
        "feed.item.dense": {"ko": "Dense", "zh": "Dense", "en": "Dense"},
        "feed.item.qa": {"ko": "질문", "zh": "提问", "en": "Ask"},
    }

    for key, translations in action_keys.items():
        assert f'data-i18n="{key}"' in feed or f'data-i18n-aria-label="{key}"' in feed
        for language, translation in translations.items():
            language_block = base.split(f"{language}: {{", 1)[1].split(
                "\n      }",
                1,
            )[0]
            assert f'"{key}": "{translation}"' in language_block

    assert "renderFeedLocalizedContent()" in feed
    assert "window.addEventListener('hedwig:languagechange', renderFeedLocalizedContent)" in feed


def test_issue34_feed_entrypoint_rerenders_immediately_on_language_change():
    base = _base_template()
    feed = FEED_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "window.HEDWIG_I18N = HEDWIG_I18N;" in base
    assert "window.HEDWIG_LANGUAGE_STATE = HEDWIG_LANGUAGE_STATE;" in base
    assert re.search(
        r"function renderFeedLocalizedContent\(\) \{[\s\S]*?"
        r"window\.HEDWIG_LANGUAGE_STATE\?\.dictionary[\s\S]*?"
        r"data-feed-entrypoint-i18n[\s\S]*?"
        r"data-post-setup-feed-actions[\s\S]*?"
        r"node\.textContent = text;[\s\S]*?"
        r"data-i18n-aria-label[\s\S]*?"
        r"node\.setAttribute\('aria-label', text\);[\s\S]*?"
        r"renderHedwigLocalizedShell\(\);",
        feed,
    )
    assert re.search(
        r"window\.addEventListener\('hedwig:languagechange', renderFeedLocalizedContent\);",
        feed,
    )


def test_issue34_brief_entrypoint_labels_and_descriptions_are_localized():
    base = _base_template()
    brief = BRIEF_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert 'data-brief-entrypoint-i18n="HEDWIG_LANGUAGE_STATE"' in brief
    assert 'data-i18n-aria-label="brief.entry.nav_label"' in brief

    entrypoint_keys = {
        "brief.entry.nav_label": {
            "ko": "브리프 이후 주요 경로",
            "zh": "简报后的主要路径",
            "en": "Post-brief navigation",
        },
        "brief.nav_lead": {
            "ko": "브리프는 요약 소비 화면입니다. 더 읽거나 질문하거나 변화 흐름을 확인하세요.",
            "zh": "简报是摘要阅读界面。继续阅读、提问，或查看变化趋势。",
            "en": "Brief is the summary surface. Continue reading, ask questions, or review how recommendations are shifting.",
        },
        "brief.entry.feed.label": {
            "ko": "피드",
            "zh": "信息流",
            "en": "Feed",
        },
        "brief.entry.feed.description": {
            "ko": "브리프를 만든 원본 시그널 카드로 돌아갑니다.",
            "zh": "回到生成简报的原始信号卡片。",
            "en": "Return to the source signal cards behind the briefing.",
        },
        "brief.entry.chat.label": {
            "ko": "채팅",
            "zh": "聊天",
            "en": "Chat",
        },
        "brief.entry.chat.description": {
            "ko": "브리핑 내용을 자연어로 더 파고듭니다.",
            "zh": "用自然语言深入追问这份简报。",
            "en": "Ask natural-language follow-up questions about a briefing.",
        },
        "brief.entry.evolution.label": {
            "ko": "진화",
            "zh": "演化",
            "en": "Evolution",
        },
        "brief.entry.evolution.description": {
            "ko": "추천 방향이 시간에 따라 어떻게 바뀌는지 봅니다.",
            "zh": "查看推荐方向如何随时间变化。",
            "en": "Review how recommendation direction changes over time.",
        },
    }

    for key, translations in entrypoint_keys.items():
        assert f'data-i18n="{key}"' in brief or f'data-i18n-aria-label="{key}"' in brief
        for language, translation in translations.items():
            language_block = base.split(f"{language}: {{", 1)[1].split(
                "\n      }",
                1,
            )[0]
            assert f'"{key}": "{translation}"' in language_block


def test_issue34_brief_entrypoint_actions_are_localized():
    base = _base_template()
    brief = BRIEF_TEMPLATE_PATH.read_text(encoding="utf-8")

    action_keys = {
        "brief.actions_label": {
            "ko": "브리프 작업",
            "zh": "简报操作",
            "en": "Brief actions",
        },
        "brief.controls": {
            "ko": "브리프 컨트롤",
            "zh": "简报控制",
            "en": "Brief controls",
        },
        "brief.controls_help": {
            "ko": "전체, 일간, 주간 브리프를 빠르게 전환합니다.",
            "zh": "快速切换全部、每日和每周简报。",
            "en": "Switch quickly between all, daily, and weekly briefs.",
        },
        "brief.all": {"ko": "전체", "zh": "全部", "en": "All"},
        "brief.daily": {"ko": "일간", "zh": "每日", "en": "Daily"},
        "brief.weekly": {"ko": "주간", "zh": "每周", "en": "Weekly"},
        "brief.full_text": {
            "ko": "원문 전체 보기",
            "zh": "查看完整原文",
            "en": "View full original",
        },
        "brief.action.deep_chat": {
            "ko": "Chat에서 더 깊이",
            "zh": "在聊天中深入",
            "en": "Go deeper in Chat",
        },
        "brief.action.evolution": {
            "ko": "evolution timeline",
            "zh": "演化时间线",
            "en": "Evolution timeline",
        },
        "brief.empty.run_daily": {
            "ko": "홈 또는 Chat에서 daily 파이프라인 실행을 요청하세요.",
            "zh": "在首页或聊天中请求运行 daily 流水线。",
            "en": "Ask Home or Chat to run the daily pipeline.",
        },
        "brief.empty.run_local": {
            "ko": "또는 python -m hedwig를 1회 실행해 daily brief를 생성하세요.",
            "zh": "或运行一次 python -m hedwig 来生成 daily brief。",
            "en": "Or run python -m hedwig once to generate a daily brief.",
        },
        "brief.empty.run_weekly": {
            "ko": "주간은 python -m hedwig --weekly를 실행하세요.",
            "zh": "每周简报请运行 python -m hedwig --weekly。",
            "en": "For weekly briefings, run python -m hedwig --weekly.",
        },
    }

    assert 'data-i18n-aria-label="brief.actions_label"' in brief
    assert "data-brief-actions" in brief
    for key, translations in action_keys.items():
        assert f'data-i18n="{key}"' in brief or f'data-i18n-aria-label="{key}"' in brief
        for language, translation in translations.items():
            language_block = base.split(f"{language}: {{", 1)[1].split(
                "\n      }",
                1,
            )[0]
            assert f'"{key}": "{translation}"' in language_block

    assert "renderBriefLocalizedContent()" in brief
    assert "window.addEventListener('hedwig:languagechange', renderBriefLocalizedContent)" in brief


def test_issue34_brief_entrypoint_rerenders_immediately_on_language_change():
    base = _base_template()
    brief = BRIEF_TEMPLATE_PATH.read_text(encoding="utf-8")

    assert "window.HEDWIG_I18N = HEDWIG_I18N;" in base
    assert "window.HEDWIG_LANGUAGE_STATE = HEDWIG_LANGUAGE_STATE;" in base
    assert re.search(
        r"function renderBriefLocalizedContent\(\) \{[\s\S]*?"
        r"window\.HEDWIG_LANGUAGE_STATE\?\.dictionary[\s\S]*?"
        r"data-brief-entrypoint-i18n[\s\S]*?"
        r"data-brief-actions[\s\S]*?"
        r"node\.textContent = text;[\s\S]*?"
        r"data-i18n-aria-label[\s\S]*?"
        r"node\.setAttribute\('aria-label', text\);[\s\S]*?"
        r"renderHedwigLocalizedShell\(\);",
        brief,
    )
    assert re.search(
        r"window\.addEventListener\('hedwig:languagechange', renderBriefLocalizedContent\);",
        brief,
    )


ISSUE34_LEGACY_SQLITE_TABLE_COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    "behavior_events": (
        ("id", "id INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("signal_id", "signal_id TEXT NOT NULL"),
        ("event_type", "event_type TEXT NOT NULL"),
        ("dwell_ms", "dwell_ms INTEGER"),
        ("position_in_feed", "position_in_feed INTEGER"),
        ("feed_id", "feed_id TEXT DEFAULT 'default'"),
        ("feed_mode", "feed_mode TEXT DEFAULT 'grid'"),
        ("device", "device TEXT"),
        ("captured_at", "captured_at TEXT DEFAULT CURRENT_TIMESTAMP"),
    ),
    "behavior_rewards": (
        ("id", "id INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("signal_id", "signal_id TEXT NOT NULL"),
        ("raw_event_id", "raw_event_id INTEGER"),
        ("event_type", "event_type TEXT NOT NULL"),
        ("reward_value", "reward_value REAL NOT NULL"),
        ("signal_strength", "signal_strength TEXT NOT NULL"),
        ("feed_mode", "feed_mode TEXT DEFAULT 'grid'"),
        ("created_at", "created_at TEXT DEFAULT CURRENT_TIMESTAMP"),
    ),
    "briefings": (
        ("id", "id INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("cycle_type", "cycle_type TEXT NOT NULL"),
        ("content", "content TEXT NOT NULL"),
        ("signal_count", "signal_count INTEGER DEFAULT 0"),
        ("generated_at", "generated_at TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("structured", "structured TEXT DEFAULT '{}'"),
    ),
}


def _create_legacy_sqlite_db_missing_columns(
    db_path: Path,
    missing_columns_by_table: dict[str, set[str]],
) -> dict[str, set[str]]:
    """Create a local DB that looks like an older install before migrations."""
    assert any(missing_columns_by_table.values())

    with sqlite3.connect(db_path) as conn:
        for table_name, column_definitions in (
            ISSUE34_LEGACY_SQLITE_TABLE_COLUMNS.items()
        ):
            missing_columns = missing_columns_by_table.get(table_name, set())
            known_columns = {name for name, _definition in column_definitions}
            assert missing_columns <= known_columns

            kept_column_sql = [
                definition
                for name, definition in column_definitions
                if name not in missing_columns
            ]
            conn.execute(
                f"""
                CREATE TABLE {table_name} (
                    {", ".join(kept_column_sql)}
                )
                """
            )

    return {
        table_name: set(missing_columns_by_table.get(table_name, set()))
        for table_name in ISSUE34_LEGACY_SQLITE_TABLE_COLUMNS
    }


def _create_old_local_db_missing_feed_mode(db_path: Path) -> None:
    _create_legacy_sqlite_db_missing_columns(
        db_path,
        {
            "behavior_events": {"feed_mode"},
            "behavior_rewards": {"feed_mode"},
            "briefings": {"structured"},
        },
    )


def _read_rows(db_path: Path, table_name: str, columns: tuple[str, ...]) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        column_list = ", ".join(columns)
        rows = conn.execute(
            f"SELECT {column_list} FROM {table_name} ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def _seed_old_local_db_data(db_path: Path) -> dict[str, list[dict]]:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO behavior_events (
                id, signal_id, event_type, dwell_ms, position_in_feed,
                feed_id, device, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    7,
                    "legacy-signal-1",
                    "viewed_card",
                    4200,
                    3,
                    "daily-main",
                    "desktop",
                    "2026-05-01T09:00:00+00:00",
                ),
                (
                    8,
                    "legacy-signal-2",
                    "click_link",
                    None,
                    4,
                    "daily-main",
                    "mobile",
                    "2026-05-01T09:05:00+00:00",
                ),
            ],
        )
        conn.execute(
            """
            INSERT INTO behavior_rewards (
                id, signal_id, raw_event_id, event_type, reward_value,
                signal_strength, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                13,
                "legacy-signal-1",
                7,
                "viewed_card",
                0.5,
                "medium",
                "2026-05-01T09:01:00+00:00",
            ),
        )
        conn.execute(
            """
            INSERT INTO briefings (
                id, cycle_type, content, signal_count, generated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                21,
                "daily",
                "Existing local briefing content",
                2,
                "2026-05-01T10:00:00+00:00",
            ),
        )

    return {
        "behavior_events": _read_rows(
            db_path,
            "behavior_events",
            (
                "id",
                "signal_id",
                "event_type",
                "dwell_ms",
                "position_in_feed",
                "feed_id",
                "device",
                "captured_at",
            ),
        ),
        "behavior_rewards": _read_rows(
            db_path,
            "behavior_rewards",
            (
                "id",
                "signal_id",
                "raw_event_id",
                "event_type",
                "reward_value",
                "signal_strength",
                "created_at",
            ),
        ),
        "briefings": _read_rows(
            db_path,
            "briefings",
            ("id", "cycle_type", "content", "signal_count", "generated_at"),
        ),
    }


def _build_issue34_sqlite_db_fixture(root: Path, fixture_name: str) -> dict:
    """Build one named DB state in its own directory for route mutation tests."""
    scenario_dir = root / fixture_name
    scenario_dir.mkdir(parents=True, exist_ok=False)
    db_path = scenario_dir / "hedwig.db"

    if fixture_name == "fresh":
        return {
            "path": db_path,
            "description": "new install with no SQLite file yet",
            "expected_briefings": [],
        }

    if fixture_name == "empty":
        sqlite3.connect(db_path).close()
        return {
            "path": db_path,
            "description": "existing empty SQLite file with no schema",
            "expected_briefings": [],
        }

    if fixture_name == "older":
        _create_old_local_db_missing_feed_mode(db_path)
        older_expected_rows = _seed_old_local_db_data(db_path)
        return {
            "path": db_path,
            "description": "pre-migration local schema with existing brief data",
            "expected_briefings": older_expected_rows["briefings"],
        }

    raise AssertionError(f"Unknown issue34 SQLite fixture: {fixture_name}")


@pytest.fixture
def issue34_legacy_sqlite_db_factory(tmp_path):
    """Build legacy SQLite DBs with caller-selected expected columns absent."""

    def build_legacy_db(
        missing_columns_by_table: dict[str, set[str]],
        *,
        name: str = "legacy-missing-columns.db",
    ) -> dict:
        db_path = tmp_path / name
        normalized_missing_columns = {
            table_name: set(columns)
            for table_name, columns in missing_columns_by_table.items()
        }
        actual_missing_columns = _create_legacy_sqlite_db_missing_columns(
            db_path,
            normalized_missing_columns,
        )
        expected_columns = {
            table_name: {name for name, _definition in column_definitions}
            for table_name, column_definitions in
            ISSUE34_LEGACY_SQLITE_TABLE_COLUMNS.items()
        }
        return {
            "path": db_path,
            "expected_columns": expected_columns,
            "missing_columns": actual_missing_columns,
        }

    return build_legacy_db


@pytest.fixture
def issue34_sqlite_db_fixtures(tmp_path):
    """Named local DB states used to verify Brief recovery paths."""
    return {
        fixture_name: _build_issue34_sqlite_db_fixture(tmp_path, fixture_name)
        for fixture_name in ("fresh", "empty", "older")
    }


def test_issue34_sqlite_fixture_states_cover_fresh_empty_and_older_databases(
    issue34_sqlite_db_fixtures,
):
    fixtures = issue34_sqlite_db_fixtures

    assert set(fixtures) == {"fresh", "empty", "older"}
    assert fixtures["fresh"]["path"].exists() is False

    with sqlite3.connect(fixtures["empty"]["path"]) as conn:
        empty_tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()

    with sqlite3.connect(fixtures["older"]["path"]) as conn:
        older_behavior_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        }
        older_brief_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        }
        older_briefings = conn.execute(
            "SELECT id, cycle_type, content, signal_count, generated_at "
            "FROM briefings ORDER BY id"
        ).fetchall()

    assert empty_tables == []
    assert "feed_mode" not in older_behavior_columns
    assert "structured" not in older_brief_columns
    assert [tuple(row) for row in older_briefings] == [
        (
            row["id"],
            row["cycle_type"],
            row["content"],
            row["signal_count"],
            row["generated_at"],
        )
        for row in fixtures["older"]["expected_briefings"]
    ]


def test_issue34_legacy_sqlite_db_factory_creates_missing_column_databases(
    issue34_legacy_sqlite_db_factory,
):
    fixture = issue34_legacy_sqlite_db_factory(
        {
            "behavior_events": {"feed_mode"},
            "briefings": {"structured", "generated_at"},
        },
    )
    db_path = fixture["path"]

    with sqlite3.connect(db_path) as conn:
        behavior_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        }
        reward_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_rewards)")
        }
        brief_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        }

    assert fixture["missing_columns"] == {
        "behavior_events": {"feed_mode"},
        "behavior_rewards": set(),
        "briefings": {"structured", "generated_at"},
    }
    assert "feed_mode" not in behavior_columns
    assert "feed_mode" in reward_columns
    assert "structured" not in brief_columns
    assert "generated_at" not in brief_columns
    assert behavior_columns == (
        fixture["expected_columns"]["behavior_events"] - {"feed_mode"}
    )
    assert brief_columns == (
        fixture["expected_columns"]["briefings"] - {"structured", "generated_at"}
    )


def test_issue34_sqlite_fixture_states_are_isolated_between_brief_scenarios(
    tmp_path,
    monkeypatch,
    issue34_sqlite_db_fixtures,
):
    fixtures = issue34_sqlite_db_fixtures
    fixture_paths = [fixture["path"] for fixture in fixtures.values()]

    assert len({path.parent for path in fixture_paths}) == len(fixture_paths)

    fresh_db = fixtures["fresh"]["path"]
    empty_db = fixtures["empty"]["path"]
    older_db = fixtures["older"]["path"]

    with sqlite3.connect(empty_db) as conn:
        empty_tables_before = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    with sqlite3.connect(older_db) as conn:
        older_behavior_columns_before = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        }
        older_brief_columns_before = {
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        }
        older_briefings_before = conn.execute(
            "SELECT id, cycle_type, content, signal_count, generated_at "
            "FROM briefings ORDER BY id"
        ).fetchall()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(fresh_db))

    from hedwig.dashboard.app import create_app

    response = TestClient(create_app()).get("/brief")

    assert response.status_code == 200
    assert fresh_db.exists()

    with sqlite3.connect(empty_db) as conn:
        empty_tables_after = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    with sqlite3.connect(older_db) as conn:
        older_behavior_columns_after = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        }
        older_brief_columns_after = {
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        }
        older_briefings_after = conn.execute(
            "SELECT id, cycle_type, content, signal_count, generated_at "
            "FROM briefings ORDER BY id"
        ).fetchall()

    assert empty_tables_after == empty_tables_before == []
    assert older_behavior_columns_after == older_behavior_columns_before
    assert older_brief_columns_after == older_brief_columns_before
    assert "feed_mode" not in older_behavior_columns_after
    assert "structured" not in older_brief_columns_after
    assert older_briefings_after == older_briefings_before


def test_issue34_sqlite_migration_adds_feed_mode_before_index_creation(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "old-hedwig.db"
    _create_old_local_db_missing_feed_mode(db_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    local_storage.init_db()

    with sqlite3.connect(db_path) as conn:
        behavior_event_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        }
        behavior_reward_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_rewards)")
        }
        brief_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        }
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(behavior_events)").fetchall()
        }

    assert "feed_mode" in behavior_event_columns
    assert "feed_mode" in behavior_reward_columns
    assert "structured" in brief_columns
    assert "idx_behavior_mode" in indexes


def test_issue34_sqlite_migration_adds_all_index_referenced_columns_first(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "older-indexed-tables.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_type TEXT NOT NULL DEFAULT 'daily',
                status TEXT NOT NULL DEFAULT 'queued'
            );
            CREATE TABLE run_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_type TEXT NOT NULL
            );
            CREATE TABLE source_reliability (
                platform TEXT PRIMARY KEY
            );
            """
        )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    local_storage.init_db()

    with sqlite3.connect(db_path) as conn:
        collection_run_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(collection_runs)")
        }
        run_history_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(run_history)")
        }
        source_reliability_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(source_reliability)")
        }
        collection_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(collection_runs)").fetchall()
        }
        run_history_indexes = {
            row[1] for row in conn.execute("PRAGMA index_list(run_history)").fetchall()
        }
        reliability_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(source_reliability)").fetchall()
        }

    assert "last_updated_at" in collection_run_columns
    assert "run_at" in run_history_columns
    assert "updated_at" in source_reliability_columns
    assert "idx_collection_runs_updated" in collection_indexes
    assert "idx_run_history_run_at" in run_history_indexes
    assert "idx_source_reliability_updated_at" in reliability_indexes
    assert local_storage.get_latest_collection_progress() == {}
    assert local_storage.get_run_stats()["total_daily_cycles"] == 0
    assert local_storage.get_source_reliability() == {}


def test_issue34_sqlite_schema_initialization_is_repeatable_without_duplicate_mutations(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "repeat-old-hedwig.db"
    _create_old_local_db_missing_feed_mode(db_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    alter_statements: list[str] = []

    def traced_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.set_trace_callback(
            lambda statement: alter_statements.append(statement)
            if statement.lstrip().upper().startswith("ALTER TABLE")
            else None
        )
        return conn

    monkeypatch.setattr(local_storage, "_conn", traced_conn)

    local_storage.init_db()
    local_storage.init_db()

    normalized_alters = [
        " ".join(statement.strip().split()) for statement in alter_statements
    ]
    assert len(normalized_alters) == len(set(normalized_alters))

    with sqlite3.connect(db_path) as conn:
        behavior_event_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        ]
        behavior_reward_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(behavior_rewards)")
        ]
        brief_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        ]
        behavior_indexes = [
            row[1]
            for row in conn.execute("PRAGMA index_list(behavior_events)").fetchall()
        ]

    assert behavior_event_columns.count("feed_mode") == 1
    assert behavior_reward_columns.count("feed_mode") == 1
    assert brief_columns.count("structured") == 1
    assert behavior_indexes.count("idx_behavior_mode") == 1


def test_issue34_repeated_sqlite_migration_preserves_existing_legacy_rows(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "repeat-old-hedwig-with-data.db"
    _create_old_local_db_missing_feed_mode(db_path)
    expected_rows = _seed_old_local_db_data(db_path)

    with sqlite3.connect(db_path) as conn:
        legacy_columns_before = {
            "behavior_events": {
                row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
            },
            "behavior_rewards": {
                row[1] for row in conn.execute("PRAGMA table_info(behavior_rewards)")
            },
            "briefings": {
                row[1] for row in conn.execute("PRAGMA table_info(briefings)")
            },
        }

    assert "feed_mode" not in legacy_columns_before["behavior_events"]
    assert "feed_mode" not in legacy_columns_before["behavior_rewards"]
    assert "structured" not in legacy_columns_before["briefings"]

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    local_storage.init_db()
    local_storage.init_db()

    assert _read_rows(
        db_path,
        "behavior_events",
        (
            "id",
            "signal_id",
            "event_type",
            "dwell_ms",
            "position_in_feed",
            "feed_id",
            "device",
            "captured_at",
        ),
    ) == expected_rows["behavior_events"]
    assert _read_rows(
        db_path,
        "behavior_rewards",
        (
            "id",
            "signal_id",
            "raw_event_id",
            "event_type",
            "reward_value",
            "signal_strength",
            "created_at",
        ),
    ) == expected_rows["behavior_rewards"]
    assert _read_rows(
        db_path,
        "briefings",
        ("id", "cycle_type", "content", "signal_count", "generated_at"),
    ) == expected_rows["briefings"]

    with sqlite3.connect(db_path) as conn:
        migrated_columns = {
            "behavior_events": {
                row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
            },
            "behavior_rewards": {
                row[1] for row in conn.execute("PRAGMA table_info(behavior_rewards)")
            },
            "briefings": {
                row[1] for row in conn.execute("PRAGMA table_info(briefings)")
            },
        }
        event_count = conn.execute("SELECT COUNT(*) FROM behavior_events").fetchone()[0]
        reward_count = conn.execute(
            "SELECT COUNT(*) FROM behavior_rewards"
        ).fetchone()[0]
        briefing_count = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]
        migrated_event_feed_modes = conn.execute(
            "SELECT feed_mode FROM behavior_events ORDER BY id"
        ).fetchall()
        migrated_reward_feed_modes = conn.execute(
            "SELECT feed_mode FROM behavior_rewards ORDER BY id"
        ).fetchall()
        migrated_brief_structures = conn.execute(
            "SELECT structured FROM briefings ORDER BY id"
        ).fetchall()

    assert legacy_columns_before["behavior_events"] | {"feed_mode"} <= migrated_columns[
        "behavior_events"
    ]
    assert legacy_columns_before["behavior_rewards"] | {"feed_mode"} <= migrated_columns[
        "behavior_rewards"
    ]
    assert legacy_columns_before["briefings"] | {"structured"} <= migrated_columns[
        "briefings"
    ]
    assert event_count == 2
    assert reward_count == 1
    assert briefing_count == 1
    assert [row[0] for row in migrated_event_feed_modes] == ["grid", "grid"]
    assert [row[0] for row in migrated_reward_feed_modes] == ["grid"]
    assert [row[0] for row in migrated_brief_structures] == ["{}"]


def test_issue34_local_sqlite_setup_migration_can_run_multiple_times(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "repeat-setup-migration.db"
    _create_old_local_db_missing_feed_mode(db_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.db_setup import ensure_local_sqlite_schema

    completed_runs: list[int] = []
    schema_states: list[dict] = []
    for run_number in range(1, 4):
        schema_states.append(ensure_local_sqlite_schema())
        completed_runs.append(run_number)

    assert completed_runs == [1, 2, 3]
    for state in schema_states:
        assert state["schema_ready"] is True
        assert state["missing_tables"] == []
        assert state["missing_columns"] == {}

    with sqlite3.connect(db_path) as conn:
        behavior_event_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        ]
        behavior_reward_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(behavior_rewards)")
        ]
        brief_columns = [
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        ]
        behavior_indexes = [
            row[1]
            for row in conn.execute("PRAGMA index_list(behavior_events)").fetchall()
        ]

    assert behavior_event_columns.count("feed_mode") == 1
    assert behavior_reward_columns.count("feed_mode") == 1
    assert brief_columns.count("structured") == 1
    assert behavior_indexes.count("idx_behavior_mode") == 1


def test_issue34_app_migration_path_recovers_legacy_sqlite_before_brief_route(
    tmp_path,
    monkeypatch,
    issue34_sqlite_db_fixtures,
):
    db_path = issue34_sqlite_db_fixtures["older"]["path"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.db_setup import ensure_local_sqlite_schema

    schema_state = ensure_local_sqlite_schema()
    response = TestClient(
        create_app(),
        raise_server_exceptions=True,
    ).get("/brief?cycle=daily")

    assert schema_state["schema_ready"] is True
    assert schema_state["missing_tables"] == []
    assert schema_state["missing_columns"] == {}
    assert response.status_code == 200
    assert "Existing local briefing content" in response.text

    with sqlite3.connect(db_path) as conn:
        behavior_event_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_events)")
        }
        behavior_reward_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(behavior_rewards)")
        }
        brief_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        }
        behavior_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(behavior_events)").fetchall()
        }
        migrated_brief = conn.execute(
            """
            SELECT cycle_type, content, signal_count, generated_at, structured
            FROM briefings WHERE id = 21
            """
        ).fetchone()

    assert "feed_mode" in behavior_event_columns
    assert "feed_mode" in behavior_reward_columns
    assert "structured" in brief_columns
    assert "idx_behavior_mode" in behavior_indexes
    assert tuple(migrated_brief) == (
        "daily",
        "Existing local briefing content",
        2,
        "2026-05-01T10:00:00+00:00",
        "{}",
    )


def test_issue34_sqlite_migration_skips_columns_already_present(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "partial-old-hedwig.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE behavior_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                feed_mode TEXT DEFAULT 'grid',
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE behavior_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                raw_event_id INTEGER,
                event_type TEXT NOT NULL,
                reward_value REAL NOT NULL,
                signal_strength TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    alter_statements: list[str] = []

    def traced_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.set_trace_callback(
            lambda statement: alter_statements.append(statement)
            if statement.lstrip().upper().startswith("ALTER TABLE")
            else None
        )
        return conn

    monkeypatch.setattr(local_storage, "_conn", traced_conn)

    local_storage.init_db()
    local_storage.init_db()

    behavior_event_feed_mode_alters = [
        statement
        for statement in alter_statements
        if "ALTER TABLE behavior_events ADD COLUMN feed_mode" in statement
    ]
    behavior_reward_feed_mode_alters = [
        statement
        for statement in alter_statements
        if "ALTER TABLE behavior_rewards ADD COLUMN feed_mode" in statement
    ]

    assert behavior_event_feed_mode_alters == []
    assert len(behavior_reward_feed_mode_alters) == 1


def test_issue34_sqlite_migration_backfills_null_feed_mode_defaults(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "nullable-feed-mode-hedwig.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE behavior_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                feed_mode TEXT,
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE behavior_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                raw_event_id INTEGER,
                event_type TEXT NOT NULL,
                reward_value REAL NOT NULL,
                signal_strength TEXT NOT NULL,
                feed_mode TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO behavior_events (signal_id, event_type, feed_mode)
            VALUES ('legacy-null-event', 'viewed_card', NULL);
            INSERT INTO behavior_rewards (
                signal_id, raw_event_id, event_type, reward_value,
                signal_strength, feed_mode
            ) VALUES ('legacy-null-reward', 1, 'viewed_card', 0.5, 'medium', NULL);
            """
        )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    local_storage.init_db()
    local_storage.init_db()

    with sqlite3.connect(db_path) as conn:
        event_feed_modes = conn.execute(
            "SELECT feed_mode FROM behavior_events ORDER BY id"
        ).fetchall()
        reward_feed_modes = conn.execute(
            "SELECT feed_mode FROM behavior_rewards ORDER BY id"
        ).fetchall()

    assert [row[0] for row in event_feed_modes] == ["grid"]
    assert [row[0] for row in reward_feed_modes] == ["grid"]
    assert local_storage.get_behavior_events(feed_mode="grid")[0]["signal_id"] == (
        "legacy-null-event"
    )
    assert local_storage.get_behavior_rewards(feed_mode="grid")[0]["signal_id"] == (
        "legacy-null-reward"
    )


def test_issue34_behavior_read_paths_default_absent_newer_columns(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "pre-feed-mode-read-paths.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE behavior_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                captured_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE behavior_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                raw_event_id INTEGER,
                event_type TEXT NOT NULL,
                reward_value REAL NOT NULL,
                signal_strength TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO behavior_events (signal_id, event_type, captured_at)
            VALUES ('legacy-missing-event', 'viewed_card', '2026-05-01T09:00:00+00:00');
            INSERT INTO behavior_rewards (
                signal_id, raw_event_id, event_type, reward_value,
                signal_strength, created_at
            ) VALUES (
                'legacy-missing-reward', 1, 'viewed_card', 0.5, 'medium',
                '2026-05-01T09:01:00+00:00'
            );
            """
        )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    monkeypatch.setattr(local_storage, "init_db", lambda: None)

    events = local_storage.get_behavior_events(feed_mode="grid")
    rewards = local_storage.get_behavior_rewards(feed_mode="grid")

    assert events[0]["signal_id"] == "legacy-missing-event"
    assert events[0]["feed_id"] == "default"
    assert events[0]["feed_mode"] == "grid"
    assert rewards[0]["signal_id"] == "legacy-missing-reward"
    assert rewards[0]["feed_mode"] == "grid"
    assert rewards[0]["source_event_ids"] == []
    assert rewards[0]["policy_version"] == 1
    assert local_storage.get_behavior_events(feed_mode="dense_reader") == []
    assert local_storage.get_behavior_rewards(feed_mode="dense_reader") == []
    usage_by_mode = local_storage.get_usage_metrics_by_mode(days=30)
    assert usage_by_mode["grid"]["viewed_card"] == 1


def test_issue34_brief_storage_returns_empty_for_missing_briefings_table(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "fresh-without-briefings.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE setup_state (id INTEGER PRIMARY KEY)")

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    monkeypatch.setattr(local_storage, "init_db", lambda: None)

    assert local_storage.get_briefings() == []
    assert local_storage.get_briefings(cycle_type="daily") == []
    assert local_storage.get_briefing(1) is None


def test_issue34_brief_storage_defaults_missing_optional_brief_columns(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "partial-briefings.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_type TEXT NOT NULL,
                content TEXT NOT NULL
            );
            INSERT INTO briefings (cycle_type, content)
            VALUES ('daily', 'Brief content from partial local DB');
            """
        )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    monkeypatch.setattr(local_storage, "init_db", lambda: None)

    rows = local_storage.get_briefings(cycle_type="daily")

    assert rows == [
        {
            "id": 1,
            "cycle_type": "daily",
            "content": "Brief content from partial local DB",
            "signal_count": 0,
            "generated_at": "",
            "structured": {},
        },
    ]
    assert local_storage.get_briefing(1) == rows[0]


def test_issue34_brief_storage_defaults_null_optional_brief_columns(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "nullable-briefings.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_type TEXT NOT NULL,
                content TEXT NOT NULL,
                signal_count INTEGER,
                generated_at TEXT,
                structured TEXT
            );
            INSERT INTO briefings (
                cycle_type, content, signal_count, generated_at, structured
            ) VALUES (
                'daily', 'Brief content from nullable local DB', NULL, NULL, NULL
            );
            """
        )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.storage import local as local_storage

    monkeypatch.setattr(local_storage, "init_db", lambda: None)

    rows = local_storage.get_briefings(cycle_type="daily")

    assert rows == [
        {
            "id": 1,
            "cycle_type": "daily",
            "content": "Brief content from nullable local DB",
            "signal_count": 0,
            "generated_at": "",
            "structured": {},
        },
    ]
    assert local_storage.get_briefing(1) == rows[0]


def test_issue34_brief_route_returns_empty_state_when_briefings_table_missing(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "fresh-route-without-briefings.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE setup_state (id INTEGER PRIMARY KEY)")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(local_storage, "init_db", lambda: None)

    response = TestClient(create_app()).get("/brief")

    assert response.status_code == 200
    assert "Briefings" in response.text
    assert "아직 브리핑이 없습니다" in response.text


@pytest.mark.parametrize("fixture_name", ["fresh", "empty", "older"])
def test_issue34_brief_route_returns_200_for_each_sqlite_fixture(
    tmp_path,
    monkeypatch,
    issue34_sqlite_db_fixtures,
    fixture_name,
):
    fixture = issue34_sqlite_db_fixtures[fixture_name]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(fixture["path"]))

    from hedwig.dashboard.app import create_app

    response = TestClient(create_app()).get("/brief")

    assert response.status_code == 200, fixture["description"]


def test_issue34_brief_route_initializes_fresh_sqlite_database(
    tmp_path,
    monkeypatch,
    issue34_sqlite_db_fixtures,
):
    db_path = issue34_sqlite_db_fixtures["fresh"]["path"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app

    response = TestClient(create_app()).get("/brief")

    assert response.status_code == 200
    assert "Briefings" in response.text
    assert "아직 브리핑이 없습니다" in response.text
    assert db_path.exists()

    with sqlite3.connect(db_path) as conn:
        briefing_count = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]

    assert briefing_count == 0


def test_issue34_brief_route_recovers_existing_empty_sqlite_database(
    tmp_path,
    monkeypatch,
    issue34_sqlite_db_fixtures,
):
    db_path = issue34_sqlite_db_fixtures["empty"]["path"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app

    response = TestClient(create_app()).get("/brief")

    assert response.status_code == 200
    assert "Briefings" in response.text
    assert "아직 브리핑이 없습니다" in response.text

    with sqlite3.connect(db_path) as conn:
        brief_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(briefings)")
        }
        briefing_count = conn.execute("SELECT COUNT(*) FROM briefings").fetchone()[0]

    assert {
        "id",
        "cycle_type",
        "content",
        "generated_at",
        "structured",
    } <= brief_columns
    assert briefing_count == 0


def test_issue34_brief_route_returns_200_for_older_sqlite_database(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "old-hedwig.db"
    _create_old_local_db_missing_feed_mode(db_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app

    response = TestClient(create_app()).get("/brief")

    assert response.status_code == 200
    assert "Briefings" in response.text


def test_issue34_brief_route_renders_sqlite_saved_brief_without_crashing(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "brief-route-saved.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app
    from hedwig.storage import save_briefing

    saved_id = save_briefing(
        "daily",
        "### Alert\n- SQLite-backed alert\n\n### Trend\n- SQLite-backed trend",
        signal_count=4,
    )
    client = TestClient(create_app(), raise_server_exceptions=True)

    response = client.get("/brief?cycle=daily")

    assert isinstance(saved_id, int)
    assert response.status_code == 200
    assert "Briefings" in response.text
    assert "SQLite-backed alert" in response.text
    assert "SQLite-backed trend" in response.text
    assert "4 signals" in response.text
    assert 'class="headline-card"' in response.text


def test_issue34_brief_route_renders_legacy_sqlite_brief_rows_without_crashing(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "brief-route-legacy-minimal.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_type TEXT NOT NULL,
                content TEXT NOT NULL
            );
            INSERT INTO briefings (cycle_type, content)
            VALUES ('daily', 'Legacy SQLite brief row without optional columns');
            """
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app

    response = TestClient(
        create_app(),
        raise_server_exceptions=True,
    ).get("/brief?cycle=daily")

    assert response.status_code == 200
    assert "Briefings" in response.text
    assert "Legacy SQLite brief row without optional columns" in response.text
    assert "0 signals" in response.text
    assert 'class="headline-card"' in response.text


@pytest.mark.parametrize(
    ("structured_value", "brief_content"),
    [
        ("{not-json", "Legacy brief row with invalid structured JSON"),
        ("[]", "Legacy brief row with non-object structured JSON"),
    ],
)
def test_issue34_brief_route_ignores_unusable_structured_payloads_without_crashing(
    tmp_path,
    monkeypatch,
    structured_value,
    brief_content,
):
    db_path = tmp_path / "brief-route-legacy-structured.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_type TEXT NOT NULL,
                content TEXT NOT NULL,
                signal_count INTEGER DEFAULT 0,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                structured TEXT DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            INSERT INTO briefings (
                cycle_type, content, signal_count, generated_at, structured
            ) VALUES ('daily', ?, 3, '2026-05-01T10:00:00+00:00', ?)
            """,
            (brief_content, structured_value),
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    response = TestClient(
        create_app(),
        raise_server_exceptions=True,
    ).get("/brief?cycle=daily")
    rows = local_storage.get_briefings(cycle_type="daily")

    assert response.status_code == 200
    assert "Briefings" in response.text
    assert brief_content in response.text
    assert "3 signals" in response.text
    assert 'class="headline-card"' in response.text
    assert rows[0]["structured"] == {}


def test_issue34_brief_route_and_storage_read_older_sqlite_schema_fixture(
    tmp_path,
    monkeypatch,
    issue34_sqlite_db_fixtures,
):
    db_path = issue34_sqlite_db_fixtures["older"]["path"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    client = TestClient(create_app())

    response = client.get("/brief")
    daily_response = client.get("/brief?cycle=daily")
    weekly_response = client.get("/brief?cycle=weekly")
    rows = local_storage.get_briefings(cycle_type="daily", limit=5)
    briefing = local_storage.get_briefing(21)

    assert response.status_code == 200
    assert daily_response.status_code == 200
    assert weekly_response.status_code == 200
    assert "Existing local briefing content" in response.text
    assert "Existing local briefing content" in daily_response.text
    assert "Existing local briefing content" not in weekly_response.text
    assert rows == [
        {
            "id": 21,
            "cycle_type": "daily",
            "content": "Existing local briefing content",
            "signal_count": 2,
            "generated_at": "2026-05-01T10:00:00+00:00",
            "structured": {},
        },
    ]
    assert briefing == rows[0]
