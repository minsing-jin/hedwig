from __future__ import annotations

import json
import os
import sqlite3

from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
import yaml


class _FakeProcess:
    pid = 4242


def _setup_requirement(payload: dict, requirement_id: str) -> dict:
    return next(
        item for item in payload["requirements"] if item["id"] == requirement_id
    )


def test_setup_route_renders_entrypoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    assert "Setup" in resp.text
    assert "OpenAI API Key" in resp.text


def test_setup_route_renders_one_shot_step_card_shell(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    assert 'class="setup-flow"' in body
    assert body.count('class="setup-step-card') >= 5
    assert 'class="setup-flow-nav"' in body
    assert 'data-advanced-setup-entrypoint' in body
    assert "Advanced setup (optional)" in body
    assert "Keep this collapsed for the one-shot OpenAI + local SQLite path." in body
    assert 'href="#setup-advanced" class="btn" data-advanced-setup-link' in body
    assert "Open advanced setup controls" in body
    advanced_entrypoint_start = body.rindex(
        "<details", 0, body.index("data-advanced-setup-entrypoint")
    )
    advanced_entrypoint = body[
        advanced_entrypoint_start : body.index('aria-label="Setup flow navigation"')
    ]
    assert "<details" in advanced_entrypoint
    assert "<details open" not in advanced_entrypoint
    assert 'href="/settings"' in advanced_entrypoint
    assert 'href="/profile"' in advanced_entrypoint
    assert 'href="#setup-essential"' in body
    assert 'href="#setup-criteria"' in body
    assert 'href="#setup-sources"' in body
    assert 'href="#setup-progress"' in body
    assert 'href="#setup-steering"' in body
    assert 'href="#setup-feed"' in body
    assert 'href="#setup-completion"' in body
    assert 'href="#setup-advanced"' in body
    assert 'id="setup-essential"' in body
    assert 'id="setup-criteria"' in body
    assert 'id="setup-sources"' in body
    assert 'id="setup-progress"' in body
    assert 'id="setup-steering"' in body
    assert 'id="setup-feed"' in body
    assert 'id="setup-completion"' in body
    assert 'id="setup-advanced"' in body
    assert "Use default criteria or add one line of steering" in body
    assert "Interest selection is not mandatory." in body
    assert 'data-step-status="essential"' in body
    assert 'data-step-status="criteria"' in body
    assert 'data-step-status="sources"' in body
    assert 'data-step-status="progress"' in body
    assert 'data-step-status="steering"' in body
    assert 'data-step-status="feed"' in body
    assert 'data-step-status="completion"' in body
    assert 'data-step-status="advanced"' in body
    assert "Status: needs OpenAI key" in body
    assert "Guidance: paste the key, then continue. SQLite is applied automatically" in body
    assert "Status: optional and default-ready" in body
    assert "Status: automatic registry defaults" in body
    assert "Status: not started" in body
    assert "Status: available after setup" in body
    assert "Status: waiting for first items" in body
    assert "Status: waiting on feed items" in body
    assert "Status: collapsed and non-blocking" in body
    assert '<details class="setup-progressive-details">' in body
    assert "Why this is enough for minimum setup" in body
    assert "What gets generated" in body
    assert "How automatic source defaults affect first run" in body
    assert "Recovery if the first run is slow" in body
    assert "quickstart default criteria" in body
    assert "AI builder" in body
    assert "Uses the existing quickstart AI-builder criteria generator." in body
    assert "Optional one-line interest seed" in body
    assert 'id="interest_text"' in body
    assert 'name="interest_text"' in body
    assert 'maxlength="160"' in body
    assert 'data-optional-interest="true"' in body
    assert 'data-default-interest="AI agents, LLM tooling, and research papers"' in body
    assert "Leaving this blank uses the default interest: AI agents, LLM tooling, and research papers." in body
    assert "Skip and use default criteria" in body
    assert "Continue with these interests" in body
    assert 'id="skip-criteria-btn"' in body
    assert 'id="criteria-step-status"' in body
    assert "Completion gate" in body
    assert "Feed-ready completion" in body
    assert "Waiting on first feed" in body
    assert 'data-completion-gate="waiting"' in body
    assert "data-feed-ready-completion-card" in body
    assert 'data-feed-ready="false"' in body
    assert 'id="setup-success-state"' in body
    assert "data-setup-success-state" in body
    assert 'data-onboarding-completion-state="pending"' in body
    assert 'data-setup-completion-distinct-state="true"' in body
    assert 'data-visible="false"' in body
    assert "Onboarding succeeded" in body
    assert "Setup complete" in body
    assert "View feed" in body
    assert "OpenAI key saved" in body
    assert "Local SQLite active" in body
    assert "Criteria generated" in body
    assert "/feed ready" in body
    assert 'data-redirect-target=""' in body
    assert 'data-setup-completion-link' in body
    assert 'id="setup-finish-feed-link"' in body
    assert 'id="setup-completion-count"' in body
    assert 'id="setup-completion-action"' in body
    assert 'id="setup-completion-redirect"' in body
    assert "No feed items yet" in body
    assert "Completion action" in body
    assert "Redirect target" in body
    assert "Keep setup open" in body
    assert "Refresh until ready" in body
    assert "Ready to launch the first collection?" in body
    assert "Start first collection" in body
    assert 'id="start-first-run-btn"' in body
    assert 'id="setup-run-feedback"' in body
    assert 'data-setup-run-feedback' in body
    assert 'data-run-feedback-state="idle"' in body
    assert 'id="setup-run-feedback-title"' in body
    assert 'id="setup-run-feedback-message"' in body
    assert "First run not started" in body
    assert "progress, success, and failure feedback appears here" in body
    assert 'id="setup-first-run-failure"' in body
    assert "data-setup-failure-state" in body
    assert "First-run setup needs attention" in body
    assert "retry without leaving setup" in body
    assert "Confirm OPENAI_API_KEY is present and current." in body
    assert "Confirm the local SQLite database path is writable." in body
    assert "Review optional source/API keys only if the error names a source." in body
    assert 'id="setup-failure-retry-btn"' in body
    assert "data-setup-failure-retry" in body
    assert 'data-ready-label="Retry first collection"' in body
    assert 'id="setup-first-run-progress"' in body
    assert "data-first-run-progress" in body
    assert 'data-active="false"' in body
    assert 'aria-busy="false"' in body
    assert 'role="progressbar"' in body
    assert "First-run setup progress" in body
    assert "Setup/feed initialization has not started" in body
    assert "Save OPENAI_API_KEY to enable local setup and first-feed initialization." in body
    assert "data-start-first-run-control" in body
    assert 'data-existing-run-mechanism="/run/daily"' in body
    assert 'data-run-start-endpoint="/setup/one-shot"' in body
    assert 'data-collection-progress-endpoint="/setup/collection-progress"' in body
    assert 'data-feed-collection-progress-endpoint="/feed/collection-progress"' in body
    assert 'data-collection-progress-polling="/setup/collection-progress"' in body
    assert 'action="/setup/one-shot"' in body
    assert 'method="post"' in body
    assert 'enctype="application/x-www-form-urlencoded"' in body
    assert "data-one-shot-submit-form" in body
    assert 'onsubmit="handleOneShotSetupSubmit(event)"' in body
    assert "data-one-shot-start-control" in body
    assert 'data-ready-label="Start first collection"' in body
    assert 'data-missing-key-label="Enter OpenAI key to start first collection"' in body
    assert "const SETUP_ONE_SHOT_RUN_ENDPOINT = '/setup/one-shot'" in body
    assert "const SETUP_COLLECTION_PROGRESS_ENDPOINT = '/setup/collection-progress'" in body
    assert "const SETUP_COLLECTION_POLL_INTERVAL_MS = 2500" in body
    assert "const SETUP_INITIAL_COLLECTION_POLL = {" in body
    assert "function setupRunStartEndpoint()" in body
    assert "function setupCollectionProgressEndpoint()" in body
    assert "function handleOneShotSetupSubmit(event)" in body
    assert "fetch(setupRunStartEndpoint()" in body
    assert "fetch(setupCollectionProgressEndpoint())" in body
    assert "registry/source_settings defaults" in body
    assert "keeps this page polling until" in body
    assert 'data-advanced-storage-mode' in body
    assert 'id="storage_sqlite"' in body
    assert 'name="HEDWIG_STORAGE"' in body
    assert 'value="sqlite"' in body
    assert "Required environment" in body
    assert "OPENAI_API_KEY is required for local SQLite first-run setup." in body
    assert "Not required for local mode" in body
    assert "SUPABASE_URL and SUPABASE_KEY are optional Advanced settings for hosted/team mode." in body
    assert "Default first-run mode. No Supabase or external delivery required." in body
    assert "Advanced storage choice" in body
    assert 'id="storage_supabase"' in body
    assert "AI agents, LLM tooling, and research papers" in body
    assert "Default enabled set from registry/source_settings" in body
    assert "Feed-first dashboard" in body
    assert "First-feed preview" in body
    assert 'data-setup-feed-preview' in body
    assert 'data-preview-ready="false"' in body
    assert 'id="setup-feed-preview-title"' in body
    assert "First feed preview pending" in body
    assert "This inline preview uses the same local SQLite feed data as /feed." in body
    assert "function renderSetupFeedPreview(state)" in body
    assert '<details class="setup-details">' in body
    assert "Storage backend and Supabase setup (optional)" in body
    assert 'id="setup-supabase-storage"' in body
    assert "data-supabase-setup-option" in body
    assert 'data-advanced-only="true"' in body
    assert "Primary path stays local" in body
    assert "The one-shot setup action still writes HEDWIG_STORAGE=sqlite for the first feed." in body
    assert "Hosted keys are optional" in body
    assert "Supabase URL and service role key are not required for local SQLite" in body
    assert "data-supabase-storage-choice" in body
    assert "data-supabase-storage-radio" in body
    assert "data-supabase-create-tables-action" in body
    assert "Delivery channels: Slack, Discord, or SMTP email" in body
    assert "Source/API keys and model/backend settings" in body
    assert "Profile, export/import, settings, and evolution tools" in body
    assert "Optional delivery configuration after the first feed" in body
    assert "Dashboard /feed remains the default delivery target." in body
    assert 'data-delivery-settings-entrypoint' in body
    assert 'href="#setup-delivery-configuration"' in body
    assert 'id="setup-delivery-configuration"' in body
    assert 'data-delivery-progressive-disclosure' in body
    assert "Keep this section collapsed for one-shot local setup" in body
    assert "Save delivery settings" in body
    assert "Test delivery settings" in body
    assert "Open ambient delivery" in body
    assert "Open brief delivery" in body
    assert 'id="delivery-test-results"' in body
    assert "Model/backend settings (optional)" in body
    assert 'href="#setup-model-backend-settings" class="btn" data-model-backend-setup-link' in body
    assert 'id="setup-model-backend-settings"' in body
    assert "data-model-backend-progressive-disclosure" in body
    assert "Save model/backend settings" in body
    assert "Open backend health status" in body
    assert "Advanced navigation" in body
    assert 'data-openai-configured="false"' in body
    assert 'data-storage-mode="sqlite"' in body
    assert 'data-safe-default="openai-only"' in body
    assert 'data-safe-default="storage-mode"' in body
    assert 'data-safe-default="interest-text"' in body
    assert 'data-safe-default="source-preset"' in body
    assert 'data-safe-default="delivery-target"' in body
    assert 'data-safe-default="model-backend"' in body
    assert "OPENAI_API_KEY; every other setup value has a safe default." in body
    assert "HEDWIG_STORAGE=sqlite for the first local feed." in body
    assert "registry_default; source selection is optional." in body
    assert "/feed; external delivery is not required." in body
    assert "gpt-4o-mini" in body
    assert "gpt-4o" in body
    assert "ensemble pipeline" in body
    assert 'id="openai-key-error"' in body
    assert "Browser draft persistence excludes secrets." in body
    assert "const SETUP_DRAFT_STORAGE_KEY = 'hedwig.setup.draft.v1'" in body
    assert "SECRET_SETUP_FIELDS" in body
    assert "OPENAI_API_KEY is required even for local SQLite mode." in body
    assert "formData.set('HEDWIG_STORAGE', 'sqlite')" in body
    assert "formData.set('source_preset', selectedSourcePreset())" in body
    assert "function skipCriteriaStep()" in body
    assert "function continueWithCriteria()" in body
    assert "function oneShotStartControls()" in body
    assert "oneShotStartControls().forEach((button) =>" in body
    assert "Default source configuration is applied automatically" in body
    assert "Source selection is not a required" in body
    assert "Optional advanced source selection and configuration" in body
    assert "Leave this closed for the lowest-friction first run." in body
    assert "Advanced source preset selection" in body
    assert 'name="source_preset"' in body
    assert 'data-default-source-preset' in body
    assert 'value="registry_default"' in body
    assert 'type="hidden"' in body
    assert 'data-advanced-source-controls' in body
    source_controls_index = body.index("data-advanced-source-controls")
    assert source_controls_index < body.index('id="source_preset_registry_default"')
    assert source_controls_index < body.index('id="source_preset_research_papers"')
    assert 'type="radio"\n                id="source_preset_' in body
    assert 'data-preset-label="Registry defaults"' in body
    assert 'data-preset-enabled-count=' in body
    assert "function selectedSourcePresetDetails()" in body
    assert "function renderSourcePresetStepState(sourcePresetState = null)" in body
    assert "sourcePresetState: null" in body
    assert "setupClientState.sourcePresetState = data.source_preset_state || null" in body
    assert "setupClientState.sourcePresetState = null" in body
    assert "renderSourcePresetStepState(data.source_preset_state)" in body
    assert "detailed source controls remain in /sources and /settings." in body
    assert "Registry defaults" in body
    assert "currently enabled source set from registry/source_settings" in body
    assert "Open detailed source settings" in body
    assert "View source registry" in body
    assert "Optional source toggles and registry settings" in body
    assert "data-source-toggle-progressive-disclosure" in body
    assert "data-advanced-source-settings" in body
    assert "Source toggles" in body
    assert "Existing source toggles are reachable here before setup completion" in body
    assert "while the first run is waiting, and after feed items are ready" in body
    assert "data-setup-source-toggle-surface" in body
    assert "data-source-settings-path" in body
    assert "data-setup-source-toggle" in body
    assert 'id="setup-source-toggle-arxiv"' in body
    assert 'id="setup-source-toggle-hackernews"' in body
    assert 'id="setup-source-toggle-save-btn"' in body
    assert "Save source toggles" in body
    assert "function sourceToggleInputs()" in body
    assert "function selectedSetupSourceIds()" in body
    assert "function saveSetupSourceToggles()" in body
    assert "fetch('/setup/source-settings/save'" in body
    assert "Optional source review after the first feed" in body
    assert 'data-feed-source-review' in body
    assert "This one-line interest will seed the generated AI-builder criteria profile." in body
    assert "const setupComplete = Boolean(state.setup_completed || state.setup_complete)" in body
    assert "const partiallyReady = ready && !setupComplete" in body
    assert "const completionGate = setupComplete ? 'complete' : (partiallyReady ? 'partial' : 'waiting')" in body
    assert "completionCard.dataset.completionGate = completionGate" in body
    assert "completionCard.dataset.feedReady = ready ? 'true' : 'false'" in body
    assert "completionCard.dataset.redirectTarget = redirectTarget" in body
    assert "completionRedirect.textContent = redirectTarget || 'Waiting for feed items'" in body
    assert "function routeToFeedWhenReady(data)" in body
    assert "const ready = Boolean(state.feed_items_available) && count > 0;" in body
    assert "const feedItemsAvailable = Boolean(state.feed_items_available) && Number(state.feed_items || 0) > 0;" in body
    assert "const redirectImmediately = data?.redirect_immediately === true;" in body
    assert "return !navigationLocked && redirectImmediately && feedItemsAvailable && target === '/feed' ? target : '';" in body
    assert "window.location.assign(target)" in body
    assert "routeToFeedWhenReady(data);" in body
    assert "if (collectionProgressIsTerminal(data)) return" in body
    assert "function collectionProgressIsActive(data)" in body
    assert "function collectionProgressIsTerminal(data)" in body
    assert "function renderCollectionProgressLifecycle(data)" in body
    assert "function clearCollectionProgressPoll()" in body
    assert "function scheduleOneShotStatusRefresh(delay = SETUP_COLLECTION_POLL_INTERVAL_MS, options = {})" in body
    assert "function startSetupCollectionLifecyclePolling(initialData = SETUP_INITIAL_COLLECTION_POLL)" in body
    assert "setupClientState.collectionPollTimer = window.setTimeout(refreshOneShotStatus, delay)" in body
    assert "startSetupCollectionLifecyclePolling();" in body
    assert "First collection running..." in body
    assert "This page will keep polling until feed items are available." in body
    assert "function updateStepState(key, stateClass, statusText, guidanceText)" in body
    assert "function renderSetupRunFeedback(stateClass, titleText, messageText)" in body
    assert "function renderFirstRunProgress(stateClass, percent, titleText, messageText)" in body
    assert "function renderSetupFailureState(messageText)" in body
    assert "function clearSetupFailureState()" in body
    assert "Starting first collection" in body
    assert "Setup/feed initialization is running" in body
    assert "Keep this page open for live progress." in body
    assert "First run succeeded" in body
    assert "First run failed" in body
    assert "Setup/feed initialization failed" in body
    assert "Fix the issue, then retry from this page without losing your setup inputs." in body
    assert "error.setupState = data.state || null" in body
    assert "setupClientState.requiredOnboardingSaved = true" in body
    assert "renderSetupFailureState(error.message);" in body
    assert "Status refresh failed" in body
    assert "updateStepState(" in body
    assert "finishFeedLink.setAttribute('aria-disabled', feedNavigationAvailable && !navigationLocked ? 'false' : 'true')" in body
    assert "document.querySelectorAll('[data-completion-check]')" in body
    assert "window.localStorage.setItem(SETUP_DRAFT_STORAGE_KEY" in body
    assert 'href="/chat"' in body
    assert 'href="/feed"' in body
    assert 'href="/profile"' in body
    assert 'href="/algorithm/export"' in body
    assert 'href="/settings"' in body
    assert 'href="/evolution"' in body
    assert 'href="/meta"' in body
    assert 'href="/sovereignty"' in body
    setup_flow_nav = body[
        body.index('aria-label="Setup flow navigation"') : body.index('<form')
    ]
    assert 'href="/meta"' not in setup_flow_nav
    assert 'href="/evolution"' not in setup_flow_nav
    assert 'href="/sovereignty"' not in setup_flow_nav
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    assert 'href="/meta"' in setup_advanced
    assert 'href="/evolution"' in setup_advanced
    assert 'href="/sovereignty"' in setup_advanced
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    assert 'id="storage_sqlite"' not in setup_essential
    assert "keep SQLite selected" not in setup_essential
    assert 'data-advanced-storage-mode' in setup_advanced
    assert 'id="storage_sqlite"' in setup_advanced
    assert "Local SQLite remains available here for explicit review" in setup_advanced
    assert "choosing storage is not part of the primary one-shot path" in setup_advanced
    assert "data-supabase-setup-option" in setup_advanced
    assert 'id="storage_supabase"' in setup_advanced
    assert "Supabase is optional and only needed" in setup_advanced
    assert "when you deliberately choose Supabase-backed storage" in setup_advanced
    assert "Create Supabase Tables" in setup_advanced


def test_setup_primary_path_consolidates_required_first_run_options(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    primary_start = body.index("data-primary-setup-path")
    option_map_index = body.index("data-setup-option-location-map")
    primary_path = body[primary_start:option_map_index]

    assert primary_start < option_map_index
    assert "Primary /setup path" in primary_path
    assert "Everything required for the first local feed is on this page." in primary_path
    assert "data-required-first-run-options" in primary_path
    assert 'data-advanced-options-non-blocking="true"' in primary_path
    assert 'href="#setup-essential" class="btn btn-primary btn-large" data-primary-setup-start' in primary_path
    assert "Start required setup" in primary_path
    assert "Use this consolidated path for first-run onboarding." in primary_path
    assert "OpenAI-only and local" in primary_path
    assert "collapsed optional sections" in primary_path

    expected_options = [
        "openai-key",
        "local-sqlite",
        "criteria-profile",
        "source-defaults",
        "first-collection",
        "feed-handoff",
    ]
    for option in expected_options:
        assert f'data-required-first-run-option="{option}"' in primary_path

    assert primary_path.count("data-required-first-run-option=") == len(expected_options)
    assert "OpenAI API key" in primary_path
    assert "HEDWIG_STORAGE=sqlite" in primary_path
    assert "AI agents, LLM tooling, and research papers" in primary_path
    assert "registry/source_settings preset" in primary_path
    assert "Starts from this /setup form" in primary_path
    assert 'href="/feed"' not in primary_path
    assert 'href="#setup-progress"' in primary_path
    assert "unlocks after the readiness criteria pass" in primary_path
    assert 'href="#setup-advanced" class="btn" data-primary-advanced-preservation-link' in primary_path
    assert "Optional advanced controls" in primary_path

    assert "SUPABASE_URL" not in primary_path
    assert "SUPABASE_KEY" not in primary_path
    assert "SLACK_WEBHOOK_ALERTS" not in primary_path
    assert "DISCORD_WEBHOOK_ALERTS" not in primary_path
    assert "SMTP_HOST" not in primary_path
    assert "OPENAI_MODEL_FAST" not in primary_path


def test_setup_maps_existing_config_and_onboarding_options_to_visible_locations(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.env_manager import EnvManager

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    option_map_index = body.index("data-setup-option-location-map")
    nav_index = body.index('aria-label="Setup flow navigation"')
    option_map = body[option_map_index:nav_index]

    assert option_map_index < nav_index
    assert "Every configuration and onboarding option has a visible home." in option_map
    assert "<details" not in option_map

    expected_groups = {
        "required-local": "#setup-essential",
        "criteria-onboarding": "#setup-criteria",
        "source-defaults": "#setup-sources",
        "advanced-storage": "#setup-supabase-storage",
        "advanced-delivery": "#setup-delivery-configuration",
        "advanced-source-api-keys": "#setup-source-api-keys",
        "advanced-model-backend": "#setup-model-backend-settings",
        "advanced-profile-ownership": "#setup-profile",
        "advanced-monitoring-tools": "#setup-status",
    }
    for group_id, href in expected_groups.items():
        assert f'data-setup-option-group="{group_id}"' in option_map
        assert f'href="{href}"' in option_map

    for key, meta in EnvManager.REQUIRED_KEYS.items():
        assert f"{key} - {meta['label']}" in option_map
    for key, meta in EnvManager.STORAGE_KEYS.items():
        assert f"{key} - {meta['label']}" in option_map
    for key, meta in EnvManager.DELIVERY_KEYS.items():
        assert f"{key} - {meta['label']}" in option_map
    for key, meta in EnvManager.MODEL_BACKEND_KEYS.items():
        assert f"{key} - {meta['label']}" in option_map
    for key, meta in EnvManager.OPTIONAL_KEYS.items():
        if key not in EnvManager.MODEL_BACKEND_KEYS:
            assert f"{key} - {meta['label']}" in option_map

    assert "HEDWIG_STORAGE=sqlite - local SQLite default" in option_map
    assert "interest_text - optional one-line interest seed" in option_map
    assert "Default AI-builder criteria - AI agents, LLM tooling, and research papers" in option_map
    assert "Socratic onboarding - /onboarding" in option_map
    assert "Auto onboarding - /onboarding/auto" in option_map
    assert "Natural-language steering - /chat and /criteria" in option_map
    assert "Registry default preset - derived from registry/source_settings" in option_map
    assert "Dashboard /feed - default delivery target" in option_map
    assert "Algorithm import dry-run - /algorithm/import/dry-run" in option_map
    assert "Sovereignty boundaries - /sovereignty" in option_map
    assert "Meta tools - /meta" in option_map


def test_setup_reachability_matrix_covers_existing_configuration_and_onboarding_options(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.env_manager import EnvManager

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    route_paths = {getattr(route, "path", "") for route in app.routes}

    setup_reachability_matrix = {
        "required OpenAI/local setup": [
            'id="setup-essential"',
            'name="OPENAI_API_KEY"',
            'action="/setup/one-shot"',
            "fetch('/setup/required/save'",
            "HEDWIG_STORAGE=sqlite - local SQLite default",
        ],
        "storage and Supabase configuration": [
            'id="setup-supabase-storage"',
            'name="HEDWIG_STORAGE"',
            'id="storage_sqlite"',
            'id="storage_supabase"',
            'name="SUPABASE_URL"',
            'name="SUPABASE_KEY"',
            'hx-post="/setup/create-tables"',
        ],
        "criteria and onboarding controls": [
            'id="setup-criteria"',
            'name="interest_text"',
            "Default AI-builder criteria - AI agents, LLM tooling, and research papers",
            'href="/onboarding"',
            'href="/onboarding/auto"',
            'href="/chat"',
            'href="/criteria"',
        ],
        "source presets and toggles": [
            'id="setup-sources"',
            'name="source_preset"',
            "data-setup-source-toggle-surface",
            "data-setup-source-toggle",
            "fetch('/setup/source-settings/save'",
            'href="/sources"',
            'href="/settings"',
        ],
        "source API keys": [
            'id="setup-source-api-keys"',
            "data-source-api-keys-progressive-disclosure",
            "Save source/API key settings",
        ],
        "delivery channels": [
            'id="setup-delivery-configuration"',
            "data-delivery-progressive-disclosure",
            "Save delivery settings",
            "Test delivery settings",
            'href="/ambient/pwa"',
            'href="/brief"',
        ],
        "model and backend settings": [
            'id="setup-model-backend-settings"',
            "data-model-backend-progressive-disclosure",
            'hx-post="/setup/model-backend/save"',
            'href="/settings#model-backend-settings"',
            'href="/status"',
        ],
        "profile and export/import": [
            'id="setup-profile"',
            'id="setup-export-import"',
            'href="/profile"',
            'href="/algorithm/export"',
            "postAlgorithmBundle('/algorithm/import/dry-run'",
            "postAlgorithmBundle('/algorithm/import'",
            'id="algorithm_bundle_file"',
        ],
        "settings, monitoring, and algorithm tools": [
            'id="setup-general-settings"',
            'id="setup-status"',
            'href="/settings"',
            'href="/status"',
            'href="/signals"',
            'href="/feed"',
            'href="/evolution"',
            'href="/meta"',
            'href="/sovereignty"',
            'href="/sandbox"',
        ],
    }
    for group_name, required_terms in setup_reachability_matrix.items():
        missing_terms = [term for term in required_terms if term not in body]
        assert missing_terms == [], group_name

    for key in EnvManager.REQUIRED_KEYS:
        assert f'name="{key}"' in body
    for key in EnvManager.STORAGE_KEYS:
        if key == "HEDWIG_STORAGE":
            assert f'name="{key}"' in body
        else:
            assert f'name="{key}"' in body
    for key in EnvManager.DELIVERY_KEYS:
        assert f'name="{key}"' in body
    for key in EnvManager.MODEL_BACKEND_KEYS:
        assert f'name="{key}"' in body
    for key in EnvManager.OPTIONAL_KEYS:
        if key not in EnvManager.MODEL_BACKEND_KEYS:
            assert f'name="{key}"' in body

    expected_reachable_routes = {
        "/setup",
        "/setup/state",
        "/setup/one-shot",
        "/setup/one-shot/status",
        "/setup/collection-progress",
        "/setup/required/save",
        "/setup/source-settings/save",
        "/setup/save",
        "/setup/test",
        "/setup/create-tables",
        "/setup/model-backend/save",
        "/onboarding",
        "/onboarding/auto",
        "/chat",
        "/criteria",
        "/sources",
        "/settings",
        "/settings/model-backend/save",
        "/feed",
        "/feed/collection-progress",
        "/signals",
        "/brief",
        "/ambient/{surface}",
        "/profile",
        "/algorithm/export",
        "/algorithm/import/dry-run",
        "/algorithm/import",
        "/status",
        "/evolution",
        "/meta",
        "/sovereignty",
        "/sandbox",
    }
    assert expected_reachable_routes <= route_paths

    auto_onboarding_resp = client.get("/onboarding/auto", follow_redirects=False)
    assert auto_onboarding_resp.status_code == 200
    assert auto_onboarding_resp.headers.get("location") is None
    assert "Tell Hedwig who you are" in auto_onboarding_resp.text
    assert "One-shot local onboarding" not in auto_onboarding_resp.text


def test_setup_supabase_option_is_advanced_and_non_blocking(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    supabase_start = body.rindex("<details", 0, body.index("data-supabase-setup-option"))
    supabase_section = body[supabase_start : body.index('id="setup-delivery-configuration"')]

    assert "data-supabase-setup-option" not in setup_essential
    assert 'id="storage_supabase"' not in setup_essential
    assert "Create Supabase Tables" not in setup_essential
    assert "data-supabase-setup-option" in setup_advanced
    assert 'data-advanced-only="true"' in setup_advanced
    assert 'id="storage_supabase"' in setup_advanced
    assert 'name="HEDWIG_STORAGE"' in setup_advanced
    assert 'value="supabase"' in setup_advanced
    assert "Supabase hosted/team mode" in setup_advanced
    assert (
        "Local SQLite is the default. Supabase is optional and only needed"
        in setup_advanced
    )
    assert "when you deliberately choose Supabase-backed storage" in setup_advanced
    assert "not a prerequisite for first-run onboarding" in setup_advanced
    assert "Choose this only when you want Supabase-backed usage" in setup_advanced
    assert "The one-shot setup action still writes HEDWIG_STORAGE=sqlite for the first feed." in setup_advanced
    assert "Hosted keys are optional" in setup_advanced
    assert "Supabase URL and service role key are not required for local SQLite" in setup_advanced
    assert "data-supabase-create-tables-action" in setup_advanced
    assert "<details" in supabase_section
    assert "<details open" not in supabase_section


def test_setup_supabase_requirements_are_optional_in_local_mode(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-local\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    supabase_start = body.rindex("<details", 0, body.index("data-supabase-setup-option"))
    supabase_section = body[supabase_start : body.index('id="setup-delivery-configuration"')]

    local_optional_copy = (
        "SUPABASE_URL and SUPABASE_KEY are only needed if you later choose "
        "Supabase hosted/team mode."
    )
    advanced_required_copy = (
        "SUPABASE_URL and SUPABASE_KEY are needed only for the advanced "
        "Supabase hosted/team mode selected here."
    )
    assert "Local SQLite selected: Supabase can stay blank." in supabase_section
    assert local_optional_copy in supabase_section
    message_start = supabase_section.index('id="supabase-requirement-message"')
    local_requirement_message = supabase_section[
        message_start : supabase_section.index("</div>", message_start)
    ]
    assert 'class="setup-client-status "' in local_requirement_message
    assert 'class="setup-client-status warn"' not in local_requirement_message
    assert "Required for Supabase" not in body
    assert advanced_required_copy not in body
    assert "Required for Supabase" not in supabase_section
    assert 'id="SUPABASE_URL"' in supabase_section
    assert 'id="SUPABASE_KEY"' in supabase_section
    assert 'aria-required="false"' in supabase_section
    assert "Supabase-backed mode is selected." not in body[: body.index("<script>")]


def test_setup_supabase_mode_does_not_add_required_first_run_fields(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-hosted\nHEDWIG_STORAGE=supabase\n",
        encoding="utf-8",
    )

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    supabase_start = body.rindex("<details", 0, body.index("data-supabase-setup-option"))
    supabase_section = body[supabase_start : body.index('id="setup-delivery-configuration"')]

    assert "Supabase-backed mode is selected." not in body[: body.index("<script>")]
    assert "OPENAI_API_KEY is the only required field for one-shot setup; Supabase keys remain Advanced." in setup_essential
    assert "SUPABASE_URL and SUPABASE_KEY are needed only if you later operate in Supabase hosted/team mode." in setup_essential
    advanced_required_copy = (
        "SUPABASE_URL and SUPABASE_KEY are needed only for the advanced "
        "Supabase hosted/team mode selected here."
    )
    assert advanced_required_copy in supabase_section
    message_start = supabase_section.index('id="supabase-requirement-message"')
    supabase_requirement_message = supabase_section[
        message_start : supabase_section.index("</div>", message_start)
    ]
    assert 'class="setup-client-status warn"' in supabase_requirement_message
    assert "Required for Supabase" not in supabase_section
    assert 'aria-required="true"' not in supabase_section
    assert 'id="storage_supabase"\n                name="HEDWIG_STORAGE"\n                value="supabase"\n                checked' in supabase_section


def test_setup_delivery_controls_are_advanced_reachable_and_non_blocking(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    delivery_start = body.rindex(
        "<details", 0, body.index('id="setup-delivery-configuration"')
    )
    delivery_section = body[
        delivery_start : body.index("Source/API keys and model/backend settings")
    ]

    assert 'href="#setup-delivery-configuration" class="btn" data-delivery-setup-link' in body
    assert 'href="#setup-delivery-configuration" class="btn">Configure delivery channels</a>' in body
    assert 'id="setup-delivery-configuration"' in setup_advanced
    assert "Delivery channels: Slack, Discord, or SMTP email" in setup_advanced
    assert "Optional for local setup." in setup_advanced
    assert "Keep this section collapsed for one-shot local setup" in setup_advanced
    assert "Save delivery settings" in setup_advanced
    assert "Test delivery settings" in setup_advanced
    assert "Open ambient delivery" in setup_advanced
    assert "Open brief delivery" in setup_advanced
    assert "<details" in delivery_section
    assert "<details open" not in delivery_section
    assert "SLACK_WEBHOOK_ALERTS" not in setup_essential
    assert "DISCORD_WEBHOOK_ALERTS" not in setup_essential
    assert "SMTP_HOST" not in setup_essential
    assert "SLACK_WEBHOOK_ALERTS" not in setup_criteria
    assert "DISCORD_WEBHOOK_ALERTS" not in setup_criteria
    assert "SMTP_HOST" not in setup_criteria


def test_setup_source_api_keys_are_advanced_reachable_and_non_blocking(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_sources = body[
        body.index('id="setup-sources"') : body.index('id="setup-progress"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    source_keys_start = body.rindex(
        "<details", 0, body.index('id="setup-source-api-keys"')
    )
    source_keys_section = body[
        source_keys_start : body.index("Profile, export/import, settings, and evolution tools")
    ]

    assert 'href="#setup-source-api-keys" class="btn" data-source-api-key-setup-link' in body
    assert 'id="setup-source-api-keys"' in setup_advanced
    assert "data-source-api-keys-progressive-disclosure" in setup_advanced
    assert "Source/API keys and model/backend settings" in setup_advanced
    assert "these source API key controls are optional and do not block" in setup_advanced
    assert "Save source/API key settings" in setup_advanced
    assert "View source registry" in setup_advanced
    assert "Open source toggles" in setup_advanced
    assert "<details" in source_keys_section
    assert "<details open" not in source_keys_section
    assert "Configure source API keys" in setup_sources
    for key in ("EXA_API_KEY", "SCRAPECREATORS_API_KEY", "JINA_API_KEY"):
        assert key in source_keys_section
        assert key not in setup_essential
        assert key not in setup_criteria
        assert key not in setup_sources


def test_setup_advanced_source_and_model_settings_are_progressively_disclosed(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_sources = body[
        body.index('id="setup-sources"') : body.index('id="setup-progress"')
    ]
    source_toggle_start = body.rindex(
        "<details", 0, body.index("data-setup-source-toggle-surface")
    )
    source_toggle_section = body[
        source_toggle_start : body.index("data-advanced-source-controls")
    ]
    source_preset_start = body.rindex(
        "<details", 0, body.index("data-advanced-source-controls")
    )
    source_preset_section = body[
        source_preset_start : body.index('id="setup-progress"')
    ]
    source_keys_start = body.rindex(
        "<details", 0, body.index('id="setup-source-api-keys"')
    )
    source_keys_section = body[
        source_keys_start : body.index('id="setup-model-backend-settings"')
    ]
    model_backend_start = body.rindex(
        "<details", 0, body.index('id="setup-model-backend-settings"')
    )
    model_backend_section = body[
        model_backend_start : body.index('id="setup-export-import"')
    ]

    assert "Default source configuration is applied automatically" in setup_sources
    assert "data-setup-source-toggle-surface" not in body[
        body.index('id="setup-sources"') : source_toggle_start
    ]
    assert "data-advanced-source-settings" in source_toggle_section
    assert "data-source-toggle-progressive-disclosure" in source_toggle_section
    assert "Optional source toggles and registry settings" in source_toggle_section
    assert "Leave this closed for the automatic registry/source_settings default." in source_toggle_section
    assert "data-setup-source-toggle-surface" in source_toggle_section
    assert "data-advanced-source-controls" in source_preset_section
    assert "Optional advanced source selection and configuration" in source_preset_section
    assert "data-source-api-keys-progressive-disclosure" in source_keys_section
    assert "data-model-backend-progressive-disclosure" in model_backend_section
    assert "<details" in source_toggle_section
    assert "<details" in source_preset_section
    assert "<details" in source_keys_section
    assert "<details" in model_backend_section
    assert "<details open" not in source_toggle_section
    assert "<details open" not in source_preset_section
    assert "<details open" not in source_keys_section
    assert "<details open" not in model_backend_section

    for key in ("EXA_API_KEY", "SCRAPECREATORS_API_KEY", "JINA_API_KEY"):
        assert key in source_keys_section
        assert key not in setup_essential
        assert key not in setup_criteria
        assert key not in setup_sources
        assert key not in model_backend_section

    for key in (
        "OPENAI_MODEL_FAST",
        "OPENAI_MODEL_DEEP",
        "HEDWIG_PIPELINE",
        "HEDWIG_DISABLE_EMBEDDINGS",
    ):
        assert key in model_backend_section
        assert key not in setup_essential
        assert key not in setup_criteria
        assert key not in setup_sources
        assert key not in source_keys_section


def test_setup_uncommon_inputs_are_only_inside_closed_optional_disclosures(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.env_manager import EnvManager

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    sources_start = body.index('id="setup-sources"')
    source_toggles_start = body.rindex(
        "<details", 0, body.index("data-setup-source-toggle-surface")
    )
    setup_sources_visible = body[sources_start:source_toggles_start]
    primary_visible_path = setup_essential + setup_criteria + setup_sources_visible

    uncommon_sections = {
        "source toggles": (
            "data-setup-source-toggle-surface",
            ["data-setup-source-toggle"],
        ),
        "source presets": (
            "data-advanced-source-controls",
            ['name="source_preset"'],
        ),
        "storage and Supabase": (
            'id="setup-supabase-storage"',
            [f'name="{key}"' for key in EnvManager.STORAGE_KEYS],
        ),
        "delivery": (
            'id="setup-delivery-configuration"',
            [f'name="{key}"' for key in EnvManager.DELIVERY_KEYS],
        ),
        "source API keys": (
            'id="setup-source-api-keys"',
            [
                f'name="{key}"'
                for key in EnvManager.OPTIONAL_KEYS
                if key not in EnvManager.MODEL_BACKEND_KEYS
            ],
        ),
        "model/backend": (
            'id="setup-model-backend-settings"',
            [f'name="{key}"' for key in EnvManager.MODEL_BACKEND_KEYS],
        ),
        "export/import": (
            'id="setup-export-import"',
            [
                'name="algorithm_bundle_file"',
                "data-algorithm-import-dry-run",
                "data-algorithm-import-confirm",
            ],
        ),
    }

    for group_name, (marker, expected_terms) in uncommon_sections.items():
        detail_start = body.rindex("<details", 0, body.index(marker))
        opening_tag = body[detail_start : body.index(">", detail_start)]
        section = body[detail_start : body.index("</details>", detail_start)]

        assert "data-uncommon-setup-inputs" in opening_tag, group_name
        assert "<details open" not in opening_tag, group_name
        for term in expected_terms:
            assert term in section, group_name
            assert term not in primary_visible_path, group_name

    assert 'name="OPENAI_API_KEY"' in setup_essential
    assert 'name="interest_text"' in setup_criteria
    assert 'name="OPENAI_API_KEY"' not in body[
        body.index('id="setup-advanced"') : body.index("</form>")
    ]


def test_setup_progressive_disclosure_links_open_targeted_optional_sections(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    advanced_detail_ids = [
        "setup-supabase-storage",
        "setup-delivery-configuration",
        "setup-source-api-keys",
        "setup-model-backend-settings",
        "setup-export-import",
        "setup-profile",
        "setup-general-settings",
        "setup-status",
    ]

    for detail_id in advanced_detail_ids:
        detail_start = body.rindex("<details", 0, body.index(f'id="{detail_id}"'))
        opening_tag = body[detail_start : body.index(">", detail_start)]
        assert "<details open" not in opening_tag
        assert f'href="#{detail_id}"' in body

    assert "function openSetupDisclosureTarget(targetId, options = {})" in body
    assert "target.matches('details') ? target : target.closest('details')" in body
    assert "disclosure.open = true" in body
    assert "disclosure.dataset.openedBySetupHash = 'true'" in body
    assert "function wireSetupProgressiveDisclosureLinks()" in body
    assert "document.querySelectorAll('a[href^=\"#\"]')" in body
    assert "openSetupDisclosureTarget(link.getAttribute('href'))" in body
    assert "window.addEventListener('hashchange'" in body
    assert "openSetupDisclosureTarget(window.location.hash, {scroll: false})" in body


def test_setup_model_backend_settings_are_advanced_reachable_and_non_blocking(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_sources = body[
        body.index('id="setup-sources"') : body.index('id="setup-progress"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    source_keys_start = body.rindex(
        "<details", 0, body.index('id="setup-source-api-keys"')
    )
    source_keys_section = body[
        source_keys_start : body.index('id="setup-model-backend-settings"')
    ]
    model_backend_start = body.rindex(
        "<details", 0, body.index('id="setup-model-backend-settings"')
    )
    model_backend_section = body[
        model_backend_start : body.index('id="setup-export-import"')
    ]

    assert 'href="#setup-model-backend-settings" class="btn" data-model-backend-setup-link' in body
    assert 'id="setup-model-backend-settings"' in setup_advanced
    assert "data-model-backend-progressive-disclosure" in setup_advanced
    assert "Model/backend settings (optional)" in setup_advanced
    assert "OpenAI model IDs, pipeline mode, and embedding behavior are advanced" in setup_advanced
    assert "The one-shot setup keeps Hedwig on the default" in setup_advanced
    assert "Save model/backend settings" in setup_advanced
    assert 'hx-post="/setup/model-backend/save"' in model_backend_section
    assert "data-setup-model-backend-save" in model_backend_section
    assert 'href="/settings#model-backend-settings" class="btn btn-primary" data-existing-model-backend-settings-link' in setup_advanced
    assert "Open existing model/backend settings" in setup_advanced
    assert "Open backend health status" in setup_advanced
    assert "<details" in model_backend_section
    assert "<details open" not in model_backend_section
    assert any(getattr(route, "path", None) == "/settings/model-backend/save" for route in app.routes)
    assert any(getattr(route, "path", None) == "/setup/model-backend/save" for route in app.routes)
    for key in (
        "OPENAI_MODEL_FAST",
        "OPENAI_MODEL_DEEP",
        "HEDWIG_PIPELINE",
        "HEDWIG_DISABLE_EMBEDDINGS",
    ):
        assert key in model_backend_section
        assert key not in setup_essential
        assert key not in setup_criteria
        assert key not in setup_sources
        assert key not in source_keys_section

    settings_resp = client.get("/settings")
    assert settings_resp.status_code == 200
    assert 'id="model-backend-settings"' in settings_resp.text
    assert "data-settings-model-backend-surface" in settings_resp.text
    assert 'action="/settings/model-backend/save"' in settings_resp.text


def test_setup_model_backend_save_reuses_settings_persistence_and_backend_behavior(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_MODEL_FAST", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_DEEP", raising=False)
    monkeypatch.delenv("HEDWIG_PIPELINE", raising=False)
    monkeypatch.delenv("HEDWIG_DISABLE_EMBEDDINGS", raising=False)

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/setup/model-backend/save",
        data={
            "OPENAI_MODEL_FAST": "gpt-4o-mini",
            "OPENAI_MODEL_DEEP": "gpt-4o",
            "HEDWIG_PIPELINE": "single",
            "HEDWIG_DISABLE_EMBEDDINGS": "1",
            "EXA_API_KEY": "ignored-by-model-backend-route",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["saved_keys"] == [
        "HEDWIG_DISABLE_EMBEDDINGS",
        "HEDWIG_PIPELINE",
        "OPENAI_MODEL_DEEP",
        "OPENAI_MODEL_FAST",
    ]

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_MODEL_FAST=gpt-4o-mini" in env_text
    assert "OPENAI_MODEL_DEEP=gpt-4o" in env_text
    assert "HEDWIG_PIPELINE=single" in env_text
    assert "HEDWIG_DISABLE_EMBEDDINGS=1" in env_text
    assert "EXA_API_KEY=ignored-by-model-backend-route" not in env_text
    assert os.environ["HEDWIG_PIPELINE"] == "single"
    assert os.environ["HEDWIG_DISABLE_EMBEDDINGS"] == "1"
    assert hedwig_config.OPENAI_MODEL_FAST == "gpt-4o-mini"
    assert hedwig_config.OPENAI_MODEL_DEEP == "gpt-4o"


def test_setup_model_backend_save_uses_settings_validation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/setup/model-backend/save",
        data={
            "HEDWIG_PIPELINE": "manus",
            "HEDWIG_DISABLE_EMBEDDINGS": "sometimes",
        },
    )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["errors"] == {
        "HEDWIG_PIPELINE": "Use single or ensemble.",
        "HEDWIG_DISABLE_EMBEDDINGS": "Use 0 or 1.",
    }
    assert not (tmp_path / ".env").exists()


def test_setup_model_backend_access_matches_existing_settings_surface(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("OPENAI_MODEL_FAST", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_DEEP", raising=False)
    monkeypatch.delenv("HEDWIG_PIPELINE", raising=False)
    monkeypatch.delenv("HEDWIG_DISABLE_EMBEDDINGS", raising=False)

    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.env_manager import EnvManager

    client = TestClient(create_app())
    setup_resp = client.get("/setup")
    settings_resp = client.get("/settings")

    assert setup_resp.status_code == 200
    assert settings_resp.status_code == 200
    setup_body = setup_resp.text
    settings_body = settings_resp.text
    setup_section = setup_body[
        setup_body.rindex("<details", 0, setup_body.index('id="setup-model-backend-settings"')) :
        setup_body.index('id="setup-export-import"')
    ]
    settings_section = settings_body[
        settings_body.index('id="model-backend-settings"') :
        settings_body.index("{% endblock %}") if "{% endblock %}" in settings_body else len(settings_body)
    ]

    assert 'id="setup-model-backend-settings"' in setup_section
    assert 'id="model-backend-settings"' in settings_section
    assert 'hx-post="/setup/model-backend/save"' in setup_section
    assert 'action="/settings/model-backend/save"' in settings_section
    assert 'href="/settings#model-backend-settings"' in setup_section
    assert 'href="/status"' in setup_section
    assert 'href="/status"' in settings_section
    for key, meta in EnvManager.MODEL_BACKEND_KEYS.items():
        assert f'name="{key}"' in setup_section
        assert f'name="{key}"' in settings_section
        assert meta["label"] in setup_section
        assert meta["label"] in settings_section
        assert meta["help"] in setup_section
        assert meta["help"] in settings_section

    payload = {
        "OPENAI_MODEL_FAST": "gpt-4o-mini",
        "OPENAI_MODEL_DEEP": "gpt-4o",
        "HEDWIG_PIPELINE": "ensemble",
        "HEDWIG_DISABLE_EMBEDDINGS": "0",
        "OPENAI_API_KEY": "ignored-by-model-backend-equivalence",
    }
    setup_save = client.post("/setup/model-backend/save", data=payload)
    setup_env_lines = {
        line
        for line in (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
        if line.partition("=")[0] in EnvManager.MODEL_BACKEND_KEYS
    }
    (tmp_path / ".env").unlink()
    for key in EnvManager.MODEL_BACKEND_KEYS:
        monkeypatch.delenv(key, raising=False)

    settings_save = client.post(
        "/settings/model-backend/save",
        data=payload,
        follow_redirects=False,
    )
    settings_env_lines = {
        line
        for line in (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
        if line.partition("=")[0] in EnvManager.MODEL_BACKEND_KEYS
    }

    assert setup_save.status_code == 200
    assert setup_save.json()["saved_keys"] == sorted(EnvManager.MODEL_BACKEND_KEYS)
    assert settings_save.status_code == 303
    assert settings_save.headers["location"] == "/settings?saved=model-backend"
    assert setup_env_lines == settings_env_lines == {
        "OPENAI_MODEL_FAST=gpt-4o-mini",
        "OPENAI_MODEL_DEEP=gpt-4o",
        "HEDWIG_PIPELINE=ensemble",
        "HEDWIG_DISABLE_EMBEDDINGS=0",
    }


def test_setup_export_import_controls_are_advanced_reachable_and_non_blocking(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    export_import_start = body.rindex(
        "<details", 0, body.index('id="setup-export-import"')
    )
    export_import_section = body[
        export_import_start : body.index("Profile, export/import, settings, and evolution tools")
    ]

    assert 'href="#setup-export-import" class="btn" data-export-import-setup-link' in body
    assert 'id="setup-export-import"' in setup_advanced
    assert "data-export-import-progressive-disclosure" in setup_advanced
    assert "Algorithm export/import bundle (optional)" in setup_advanced
    assert "do not block setup completion" in setup_advanced
    assert 'href="/algorithm/export" class="btn btn-primary" download data-algorithm-export-control' in setup_advanced
    assert 'id="algorithm_bundle_file"' in setup_advanced
    assert "data-algorithm-import-file" in setup_advanced
    assert "data-algorithm-import-dry-run" in setup_advanced
    assert "data-algorithm-import-confirm" in setup_advanced
    assert 'id="algorithm-import-results"' in setup_advanced
    assert "fetch(endpoint" in body
    assert "postAlgorithmBundle('/algorithm/import/dry-run'" in body
    assert "postAlgorithmBundle('/algorithm/import'" in body
    assert "<details" in export_import_section
    assert "<details open" not in export_import_section
    assert "algorithm_bundle_file" not in setup_essential
    assert "algorithm_bundle_file" not in setup_criteria
    assert "Dry-run import" not in setup_essential
    assert "Confirm import" not in setup_criteria

    assert client.get("/algorithm/export").status_code == 200
    assert client.post("/algorithm/import/dry-run", content=b"not a zip").status_code == 200


def test_export_import_controls_remain_reachable_from_post_setup_profile(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())

    setup_resp = client.get("/setup")
    assert setup_resp.status_code == 200
    setup_body = setup_resp.text
    setup_flow_nav = setup_body[
        setup_body.index('class="setup-flow-nav"') : setup_body.index('id="setup-form"')
    ]

    assert "Algorithm export/import" not in setup_flow_nav
    assert "Dry-run import" not in setup_flow_nav
    assert "Confirm import" not in setup_flow_nav
    assert 'href="/profile" data-primary-nav-target="profile"' in setup_body

    profile_resp = client.get("/profile")
    assert profile_resp.status_code == 200
    profile_body = profile_resp.text

    assert 'id="algorithm-export-import"' in profile_body
    assert "data-post-setup-export-import-controls" in profile_body
    assert "data-post-setup-import-disclosure" in profile_body
    assert 'href="/algorithm/export"' in profile_body
    assert "data-algorithm-export-control" in profile_body
    assert "data-algorithm-import-file" in profile_body
    assert "data-algorithm-import-dry-run" in profile_body
    assert "data-algorithm-import-confirm" in profile_body
    assert "postAlgorithmBundle('/algorithm/import/dry-run'" in profile_body
    assert "postAlgorithmBundle('/algorithm/import'" in profile_body
    assert "not part of the first-run step sequence" in profile_body

    assert client.get("/algorithm/export").status_code == 200
    assert client.post("/algorithm/import/dry-run", content=b"not a zip").status_code == 200


def test_setup_profile_section_is_collapsed_and_links_existing_profile(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_flow_nav = body[
        body.index('class="setup-flow-nav"') : body.index('id="setup-form"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    profile_start = body.rindex("<details", 0, body.index('id="setup-profile"'))
    profile_section = body[
        profile_start : body.index("Profile, export/import, settings, and evolution tools")
    ]

    assert 'id="setup-profile"' in setup_advanced
    assert "data-profile-progressive-disclosure" in setup_advanced
    assert "data-post-onboarding-profile-polish" in setup_advanced
    assert "Algorithm profile review (optional)" in setup_advanced
    assert "The existing profile page remains available" in setup_advanced
    assert "data-profile-polish-non-blocking" in setup_advanced
    assert "Profile polish is an after-onboarding activity, not a required setup task." in setup_advanced
    assert 'href="/profile" class="btn btn-primary" data-profile-setup-link' in setup_advanced
    assert "data-profile-polish-link" in setup_advanced
    assert "Open existing profile page" in setup_advanced
    assert "interpretation style, behavior signals, or bundle access" in setup_advanced
    assert "<details" in profile_section
    assert "<details open" not in profile_section
    assert 'id="setup-profile"' not in setup_essential
    assert 'id="setup-profile"' not in setup_criteria
    assert "Profile polish" not in setup_flow_nav
    assert any(getattr(route, "path", None) == "/profile" for route in app.routes)

    profile_resp = client.get("/profile")
    assert profile_resp.status_code == 200
    assert "My Algorithm Profile" in profile_resp.text
    assert "Interpretation Style" in profile_resp.text
    assert "Feed Personality" in profile_resp.text


def test_setup_status_section_is_collapsed_and_links_existing_status(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    status_start = body.rindex("<details", 0, body.index('id="setup-status"'))
    status_section = body[
        status_start : body.index("Profile, export/import, settings, and evolution tools")
    ]

    assert 'id="setup-status"' in setup_advanced
    assert "data-status-progressive-disclosure" in setup_advanced
    assert "Status and runtime health (optional)" in setup_advanced
    assert "The existing status page remains available" in setup_advanced
    assert "opening status does not change setup behavior" in setup_advanced
    assert 'href="/status" class="btn btn-primary" data-status-setup-link' in setup_advanced
    assert "Open existing status page" in setup_advanced
    assert "<details" in status_section
    assert "<details open" not in status_section
    assert 'id="setup-status"' not in setup_essential
    assert 'id="setup-status"' not in setup_criteria
    assert any(getattr(route, "path", None) == "/status" for route in app.routes)

    status_resp = client.get("/status")
    assert status_resp.status_code == 200
    assert "Owned Algorithm Training Status" in status_resp.text
    assert "Source Health" in status_resp.text


def test_setup_general_settings_section_is_collapsed_and_links_existing_settings(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    setup_essential = body[
        body.index('id="setup-essential"') : body.index('id="setup-criteria"')
    ]
    setup_criteria = body[
        body.index('id="setup-criteria"') : body.index('id="setup-sources"')
    ]
    setup_advanced = body[body.index('id="setup-advanced"') : body.index("</form>")]
    settings_start = body.rindex(
        "<details", 0, body.index('id="setup-general-settings"')
    )
    settings_section = body[
        settings_start : body.index('id="setup-status"')
    ]

    assert 'href="#setup-general-settings" class="btn" data-general-settings-setup-link' in body
    assert 'id="setup-general-settings"' in setup_advanced
    assert "data-general-settings-progressive-disclosure" in setup_advanced
    assert "General Settings (optional)" in setup_advanced
    assert "The existing settings page remains the canonical place" in setup_advanced
    assert "/settings and /settings/save behavior stays unchanged" in setup_advanced
    assert "Existing behavior preserved" in setup_advanced
    assert "Uses the current /settings page and save route instead of adding a second settings form here." in setup_advanced
    assert 'href="/settings" class="btn btn-primary" data-general-settings-link' in setup_advanced
    assert "Open existing settings page" in setup_advanced
    assert "<details" in settings_section
    assert "<details open" not in settings_section
    assert 'id="setup-general-settings"' not in setup_essential
    assert 'id="setup-general-settings"' not in setup_criteria
    assert 'action="/settings/save"' not in settings_section
    assert any(getattr(route, "path", None) == "/settings" for route in app.routes)
    assert any(getattr(route, "path", None) == "/settings/save" for route in app.routes)

    settings_resp = client.get("/settings")
    assert settings_resp.status_code == 200
    assert "Source Settings" in settings_resp.text
    assert 'data-settings-source-toggle-surface' in settings_resp.text
    assert 'action="/settings/save"' in settings_resp.text


def test_setup_route_context_defaults_to_local_sqlite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard import app as dashboard_app
    from hedwig.quickstart import DEFAULT_INTEREST

    captured = {}

    def fake_template_response(request, name, context):
        captured["name"] = name
        captured["context"] = context
        return HTMLResponse("setup")

    monkeypatch.setattr(dashboard_app.TEMPLATES, "TemplateResponse", fake_template_response)

    client = TestClient(dashboard_app.create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    assert captured["name"] == "setup.html"
    assert captured["context"]["values"]["HEDWIG_STORAGE"] == "sqlite"
    assert "OPENAI_API_KEY" in captured["context"]["required_keys"]
    assert "HEDWIG_STORAGE" in captured["context"]["storage_keys"]
    assert captured["context"]["status"]["ready"] is False
    assert captured["context"]["setup_state"]["storage_mode"] == "sqlite"
    assert captured["context"]["setup_state"]["openai_configured"] is False
    assert captured["context"]["setup_state"]["completion_action"] == "/feed"
    assert captured["context"]["setup_defaults"] == {
        "storage_mode": "sqlite",
        "interest_text": DEFAULT_INTEREST,
        "source_preset": "registry_default",
        "delivery_target": "/feed",
        "delivery_required": False,
        "source_selection_required": False,
        "model_backend": {
            "OPENAI_MODEL_FAST": "gpt-4o-mini",
            "OPENAI_MODEL_DEEP": "gpt-4o",
            "HEDWIG_PIPELINE": "ensemble",
            "HEDWIG_DISABLE_EMBEDDINGS": "0",
        },
    }
    assert captured["context"]["setup_default_interest"] == DEFAULT_INTEREST
    assert captured["context"]["default_source_preset"] == "registry_default"
    assert captured["context"]["source_presets"][0]["id"] == "registry_default"
    assert captured["context"]["source_presets"][0]["enabled_count"] >= 16
    assert captured["context"]["setup_source_settings_path"].endswith("source_settings.json")
    assert captured["context"]["setup_source_toggles"][0]["id"]
    assert captured["context"]["setup_source_toggles"][0]["enabled"] is True
    assert "OPENAI_MODEL_FAST" in captured["context"]["model_backend_keys"]
    assert "OPENAI_MODEL_DEEP" in captured["context"]["model_backend_keys"]
    assert "HEDWIG_PIPELINE" in captured["context"]["model_backend_keys"]


def test_setup_seeds_first_feed_app_config_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard import app as dashboard_app
    from hedwig.quickstart import DEFAULT_INTEREST

    captured = {}

    def fake_template_response(request, name, context):
        captured["context"] = context
        return HTMLResponse("setup")

    monkeypatch.setattr(
        dashboard_app.TEMPLATES,
        "TemplateResponse",
        fake_template_response,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    first_feed_config = captured["context"]["first_feed_config"]
    assert first_feed_config["schema_version"] == "hedwig.first_feed_config.v1"
    assert first_feed_config["route"] == "/feed"
    assert first_feed_config["api_route"] == "/feed/api"
    assert first_feed_config["list_route"] == "/feed/list"
    assert first_feed_config["event_route"] == "/events/beacon"
    assert first_feed_config["default_stream"] == "default"
    assert first_feed_config["available_streams"] == [
        "default",
        "morning_deep",
        "weekend_explore",
        "critical_only",
    ]
    assert first_feed_config["default_mode"] == "grid"
    assert first_feed_config["available_modes"] == [
        "grid",
        "detail_swipe",
        "dense_reader",
    ]
    assert first_feed_config["storage_mode"] == "sqlite"
    assert first_feed_config["delivery_target"] == "/feed"
    assert first_feed_config["delivery_required"] is False
    assert first_feed_config["source_preset"] == "registry_default"
    assert first_feed_config["source_selection_required"] is False
    assert first_feed_config["interest_text"] == DEFAULT_INTEREST
    assert first_feed_config["empty_state_recovery_target"] == "/setup"
    assert first_feed_config["source_recovery_target"] == "/settings"
    assert first_feed_config["post_setup_nav_targets"] == [
        "/chat",
        "/profile",
        "/status",
    ]
    assert captured["context"]["setup_state"]["first_feed_config"] == first_feed_config


def test_setup_status_and_one_shot_return_seeded_first_feed_config(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(
        hedwig_config,
        "USER_MEMORY_PATH",
        tmp_path / "user_memory.jsonl",
    )
    monkeypatch.setattr(
        source_settings,
        "SOURCE_SETTINGS_PATH",
        tmp_path / "source_settings.json",
    )
    monkeypatch.setattr(
        dashboard_app.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(),
    )

    client = TestClient(dashboard_app.create_app())
    initial_status = client.get("/setup/one-shot/status").json()
    setup_resp = client.post(
        "/setup/one-shot",
        data={"OPENAI_API_KEY": "sk-first-feed-config"},
    )

    assert setup_resp.status_code == 200
    setup_payload = setup_resp.json()
    assert setup_payload["first_feed_config"]["route"] == "/feed"
    assert setup_payload["first_feed_config"]["storage_mode"] == "sqlite"
    assert setup_payload["first_feed_config"]["default_mode"] == "grid"
    assert setup_payload["first_feed_config"]["default_stream"] == "default"
    assert setup_payload["first_feed_config"]["source_preset"] == "registry_default"
    assert setup_payload["state"]["first_feed_config"] == setup_payload["first_feed_config"]
    assert initial_status["first_feed_config"] == setup_payload["first_feed_config"]


def test_feed_page_renders_seeded_first_feed_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/feed")

    assert resp.status_code == 200
    body = resp.text
    assert 'data-stream="default"' in body
    assert 'data-mode="grid"' in body
    assert 'data-default-stream="default"' in body
    assert 'data-default-mode="grid"' in body
    assert 'data-first-feed-config-version="hedwig.first_feed_config.v1"' in body


def test_first_time_setup_storage_choice_defaults_to_local_sqlite(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    storage_start = body.index('data-advanced-storage-mode')
    storage_section = body[storage_start : body.index('id="supabase-requirement-message"')]
    sqlite_start = storage_section.index('id="storage_sqlite"')
    sqlite_input = storage_section[
        storage_section.rindex("<input", 0, sqlite_start) :
        storage_section.index(">", sqlite_start)
    ]
    supabase_start = storage_section.index('id="storage_supabase"')
    supabase_input = storage_section[
        storage_section.rindex("<input", 0, supabase_start) :
        storage_section.index(">", supabase_start)
    ]

    assert 'data-storage-mode="sqlite"' in body
    assert 'value="sqlite"' in sqlite_input
    assert "checked" in sqlite_input
    assert 'value="supabase"' in supabase_input
    assert "checked" not in supabase_input
    assert "Local SQLite selected automatically; storage choices live in Advanced." in body


def test_setup_first_run_controls_wait_for_saved_required_inputs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    one_shot_id = body.index('id="one-shot-btn"')
    first_run_id = body.index('id="start-first-run-btn"')
    one_shot_button = body[
        body.rindex("<button", 0, one_shot_id) : body.index("</button>", one_shot_id)
    ]
    first_run_button = body[
        body.rindex("<button", 0, first_run_id) :
        body.index("</button>", first_run_id)
    ]

    assert 'data-required-onboarding-saved="false"' in body
    assert 'data-required-onboarding-save-control' in body
    assert 'id="required-onboarding-save-results"' in body
    assert 'data-missing-key-label="Enter OpenAI key to continue"' in one_shot_button
    assert 'data-missing-key-label="Enter OpenAI key to start first collection"' in first_run_button
    assert 'aria-disabled="true"' in one_shot_button
    assert 'aria-disabled="true"' in first_run_button
    assert "disabled" in one_shot_button
    assert "disabled" in first_run_button
    assert "function saveRequiredOnboardingInputs()" in body
    assert "fetch('/setup/required/save'" in body
    assert "setupClientState.requiredOnboardingSaved = false" in body
    assert "OPENAI_API_KEY is required before Hedwig can start the local first collection." in body
    assert "Save required setup inputs before starting local setup." not in body


def test_setup_only_openai_key_is_required_for_form_submission(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-hosted\nHEDWIG_STORAGE=supabase\n",
        encoding="utf-8",
    )

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    openai_id = body.index('id="OPENAI_API_KEY"')
    openai_field = body[body.rindex("<input", 0, openai_id) : body.index(">", openai_id)]
    supabase_section = body[
        body.rindex("<details", 0, body.index("data-supabase-setup-option")) :
        body.index('id="setup-delivery-configuration"')
    ]
    one_shot_button = body[
        body.index('id="one-shot-btn"') :
        body.index("</button>", body.index('id="one-shot-btn"'))
    ]
    first_run_button = body[
        body.index('id="start-first-run-btn"') :
        body.index("</button>", body.index('id="start-first-run-btn"'))
    ]

    assert 'name="OPENAI_API_KEY"' in openai_field
    assert 'aria-required="true"' in openai_field
    assert "required" in openai_field
    assert 'id="SUPABASE_URL"' in supabase_section
    assert 'id="SUPABASE_KEY"' in supabase_section
    assert 'aria-required="true"' not in supabase_section
    assert "Required for Supabase" not in supabase_section
    assert 'data-required-onboarding-saved="true"' in body
    assert 'aria-disabled="false"' in one_shot_button
    assert 'aria-disabled="false"' in first_run_button
    assert "\n            disabled" not in one_shot_button
    assert "\n            disabled" not in first_run_button
    assert "OpenAI key is present. Starting the first collection will save the local SQLite setup automatically." in body


def test_setup_form_submit_targets_one_shot_handler_with_onboarding_inputs(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    launched = {}

    def fake_start_daily_collection_run(env=None):
        launched["env"] = env
        return _FakeProcess()

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    page = client.get("/setup")

    assert page.status_code == 200
    body = page.text
    form = body[body.index('id="setup-form"') : body.index('id="setup-essential"')]
    one_shot_id = body.index('id="one-shot-btn"')
    first_run_id = body.index('id="start-first-run-btn"')
    one_shot_button = body[
        body.rindex("<button", 0, one_shot_id) : body.index("</button>", one_shot_id)
    ]
    first_run_button = body[
        body.rindex("<button", 0, first_run_id) :
        body.index("</button>", first_run_id)
    ]
    assert 'action="/setup/one-shot"' in form
    assert 'method="post"' in form
    assert 'data-one-shot-submit-form' in form
    assert 'onsubmit="handleOneShotSetupSubmit(event)"' in form
    assert 'type="submit"' in one_shot_button
    assert 'type="submit"' in first_run_button

    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": " sk-submit ",
            "HEDWIG_STORAGE": "supabase",
            "interest_text": "  local-first agent observability  ",
            "source_preset": "research_papers",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["interest"] == "local-first agent observability"
    assert payload["source_preset_state"]["preset_id"] == "research_papers"
    assert payload["state"]["storage_mode"] == "sqlite"
    assert launched["env"]["OPENAI_API_KEY"] == "sk-submit"
    assert launched["env"]["HEDWIG_STORAGE"] == "sqlite"
    assert launched["env"]["HEDWIG_CRITERIA_PATH"] == str(criteria_path)


def test_setup_first_run_controls_enable_after_required_inputs_are_saved(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-saved\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    one_shot_button = body[
        body.index('id="one-shot-btn"') : body.index("</button>", body.index('id="one-shot-btn"'))
    ]
    first_run_button = body[
        body.index('id="start-first-run-btn"') :
        body.index("</button>", body.index('id="start-first-run-btn"'))
    ]

    assert 'data-required-onboarding-saved="true"' in body
    assert "Status: ready" in body
    assert 'aria-disabled="false"' in one_shot_button
    assert 'aria-disabled="false"' in first_run_button
    assert "\n            disabled" not in one_shot_button
    assert "\n            disabled" not in first_run_button


def test_feed_page_runtime_config_reads_persisted_openai_key_without_process_env(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-feed-persisted\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "OPENAI_API_KEY", "")

    client = TestClient(create_app())
    resp = client.get("/feed")

    assert resp.status_code == 200
    assert 'class="feed-shell"' in resp.text
    assert hedwig_config.OPENAI_API_KEY == "sk-feed-persisted"
    assert os.getenv("OPENAI_API_KEY") is None
    assert hedwig_config.check_required_keys("daily") == []


def test_setup_shows_active_in_page_progress_while_first_run_is_waiting(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-progress\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["progress"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    progress_start = body.index('id="setup-first-run-progress"')
    progress_panel = body[
        body.rindex("<div", 0, progress_start) :
        body.index('id="setup-progress-list"')
    ]
    assert 'class="setup-first-run-progress active"' in progress_panel
    assert 'data-first-run-progress' in progress_panel
    assert 'data-active="true"' in progress_panel
    assert 'data-progress-percent="80"' in progress_panel
    assert 'aria-busy="true"' in progress_panel
    assert 'aria-valuenow="80"' in progress_panel
    assert "Setup/feed initialization is running" in progress_panel
    assert "Hedwig is collecting and scoring the first feed" in progress_panel
    assert 'data-run-feedback-state="progress"' in body
    assert "First run in progress" in body

    status_payload = client.get("/setup/one-shot/status").json()
    assert status_payload["state"]["first_run_active"] is True
    assert status_payload["state"]["minimum_ready"] is True
    assert status_payload["state"]["progress_percent"] == 80
    assert status_payload["state"]["first_run_status"] == "waiting_for_feed_items"
    assert status_payload["redirect_to"] is None


def test_setup_completion_hides_feed_navigation_until_readiness_passes(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-partial\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["partial readiness"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO signals (platform, external_id, title, url)
            VALUES (?, ?, ?, ?)
            """,
            (
                "hackernews",
                "partial-feed-item",
                "Partial feed item",
                "https://example.test/partial",
            ),
        )
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.update_collection_run(
        run_id,
        status="running",
        counts={
            "posts_collected": 3,
            "posts_filtered": 2,
            "signals_scored": 1,
            "signals_saved": 1,
        },
    )

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    completion = body[body.index('id="setup-completion"') : body.index('id="setup-advanced"')]
    partial = body[
        body.index('id="setup-partial-feed-readiness"') :
        body.index("data-advanced-setup-entrypoint")
    ]

    assert 'data-completion-gate="partial"' in completion
    assert 'data-feed-ready="true"' in completion
    assert 'data-feed-navigation-available="false"' in completion
    assert 'href="/feed"' not in completion
    assert 'href="#setup-progress"' in completion
    assert "Feed unlocks after collection" in completion
    assert "Feed data is usable now, but setup keeps navigation here until collection finishes." in completion
    assert 'href="/feed"' not in partial
    assert "stay on /setup until the tracked first collection completes" in partial

    status_payload = client.get("/setup/one-shot/status").json()
    assert status_payload["redirect_to"] is None
    assert status_payload["redirect_immediately"] is False
    assert status_payload["state"]["first_feed_usable_before_collection_complete"] is True
    assert status_payload["state"]["feed_navigation_available"] is False
    assert status_payload["state"]["feed_navigation_blocking_criteria_ids"] == [
        "first_collection_completed"
    ]


def test_setup_slow_collection_message_keeps_user_on_setup_until_feed_ready(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-slow\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["slow collection"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.update_collection_run(
        run_id,
        status="collected",
        counts={"posts_collected": 5, "posts_filtered": 0, "signals_scored": 0},
    )

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    progress = body[body.index('id="setup-progress"') : body.index('id="setup-steering"')]
    completion = body[body.index('id="setup-completion"') : body.index('id="setup-advanced"')]

    assert "Slow collection is expected on the first run" in progress
    assert "keep this page open for live counts and recovery options" in progress
    assert "Waiting for /feed readiness" in progress
    assert 'href="/feed"' not in completion
    assert "Feed opens after readiness" in completion
    assert "Slow collection progress stays visible here" in completion

    status_payload = client.get("/setup/collection-progress").json()
    assert status_payload["redirect_to"] is None
    assert status_payload["collection_progress"]["first_run_active"] is True
    assert status_payload["collection_progress"]["feed_items_available"] is False
    assert status_payload["collection_progress"]["redirect_target"] is None


def test_setup_required_save_persists_openai_local_mode_before_enabling_control(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.env_manager import EnvManager

    client = TestClient(create_app())
    blank_resp = client.post("/setup/required/save", data={"OPENAI_API_KEY": " "})

    assert blank_resp.status_code == 400
    assert blank_resp.json()["ok"] is False
    assert not (tmp_path / ".env").exists()

    save_resp = client.post(
        "/setup/required/save",
        data={
            "OPENAI_API_KEY": " sk-required ",
            "HEDWIG_STORAGE": "supabase",
        },
    )

    assert save_resp.status_code == 200
    payload = save_resp.json()
    assert payload["ok"] is True
    assert payload["saved_keys"] == ["HEDWIG_STORAGE", "OPENAI_API_KEY"]
    assert payload["state"]["openai_configured"] is True
    assert payload["state"]["storage_mode"] == "sqlite"
    assert payload["state"]["local_ready"] is True
    assert hedwig_config.OPENAI_API_KEY == "sk-required"
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-required" in env_text
    assert "HEDWIG_STORAGE=sqlite" in env_text
    persisted = EnvManager(env_path=tmp_path / ".env").load()
    assert persisted["OPENAI_API_KEY"] == "sk-required"
    assert persisted["HEDWIG_STORAGE"] == "sqlite"


def test_setup_required_save_validates_openai_key_format_without_other_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    invalid_resp = client.post(
        "/setup/required/save",
        data={
            "OPENAI_API_KEY": "not-an-openai-key",
            "SUPABASE_URL": "",
            "SUPABASE_KEY": "",
            "SLACK_WEBHOOK_DAILY": "",
        },
    )

    assert invalid_resp.status_code == 400
    invalid_payload = invalid_resp.json()
    assert invalid_payload["ok"] is False
    assert invalid_payload["error"] == "OPENAI_API_KEY must start with sk-."
    assert invalid_payload["state"]["openai_configured"] is False
    assert not (tmp_path / ".env").exists()


def test_setup_completion_gate_opens_when_feed_items_exist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-test\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["completion"]}}),
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO signals (platform, external_id, title) VALUES (?, ?, ?)",
            ("hackernews", "item-1", "First feed item"),
        )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    assert 'data-completion-gate="complete"' in body
    assert 'data-completion-requires-delivery="false"' in body
    assert 'data-feed-ready="true"' in body
    assert 'data-completion-check="delivery_optional" class="complete"' in body
    assert "External delivery optional" in body
    assert 'class="setup-success-state visible"' in body
    assert 'data-setup-success-state' in body
    assert 'data-onboarding-completion-state="succeeded"' in body
    assert 'data-setup-completion-distinct-state="true"' in body
    assert 'data-feed-items="1"' in body
    assert 'data-completion-action="/feed"' in body
    assert 'data-visible="true"' in body
    assert "Onboarding succeeded" in body
    assert "Setup complete" in body
    assert "Hedwig is ready locally." in body
    assert "First-run setup completed with OpenAI, local SQLite, generated criteria, and 1 feed item" in body
    assert 'data-setup-success-copy' in body
    assert 'aria-label="Completed setup proof points"' in body
    assert 'data-setup-success-proof="openai"' in body
    assert 'data-setup-success-proof="sqlite"' in body
    assert 'data-setup-success-proof="criteria"' in body
    assert 'data-setup-success-proof="feed"' in body
    assert (
        'href="/feed" class="btn btn-primary btn-large" '
        'data-setup-success-feed-link data-setup-feed-navigation aria-label="View feed"'
        in body
    )
    assert "View feed" in body
    assert 'data-redirect-target="/feed"' in body
    assert "Ready for /feed" in body
    assert "Open completed /feed" in body
    assert 'data-run-feedback-state="success"' in body
    assert "First run succeeded" in body
    assert "Feed items are available. Open /feed to start consuming your personal algorithm." in body
    assert "1 feed item" in body
    assert "Feed has 1 items" in body
    assert 'aria-label="Post-setup primary navigation"' in body
    assert "Setup is complete. Continue with the primary Hedwig surfaces." in body
    assert 'data-post-setup-primary-nav' in body
    assert 'data-ready="true"' in body
    assert 'href="/feed" data-primary-nav-target="feed"' in body
    assert 'href="/chat" data-primary-nav-target="chat"' in body
    assert 'href="/profile" data-primary-nav-target="profile"' in body
    assert 'href="/status" data-primary-nav-target="status"' in body
    assert 'data-setup-source-toggle-surface' in body
    assert 'id="setup-source-toggle-save-btn"' in body
    assert "Open your personal SNS-style feed." in body
    assert "Steer Hedwig in natural language." in body
    assert "Review preferences and export surfaces." in body
    assert "Check readiness and runtime health." in body

    status_payload = client.get("/setup/one-shot/status").json()
    assert status_payload["state"]["delivery_optional"] is True
    assert status_payload["state"]["delivery_required_for_completion"] is False
    assert status_payload["state"]["delivery_channels_configured"] is False
    assert status_payload["state"]["setup_completed"] is True


def test_setup_renders_inline_first_feed_preview_from_sqlite_data(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-preview\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["first feed preview"]}}),
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                content TEXT,
                author TEXT,
                relevance_score REAL DEFAULT 0,
                urgency TEXT DEFAULT 'skip',
                why_relevant TEXT,
                collected_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO signals (
                platform, external_id, title, url, content, author,
                relevance_score, urgency, why_relevant
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "hackernews",
                "preview-item",
                "Inline setup preview item",
                "https://example.test/preview-item",
                "Preview content should be available before opening the feed.",
                "preview-author",
                0.94,
                "digest",
                "Matches the generated first-feed criteria.",
            ),
        )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    resp = client.get("/setup?review=1")

    assert resp.status_code == 200
    body = resp.text
    assert 'data-setup-feed-preview' in body
    assert 'data-preview-ready="true"' in body
    assert "First-feed preview" in body
    assert "Inline setup preview item" in body
    assert "hackernews" in body
    assert "preview-author" in body
    assert "digest" in body
    assert "Score 0.94" in body
    assert "Matches the generated first-feed criteria." in body
    assert 'href="https://example.test/preview-item"' in body
    assert "Open source item" in body
    assert "Open dashboard /feed" in body

    payload = client.get("/setup/state").json()
    first_item = payload["state"]["first_feed_item"]
    assert first_item["title"] == "Inline setup preview item"
    assert first_item["url"] == "https://example.test/preview-item"
    assert first_item["content"] == "Preview content should be available before opening the feed."
    assert first_item["author"] == "preview-author"
    assert first_item["why_relevant"] == "Matches the generated first-feed criteria."


def test_setup_initial_page_auto_hands_off_to_feed_when_feed_items_exist(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-auto-feed\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["auto feed handoff"]}}),
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO signals (platform, external_id, title) VALUES (?, ?, ?)",
            ("hackernews", "auto-feed-item", "Auto feed redirect item"),
        )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    assert "const SETUP_INITIAL_REDIRECT = {" in body
    assert "feed_items_available: true" in body
    assert "first_feed_data_verified: true" in body
    assert "feed_items: 1" in body
    assert 'redirect_target: "/feed"' in body
    assert 'redirect_to: "/feed"' in body
    assert "redirect_immediately: true" in body
    assert "function setupInitialRedirectSuppressed()" in body
    assert "params.get('review') === '1'" in body
    assert "params.get('redirect') === '0'" in body
    assert "Boolean(window.location.hash)" in body
    assert "function routeInitialSetupToFeedWhenReady()" in body
    assert "return routeToFeedWhenReady(SETUP_INITIAL_REDIRECT);" in body
    assert "routeInitialSetupToFeedWhenReady();" in body
    assert "window.location.assign(target)" in body


def test_setup_persists_successful_first_run_completion_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-complete\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["persisted completion"]}}),
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO signals (platform, external_id, title) VALUES (?, ?, ?)",
            ("hackernews", "persisted-item", "Persisted completion item"),
        )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    status_payload = client.get("/setup/one-shot/status").json()

    assert status_payload["state"]["feed_items_available"] is True
    assert status_payload["state"]["setup_completed"] is True
    assert status_payload["state"]["setup_completion_persisted"] is True
    assert status_payload["state"]["setup_state_path"] == str(state_path)
    assert status_payload["state"]["persisted_feed_items"] == 1
    assert status_payload["state"]["delivery_channels_configured"] is False
    assert status_payload["state"]["delivery_configuration_status"] == "deferred"
    assert status_payload["state"]["delivery_configuration_deferred"] is True
    assert (
        status_payload["state"]["delivery_configuration_resume_target"]
        == "/setup#setup-delivery-configuration"
    )
    assert status_payload["state"]["deferred_delivery_channels"] == [
        "slack",
        "discord",
        "smtp",
    ]
    assert status_payload["state"]["delivery_configuration_deferred_at"]
    assert state_path.exists()

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == "hedwig.setup_state.v1"
    assert persisted["completed"] is True
    assert persisted["storage_mode"] == "sqlite"
    assert persisted["db_path"] == str(db_path)
    assert persisted["criteria_exists"] is True
    assert persisted["feed_items"] == 1
    assert persisted["completion_action"] == "/feed"
    assert persisted["redirect_target"] == "/feed"
    assert persisted["delivery_channels_configured"] is False
    assert persisted["delivery_configuration_status"] == "deferred"
    assert persisted["delivery_configuration_deferred"] is True
    assert (
        persisted["delivery_configuration_deferred_at"]
        == persisted["completed_at"]
    )
    assert (
        persisted["delivery_configuration_resume_target"]
        == "/setup#setup-delivery-configuration"
    )
    assert persisted["deferred_delivery_channels"] == ["slack", "discord", "smtp"]
    assert persisted["completed_at"]
    assert persisted["last_seen_at"]

    rerender = client.get("/setup")
    assert rerender.status_code == 200
    assert (
        json.loads(state_path.read_text(encoding="utf-8"))["completed_at"]
        == persisted["completed_at"]
    )


def test_setup_status_poll_persists_completion_after_slow_first_feed_finishes(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-slow-complete\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["slow completion"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()

    client = TestClient(create_app())
    waiting_payload = client.get("/setup/one-shot/status").json()

    assert waiting_payload["state"]["first_run_status"] == "waiting_for_feed_items"
    assert waiting_payload["state"]["setup_completed"] is False
    assert not state_path.exists()

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO signals (platform, external_id, title, url)
            VALUES (?, ?, ?, ?)
            """,
            (
                "hackernews",
                "slow-finished-item",
                "Slow first feed finished",
                "https://example.test/slow",
            ),
        )

    completed_payload = client.get("/setup/one-shot/status").json()

    assert completed_payload["redirect_to"] == "/feed"
    assert completed_payload["state"]["first_run_status"] == "ready"
    assert completed_payload["state"]["feed_items_available"] is True
    assert completed_payload["state"]["setup_completed"] is True
    assert completed_payload["state"]["setup_completion_persisted"] is True
    assert json.loads(state_path.read_text(encoding="utf-8"))["completed"] is True


def test_setup_advanced_navigation_links_to_reachable_power_user_pages(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    setup_flow_nav = resp.text[
        resp.text.index('aria-label="Setup flow navigation"') : resp.text.index("<form")
    ]
    setup_advanced = resp.text[
        resp.text.index('id="setup-advanced"') : resp.text.index("</form>")
    ]
    for path in ("/meta", "/evolution", "/sovereignty"):
        assert f'href="{path}"' not in setup_flow_nav
        assert f'href="{path}"' in setup_advanced
        assert client.get(path).status_code == 200


def test_setup_source_toggles_are_disclosed_and_save_before_setup_completion(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    source_settings_path = tmp_path / "source_settings.json"
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)

    client = TestClient(dashboard_app.create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    assert 'data-openai-configured="false"' in body
    assert 'data-feed-ready="false"' in body
    source_toggle_start = body.rindex(
        "<details", 0, body.index("data-setup-source-toggle-surface")
    )
    source_toggle_section = body[
        source_toggle_start : body.index("data-advanced-source-controls")
    ]
    assert "data-source-toggle-progressive-disclosure" in source_toggle_section
    assert "data-advanced-source-settings" in source_toggle_section
    assert "<details open" not in source_toggle_section
    assert 'data-setup-source-toggle-surface' in body
    assert body.index('data-setup-source-toggle-surface') < body.index('id="setup-progress"')
    assert 'id="setup-source-toggle-github_trending"' in body
    assert 'id="setup-source-toggle-youtube"' in body
    assert 'id="setup-source-toggle-arxiv"' in body
    assert 'id="setup-source-toggle-save-btn"' in body

    save_resp = client.post(
        "/setup/source-settings/save",
        data={
            "enabled_sources": ["github_trending", "youtube"],
        },
    )

    assert save_resp.status_code == 200
    payload = save_resp.json()
    assert payload["ok"] is True
    assert payload["enabled_source_ids"] == ["github_trending", "youtube"]
    assert payload["enabled_count"] == 2
    assert payload["source_settings_path"] == str(source_settings_path)

    saved = json.loads(source_settings_path.read_text(encoding="utf-8"))
    assert saved["sources"]["github_trending"] is True
    assert saved["sources"]["youtube"] is True
    assert saved["sources"]["arxiv"] is False

    rerender = client.get("/setup")
    assert rerender.status_code == 200

    def source_toggle_markup(source_id: str) -> str:
        start = rerender.text.index(f'id="setup-source-toggle-{source_id}"')
        return rerender.text[start : rerender.text.index("</label>", start)]

    github_toggle = source_toggle_markup("github_trending")
    youtube_toggle = source_toggle_markup("youtube")
    arxiv_toggle = source_toggle_markup("arxiv")
    assert 'value="github_trending"' in github_toggle
    assert "data-setup-source-toggle" in github_toggle
    assert "checked" in github_toggle
    assert 'value="youtube"' in youtube_toggle
    assert "data-setup-source-toggle" in youtube_toggle
    assert "checked" in youtube_toggle
    assert 'value="arxiv"' in arxiv_toggle
    assert "data-setup-source-toggle" in arxiv_toggle
    assert "checked" not in arxiv_toggle


def test_setup_delivery_configuration_is_optional_with_skip_and_defer_paths(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/setup")

    assert resp.status_code == 200
    body = resp.text
    delivery = body[
        body.index('id="setup-delivery-configuration"') : body.index(
            'id="setup-source-api-keys"'
        )
    ]
    assert "<details" in delivery
    assert "<details open" not in delivery
    assert "data-delivery-optional-configuration" in delivery
    assert "data-delivery-progressive-disclosure" in delivery
    assert "Status: optional and skipped by default" in delivery
    assert "dashboard /feed is already the default delivery target" in delivery
    assert "Leave Slack, Discord, and SMTP blank, then continue to first-run progress." in delivery
    assert "Return here after the first feed if you want alerts or email briefs." in delivery
    assert "No delivery channel is required for setup completion." in delivery
    assert "Slack Alerts Webhook" in delivery
    assert "Discord Alerts Webhook" in delivery
    assert "SMTP Email" in delivery
    assert "Save delivery settings" in delivery
    assert "Test delivery settings" in delivery
    assert 'href="#setup-progress" class="btn btn-primary" data-skip-delivery-setup' in delivery
    assert "Skip delivery for now" in delivery
    assert 'href="#setup-feed" class="btn" data-defer-delivery-setup' in delivery
    assert "Defer until after first feed" in delivery


def test_one_shot_setup_uses_default_criteria_when_interest_is_blank(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.dashboard.env_manager import EnvManager
    from hedwig.quickstart import DEFAULT_INTEREST
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(dashboard_app.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "sk-test",
            "HEDWIG_STORAGE": "supabase",
            "interest_text": "   ",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["interest"] == DEFAULT_INTEREST
    assert payload["criteria_path"] == str(criteria_path)
    assert payload["criteria_state"] == {
        "interest_text": DEFAULT_INTEREST,
        "uses_default": True,
        "default_interest": DEFAULT_INTEREST,
    }
    assert payload["first_run_started"] is True
    assert payload["profile_state"]["criteria_version"] == 1
    assert payload["profile_state"]["criteria_version_persisted"] is True
    assert payload["profile_state"]["user_memory_persisted_db"] is True
    assert payload["profile_state"]["user_memory_persisted_jsonl"] is True
    assert payload["source_preset_state"]["preset_id"] == "registry_default"
    assert payload["source_preset_state"]["enabled_count"] >= 16
    assert payload["source_preset_state"]["source_settings_created"] is True
    assert payload["source_preset_state"]["source_settings_path"] == str(source_settings_path)
    assert payload["state"]["storage_mode"] == "sqlite"
    assert payload["state"]["openai_configured"] is True
    assert payload["state"]["criteria_exists"] is True
    assert payload["state"]["db_exists"] is True
    assert payload["state"]["completion_action"] == "/feed"

    criteria = yaml.safe_load(criteria_path.read_text(encoding="utf-8"))
    assert criteria["identity"]["role"] == "AI builder"
    assert criteria["identity"]["focus"] == [DEFAULT_INTEREST]
    assert criteria["signal_preferences"]["care_about"][0] == DEFAULT_INTEREST
    assert criteria["context"]["interests"] == [DEFAULT_INTEREST]
    assert criteria["metadata"]["generated_by"] == "quickstart"
    assert (tmp_path / ".env").read_text(encoding="utf-8").count("HEDWIG_STORAGE=sqlite") == 1
    with sqlite3.connect(tmp_path / "hedwig.db") as conn:
        version = conn.execute(
            "SELECT version, created_by, criteria FROM criteria_versions"
        ).fetchone()
        memory = conn.execute(
            "SELECT confirmed_interests, context FROM user_memory"
        ).fetchone()

    assert version[0] == 1
    assert version[1] == "one_shot_setup"
    assert yaml.safe_load(version[2])["identity"]["focus"] == [DEFAULT_INTEREST]
    assert json.loads(memory[0]) == [DEFAULT_INTEREST]
    assert json.loads(memory[1])["criteria_interests"] == [DEFAULT_INTEREST]
    latest_memory = json.loads(user_memory_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert latest_memory["confirmed_interests"] == [DEFAULT_INTEREST]
    saved_sources = json.loads(source_settings_path.read_text(encoding="utf-8"))
    assert set(saved_sources["sources"]) == set(source_settings.get_source_presets()[0]["source_ids"])
    assert all(saved_sources["sources"].values())
    assert set(payload["source_preset_state"]["enabled_source_ids"]) == set(
        saved_sources["sources"]
    )
    assert saved_sources["sources"]["arxiv"] is True
    assert saved_sources["sources"]["hackernews"] is True


def test_one_shot_setup_completes_minimum_openai_key_only_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.dashboard.env_manager import EnvManager
    from hedwig.quickstart import DEFAULT_INTEREST
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    spawned = {}

    def fake_popen(args, cwd, env):
        spawned["args"] = args
        spawned["cwd"] = cwd
        spawned["env"] = env
        return _FakeProcess()

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)

    client = TestClient(dashboard_app.create_app())
    resp = client.post("/setup/one-shot", data={"OPENAI_API_KEY": "sk-only"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["interest"] == DEFAULT_INTEREST
    assert payload["first_run_started"] is True
    assert payload["pid"] == _FakeProcess.pid
    assert payload["redirect_to"] is None
    assert payload["redirect_immediately"] is False
    assert payload["state"]["storage_mode"] == "sqlite"
    assert payload["state"]["openai_configured"] is True
    assert payload["state"]["local_ready"] is True
    assert payload["state"]["criteria_exists"] is True
    assert payload["state"]["db_exists"] is True
    assert payload["state"]["feed_items_available"] is False
    assert payload["state"]["feed_navigation_ready"] is False
    assert payload["state"]["first_run_status"] == "waiting_for_feed_items"
    assert payload["state"]["first_run_active"] is True
    assert payload["state"]["minimum_ready"] is True
    assert payload["state"]["progress_percent"] == 80
    assert payload["state"]["completion_action"] == "/feed"
    assert payload["source_preset_state"]["preset_id"] == "registry_default"
    assert payload["source_preset_state"]["source_settings_created"] is True

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-only" in env_text
    assert "HEDWIG_STORAGE=sqlite" in env_text
    assert "SUPABASE_URL=\n" in env_text
    assert "SUPABASE_KEY=\n" in env_text
    persisted = EnvManager(env_path=tmp_path / ".env").load()
    assert persisted["OPENAI_API_KEY"] == "sk-only"
    assert persisted["HEDWIG_STORAGE"] == "sqlite"
    assert persisted["SUPABASE_URL"] == ""
    assert persisted["SUPABASE_KEY"] == ""

    criteria = yaml.safe_load(criteria_path.read_text(encoding="utf-8"))
    assert criteria["identity"]["role"] == "AI builder"
    assert criteria["context"]["interests"] == [DEFAULT_INTEREST]

    with sqlite3.connect(tmp_path / "hedwig.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM criteria_versions").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM user_memory").fetchone()[0] == 1

    saved_sources = json.loads(source_settings_path.read_text(encoding="utf-8"))
    assert all(saved_sources["sources"].values())
    assert spawned["args"] == [dashboard_app.sys.executable, "-m", "hedwig"]
    assert spawned["cwd"] == str(tmp_path)
    assert spawned["env"]["OPENAI_API_KEY"] == "sk-only"
    assert spawned["env"]["HEDWIG_STORAGE"] == "sqlite"
    assert spawned["env"]["HEDWIG_CRITERIA_PATH"] == str(criteria_path)
    assert "SUPABASE_URL" not in spawned["env"]
    assert "SUPABASE_KEY" not in spawned["env"]


def test_setup_one_shot_validates_openai_key_without_optional_credentials(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard import app as dashboard_app

    def fail_if_started(*args, **kwargs):
        raise AssertionError("invalid setup submission must not start first run")

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fail_if_started,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "missing-sk-prefix",
            "SUPABASE_URL": "",
            "SUPABASE_KEY": "",
            "SLACK_WEBHOOK_ALERTS": "",
            "DISCORD_WEBHOOK_DAILY": "",
            "SMTP_HOST": "",
        },
    )

    assert resp.status_code == 400
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["error"] == "OPENAI_API_KEY must start with sk-."
    assert payload["state"]["openai_configured"] is False
    assert payload["state"]["storage_mode"] == "sqlite"
    assert not (tmp_path / ".env").exists()
    assert not (tmp_path / "hedwig.db").exists()


def test_setup_completion_ignores_export_import_and_profile_polish_fields(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.sources import settings as source_settings
    from hedwig.storage import local as local_storage

    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(
        hedwig_config,
        "USER_MEMORY_PATH",
        tmp_path / "user_memory.jsonl",
    )
    monkeypatch.setattr(
        source_settings,
        "SOURCE_SETTINGS_PATH",
        tmp_path / "source_settings.json",
    )

    def fake_start_daily_collection_run(env=None):
        signal = ScoredSignal(
            raw=RawPost(
                platform=Platform.HACKERNEWS,
                external_id="completion-without-profile-polish",
                title="Completion without profile polish",
                url="https://example.test/completion-without-profile-polish",
                content="Setup completion should only depend on local feed readiness.",
            ),
            relevance_score=0.88,
            urgency=UrgencyLevel.DIGEST,
            why_relevant="Validates setup completion ignores optional advanced forms.",
        )
        local_storage.save_signals([signal])
        return _FakeProcess()

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "sk-no-profile-polish",
            "algorithm_bundle_file": "ignored-export.zip",
            "profile_display_name": "Ignored Setup Profile",
            "profile_bio": "Ignored profile polish",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["redirect_to"] == "/feed"
    assert payload["state"]["feed_items_available"] is True
    assert payload["state"]["setup_completed"] is True
    assert payload["state"]["setup_completion_persisted"] is True

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-no-profile-polish" in env_text
    assert "HEDWIG_STORAGE=sqlite" in env_text
    assert "algorithm_bundle_file" not in env_text
    assert "profile_display_name" not in env_text
    assert "profile_bio" not in env_text
    assert "ignored-export.zip" not in env_text
    assert "Ignored Setup Profile" not in env_text

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["completed"] is True
    assert persisted["completion_action"] == "/feed"
    assert persisted["redirect_target"] == "/feed"
    assert persisted["feed_items"] == 1
    assert "algorithm_bundle_file" not in persisted
    assert "profile_display_name" not in persisted
    assert "profile_bio" not in persisted

    status_payload = client.get("/setup/one-shot/status").json()
    assert status_payload["state"]["setup_completed"] is True
    assert status_payload["state"]["feed_navigation_ready"] is True


def test_setup_completion_succeeds_with_advanced_settings_unopened(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.dashboard.env_manager import EnvManager
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.quickstart import DEFAULT_INTEREST
    from hedwig.sources import settings as source_settings
    from hedwig.storage import local as local_storage

    criteria_path = tmp_path / "criteria.yaml"
    source_settings_path = tmp_path / "source_settings.json"
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(
        hedwig_config,
        "USER_MEMORY_PATH",
        tmp_path / "user_memory.jsonl",
    )
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)

    def fake_start_daily_collection_run(env=None):
        signal = ScoredSignal(
            raw=RawPost(
                platform=Platform.HACKERNEWS,
                external_id="essential-only-first-feed",
                title="Essential-only first feed",
                url="https://example.test/essential-only-first-feed",
            ),
            relevance_score=0.84,
            urgency=UrgencyLevel.DIGEST,
            why_relevant="Confirms advanced setup stays optional.",
        )
        local_storage.save_signals([signal])
        return _FakeProcess()

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post("/setup/one-shot", data={"OPENAI_API_KEY": "sk-essential"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["interest"] == DEFAULT_INTEREST
    assert payload["redirect_to"] == "/feed"
    assert payload["state"]["storage_mode"] == "sqlite"
    assert payload["state"]["feed_items_available"] is True
    assert payload["state"]["setup_completed"] is True
    assert payload["state"]["delivery_required_for_completion"] is False
    assert payload["state"]["delivery_configuration_status"] == "deferred"
    assert payload["state"]["deferred_delivery_channels"] == ["slack", "discord", "smtp"]
    assert payload["source_preset_state"]["preset_id"] == "registry_default"

    criteria = yaml.safe_load(criteria_path.read_text(encoding="utf-8"))
    assert criteria["identity"]["focus"] == [DEFAULT_INTEREST]
    saved_sources = json.loads(source_settings_path.read_text(encoding="utf-8"))
    assert all(saved_sources["sources"].values())

    env_values = {}
    for line in (tmp_path / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            env_values[key] = value

    assert env_values["OPENAI_API_KEY"] == "sk-essential"
    assert env_values["HEDWIG_STORAGE"] == "sqlite"
    assert env_values["SUPABASE_URL"] == ""
    assert env_values["SUPABASE_KEY"] == ""
    for key in EnvManager.DELIVERY_KEYS:
        assert env_values[key] == ""
    for key in EnvManager.OPTIONAL_KEYS:
        if key not in EnvManager.MODEL_BACKEND_KEYS:
            assert env_values[key] == ""
    for key, value in EnvManager.MODEL_BACKEND_DEFAULTS.items():
        assert env_values[key] == value

    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["completed"] is True
    assert persisted["storage_mode"] == "sqlite"
    assert persisted["feed_items"] == 1
    assert persisted["completion_action"] == "/feed"
    assert persisted["delivery_configuration_status"] == "deferred"


def test_one_shot_setup_clears_supabase_and_skips_validation_for_local_completion(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("SUPABASE_URL", "https://stale.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "stale-service-role-key")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=sk-old",
                "HEDWIG_STORAGE=supabase",
                "SUPABASE_URL=https://stale.supabase.co",
                "SUPABASE_KEY=stale-service-role-key",
                "",
            ]
        ),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    launched = {}

    async def fail_if_general_validation_runs(values):
        raise AssertionError("one-shot local setup must not run credential validation")

    def fake_start_daily_collection_run(env=None):
        launched["env"] = env
        return _FakeProcess()

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(
        hedwig_config, "USER_MEMORY_PATH", tmp_path / "user_memory.jsonl"
    )
    monkeypatch.setattr(
        source_settings, "SOURCE_SETTINGS_PATH", tmp_path / "source_settings.json"
    )
    monkeypatch.setattr(dashboard_app, "test_all", fail_if_general_validation_runs)
    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "sk-local-only",
            "HEDWIG_STORAGE": "supabase",
            "SUPABASE_URL": "",
            "SUPABASE_KEY": "",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["state"]["storage_mode"] == "sqlite"
    assert payload["state"]["local_ready"] is True

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-local-only" in env_text
    assert "HEDWIG_STORAGE=sqlite" in env_text
    assert "SUPABASE_URL=\n" in env_text
    assert "SUPABASE_KEY=\n" in env_text
    assert "stale.supabase.co" not in env_text
    assert "stale-service-role-key" not in env_text
    assert "SUPABASE_URL" not in os.environ
    assert "SUPABASE_KEY" not in os.environ
    assert "SUPABASE_URL" not in launched["env"]
    assert "SUPABASE_KEY" not in launched["env"]
    assert hedwig_config.SUPABASE_URL == ""
    assert hedwig_config.SUPABASE_KEY == ""


def test_setup_one_shot_uses_existing_daily_collection_launcher(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    launched = {}

    def fake_start_daily_collection_run(env=None):
        launched["env"] = env
        return _FakeProcess()

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", tmp_path / "user_memory.jsonl")
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", tmp_path / "source_settings.json")
    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post("/setup/one-shot", data={"OPENAI_API_KEY": "sk-launcher"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["first_run_started"] is True
    assert payload["pid"] == _FakeProcess.pid
    assert launched["env"]["OPENAI_API_KEY"] == "sk-launcher"
    assert launched["env"]["HEDWIG_STORAGE"] == "sqlite"
    assert launched["env"]["HEDWIG_CRITERIA_PATH"] == str(criteria_path)
    assert "SUPABASE_URL" not in launched["env"]
    assert "SUPABASE_KEY" not in launched["env"]


def test_one_shot_setup_returns_page_renderable_failure_when_launcher_fails(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(
        hedwig_config, "USER_MEMORY_PATH", tmp_path / "user_memory.jsonl"
    )
    monkeypatch.setattr(
        source_settings, "SOURCE_SETTINGS_PATH", tmp_path / "source_settings.json"
    )

    def fail_start_daily_collection_run(env=None):
        raise OSError("launcher unavailable")

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fail_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post("/setup/one-shot", data={"OPENAI_API_KEY": "sk-launch-fail"})

    assert resp.status_code == 500
    payload = resp.json()
    assert payload["ok"] is False
    assert payload["first_run_started"] is False
    assert payload["error"] == "First feed run could not start: launcher unavailable"
    assert payload["redirect_to"] is None
    assert payload["state"]["openai_configured"] is True
    assert payload["state"]["local_ready"] is True
    assert payload["state"]["criteria_exists"] is True
    assert payload["state"]["db_exists"] is True
    assert payload["state"]["completion_action"] == "/feed"


def test_manual_daily_run_uses_shared_collection_launcher(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    from hedwig.dashboard import app as dashboard_app

    launched = {"count": 0}

    def fake_start_daily_collection_run(env=None):
        launched["count"] += 1
        launched["env"] = env
        return _FakeProcess()

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post("/run/daily")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "message": "Daily run started"}
    assert launched == {"count": 1, "env": None}


def test_one_shot_setup_creates_criteria_before_triggering_first_feed_run(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.quickstart import DEFAULT_INTEREST
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    observed = {}

    def fake_popen(args, cwd, env):
        observed["criteria_exists_at_first_run"] = criteria_path.exists()
        observed["criteria_env"] = env.get("HEDWIG_CRITERIA_PATH")
        observed["criteria_yaml"] = yaml.safe_load(
            criteria_path.read_text(encoding="utf-8")
        )
        observed["args"] = args
        return _FakeProcess()

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)

    client = TestClient(dashboard_app.create_app())
    resp = client.post("/setup/one-shot", data={"OPENAI_API_KEY": "sk-before-run"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["first_run_started"] is True
    assert observed["args"] == [dashboard_app.sys.executable, "-m", "hedwig"]
    assert observed["criteria_exists_at_first_run"] is True
    assert observed["criteria_env"] == str(criteria_path)
    assert observed["criteria_yaml"]["identity"]["role"] == "AI builder"
    assert observed["criteria_yaml"]["context"]["interests"] == [DEFAULT_INTEREST]
    assert payload["criteria_path"] == str(criteria_path)
    assert payload["state"]["criteria_exists"] is True


def test_one_shot_setup_returns_feed_redirect_when_first_run_creates_items(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", tmp_path / "user_memory.jsonl")
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", tmp_path / "source_settings.json")

    def fake_popen(args, cwd, env):
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO signals (platform, external_id, title, url)
                VALUES (?, ?, ?, ?)
                """,
                ("hackernews", "first-feed-item", "First feed item", "https://example.test/item"),
            )
        return _FakeProcess()

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)

    client = TestClient(dashboard_app.create_app())
    resp = client.post("/setup/one-shot", data={"OPENAI_API_KEY": "sk-feed-ready"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["redirect_to"] == "/feed"
    assert payload["redirect_immediately"] is True
    assert payload["state"]["redirect_target"] == "/feed"
    assert payload["state"]["feed_items_available"] is True
    assert payload["state"]["first_feed_data_verified"] is True
    assert payload["state"]["first_feed_item"]["external_id"] == "first-feed-item"
    assert payload["state"]["feed_navigation_ready"] is True
    assert payload["state"]["feed_items"] == 1
    assert payload["state"]["completion_action"] == "/feed"

    feed_resp = client.get(payload["redirect_to"])
    assert feed_resp.status_code == 200
    feed_body = feed_resp.text
    assert 'class="feed-shell"' in feed_body
    assert 'aria-label="Feed actions"' in feed_body
    assert "data-post-setup-feed-actions" in feed_body
    assert "data-post-setup-feed-nav" in feed_body
    assert 'id="feed-list"' in feed_body
    assert 'id="feed-empty"' in feed_body
    assert 'class="setup-shell"' not in feed_body
    assert 'id="setup-success-state"' not in feed_body
    assert "One-shot local onboarding" not in feed_body


def test_completed_one_shot_setup_preserves_visible_and_usable_feed_actions(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.sources import settings as source_settings
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(
        hedwig_config, "USER_MEMORY_PATH", tmp_path / "user_memory.jsonl"
    )
    monkeypatch.setattr(
        source_settings,
        "SOURCE_SETTINGS_PATH",
        tmp_path / "source_settings.json",
    )
    launched = {"count": 0}

    def fake_start_daily_collection_run(env=None):
        launched["count"] += 1
        launched["env"] = env
        signal = ScoredSignal(
            raw=RawPost(
                platform=Platform.HACKERNEWS,
                external_id="completed-setup-feed-actions",
                title="Completed setup feed actions",
                url="https://example.test/completed-setup-feed-actions",
                content="Completed first-run setup should keep feed controls usable.",
            ),
            relevance_score=0.93,
            urgency=UrgencyLevel.DIGEST,
            why_relevant="Confirms post-setup feed actions are preserved.",
        )
        launched["saved"] = local_storage.save_signals([signal])
        return _FakeProcess()

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    setup_resp = client.post(
        "/setup/one-shot",
        data={"OPENAI_API_KEY": "sk-feed-actions"},
    )

    assert setup_resp.status_code == 200
    setup_payload = setup_resp.json()
    assert setup_payload["redirect_to"] == "/feed"
    assert setup_payload["state"]["setup_completed"] is True
    assert setup_payload["state"]["feed_items_available"] is True
    assert setup_payload["state"]["completion_action"] == "/feed"

    setup_page = client.get("/setup")
    assert setup_page.status_code == 200
    assert 'class="setup-success-state visible"' in setup_page.text
    assert (
        'href="/feed" class="btn btn-primary btn-large" '
        'data-setup-success-feed-link data-setup-feed-navigation aria-label="View feed"'
        in setup_page.text
    )
    assert "View feed" in setup_page.text
    assert 'href="/feed" data-primary-nav-target="feed"' in setup_page.text

    feed_resp = client.get("/feed?stream=morning_deep&mode=dense_reader")
    assert feed_resp.status_code == 200
    feed_body = feed_resp.text
    assert 'aria-label="Feed actions"' in feed_body
    assert "data-post-setup-feed-actions" in feed_body
    assert 'action="/run/daily" method="post" data-feed-action="refresh-sync"' in feed_body
    assert 'href="/feed?stream=morning_deep&mode=dense_reader" data-feed-action="reload"' in feed_body
    assert 'href="/feed?stream=morning_deep&mode=grid" data-feed-filter="mode-grid"' in feed_body
    assert 'href="/feed?stream=morning_deep&mode=detail_swipe" data-feed-filter="mode-detail-swipe"' in feed_body
    assert 'href="/feed?stream=morning_deep&mode=dense_reader" data-feed-filter="mode-dense-reader"' in feed_body
    assert 'data-feed-filter="stream-default"' in feed_body
    assert 'data-feed-filter="stream-morning_deep"' in feed_body
    assert 'aria-label="Post-setup feed navigation"' in feed_body
    assert 'href="/chat" data-feed-nav-target="chat"' in feed_body
    assert 'href="/profile" data-feed-nav-target="profile"' in feed_body
    assert 'href="/status" data-feed-nav-target="status"' in feed_body
    for action, label in {
        "open": "Open",
        "read-state": "Mark read",
        "save": "Left: save/later",
        "dismiss": "Dismiss",
    }.items():
        assert f'data-feed-item-action="{action}"' in feed_body
        assert label in feed_body
    assert "async function onAction(card, act)" in feed_body
    assert "enqueue({...base, event_type: 'save'});" in feed_body
    assert "enqueue({...base, event_type: 'open'});" in feed_body
    assert "enqueue({...base, event_type: 'dismissed'});" in feed_body

    feed_payload = client.get("/feed/api?stream=morning_deep&limit=5").json()
    assert feed_payload["items"][0]["title"] == "Completed setup feed actions"
    signal_id = feed_payload["items"][0]["id"]

    reload_resp = client.get("/feed?stream=morning_deep&mode=dense_reader")
    assert reload_resp.status_code == 200
    grid_resp = client.get("/feed?stream=morning_deep&mode=grid")
    assert grid_resp.status_code == 200
    refresh_resp = client.post("/run/daily")
    assert refresh_resp.status_code == 200
    assert refresh_resp.json() == {"ok": True, "message": "Daily run started"}
    assert launched["count"] == 2

    event_resp = client.post(
        "/events/beacon",
        json={
            "events": [
                {
                    "signal_id": signal_id,
                    "event_type": "open",
                    "position_in_feed": 0,
                    "feed_id": "morning_deep",
                    "feed_mode": "dense_reader",
                },
                {
                    "signal_id": signal_id,
                    "event_type": "save",
                    "position_in_feed": 0,
                    "feed_id": "morning_deep",
                    "feed_mode": "dense_reader",
                },
                {
                    "signal_id": signal_id,
                    "event_type": "dismissed",
                    "position_in_feed": 0,
                    "feed_id": "morning_deep",
                    "feed_mode": "dense_reader",
                },
            ]
        },
    )
    assert event_resp.status_code == 200
    assert event_resp.json()["ok"] is True
    assert event_resp.json()["saved"] == 3


def test_setup_triggered_collection_persists_item_and_makes_feed_available(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.sources import settings as source_settings
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(
        hedwig_config, "USER_MEMORY_PATH", tmp_path / "user_memory.jsonl"
    )
    monkeypatch.setattr(
        source_settings, "SOURCE_SETTINGS_PATH", tmp_path / "source_settings.json"
    )
    launched = {}

    def fake_start_daily_collection_run(env=None):
        launched["env"] = env
        signal = ScoredSignal(
            raw=RawPost(
                platform=Platform.HACKERNEWS,
                external_id="setup-persisted-first-feed",
                title="Setup persisted first feed",
                url="https://example.test/setup-feed",
                content="Persisted by the setup-triggered first collection.",
            ),
            relevance_score=0.91,
            urgency=UrgencyLevel.DIGEST,
            why_relevant="Confirms first /feed availability after setup.",
        )
        launched["saved"] = local_storage.save_signals([signal])
        return _FakeProcess()

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={"OPENAI_API_KEY": "sk-feed-persist"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert launched["env"]["OPENAI_API_KEY"] == "sk-feed-persist"
    assert launched["env"]["HEDWIG_STORAGE"] == "sqlite"
    assert launched["env"]["HEDWIG_DB_PATH"] == str(db_path)
    assert launched["saved"] == 1
    assert payload["ok"] is True
    assert payload["redirect_to"] == "/feed"
    assert payload["setup_defaults"]["storage_mode"] == "sqlite"
    assert payload["setup_defaults"]["delivery_target"] == "/feed"
    assert payload["setup_defaults"]["delivery_required"] is False
    assert payload["first_feed_config"]["storage_mode"] == "sqlite"
    assert payload["first_feed_config"]["route"] == "/feed"
    assert payload["first_feed_config"]["delivery_target"] == "/feed"
    assert payload["state"]["storage_mode"] == "sqlite"
    assert payload["state"]["db_path"] == str(db_path)
    assert payload["state"]["criteria_exists"] is True
    assert payload["state"]["db_schema_ready"] is True
    assert payload["state"]["local_database_ready"] is True
    assert payload["state"]["setup_completed"] is True
    assert payload["state"]["setup_completion_persisted"] is True
    assert payload["state"]["first_run_status"] == "ready"
    assert payload["state"]["first_run_active"] is False
    assert payload["state"]["minimum_ready"] is True
    assert payload["state"]["progress_percent"] == 100
    assert payload["state"]["feed_items_available"] is True
    assert payload["state"]["first_feed_data_verified"] is True
    assert payload["state"]["first_feed_item"] == {
        "id": 1,
        "platform": "hackernews",
        "external_id": "setup-persisted-first-feed",
        "title": "Setup persisted first feed",
        "url": "https://example.test/setup-feed",
        "content": "Persisted by the setup-triggered first collection.",
        "author": "",
        "relevance_score": 0.91,
        "urgency": "digest",
        "why_relevant": "Confirms first /feed availability after setup.",
        "collected_at": payload["state"]["first_feed_item"]["collected_at"],
    }
    assert payload["state"]["feed_navigation_ready"] is True
    assert payload["state"]["feed_items"] == 1
    assert payload["state"]["completion_action"] == "/feed"
    assert payload["state"]["redirect_target"] == "/feed"

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT platform, external_id, title, url, relevance_score, urgency
            FROM signals
            WHERE external_id = ?
            """,
            ("setup-persisted-first-feed",),
        ).fetchone()

    assert row == (
        "hackernews",
        "setup-persisted-first-feed",
        "Setup persisted first feed",
        "https://example.test/setup-feed",
        0.91,
        "digest",
    )

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-feed-persist" in env_text
    assert "HEDWIG_STORAGE=sqlite" in env_text
    assert "SUPABASE_URL=\n" in env_text
    assert "SUPABASE_KEY=\n" in env_text

    setup_state_path = tmp_path / ".hedwig" / "setup_state.json"
    setup_state = json.loads(setup_state_path.read_text(encoding="utf-8"))
    assert setup_state["completed"] is True
    assert setup_state["storage_mode"] == "sqlite"
    assert setup_state["db_path"] == str(db_path)
    assert setup_state["criteria_exists"] is True
    assert setup_state["feed_items"] == 1
    assert setup_state["completion_action"] == "/feed"
    assert setup_state["redirect_target"] == "/feed"

    status_payload = client.get("/setup/one-shot/status").json()
    assert status_payload["redirect_to"] == "/feed"
    assert status_payload["redirect_immediately"] is True
    assert status_payload["state"]["setup_completed"] is True
    assert status_payload["state"]["storage_mode"] == "sqlite"
    assert status_payload["state"]["local_database_ready"] is True
    assert status_payload["state"]["feed_items_available"] is True
    assert status_payload["state"]["first_feed_data_verified"] is True
    assert status_payload["state"]["first_feed_item"]["external_id"] == (
        "setup-persisted-first-feed"
    )
    assert status_payload["state"]["feed_items"] == 1

    feed_page = client.get("/feed")
    assert feed_page.status_code == 200
    assert 'class="feed-list' in feed_page.text
    assert 'aria-label="Post-setup feed navigation"' in feed_page.text
    assert 'data-post-setup-feed-actions' in feed_page.text

    feed_payload = client.get("/feed/api?limit=5").json()
    assert feed_payload["items"][0]["title"] == "Setup persisted first feed"
    assert feed_payload["items"][0]["url"] == "https://example.test/setup-feed"
    assert feed_payload["items"][0]["platform"] == "hackernews"
    assert feed_payload["items"][0]["urgency"] == "digest"
    assert feed_payload["items"][0]["why_relevant"] == (
        "Confirms first /feed availability after setup."
    )


def test_completed_setup_feed_renders_local_sqlite_items_without_extra_config_prompt(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.sources import settings as source_settings
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(
        hedwig_config,
        "USER_MEMORY_PATH",
        tmp_path / "user_memory.jsonl",
    )
    monkeypatch.setattr(
        source_settings,
        "SOURCE_SETTINGS_PATH",
        tmp_path / "source_settings.json",
    )

    def fake_start_daily_collection_run(env=None):
        signal = ScoredSignal(
            raw=RawPost(
                platform=Platform.HACKERNEWS,
                external_id="setup-feed-no-extra-config",
                title="No extra configuration first feed",
                url="https://example.test/no-extra-config",
                content="The completed local setup feed should render immediately.",
            ),
            relevance_score=0.88,
            urgency=UrgencyLevel.DIGEST,
            why_relevant="Proves the first feed comes from local SQLite.",
        )
        local_storage.save_signals([signal])
        return _FakeProcess()

    monkeypatch.setattr(
        dashboard_app,
        "_start_daily_collection_run",
        fake_start_daily_collection_run,
    )

    client = TestClient(dashboard_app.create_app())
    setup_resp = client.post(
        "/setup/one-shot",
        data={"OPENAI_API_KEY": "sk-local-feed-visible"},
    )
    assert setup_resp.status_code == 200
    assert setup_resp.json()["redirect_to"] == "/feed"

    monkeypatch.setenv("HEDWIG_STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://stale.example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "stale-service-key")

    feed_resp = client.get("/feed")
    assert feed_resp.status_code == 200
    body = feed_resp.text
    assert "No extra configuration first feed" in body
    assert "Proves the first feed comes from local SQLite." in body
    assert 'data-initial-feed-item="true"' in body
    assert "delivery dashboard via local SQLite" in body
    assert "No source selection, Supabase setup, or delivery channel configuration is required." in body
    assert "Waiting for first feed items" not in body
    assert "Choose sources before using /feed" not in body
    assert "Select sources to continue" not in body

    feed_payload = client.get("/feed/api?limit=5").json()
    assert feed_payload["items"][0]["title"] == "No extra configuration first feed"
    assert feed_payload["items"][0]["platform"] == "hackernews"


def test_one_shot_setup_preserves_existing_registry_default_source_settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import get_registered_sources
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    source_settings.save_source_settings(
        {
            plugin_id: plugin_id != "arxiv"
            for plugin_id in get_registered_sources()
        },
        path=source_settings_path,
    )
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(dashboard_app.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "sk-test",
            "source_preset": "registry_default",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source_preset_state"]["preset_id"] == "registry_default"
    assert payload["source_preset_state"]["source_settings_created"] is False
    assert "arxiv" not in payload["source_preset_state"]["enabled_source_ids"]

    saved_sources = json.loads(source_settings_path.read_text(encoding="utf-8"))
    assert saved_sources["sources"]["arxiv"] is False
    assert saved_sources["sources"]["hackernews"] is True


def test_one_shot_setup_initializes_advanced_model_and_source_defaults_without_user_input(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    for key in (
        "OPENAI_MODEL_FAST",
        "OPENAI_MODEL_DEEP",
        "HEDWIG_PIPELINE",
        "HEDWIG_DISABLE_EMBEDDINGS",
    ):
        monkeypatch.delenv(key, raising=False)

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.dashboard.env_manager import EnvManager
    from hedwig.sources import get_registered_sources
    from hedwig.sources import settings as source_settings

    captured_run_env = {}
    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    registry = get_registered_sources()
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)

    def fake_popen(*args, **kwargs):
        captured_run_env.update(kwargs.get("env") or {})
        return _FakeProcess()

    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={"OPENAI_API_KEY": "sk-safe-defaults"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["source_preset_state"]["preset_id"] == "registry_default"
    assert payload["source_preset_state"]["source_settings_created"] is True
    assert set(payload["source_preset_state"]["enabled_source_ids"]) == set(registry)
    assert payload["setup_defaults"] == {
        "storage_mode": "sqlite",
        "interest_text": "AI agents, LLM tooling, and research papers",
        "source_preset": "registry_default",
        "delivery_target": "/feed",
        "delivery_required": False,
        "source_selection_required": False,
        "model_backend": EnvManager.MODEL_BACKEND_DEFAULTS,
    }
    assert payload["criteria_state"] == {
        "interest_text": "AI agents, LLM tooling, and research papers",
        "uses_default": True,
        "default_interest": "AI agents, LLM tooling, and research papers",
    }
    assert payload["state"]["storage_mode"] == "sqlite"
    assert payload["state"]["completion_action"] == "/feed"
    assert payload["state"]["delivery_required_for_completion"] is False

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-safe-defaults" in env_text
    assert "HEDWIG_STORAGE=sqlite" in env_text
    assert "SUPABASE_URL=" in env_text
    assert "SUPABASE_KEY=" in env_text
    for key, value in EnvManager.MODEL_BACKEND_DEFAULTS.items():
        assert f"{key}={value}" in env_text
        assert captured_run_env[key] == value
        assert os.environ[key] == value
    assert hedwig_config.OPENAI_MODEL_FAST == "gpt-4o-mini"
    assert hedwig_config.OPENAI_MODEL_DEEP == "gpt-4o"

    saved_sources = json.loads(source_settings_path.read_text(encoding="utf-8"))
    assert set(saved_sources["sources"]) == set(registry)
    assert all(saved_sources["sources"].values())


def test_one_shot_setup_uses_optional_interest_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    custom_interest = "AI observability tools for local-first agents"
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(dashboard_app.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "sk-test",
            "interest_text": f"  {custom_interest}  ",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["interest"] == custom_interest
    assert payload["criteria_state"]["interest_text"] == custom_interest
    assert payload["criteria_state"]["uses_default"] is False
    assert payload["state"]["criteria_exists"] is True
    assert payload["state"]["local_ready"] is True

    criteria = yaml.safe_load(criteria_path.read_text(encoding="utf-8"))
    assert criteria["identity"]["focus"] == [custom_interest]
    assert criteria["signal_preferences"]["care_about"][0] == custom_interest
    assert criteria["context"]["interests"] == [custom_interest]
    with sqlite3.connect(tmp_path / "hedwig.db") as conn:
        version = conn.execute(
            "SELECT version, created_by, criteria FROM criteria_versions"
        ).fetchone()
        memory = conn.execute(
            "SELECT confirmed_interests, natural_language_feedback FROM user_memory"
        ).fetchone()

    assert version[0] == 1
    assert version[1] == "one_shot_setup"
    assert yaml.safe_load(version[2])["context"]["interests"] == [custom_interest]
    assert json.loads(memory[0]) == [custom_interest]
    assert json.loads(memory[1]) == [custom_interest]
    latest_memory = json.loads(user_memory_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert latest_memory["confirmed_interests"] == [custom_interest]


def test_one_shot_setup_writes_valid_criteria_yaml_from_resolved_interest(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    raw_interest = '  "AI observability": local-first agents\nand YAML-safe setup  '
    resolved_interest = '"AI observability": local-first agents and YAML-safe setup'
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(
        dashboard_app.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(),
    )

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "sk-test",
            "interest_text": raw_interest,
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["interest"] == resolved_interest
    assert payload["criteria_path"] == str(criteria_path)
    assert payload["criteria_state"]["interest_text"] == resolved_interest
    assert payload["criteria_state"]["uses_default"] is False

    criteria_text = criteria_path.read_text(encoding="utf-8")
    criteria = yaml.safe_load(criteria_text)
    assert isinstance(criteria, dict)
    assert criteria["identity"] == {
        "role": "AI builder",
        "focus": [resolved_interest],
    }
    assert criteria["signal_preferences"]["care_about"][0] == resolved_interest
    assert criteria["context"]["interests"] == [resolved_interest]
    assert criteria["metadata"] == {
        "generated_by": "quickstart",
        "source": "single-sentence interest",
    }

    for section, key in (
        ("identity", "focus"),
        ("signal_preferences", "care_about"),
        ("signal_preferences", "ignore"),
        ("urgency_rules", "alert"),
        ("urgency_rules", "digest"),
        ("urgency_rules", "skip"),
        ("context", "interests"),
    ):
        assert criteria[section][key]
        assert all(isinstance(item, str) and item for item in criteria[section][key])

    with sqlite3.connect(tmp_path / "hedwig.db") as conn:
        version = conn.execute(
            "SELECT created_by, criteria FROM criteria_versions"
        ).fetchone()

    assert version[0] == "one_shot_setup"
    assert yaml.safe_load(version[1]) == criteria


def test_one_shot_setup_persists_selected_source_preset(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.sources import settings as source_settings

    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(dashboard_app.subprocess, "Popen", lambda *args, **kwargs: _FakeProcess())

    client = TestClient(dashboard_app.create_app())
    resp = client.post(
        "/setup/one-shot",
        data={
            "OPENAI_API_KEY": "sk-test",
            "source_preset": "research_papers",
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source_preset_state"]["preset_id"] == "research_papers"
    assert payload["source_preset_state"]["enabled_source_ids"] == [
        "arxiv",
        "arxiv_recsys",
        "papers_with_code",
        "semantic_scholar",
    ]

    saved = json.loads(source_settings_path.read_text(encoding="utf-8"))
    assert saved["sources"]["arxiv"] is True
    assert saved["sources"]["arxiv_recsys"] is True
    assert saved["sources"]["papers_with_code"] is True
    assert saved["sources"]["semantic_scholar"] is True
    assert saved["sources"]["hackernews"] is False
    assert saved["sources"]["reddit"] is False


def test_setup_state_api_reports_blocking_and_non_blocking_requirements(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    payload = client.get("/setup/state").json()
    state = payload["state"]

    assert payload["schema_version"] == "hedwig.setup_state_api.v1"
    assert payload["setup_status"] == "blocked"
    assert payload["setup_complete"] is False
    assert payload["setup_completion_blocked"] is True
    assert state["setup_status"] == payload["setup_status"]
    assert state["partial_readiness"] == payload["partial_readiness"]
    assert state["blocking_requirement_ids"] == payload["blocking_requirement_ids"]
    assert payload["partial_readiness"]["openai_ready"] is False
    assert payload["partial_readiness"]["can_start_first_run"] is False
    assert payload["partial_readiness"]["can_open_feed"] is False

    openai_requirement = _setup_requirement(payload, "openai_api_key")
    storage_requirement = _setup_requirement(payload, "local_sqlite_storage")
    delivery_requirement = _setup_requirement(payload, "delivery_channels")
    supabase_requirement = _setup_requirement(payload, "supabase_storage")

    assert openai_requirement["blocking"] is True
    assert openai_requirement["required_for_completion"] is True
    assert openai_requirement["target"] == "#setup-essential"
    assert storage_requirement["configured"] is True
    assert storage_requirement["blocking"] is False
    assert delivery_requirement["non_blocking"] is True
    assert delivery_requirement["status"] == "deferred"
    assert supabase_requirement["non_blocking"] is True
    assert "openai_api_key" in payload["blocking_requirement_ids"]
    assert "delivery_channels" in payload["non_blocking_requirement_ids"]
    assert "supabase_storage" in payload["non_blocking_requirement_ids"]


def test_setup_state_api_reports_partial_readiness_after_openai_local_save(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    criteria_path = tmp_path / "criteria.yaml"
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-partial\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    payload = client.get("/setup/state").json()

    assert payload["setup_status"] == "partial_ready"
    assert payload["setup_complete"] is False
    assert payload["partial_readiness"]["minimum_required_inputs_saved"] is True
    assert payload["partial_readiness"]["openai_ready"] is True
    assert payload["partial_readiness"]["local_mode_ready"] is True
    assert payload["partial_readiness"]["criteria_ready"] is False
    assert payload["partial_readiness"]["local_database_ready"] is False
    assert payload["partial_readiness"]["first_feed_ready"] is False
    assert payload["partial_readiness"]["can_start_first_run"] is True
    assert payload["partial_readiness"]["can_open_feed"] is False
    assert payload["state"]["local_ready"] is True
    assert payload["state"]["setup_completion_blocked"] is True
    assert payload["blocking_requirement_ids"] == [
        "criteria_profile",
        "local_sqlite_schema",
        "first_feed_items",
    ]
    assert _setup_requirement(payload, "openai_api_key")["blocking"] is False
    assert _setup_requirement(payload, "source_defaults")["status"] == "default_ready"
    assert _setup_requirement(payload, "model_backend_settings")["status"] == "default_ready"
    assert _setup_requirement(payload, "source_api_keys")["status"] == "advanced_optional"
    assert "supabase_storage" in payload["non_blocking_requirement_ids"]
    assert "delivery_channels" in payload["non_blocking_requirement_ids"]


def test_setup_state_api_reports_in_progress_first_collection_before_completion(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-running-state\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["running first collection"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.update_collection_run(
        run_id,
        status="filtered",
        counts={
            "posts_collected": 12,
            "posts_filtered": 4,
            "signals_scored": 0,
            "signals_saved": 0,
        },
    )

    client = TestClient(create_app())
    payload = client.get("/setup/state").json()
    state = payload["state"]

    assert payload["setup_status"] == "partial_ready"
    assert payload["setup_complete"] is False
    assert payload["setup_completion_blocked"] is True
    assert payload["blocking_requirement_ids"] == ["first_feed_items"]
    assert payload["redirect_to"] is None
    assert payload["redirect_immediately"] is False
    assert payload["partial_readiness"]["minimum_required_inputs_saved"] is True
    assert payload["partial_readiness"]["openai_ready"] is True
    assert payload["partial_readiness"]["criteria_ready"] is True
    assert payload["partial_readiness"]["local_database_ready"] is True
    assert payload["partial_readiness"]["first_feed_ready"] is False
    assert payload["partial_readiness"]["can_start_first_run"] is True
    assert payload["partial_readiness"]["can_open_feed"] is False
    assert payload["partial_readiness"]["first_run_status"] == "waiting_for_feed_items"
    assert payload["partial_readiness"]["progress_percent"] == 75
    assert state["minimum_ready"] is True
    assert state["first_run_active"] is True
    assert state["first_run_status"] == "waiting_for_feed_items"
    assert state["feed_items_available"] is False
    assert state["feed_navigation_ready"] is False
    assert state["collection_progress_status"] == "filtered"
    assert state["collection_progress_counts"] == {
        "posts_collected": 12,
        "posts_filtered": 4,
        "signals_scored": 0,
        "signals_saved": 0,
        "alerts_count": 0,
        "digest_count": 0,
        "skipped_count": 0,
    }
    assert state["collection_progress_errors"] == []
    assert _setup_requirement(payload, "first_feed_items")["blocking"] is True
    assert _setup_requirement(payload, "first_feed_items")["configured"] is False
    assert not state_path.exists()

    feed_payload = client.get("/feed/api?limit=5").json()
    assert feed_payload["items"] == []
    assert feed_payload["collection_progress"]["status"] == "filtered"
    assert feed_payload["collection_progress"]["posts_collected"] == 12
    assert feed_payload["collection_progress"]["posts_filtered"] == 4
    assert feed_payload["setup_readiness"]["setup_complete"] is False
    assert feed_payload["setup_readiness"]["setup_status"] == "partial_ready"
    assert feed_payload["setup_readiness"]["feed_items_available"] is False
    assert feed_payload["setup_readiness"]["can_read_feed_data"] is False
    assert feed_payload["setup_readiness"]["requires_setup_complete"] is False
    assert feed_payload["setup_readiness"]["blocking_requirement_ids"] == [
        "first_feed_items"
    ]


def test_setup_page_bootstraps_collection_lifecycle_polling_for_active_run(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-active-setup-page\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["active setup polling"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.update_collection_run(
        run_id,
        status="filtered",
        counts={"posts_collected": 7, "posts_filtered": 3},
    )

    body = TestClient(create_app()).get("/setup").text

    assert "const SETUP_INITIAL_COLLECTION_POLL = {" in body
    assert f"run_id: {run_id}" in body
    assert 'collection_progress_status: "filtered"' in body
    assert "is_active: true" in body
    assert "startSetupCollectionLifecyclePolling();" in body
    assert "scheduleOneShotStatusRefresh(SETUP_COLLECTION_POLL_INTERVAL_MS, {force: true})" in body


def test_setup_page_renders_collection_failure_state_in_place(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-failed-setup-page\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["failed setup polling"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.update_collection_run(
        run_id,
        status="filtered",
        counts={"posts_collected": 6, "posts_filtered": 2},
    )
    local_storage.finish_collection_run(
        run_id,
        status="failed",
        error="Missing env vars: OPENAI_API_KEY",
    )

    client = TestClient(create_app())
    body = client.get("/setup").text

    failure_start = body.index('id="setup-first-run-failure"')
    failure_panel = body[
        body.rindex("<div", 0, failure_start) :
        body.index('id="setup-first-run-progress"', failure_start)
    ]
    assert 'data-run-feedback-state="failure"' in body
    assert "First collection failed" in body
    assert "Missing env vars: OPENAI_API_KEY" in failure_panel
    assert 'data-visible="true"' in failure_panel
    assert "hidden" not in failure_panel
    assert 'class="setup-first-run-progress failure"' in body
    assert 'data-active="false"' in body
    assert 'aria-busy="false"' in body
    assert "Fix the issue, then retry from this page" in body
    assert "is_terminal: true" in body

    payload = client.get("/setup/collection-progress").json()
    assert payload["state"]["first_run_status"] == "failed"
    assert payload["state"]["first_run_active"] is False
    assert payload["state"]["collection_failed"] is True
    assert payload["collection_progress"]["status"] == "failed"
    assert payload["collection_progress"]["is_terminal"] is True
    assert payload["collection_progress"]["errors"][0]["message"] == (
        "Missing env vars: OPENAI_API_KEY"
    )


def test_setup_page_renders_no_items_collection_state_in_place(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-empty-setup-page\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["empty setup polling"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.finish_collection_run(
        run_id,
        status="no_items",
        counts={"posts_collected": 0, "posts_filtered": 0},
    )

    client = TestClient(create_app())
    body = client.get("/setup").text

    assert 'data-run-feedback-state="failure"' in body
    assert "No feed items yet" in body
    assert "First collection finished with no items" in body
    assert "The first collection finished without feed items" in body
    assert 'data-visible="true"' in body
    assert 'class="setup-first-run-progress failure"' in body
    assert 'aria-valuenow="90"' in body

    payload = client.get("/setup/collection-progress").json()
    assert payload["state"]["first_run_status"] == "no_items"
    assert payload["state"]["first_run_active"] is False
    assert payload["state"]["collection_no_items"] is True
    assert payload["state"]["progress_percent"] == 90
    assert payload["collection_progress"]["status"] == "no_items"
    assert payload["collection_progress"]["is_terminal"] is True


def test_collection_progress_polling_endpoints_expose_setup_feed_workflow(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-progress-poll\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["polling progress"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot", "pid": 4242},
    )
    local_storage.update_collection_run(
        run_id,
        status="scored",
        counts={
            "posts_collected": 9,
            "posts_filtered": 5,
            "signals_scored": 3,
        },
    )

    client = TestClient(create_app())
    setup_payload = client.get("/setup/collection-progress").json()
    feed_payload = client.get("/feed/collection-progress").json()

    for payload, endpoint in (
        (setup_payload, "/setup/collection-progress"),
        (feed_payload, "/feed/collection-progress"),
    ):
        progress = payload["collection_progress"]
        assert payload["schema_version"] == "hedwig.collection_progress_api.v1"
        assert payload["polling"] == {
            "endpoint": endpoint,
            "interval_ms": 2500,
            "method": "GET",
        }
        assert progress["schema_version"] == "hedwig.collection_progress.v1"
        assert progress["run_id"] == run_id
        assert progress["run_type"] == "daily"
        assert progress["status"] == "scored"
        assert progress["first_run_active"] is True
        assert progress["is_active"] is True
        assert progress["is_terminal"] is False
        assert progress["progress_percent"] == 85
        assert progress["counts"]["posts_collected"] == 9
        assert progress["counts"]["posts_filtered"] == 5
        assert progress["counts"]["signals_scored"] == 3
        assert progress["metadata"]["source"] == "setup_one_shot"
        assert progress["metadata"]["pid"] == 4242
        assert progress["last_updated_at"]
        assert payload["setup_status"] == "partial_ready"
        assert payload["setup_complete"] is False
        assert payload["feed_items_available"] is False
        assert payload["redirect_to"] is None
        assert payload["redirect_immediately"] is False
        assert payload["state"]["collection_progress_status"] == "scored"


def test_setup_exposes_partial_feed_readiness_before_collection_completes(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-partial-feed\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["partial feed readiness"]}}),
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.storage import local as local_storage

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    local_storage.init_db()
    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.save_signals(
        [
            ScoredSignal(
                raw=RawPost(
                    platform=Platform.HACKERNEWS,
                    external_id="partial-before-complete",
                    title="Partial feed before completion",
                    url="https://example.test/partial-before-complete",
                ),
                relevance_score=0.91,
                urgency=UrgencyLevel.DIGEST,
                why_relevant="Feed row is usable before collection completion.",
            )
        ]
    )
    local_storage.update_collection_run(
        run_id,
        status="saved",
        counts={"signals_saved": 1},
    )

    client = TestClient(create_app())
    setup_payload = client.get("/setup/state").json()
    state = setup_payload["state"]

    assert setup_payload["setup_status"] == "partial_ready"
    assert setup_payload["setup_complete"] is False
    assert setup_payload["setup_completion_blocked"] is True
    assert setup_payload["redirect_to"] is None
    assert setup_payload["redirect_immediately"] is False
    assert setup_payload["blocking_requirement_ids"] == [
        "first_collection_completed"
    ]
    assert _setup_requirement(setup_payload, "first_feed_items")["configured"] is True
    assert (
        _setup_requirement(setup_payload, "first_collection_completed")["blocking"]
        is True
    )
    assert state["feed_items_available"] is True
    assert state["feed_navigation_ready"] is True
    assert state["feed_navigation_available"] is False
    assert state["feed_navigation_blocked"] is True
    assert state["feed_navigation_blocking_criteria_ids"] == [
        "first_collection_completed"
    ]
    assert state["feed_navigation_readiness"]["schema_version"] == (
        "hedwig.feed_navigation_readiness.v1"
    )
    assert state["feed_navigation_readiness"]["ready"] is False
    assert state["feed_navigation_readiness"]["redirect_target_when_ready"] == "/feed"
    criteria = {
        criterion["id"]: criterion
        for criterion in state["feed_navigation_readiness"]["criteria"]
    }
    assert criteria["openai_local_mode"]["satisfied"] is True
    assert criteria["criteria_profile"]["satisfied"] is True
    assert criteria["local_sqlite_ready"]["satisfied"] is True
    assert criteria["verified_feed_item"]["satisfied"] is True
    assert criteria["first_collection_completed"]["satisfied"] is False
    assert criteria["first_collection_not_failed"]["satisfied"] is True
    assert state["first_feed_usable_before_collection_complete"] is True
    assert state["collection_process_incomplete"] is True
    assert state["first_collection_completed"] is False
    assert state["first_run_active"] is True
    assert state["setup_navigation_locked"] is True
    assert state["completion_navigation_disabled"] is True
    assert state["navigation_lock_reason"] == "first_collection_in_progress"
    assert state["redirect_target"] is None
    assert state["first_run_status"] == "feed_ready_collection_finishing"
    assert state["progress_percent"] == 95
    assert not state_path.exists()

    progress_payload = client.get("/setup/collection-progress").json()
    progress = progress_payload["collection_progress"]
    assert progress_payload["setup_status"] == "partial_ready"
    assert progress_payload["setup_complete"] is False
    assert progress_payload["feed_items_available"] is True
    assert progress_payload["redirect_to"] is None
    assert progress_payload["redirect_immediately"] is False
    assert progress["feed_data_usable"] is True
    assert progress["collection_process_incomplete"] is True
    assert progress["first_feed_usable_before_collection_complete"] is True
    assert progress["is_active"] is True
    assert progress["is_terminal"] is False

    feed_payload = client.get("/feed/api?limit=5").json()
    setup_readiness = feed_payload["setup_readiness"]
    assert feed_payload["items"][0]["title"] == "Partial feed before completion"
    assert setup_readiness["setup_complete"] is False
    assert setup_readiness["setup_status"] == "partial_ready"
    assert setup_readiness["can_read_feed_data"] is True
    assert setup_readiness["feed_items_available"] is True
    assert setup_readiness["feed_navigation_available"] is False
    assert setup_readiness["feed_navigation_blocking_criteria_ids"] == [
        "first_collection_completed"
    ]
    assert setup_readiness["first_feed_usable_before_collection_complete"] is True
    assert setup_readiness["collection_process_incomplete"] is True
    assert setup_readiness["blocking_requirement_ids"] == [
        "first_collection_completed"
    ]

    body = client.get("/setup").text
    assert 'id="setup-partial-feed-readiness"' in body
    assert 'data-visible="true"' in body
    assert 'data-completion-gate="partial"' in body
    assert 'class="completion-link partial"' in body
    assert 'data-partial-feed-ready="true"' in body
    assert 'class="setup-primary-nav partial"' in body
    assert 'data-ready="false"' in body
    assert 'data-setup-navigation-locked="true"' in body
    assert "Your local feed is almost ready while collection finishes." in body
    assert "data-setup-partial-feed-copy" in body
    assert "stay on /setup until the tracked first collection completes" in body
    assert "Feed navigation unlocks after completion." in body
    assert "Local SQLite already has readable feed items. Stay on /setup while this page keeps polling for the tracked collection to finish." in body
    assert "Feed items are readable from local SQLite now. Stay on /setup while it keeps watching the first collection." in body
    assert "Feed unlocks after collection" in body
    assert 'data-setup-feed-navigation' in body
    assert 'aria-disabled="true"' in body
    assert "function interceptSetupFeedNavigation(event)" in body
    assert "document.addEventListener('click', interceptSetupFeedNavigation, true)" in body
    assert "Stay on /setup while Hedwig finishes collection." in body
    assert "feed usable, collection finishing" in body
    assert "const partialState = document.querySelector('[data-setup-partial-feed-readiness]')" in body
    assert "partialState.hidden = !partiallyReady" in body
    assert "partialState.dataset.visible = partiallyReady ? 'true' : 'false'" in body
    assert "partialState.classList.toggle('visible', partiallyReady)" in body
    assert "first_feed_usable_before_collection_complete:" in body
    assert "collection_process_incomplete:" in body
    assert "Feed navigation readiness criteria" in body
    assert 'data-feed-navigation-readiness-criteria' in body
    assert 'data-feed-navigation-criterion="first_collection_completed"' in body
    assert 'data-feed-navigation-available="false"' in body
    assert "/feed navigation unlocks after setup completion only when every local" in body


def test_setup_state_api_reports_completion_when_local_feed_is_ready(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-complete-state\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["state api completion"]}}),
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO signals (platform, external_id, title) VALUES (?, ?, ?)",
            ("hackernews", "state-api-item", "State API completion item"),
        )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    payload = client.get("/setup/state").json()

    assert payload["setup_status"] == "complete"
    assert payload["setup_complete"] is True
    assert payload["setup_completion_blocked"] is False
    assert payload["blocking_setup_requirements"] == []
    assert payload["blocking_requirement_ids"] == []
    assert payload["redirect_to"] == "/feed"
    assert payload["redirect_immediately"] is True
    assert payload["partial_readiness"]["can_open_feed"] is True
    assert payload["partial_readiness"]["first_feed_ready"] is True
    assert payload["partial_readiness"]["feed_navigation_available"] is True
    assert payload["partial_readiness"]["progress_percent"] == 100
    assert payload["state"]["setup_completed"] is True
    assert payload["state"]["setup_complete"] is True
    assert payload["state"]["feed_navigation_available"] is True
    assert payload["state"]["feed_navigation_blocked"] is False
    assert payload["state"]["feed_navigation_blocking_criteria_ids"] == []
    assert payload["state"]["feed_navigation_readiness"]["ready"] is True
    assert all(
        criterion["satisfied"]
        for criterion in payload["state"]["feed_navigation_readiness"]["criteria"]
    )
    assert payload["state"]["setup_completion_persisted"] is True
    assert _setup_requirement(payload, "first_feed_items")["configured"] is True
    assert _setup_requirement(payload, "delivery_channels")["non_blocking"] is True
    assert state_path.exists()


def test_setup_status_detects_missing_local_state_without_creating_files(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-existing\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    payload = client.get("/setup/one-shot/status").json()
    state = payload["state"]

    assert payload["redirect_to"] is None
    assert state["openai_configured"] is True
    assert state["local_ready"] is True
    assert state["env_file_exists"] is True
    assert state["criteria_exists"] is False
    assert state["local_config_exists"] is False
    assert state["db_exists"] is False
    assert state["db_schema_ready"] is False
    assert state["local_database_ready"] is False
    assert state["setup_completed"] is False
    assert state["setup_completion_stale"] is False
    assert state["missing_local_state"] == [
        "criteria.yaml",
        "sqlite database",
        "feed items",
    ]
    assert not criteria_path.exists()
    assert not db_path.exists()
    assert not state_path.exists()


def test_setup_completion_marker_is_stale_when_local_state_is_missing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-existing\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    state_path.parent.mkdir(parents=True)
    stale_marker = {
        "schema_version": "hedwig.setup_state.v1",
        "completed": True,
        "completed_at": "2026-05-01T00:00:00+00:00",
        "last_seen_at": "2026-05-01T00:00:00+00:00",
        "storage_mode": "sqlite",
        "db_path": str(db_path),
        "criteria_exists": True,
        "feed_items": 3,
        "completion_action": "/feed",
        "redirect_target": "/feed",
        "delivery_channels_configured": False,
        "delivery_configuration_status": "deferred",
        "delivery_configuration_deferred": True,
        "delivery_configuration_deferred_at": "2026-05-01T00:00:00+00:00",
        "delivery_configuration_resume_target": (
            "/setup#setup-delivery-configuration"
        ),
        "deferred_delivery_channels": ["slack", "discord", "smtp"],
    }
    state_path.write_text(
        json.dumps(stale_marker, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    original_marker = state_path.read_text(encoding="utf-8")

    from hedwig import config as hedwig_config
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)

    client = TestClient(create_app())
    payload = client.get("/setup/one-shot/status").json()
    state = payload["state"]

    assert payload["redirect_to"] is None
    assert state["persisted_setup_completed"] is True
    assert state["setup_completed"] is False
    assert state["setup_completion_persisted"] is False
    assert state["setup_completion_stale"] is True
    assert state["setup_completed_at"] == stale_marker["completed_at"]
    assert state["persisted_feed_items"] == 3
    assert state["missing_local_state"] == [
        "criteria.yaml",
        "sqlite database",
        "feed items",
    ]
    assert state_path.read_text(encoding="utf-8") == original_marker
    assert not criteria_path.exists()
    assert not db_path.exists()
