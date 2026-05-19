# Issue 34 Dashboard Navigation Groups

This note classifies the issue #32 dashboard routes for issue #34 navigation simplification. The goal is progressive disclosure: keep every existing capability reachable while making the first-level dashboard understandable for first-time local users.

## Primary Navigation

| Group | Routes | Rationale |
| --- | --- | --- |
| Primary | `/setup`, `/feed`, `/brief`, `/chat` | High-frequency first-run and daily-use surfaces: setup, default feed consumption, briefing consumption, and natural-language steering. |

### Most-Used Primary Route Selection

The primary set is intentionally limited to four route targets from the issue #32 inventory:

| Route | Usage signal | Why it stays first-level |
| --- | --- | --- |
| `/setup` | First-run configuration and recovery entry point. | New local users need it before other dashboard capabilities are actionable. |
| `/feed` | Default post-setup delivery and daily consumption surface. | It is the normal reading destination after one-shot setup. |
| `/brief` | Daily, weekly, and critical summary consumption surface. | It gives returning users a compact reading path without requiring external delivery. |
| `/chat` | Natural-language steering and command surface. | It is the simplest ongoing control path for changing what Hedwig does. |

All other HTML routes from the issue #32 inventory are preserved below as secondary, advanced, conditional SaaS/account, or supporting endpoints.

## Secondary Navigation

| Group | Routes | Rationale |
| --- | --- | --- |
| Read | `/`, `/dashboard/generative`, `/ambient/pwa`, `/signals`, `/profile`, `/status` | Lower-frequency reading, alternate dashboard, monitoring, ownership, and recovery surfaces that support normal use without being first-run essentials. |
| Steer | `/criteria`, `/onboarding`, `/onboarding/auto`, `/sovereignty` | Lower-frequency preference, recalibration, auto-context, and ownership contract surfaces used when the user intentionally adjusts Hedwig. |

These groups render inside the dedicated `nav-secondary-surface` disclosure menu area with an explicit `Secondary` tier label, so they stay visible as preserved capabilities without competing with the primary setup, feed, brief, and chat path. The shell also exposes a compact `More` overflow menu that repeats every route moved out of primary navigation for users who scan for a single catch-all access point.

### Routes Moved Out Of Primary Navigation

These routes were present in the issue #32 first-level dashboard header inventory but are intentionally removed from the issue #34 primary route set. Each route remains reachable through the listed shell destination.

| Route removed from primary | Secondary navigation destination | Destination tier | Why it moves out of primary |
| --- | --- | --- | --- |
| `/` | Read > Home | Secondary | Operations dashboard remains available, but first-time users should start with setup/feed rather than the legacy home surface. |
| `/ambient/pwa` | Read > Ambient | Secondary | Ambient/PWA delivery is a preserved reading surface, not the default first-run destination. |
| `/signals` | Read > Signals | Secondary | Raw signal review supports monitoring and debugging after the feed is usable. |
| `/profile` | Read > Profile | Secondary | Ownership, export, and profile details are important follow-up tasks rather than first-run navigation. |
| `/status` | Read > Status | Secondary | Health and recovery stay close to daily use without competing with setup/feed. |
| `/criteria` | Steer > Criteria | Secondary | Raw criteria editing remains available for intentional recalibration after the simple setup path. |
| `/onboarding` | Steer > Onboarding | Secondary | Socratic onboarding is preserved as a steering path, but not required for first-run local setup. |
| `/onboarding/auto` | Steer > Auto Onboarding | Secondary | Auto-context inference remains optional and advanced relative to first-time comprehension. |
| `/sovereignty` | Steer > Sovereignty | Secondary | Ownership boundaries remain visible while staying outside the compact primary surface. |
| `/sources` | Tools > Sources | Advanced | Source registry inspection is a power-user control. |
| `/settings` | Tools > Settings | Advanced | Detailed source and backend settings are preserved as advanced controls. |
| `/evolution` | Tools > Evolution | Advanced | Algorithm evolution history is useful but not a first-run essential. |
| `/sandbox` | Tools > Sandbox | Advanced | Mutation simulation is experimentation tooling. |
| `/meta` | Tools > Meta | Advanced | Meta-evolution and algorithm edit controls are advanced self-improvement tooling. |
| `/demo` | Tools > Demo | Advanced | Demo seed/reset is preserved for walkthroughs and testing, not normal first-level use. |
| `/admin` | Tools > Reset | Advanced | Destructive reset controls must stay separated from primary navigation. |

