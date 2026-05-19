from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
BASE_TEMPLATE_PATH = ROOT / "hedwig" / "dashboard" / "templates" / "base.html"
INVENTORY_PATH = ROOT / "docs" / "issue32-user-facing-route-inventory.md"
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


def _dashboard_nav_routes(source: str) -> set[str]:
    return set(re.findall(r'href="([^"]+)"', _dashboard_nav_body(source)))


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


def _route_path_is_registered(path: str, registered_route_paths: set[str]) -> bool:
    if path in registered_route_paths:
        return True
    return any(
        "{" in route_path
        and re.fullmatch(re.sub(r"\{[^/]+\}", r"[^/]+", route_path), path)
        for route_path in registered_route_paths
    )


def test_issue34_navigation_groups_routes_without_removing_existing_links():
    source = _base_template()

    assert 'data-dashboard-nav-grouped="true"' in source
    assert 'aria-label="Dashboard navigation"' in source
    assert 'data-primary-navigation="/setup /feed /brief /chat"' in source
    assert source.count('class="nav-primary"') == 4
    assert source.count('class="nav-group"') == 3
    assert source.count("data-secondary-navigation=") == 3
    assert 'data-i18n="nav.group.read"' in source
    assert 'data-i18n="nav.group.steer"' in source
    assert 'data-i18n="nav.group.system"' in source

    expected_routes = _issue32_preserved_dashboard_nav_routes()
    linked_routes = _dashboard_nav_routes(source)
    assert expected_routes <= linked_routes


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
    nav_routes = _dashboard_nav_routes(_base_template())

    missing_registered_paths = sorted(
        path
        for path in nav_routes
        if not _route_path_is_registered(path, registered_route_paths)
    )
    assert missing_registered_paths == []

    for path in sorted(nav_routes):
        response = client.get(path, follow_redirects=False)
        if path == "/":
            assert response.status_code == 303
            assert response.headers["location"] == "/setup"
        else:
            assert response.status_code == 200, path
            assert "Hedwig" in response.text


def test_issue34_language_selector_supports_ko_zh_en_and_persists_locally():
    source = _base_template()

    assert 'data-language-selector' in source
    assert '<option value="ko"' in source
    assert '<option value="zh"' in source
    assert '<option value="en"' in source
    assert 'localStorage.setItem("hedwig.language", language)' in source
    assert 'localStorage.getItem("hedwig.language")' in source
    assert 'document.documentElement.lang = language' in source


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


def _create_old_local_db_missing_feed_mode(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE behavior_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                dwell_ms INTEGER,
                position_in_feed INTEGER,
                feed_id TEXT DEFAULT 'default',
                device TEXT,
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
            CREATE TABLE briefings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_type TEXT NOT NULL,
                content TEXT NOT NULL,
                signal_count INTEGER DEFAULT 0,
                generated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


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
