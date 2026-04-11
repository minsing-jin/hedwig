"""
Test: Signup template contains 12 OAuth provider buttons.

Verifies the rendered /signup page contains the expected OAuth button set
with the right provider ids, links, visible labels, icons, and colors.
"""
from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


EXPECTED_BUTTONS = {
    "google": {"label": "Google", "icon": "G", "color": "#4285F4"},
    "github": {"label": "GitHub", "icon": "GH", "color": "#181717"},
    "twitter": {"label": "X (Twitter)", "icon": "X", "color": "#000000"},
    "discord": {"label": "Discord", "icon": "D", "color": "#5865F2"},
    "linkedin_oidc": {"label": "LinkedIn", "icon": "in", "color": "#0A66C2"},
    "facebook": {"label": "Facebook", "icon": "f", "color": "#1877F2"},
    "apple": {"label": "Apple", "icon": "A", "color": "#000000"},
    "azure": {"label": "Microsoft", "icon": "M", "color": "#0078D4"},
    "spotify": {"label": "Spotify", "icon": "S", "color": "#1DB954"},
    "slack_oidc": {"label": "Slack", "icon": "Sl", "color": "#4A154B"},
    "twitch": {"label": "Twitch", "icon": "Tw", "color": "#9146FF"},
    "notion": {"label": "Notion", "icon": "N", "color": "#000000"},
}


class SignupOAuthParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.buttons: list[dict[str, str]] = []
        self.found_container = False
        self._current_button: dict[str, str] | None = None
        self._current_span_class: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        if tag == "div" and attr_map.get("class") == "oauth-buttons":
            self.found_container = True
            return

        if tag == "a" and attr_map.get("class") == "oauth-btn":
            self._current_button = {
                "href": attr_map.get("href", ""),
                "style": attr_map.get("style", ""),
                "data_provider": attr_map.get("data-provider", ""),
                "aria_label": attr_map.get("aria-label", ""),
                "icon": "",
                "label": "",
            }
            return

        if tag == "span" and self._current_button is not None:
            span_class = attr_map.get("class", "")
            if span_class in {"oauth-icon", "oauth-label"}:
                self._current_span_class = span_class

    def handle_data(self, data: str) -> None:
        if self._current_button is None or self._current_span_class is None:
            return

        text = data.strip()
        if not text:
            return

        field = "icon" if self._current_span_class == "oauth-icon" else "label"
        self._current_button[field] += text

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._current_span_class = None
            return

        if tag == "a" and self._current_button is not None:
            self.buttons.append(self._current_button)
            self._current_button = None
            self._current_span_class = None


@pytest.fixture(scope="module")
def parsed_signup_buttons():
    """Fetch the signup page HTML from the SaaS-mode dashboard."""
    from hedwig.dashboard.app import create_app
    from starlette.testclient import TestClient

    app = create_app(saas_mode=True)
    client = TestClient(app)
    resp = client.get("/signup")
    assert resp.status_code == 200

    parser = SignupOAuthParser()
    parser.feed(resp.text)
    return parser


class TestSignupOAuthButtons:
    """Signup template renders the expected OAuth button set."""

    def test_oauth_buttons_container_present(self, parsed_signup_buttons):
        """The oauth-buttons wrapper is rendered on /signup."""
        assert parsed_signup_buttons.found_container, "Missing .oauth-buttons container"

    def test_exactly_12_oauth_buttons_render(self, parsed_signup_buttons):
        """Signup page contains exactly 12 OAuth provider buttons."""
        assert len(parsed_signup_buttons.buttons) == 12, (
            f"Expected 12 OAuth buttons, found {len(parsed_signup_buttons.buttons)}"
        )

    def test_each_provider_button_has_expected_rendered_content(self, parsed_signup_buttons):
        """Every rendered button exposes the expected provider metadata."""
        buttons_by_provider = {
            button["data_provider"]: button
            for button in parsed_signup_buttons.buttons
        }

        assert set(buttons_by_provider) == set(EXPECTED_BUTTONS), (
            f"Rendered provider ids mismatch: {sorted(buttons_by_provider)}"
        )

        for provider, expected in EXPECTED_BUTTONS.items():
            button = buttons_by_provider[provider]
            expected_label = f"Continue with {expected['label']}"

            assert button["href"] == f"/auth/oauth/{provider}"
            assert button["label"] == expected_label
            assert button["aria_label"] == expected_label
            assert button["icon"] == expected["icon"]
            assert f"--oauth-color: {expected['color']}" in button["style"]