## Advanced Navigation

| Group | Routes | Rationale |
| --- | --- | --- |
| Advanced tools | `/sources`, `/settings`, `/evolution`, `/sandbox`, `/meta`, `/demo`, `/admin` | Power-user, backend, experimentation, demo, and destructive/admin surfaces. These remain reachable but should not compete with primary setup, feed, brief, or chat actions. |

This group renders inside the same secondary access surface with an explicit `Advanced` tier label because these destinations are lower-frequency, higher-power, or potentially destructive.

## SaaS And Public Navigation

| Group | Routes | Rationale |
| --- | --- | --- |
| Account | `/landing`, `/ko`, `/zh`, `/signup`, `/login`, `/auth/callback`, `/billing`, `/invite`, `/terms`, `/privacy`, `/about` | SaaS discovery, localized landing, account, OAuth callback, billing, referral, legal, and informational surfaces are visible from the shell only when `saas_mode=True`, matching route registration and avoiding broken links in local single-user mode. |

This group renders inside the same secondary access surface with an explicit `SaaS` tier label. It maps every SaaS/public HTML route from the issue #32 inventory to a visible shell entry without adding those SaaS-only links to the local single-user dashboard.

## Overflow Navigation

| Group | Routes | Rationale |
| --- | --- | --- |
| More | `/`, `/ambient/pwa`, `/signals`, `/profile`, `/status`, `/criteria`, `/onboarding`, `/onboarding/auto`, `/sovereignty`, `/sources`, `/settings`, `/evolution`, `/sandbox`, `/meta`, `/demo`, `/admin` | Catch-all overflow access repeats the exact routes removed from the first-level primary surface so users can still discover every preserved capability from one compact menu. |

## Preserved Dashboard Route Audit

Issue #34 changes the shell hierarchy only. The route audit below is the preservation contract for the navigation work: every existing dashboard route remains registered and reachable through either the visible shell, an in-page link/control, a route family used by that page, or the SaaS/public surface where it already belonged.

### HTML Surfaces

| Route | Template | Navigation / reachability tier | Preservation note |
| --- | --- | --- | --- |
| `/` | `home.html` | Secondary Read shell link | Operations dashboard and first-run redirect to `/setup` remain intact. |
| `/setup` | `setup.html` | Primary shell link | First-run OpenAI/local SQLite setup stays the main entry point. |
| `/onboarding` | `onboarding.html` | Secondary Steer shell link | Socratic steering remains available after setup. |
| `/signals` | `signals.html` | Secondary Read shell link | Raw signal monitoring and chat deep links remain available. |
| `/dashboard/generative` | `generative.html` | Secondary Read shell link | Alternate dashboard visualization remains visible without becoming a primary route. |
| `/evolution` | `evolution.html` | Advanced Tools shell link | Evolution timeline remains available as an advanced surface. |
| `/sandbox` | `sandbox.html` | Advanced Tools shell link | Experimentation remains available without becoming first-level navigation. |
| `/meta` | `meta.html` | Advanced Tools shell link | Meta-evolution and algorithm editing stay in the advanced group. |
| `/chat` | `chat.html` | Primary shell link | Natural-language steering remains a primary path. |
| `/feed` | `feed.html` | Primary shell link | Default post-setup feed remains a primary path. |
| `/ambient/{surface}` | `ambient_surface.html` | Secondary Read via `/ambient/pwa` shell link | Ambient/PWA delivery remains reachable through the concrete `/ambient/pwa` entry. |
| `/status` | `status.html` | Secondary Read shell link | Health, readiness, and recovery remain available. |
| `/profile` | `profile.html` | Secondary Read shell link | Profile, ownership, and export/import entry points remain available. |
| `/admin` | `admin.html` | Advanced Tools shell link | Destructive reset controls remain separated from primary navigation. |
| `/sovereignty` | `sovereignty.html` | Secondary Steer shell link | Ownership boundaries remain visible without crowding primary navigation. |
| `/brief` | `brief.html` | Primary shell link | Daily/weekly/critical briefing reading remains a primary surface. |
| `/demo` | `demo.html` | Advanced Tools shell link | Demo seed/reset and walkthrough remain available as advanced tooling. |
| `/sources` | `sources.html` | Advanced Tools shell link | Source registry visibility remains available. |
| `/settings` | `settings.html` | Advanced Tools shell link | Detailed source and model/backend controls remain available. |
| `/criteria` | `criteria.html` | Secondary Steer shell link | Raw criteria editing remains available. |
| `/onboarding/auto` | `onboarding_auto.html` | Secondary Steer shell link | Optional auto-context onboarding remains available. |
| `/landing` | `landing.html` | Conditional SaaS Account shell link | Public landing page remains registered and visible in SaaS mode. |
| `/signup` | `signup.html` | Conditional SaaS Account shell link | Signup remains registered and visible in SaaS mode. |
| `/login` | `login.html` | Conditional SaaS Account shell link | Login remains registered and visible in SaaS mode. |
| `/auth/callback` | `oauth_callback.html` | Conditional SaaS Account shell link | OAuth callback UI remains registered and visible in SaaS mode. |
| `/billing` | `billing.html` | Conditional SaaS Account shell link | Billing dashboard remains registered and visible in SaaS mode. |
| `/invite` | `invite.html` | Conditional SaaS Account shell link | Invite/referral page remains registered and visible in SaaS mode. |
| `/ko` | `landing_ko.html` | Conditional SaaS Account shell link | Korean public landing page remains registered and visible in SaaS mode. |
| `/zh` | `landing_zh.html` | Conditional SaaS Account shell link | Chinese public landing page remains registered and visible in SaaS mode. |
| `/terms` | `terms.html` | Conditional SaaS Account shell link | Terms page remains registered and visible in SaaS mode. |
| `/privacy` | `privacy.html` | Conditional SaaS Account shell link | Privacy page remains registered and visible in SaaS mode. |
| `/about` | `about.html` | Conditional SaaS Account shell link | About page remains registered and visible in SaaS mode. |

