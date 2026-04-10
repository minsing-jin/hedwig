"""
Test: Dashboard signup form renders correctly with all required fields.

Verifies:
  - GET /signup returns HTTP 200 in SaaS mode
  - HTML contains email input (type=email, required)
  - HTML contains password input (type=password, required, minlength)
  - HTML contains submit button
  - HTML contains link to /login for existing users
  - Error display element exists
  - Form posts to /auth/signup
  - CSS styles for auth forms are present in static assets
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="module")
def saas_app():
    """Create a SaaS-mode FastAPI app for testing."""
    from hedwig.dashboard.app import create_app

    app = create_app(saas_mode=True)
    return app


@pytest.fixture(scope="module")
def client(saas_app):
    """Provide a Starlette TestClient for the SaaS app."""
    from starlette.testclient import TestClient

    return TestClient(saas_app)


class TestSignupFormRenders:
    """Signup form renders correctly with all required fields."""

    def test_signup_returns_200(self, client):
        """GET /signup returns HTTP 200."""
        resp = client.get("/signup")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

    def test_signup_content_type_html(self, client):
        """Response content type is HTML."""
        resp = client.get("/signup")
        assert "text/html" in resp.headers.get("content-type", "")

    def test_signup_has_email_field(self, client):
        """Signup form contains an email input with type=email and required attribute."""
        html = client.get("/signup").text
        # Match an <input> with type="email" and required
        assert re.search(
            r'<input[^>]*type=["\']email["\'][^>]*required', html
        ), "Missing required email input field"

    def test_signup_has_password_field(self, client):
        """Signup form contains a password input with type=password and required attribute."""
        html = client.get("/signup").text
        assert re.search(
            r'<input[^>]*type=["\']password["\'][^>]*required', html
        ), "Missing required password input field"

    def test_signup_password_has_minlength(self, client):
        """Password field has a minlength constraint."""
        html = client.get("/signup").text
        assert re.search(
            r'<input[^>]*type=["\']password["\'][^>]*minlength=["\']?\d+', html
        ), "Password field should have minlength attribute"

    def test_signup_has_submit_button(self, client):
        """Signup form contains a submit button."""
        html = client.get("/signup").text
        assert re.search(
            r'<button[^>]*type=["\']submit["\']', html
        ), "Missing submit button"

    def test_signup_has_form_element(self, client):
        """Signup page contains a <form> element."""
        html = client.get("/signup").text
        assert "<form" in html, "Missing <form> element"

    def test_signup_form_posts_to_auth_signup(self, client):
        """The JavaScript submits form data to /auth/signup."""
        html = client.get("/signup").text
        assert "/auth/signup" in html, "Form should POST to /auth/signup"

    def test_signup_has_login_link(self, client):
        """Signup page has a link to the login page for existing users."""
        html = client.get("/signup").text
        assert re.search(
            r'<a[^>]*href=["\']/login["\']', html
        ), "Missing link to /login"

    def test_signup_has_error_display(self, client):
        """Signup page has an error display element."""
        html = client.get("/signup").text
        assert 'id="error"' in html, "Missing error display element"

    def test_signup_has_email_label(self, client):
        """Signup form has a label for the email field."""
        html = client.get("/signup").text
        assert re.search(
            r'<label[^>]*for=["\']email["\']', html
        ), "Missing label for email field"

    def test_signup_has_password_label(self, client):
        """Signup form has a label for the password field."""
        html = client.get("/signup").text
        assert re.search(
            r'<label[^>]*for=["\']password["\']', html
        ), "Missing label for password field"

    def test_signup_has_page_title(self, client):
        """Signup page has a descriptive title."""
        html = client.get("/signup").text
        assert re.search(
            r'<title>[^<]*[Ss]ign\s*[Uu]p[^<]*</title>', html
        ), "Page title should contain 'Sign Up'"


class TestSignupFormCSS:
    """Auth form CSS styles are present in the static stylesheet."""

    def test_auth_container_css_exists(self):
        """The style.css file contains .auth-container styles."""
        css_path = ROOT / "hedwig" / "dashboard" / "static" / "style.css"
        assert css_path.exists(), "style.css not found"
        css = css_path.read_text()
        assert ".auth-container" in css, "Missing .auth-container CSS"

    def test_auth_card_css_exists(self):
        """The style.css file contains .auth-card styles."""
        css_path = ROOT / "hedwig" / "dashboard" / "static" / "style.css"
        css = css_path.read_text()
        assert ".auth-card" in css, "Missing .auth-card CSS"

    def test_auth_footer_css_exists(self):
        """The style.css file contains .auth-footer styles."""
        css_path = ROOT / "hedwig" / "dashboard" / "static" / "style.css"
        css = css_path.read_text()
        assert ".auth-footer" in css, "Missing .auth-footer CSS"

    def test_field_css_exists(self):
        """The style.css file contains .field styles for form inputs."""
        css_path = ROOT / "hedwig" / "dashboard" / "static" / "style.css"
        css = css_path.read_text()
        assert ".field" in css, "Missing .field CSS for form inputs"

    def test_btn_primary_css_exists(self):
        """The style.css file contains .btn-primary styles."""
        css_path = ROOT / "hedwig" / "dashboard" / "static" / "style.css"
        css = css_path.read_text()
        assert ".btn-primary" in css, "Missing .btn-primary CSS"


class TestSignupRouteExists:
    """The /signup route is registered and the /auth/signup API exists."""

    def test_signup_route_registered_in_saas_mode(self, saas_app):
        """GET /signup route exists in SaaS mode."""
        routes = [r.path for r in saas_app.routes if hasattr(r, "path")]
        assert "/signup" in routes, "/signup route not registered"

    def test_auth_signup_api_registered(self, saas_app):
        """POST /auth/signup API route exists in SaaS mode."""
        routes = [r.path for r in saas_app.routes if hasattr(r, "path")]
        assert "/auth/signup" in routes, "/auth/signup API route not registered"

    def test_signup_not_in_non_saas_mode(self):
        """GET /signup should NOT be registered in non-SaaS mode."""
        from hedwig.dashboard.app import create_app

        app = create_app(saas_mode=False)
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/signup" not in routes, "/signup should only exist in SaaS mode"
