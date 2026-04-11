"""Tests for the auto-onboarding template — AC 21.

Verify the onboarding_auto.html template contains at least 10 SNS handle inputs.
"""

import re
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "hedwig" / "dashboard" / "templates" / "onboarding_auto.html"

EXPECTED_SNS_HANDLES = [
    "sns_x",
    "sns_github",
    "sns_linkedin",
    "sns_instagram",
    "sns_threads",
    "sns_bluesky",
    "sns_youtube",
    "sns_tiktok",
    "sns_medium",
    "sns_substack",
]


def test_onboarding_auto_template_exists():
    """Template file must exist."""
    assert TEMPLATE_PATH.exists(), f"Missing template: {TEMPLATE_PATH}"


def test_onboarding_auto_has_at_least_10_sns_inputs():
    """The auto-onboarding form must contain >= 10 SNS handle input fields."""
    html = TEMPLATE_PATH.read_text()
    sns_inputs = re.findall(r'name="sns_\w+"', html)
    assert len(sns_inputs) >= 10, (
        f"Expected at least 10 SNS handle inputs, found {len(sns_inputs)}: {sns_inputs}"
    )


def test_onboarding_auto_contains_all_expected_handles():
    """Each expected SNS handle input must be present."""
    html = TEMPLATE_PATH.read_text()
    for handle in EXPECTED_SNS_HANDLES:
        assert f'name="{handle}"' in html, f"Missing SNS input: {handle}"


def test_onboarding_auto_has_bio_field():
    """Auto-onboarding should include a free-form bio textarea."""
    html = TEMPLATE_PATH.read_text()
    assert 'name="bio"' in html, "Missing bio textarea"


def test_onboarding_auto_has_submit_button():
    """Auto-onboarding form must have a submit button."""
    html = TEMPLATE_PATH.read_text()
    assert 'type="submit"' in html, "Missing submit button"