### Supporting Endpoints

| Route | Method(s) | Visible capability preserved |
| --- | --- | --- |
| `/setup/save` | `POST` | Full setup environment persistence. |
| `/setup/required/save` | `POST` | Required OpenAI/local SQLite first-run save. |
| `/setup/model-backend/save` | `POST` | Setup-side model/backend persistence. |
| `/setup/test` | `POST` | Setup environment validation. |
| `/setup/create-tables` | `POST` | Optional hosted table creation. |
| `/setup/one-shot` | `POST` | One-shot local setup/feed run. |
| `/setup/one-shot/status` | `GET` | One-shot run polling. |
| `/setup/collection-progress` | `GET` | Setup/feed collection progress polling. |
| `/setup/state` | `GET` | Setup state polling. |
| `/setup/source-settings/save` | `POST` | Setup-side source toggle persistence. |
| `/onboarding/start` | `POST` | Socratic onboarding start. |
| `/onboarding/respond` | `POST` | Socratic onboarding response loop. |
| `/signals/export` | `GET` | Signal export. |
| `/signals/search` | `GET` | Signal search. |
| `/dashboard/stats` | `GET` | Dashboard stats cards. |
| `/health` | `GET` | Health check. |
| `/ask` | `POST` | On-demand dashboard Q&A. |
| `/qa/feedback` | `POST` | Q&A feedback learning loop. |
| `/criteria/propose` | `POST` | Natural-language criteria preview. |
| `/criteria/apply` | `POST` | Natural-language criteria apply. |
| `/algorithm/propose` | `POST` | Natural-language algorithm preview. |
| `/algorithm/apply` | `POST` | Natural-language algorithm apply. |
| `/signals/{signal_id}/trace` | `GET` | Signal why/trace inspection. |
| `/evolution/timeline` | `GET` | Evolution timeline data. |
| `/chat/conversations` | `GET` | Chat conversation list. |
| `/chat/conversations/{conv_id}/messages` | `GET` | Chat message retrieval. |
| `/chat/conversations/{conv_id}` | `DELETE` | Chat conversation deletion. |
| `/chat/message` | `POST` | Natural-language command execution. |
| `/feed/list` | `GET` | Feed stream metadata. |
| `/feed/collection-progress` | `GET` | Feed collection progress polling. |
| `/feed/api` | `GET` | Paginated feed data. |
| `/events/beacon` | `POST` | Passive feed behavior events. |
| `/feed/metrics` | `GET` | Feed mode metrics. |
| `/ambient/surfaces` | `GET` | Ambient surface registry. |
| `/ambient/{surface}/api` | `GET` | Ambient surface item API. |
| `/policy/personal-algorithm` | `GET` | Policy inspection. |
| `/policy/natural-language` | `POST` | Policy natural-language edit. |
| `/policy/rollback` | `POST` | Policy rollback. |
| `/algorithm/export` | `GET` | Algorithm/profile export. |
| `/algorithm/import/dry-run` | `POST` | Import preview. |
| `/algorithm/import` | `POST` | Import apply. |
| `/admin/reset` | `POST` | Destructive reset action. |
| `/demo/seed` | `POST` | Demo data seed. |
| `/demo/reset` | `POST` | Demo reset. |
| `/meta/cycle` | `POST` | Meta-evolution cycle. |
| `/sandbox/simulate` | `POST` | Sandbox simulation. |
| `/feedback/{signal_id}/{vote}` | `POST` | Direct signal feedback. |
| `/run/daily` | `POST` | Daily collection run. |
| `/run/dry` | `POST` | Dry run. |
| `/run/weekly` | `POST` | Weekly run. |
| `/run/critical` | `POST` | Critical alert run. |
| `/settings/save` | `POST` | Detailed source settings save. |
| `/settings/model-backend/save` | `POST` | Settings-side model/backend persistence. |
| `/criteria/save` | `POST` | Raw criteria editor save. |
| `/onboarding/auto/infer` | `POST` | Optional auto-context inference. |
| `/auth/oauth/{provider}` | `GET` | SaaS OAuth redirect. |
| `/auth/oauth/save-token` | `POST` | SaaS OAuth token handoff. |
| `/auth/signup` | `POST` | SaaS signup. |
| `/auth/login` | `POST` | SaaS login. |
| `/auth/logout` | `POST` | SaaS logout. |
| `/auth/me` | `GET` | SaaS current-user check. |
| `/billing/checkout` | `POST` | SaaS checkout. |
| `/billing/webhook` | `POST` | SaaS billing webhook. |
| `/billing/portal` | `GET` | SaaS billing portal placeholder. |

## Preservation Rules

- Do not remove links from the shared dashboard shell unless the underlying route is intentionally removed in a separate issue.
- Keep advanced routes grouped behind a single disclosure control rather than placing them in the first-level dashboard nav.
- Keep secondary routes grouped by user intent: reading/recovery versus steering/ownership.
- Keep this audit in sync with `hedwig/dashboard/app.py` when adding, removing, or renaming dashboard routes.

## PR Documentation

This issue #34 change is stacked on issue #32/#33 work through the
`issue/34-nav-i18n-brief-fix` branch. The pull request must include:

Closes #34

### Verification Steps And Results

| Step | Result |
| --- | --- |
| `git diff --check` | Passed with no whitespace errors. |
| `python3 -m pytest -p no:rerunfailures tests/test_issue34_nav_i18n_brief.py tests/test_v3_brief.py tests/test_local_sqlite_setup_schema.py tests/test_issue32_route_inventory.py` | Passed with `79 passed`; focused coverage exercises navigation grouping, preserved route reachability, ko/zh/en language selection and persistence hooks, localized shell/page strings, SQLite migration idempotency, and `/brief` behavior for fresh, empty, and older local databases. |
| `pytest -p no:rerunfailures` | Passed with `924 passed, 1 warning`. |

Plain `pytest` is intentionally not used for the PR verification command in
this sandbox because `pytest_rerunfailures` attempts to bind a localhost socket
and is blocked before repository assertions run. Disabling only that plugin
keeps the repository tests runnable without changing product behavior.

### Ouroboros Recovery Limitations

Official Ouroboros execution `exec_0161a01ad8ea` recorded
`execution.terminal` and `orchestrator.session.completed` events for session
`orch_f9a2eb42432c` at 2026-05-19 13:39:11, with all 11 acceptance criteria
and 77 subtasks complete. The background JobManager wrapper
`job_857b8f2b5e44` did not flip from `running` to a terminal status after the
execution terminal event, so `ouroboros_job_result` continued to report
`Job still running: running`. The completion evidence for the official run is
therefore the event log and AC/Sub-AC status, not the stale job-result wrapper.

The remaining recorded limitation is environmental: plain `pytest` is blocked
by sandbox socket restrictions in `pytest_rerunfailures`. Disabling only that
plugin keeps the repository tests runnable without changing product behavior.

The formal `ouroboros_evaluate` call was attempted twice after the successful
run and timed out after 120 seconds both times without recording evaluation
events. As a bounded fallback, `ouroboros_qa` was run against code-level
evidence for the same acceptance criteria and returned `0.92 / 1.00 [PASS]`.
