# Issue 32 User-Facing Route Inventory

This inventory captures the existing Hedwig dashboard pages before the one-shot `/setup` UX consolidation. It is intended to prevent feature removal: setup may combine, link to, or progressively disclose these capabilities, but the underlying pages and controls remain reachable.

## HTML Pages

| Route | Template | Primary visible features | Setup layering / preservation note |
| --- | --- | --- | --- |
| `/` | `home.html` | Dashboard summary stats, pipeline controls for daily/dry/weekly runs, recent signals with voting, recent evolution history, on-demand Q&A, natural-language criteria edits. | Home remains the post-setup operations dashboard; first-run setup can redirect here only after required config is ready, but feed is the default first delivery target. |
| `/setup` | `setup.html` | One-shot local setup, OpenAI key capture, local SQLite default, optional interest steering, source preset/toggles, first-run progress, feed handoff, collapsed advanced settings. | Primary first-run entry point for issue 32; advanced controls must stay optional and non-blocking. |
| `/onboarding` | `onboarding.html` | Socratic onboarding chat for initial criteria creation or recalibration. | Preserved as a steering path linked from setup, not required for minimum setup. |
| `/onboarding/auto` | `onboarding_auto.html` | SaaS auto-context onboarding from bio, SNS handles, and extra links; inferred profile/criteria preview. | Preserved as an optional advanced/profile inference path and not part of OpenAI-only local minimum setup. |
| `/chat` | `chat.html` | Natural-language control surface, conversation history, message composer, and chat-driven Hedwig actions. | Setup should surface chat as the primary post-setup steering control without replacing it. |
| `/feed` | `feed.html` | SNS-style feed, stream tabs, feed modes, infinite scroll, passive behavior feedback, setup/source readiness recovery links. | Default delivery destination after one-shot setup; must remain reachable even if first collection is slow or empty. |
| `/signals` | `signals.html` | Recent signal list, platform/score metadata, source links, direct chat deep-dive links. | Preserved as a monitoring/detail surface behind feed-first consumption. |
| `/brief` | `brief.html` | Daily/weekly/critical briefing list, cycle filtering, markdown rendering, chat/evolution follow-up links. | Preserved as an optional delivery/summary surface linked from setup advanced delivery. |
| `/ambient/{surface}` | `ambient_surface.html` | Ambient/PWA/native delivery surface for selected feed items, delivery state handling, empty/unavailable states, beacon tracking. | Preserved as optional delivery; setup links to ambient without requiring external delivery for completion. |
| `/profile` | `profile.html` | Algorithm profile, export/import entry points, criteria YAML preview, algorithm config, interpretation style, feed personality, source count, recent evolution. | Preserved as profile polish, ownership, and export surface after setup. |
| `/status` | `status.html` | Exit condition progress, algorithm training status, retrain history, source health, setup remediation links. | Preserved as monitoring/recovery for setup and advanced backend health. |
| `/settings` | `settings.html` | Source plugin enabled toggles, local/SaaS settings save messaging, collapsed model/backend settings. | Preserved as detailed source and model/backend control; setup may expose a simplified subset and link here. |
| `/sources` | `sources.html` | Registered source plugin catalog with metadata, fetch method, and plugin type. | Preserved as source registry visibility; setup source defaults should derive from registry/source settings. |
| `/criteria` | `criteria.html` | Raw `criteria.yaml` editor and re-run onboarding link. | Preserved as power-user criteria editor; setup-generated criteria must remain editable here. |
| `/dashboard/generative` | `generative.html` | Generative dashboard layout cards built from criteria, recent signals, and dashboard stats. | Preserved as an alternate dashboard visualization, not part of first-run essentials. |
| `/evolution` | `evolution.html` | Evolution timeline page for algorithm/history events. | Preserved as advanced algorithm evolution visibility. |
| `/meta` | `meta.html` | Meta-evolution controls, natural-language `algorithm.yaml` edits, algorithm version history. | Preserved as advanced algorithm tuning/evolution tooling. |
| `/sandbox` | `sandbox.html` | Mutation sandbox for candidate algorithm perturbations and simulated events. | Preserved as advanced experimentation tooling. |
| `/sovereignty` | `sovereignty.html` | Algorithm sovereignty domains, user-editable/system-mutable/read-only history boundaries, export contract. | Preserved as the ownership/sovereignty explanation and contract surface. |
| `/admin` | `admin.html` | Data reset controls and CLI reset guidance. | Preserved as a clearly separated destructive/admin surface. |
| `/demo` | `demo.html` | Concept demo, seed/reset controls, differentiator walkthrough, architecture/status overview. | Preserved as demo/evaluation surface outside first-run setup. |
| `/landing` | `landing.html` | Public SaaS landing page, differentiators, pricing, CTA links, legal links. | Preserved for SaaS mode and not mixed into local setup completion. |
| `/ko` | `landing_ko.html` | Korean localized landing page, pricing, CTAs, language links. | Preserved for localized SaaS discovery. |
| `/zh` | `landing_zh.html` | Chinese localized landing page, pricing, CTAs, language links. | Preserved for localized SaaS discovery. |
| `/signup` | `signup.html` | Signup form, OAuth provider buttons, sign-in link. | Preserved for SaaS auth; not required for local SQLite first-run setup. |
| `/login` | `login.html` | Login form, OAuth provider buttons, signup link. | Preserved for SaaS auth; not required for local SQLite first-run setup. |
| `/auth/callback` | `oauth_callback.html` | OAuth callback token handling/loading page. | Preserved for SaaS OAuth flow. |
| `/billing` | `billing.html` | Plan/status card, manage subscription link, usage meters, tier comparison. | Preserved for SaaS billing; setup may link to it only as advanced/SaaS context. |
| `/invite` | `invite.html` | Invite/referral link display and referrals section. | Preserved for SaaS growth/referral surface. |
| `/terms` | `terms.html` | Terms of service. | Preserved as legal page. |
| `/privacy` | `privacy.html` | Privacy policy, data collection/use/isolation, rights, cookies, contact. | Preserved as legal/privacy page. |
| `/about` | `about.html` | Hedwig mission, five moats, non-goals, open-source info, stack, inspirations, contact. | Preserved as informational page. |

## Global Header Navigation

The shared `base.html` header is the always-visible menu/sidebar equivalent for dashboard pages that extend the base layout. These links intentionally keep existing features reachable after `/setup` becomes the first-run entry point.

| Header item | Link | Feature exposed | Setup preservation note |
| --- | --- | --- | --- |
| 💬 Chat | `/chat` | Natural-language command and steering surface. | Promoted as post-setup steering rather than replaced by setup. |
| 🎯 Demo | `/demo` | Demo seed/reset and concept walkthrough. | Preserved outside the minimum first-run path. |
| Home | `/` | Existing operations dashboard and manual run controls. | Redirects first-time users to `/setup` until required config is ready. |
| Ambient | `/ambient/pwa` | PWA/ambient delivery surface. | Optional delivery channel, never required for setup completion. |
| 📱 Feed | `/feed` | Default SNS-style feed consumption surface. | Default completion target and fallback action. |
| Brief | `/brief` | Daily, weekly, and critical briefing surface. | Optional summary/delivery view linked from Advanced. |
| 👤 Profile | `/profile` | Profile, ownership, and export/import entry points. | Preserved for profile polish and bundle ownership after setup. |
| Signals | `/signals` | Raw signal list, feedback, and trace deep dives. | Preserved as monitoring/detail behind feed-first consumption. |
| Evolution | `/evolution` | Algorithm evolution timeline. | Preserved as advanced algorithm visibility. |
| Sandbox | `/sandbox` | Ranking and mutation experimentation surface. | Preserved as advanced experimentation. |
| Meta | `/meta` | Meta-evolution and algorithm edit tooling. | Preserved as advanced self-improvement control. |
| Status | `/status` | Readiness, health, source, and training status. | Recovery/monitoring companion for setup and first run. |
| Sovereignty | `/sovereignty` | Ownership boundaries and export contract. | Preserved as algorithm sovereignty explanation. |
| Sources | `/sources` | Source plugin registry catalog. | Preserved as source visibility; setup uses registry defaults. |
| Settings | `/settings` | Source toggles and model/backend settings. | Preserved as detailed controls behind progressive disclosure. |
| Criteria | `/criteria` | Raw `criteria.yaml` editor. | Preserved as power-user editor for setup-generated criteria. |
| Setup | `/setup` | One-shot setup and advanced configuration layering. | Primary issue 32 first-run entry point. |
| Onboarding | `/onboarding` | Socratic preference interview. | Optional steering path, not required for minimum setup. |
| Auto Onboarding | `/onboarding/auto` | SaaS auto-context profile inference. | Optional SaaS/profile path, not required for local setup. |
| 🔧 Reset | `/admin` | Destructive data reset controls. | Preserved as separated admin surface. |

## Template Navigation Entry Points

These are the main internal links, form actions, and HTMX/API-backed controls exposed by templates. External links, static assets, same-page anchors, and item-specific outbound signal URLs are intentionally excluded from this feature-preservation inventory.

| Surface | Entry point(s) | Feature exposed / preservation reason |
| --- | --- | --- |
| `base.html` global header | `/chat`, `/demo`, `/`, `/ambient/pwa`, `/feed`, `/brief`, `/profile`, `/signals`, `/evolution`, `/sandbox`, `/meta`, `/status`, `/sovereignty`, `/sources`, `/settings`, `/criteria`, `/setup`, `/onboarding`, `/onboarding/auto`, `/admin` | Always-visible access to existing dashboard, feed, steering, source, profile, evolution, setup, and admin surfaces. |
| `setup.html` essential/flow nav | `/setup/one-shot`, `/setup/required/save`, `/setup/one-shot/status`, `/feed`, `/status`, `/chat`, `/criteria`, `/onboarding`, `/onboarding/auto` | One-shot first run, slow-run recovery, feed fallback, and steering handoff. |
| `setup.html` source/backend advanced controls | `/setup/source-settings/save`, `/setup/model-backend/save`, `/setup/create-tables`, `/setup/save`, `/setup/test`, `/sources`, `/settings`, `/settings#model-backend-settings`, `/status` | Optional source toggles, Supabase tables, env checks, model/backend settings, and detailed settings remain reachable without blocking setup. |
| `setup.html` delivery/profile/evolution advanced controls | `/ambient/pwa`, `/brief`, `/profile`, `/algorithm/export`, `/settings`, `/evolution`, `/meta`, `/sovereignty`, `/sandbox`, `/` | External delivery, profile/export, settings, and advanced algorithm tools are progressively disclosed instead of removed. |
| `feed.html` local recovery nav | `/chat`, `/profile`, `/status`, `/settings`, `/setup`, `/feed?stream={id}&mode={mode}` | Feed keeps steering, profile, status, source tuning, setup recovery, and stream switching close to consumption. |
| `profile.html` ownership nav | `/algorithm/export`, `/sovereignty`, `/evolution`, `/onboarding`, `/sources`, `/settings` | Export/import ownership, sovereignty, evolution, onboarding, and source management stay reachable from profile. |
| `settings.html` forms | `/settings/save`, `/settings/model-backend/save`, `/status` | Detailed source toggles, model/backend persistence, and backend health remain available after setup simplification. |
| `criteria.html` controls | `/criteria/save`, `/onboarding` | Raw criteria edits and Socratic recalibration remain available. |
| `home.html` controls | `/run/daily`, `/run/dry`, `/run/weekly`, `/feedback/{signal_id}/{vote}`, `/signals`, `/ask`, `/qa/feedback`, `/criteria/propose`, `/criteria/apply` | Existing manual runs, signal feedback, Q&A, and natural-language criteria editing remain on the dashboard. |
| `signals.html` links | `/chat?q={signal}`, `/` | Signal detail flow can hand off to chat or home pipeline controls. |
| `brief.html` links | `/chat?q={briefing}`, `/evolution` | Briefings can hand off to chat and evolution history. |
| `demo.html` links | `/criteria`, `/evolution`, `/meta`, `/sandbox`, `/demo/seed`, `/demo/reset` | Demo walkthrough keeps criteria, evolution, meta, sandbox, and demo reset controls. |
| `landing*.html`, `signup.html`, `login.html`, `oauth_callback.html`, `billing.html`, `invite.html` | `/landing`, `/ko`, `/zh`, `/signup`, `/login`, `/auth/oauth/{provider}`, `/auth/signup`, `/auth/login`, `/auth/callback`, `/auth/oauth/save-token`, `/onboarding/auto`, `/billing`, `/billing/checkout`, `/billing/portal`, `/invite`, `/privacy`, `/terms` | SaaS account, localized landing, OAuth, billing, invite, and legal flows remain preserved outside the local setup minimum. |

## Setup/Onboarding First-Run UX Inventory

This focused inventory captures the setup, onboarding, empty-state, first-run, and configuration affordances that the one-shot `/setup` page must combine or layer without removing.

| Surface | Setup/onboarding UI | Empty or first-run state | Configuration affordance to preserve |
| --- | --- | --- | --- |
| `setup.html` option-location map | Visible setup inventory mapping required local setup, criteria/onboarding, source defaults, storage, delivery, source/API keys, model/backend settings, profile/export/import, monitoring, and algorithm tools to their `/setup` anchors. | The map renders before the step navigation so first-time users can see where existing options live without expanding Advanced sections. | Every existing environment-key group from `EnvManager`, onboarding option, source/default control, delivery target, export/import path, profile/status/settings link, and meta/evolution/sandbox tool has a visible home in the single `/setup` page. |
| `setup.html` essential card | OpenAI key capture, required setup save, local SQLite storage summary. | `OPENAI_API_KEY` missing shows `needs OpenAI key`; setup starts with `first_run_status=not_started` and `progress_percent=20`. | `POST /setup/required/save`, `POST /setup/one-shot`, and hidden/default `HEDWIG_STORAGE=sqlite` keep minimum setup OpenAI-only and local. |
| `setup.html` criteria card | Optional one-line `interest_text`, skip/default action, continue action. | Blank interest is an accepted first-run state and uses `AI agents, LLM tooling, and research papers`. | Default AI-builder criteria generation remains editable later through `/criteria`, `/onboarding`, and `/chat`. |
| `setup.html` source card | Automatic registry/source_settings default source preset plus collapsed source overrides. | Source selection is explicitly non-blocking; first run can proceed with default enabled sources. | `POST /setup/source-settings/save`, `/sources`, and `/settings` preserve source toggles and registry review. |
| `setup.html` progress/completion cards | First-run status, polling, retry, failure recovery, completion summary. | `ready_to_run`, `waiting_for_feed_items`, `feed_items_available=false`, and failure states keep slow or empty collection from stranding the user. | `GET /setup/one-shot/status`, `/status`, and `/feed` fallback remain available until `redirect_target=/feed` is valid. |
| `setup.html` advanced details | Collapsed Supabase, delivery, source/API keys, model/backend, export/import, profile, settings, status, and evolution sections. | Advanced sections are optional and collapsed by default, with delivery marked skipped/deferred. | `/setup/save`, `/setup/test`, `/setup/create-tables`, `/setup/model-backend/save`, `/algorithm/export`, `/algorithm/import/dry-run`, `/algorithm/import`, `/profile`, `/settings`, `/evolution`, `/meta`, `/sandbox`, and `/sovereignty` remain reachable. |
| `onboarding.html` | Socratic interview start button, chat transcript, answer form. | Initial empty transcript says to click Start; no active session returns an error from `/onboarding/respond`. | `POST /onboarding/start` and `POST /onboarding/respond` remain optional steering/recalibration paths after setup. |
| `onboarding_auto.html` | Optional bio, SNS handles, extra links, inferred profile preview. | Loading and error/result containers handle the first inference run without affecting local setup completion. | `/onboarding/auto/infer`, `/onboarding`, `/criteria`, and `/` preserve SaaS/profile inference as optional. |
| `feed.html` | Feed modes, stream tabs, post-setup nav to chat/profile/status. | Empty feed distinguishes waiting for first feed items from no enabled sources and links to `/setup` or `/settings`. | `/feed/api`, `/feed/list`, `/events/beacon`, `/feed/metrics`, `/chat`, `/profile`, `/status`, and `/settings` remain available from the feed. |
| `profile.html` | Profile cards, criteria preview, export/import controls. | Missing criteria shows an onboarding recovery link; missing interpretation style shows an inactive-style message. | `/algorithm/export`, `/algorithm/import/dry-run`, `/algorithm/import`, `/sovereignty`, `/evolution`, `/onboarding`, `/sources`, and `/settings` preserve ownership/profile polish. |
| `status.html` | Exit conditions, training readiness, retrain history, source health. | Missing source env keys and zero recent source counts show recovery guidance; missing retrain history shows manual `/meta`/CLI path. | `/setup`, `/meta`, and source health details remain the monitoring/recovery layer for first-run setup. |

## Redirect And Handoff Inventory

| Source | Target | Trigger / preservation note |
| --- | --- | --- |
| `/` | `/setup` | Server-side `RedirectResponse` when required environment status is not ready, making `/setup` the first-run entry point. |
| `/settings/save` | `/settings?saved=1` | Server-side `RedirectResponse` after detailed source toggles are saved. |
| `/settings/model-backend/save` | `/settings?saved=model-backend` | Server-side `RedirectResponse` after advanced model/backend settings are saved. |
| `/auth/oauth/{provider}` | external Supabase OAuth URL with callback `/auth/callback` | Server-side OAuth redirect for SaaS login/signup mode. |
| `/auth/oauth/save-token` | `/onboarding/auto` in JSON `next` | OAuth callback handoff preserves auto-context onboarding. |
| `signup.html` successful signup | `/onboarding/auto` | Client-side post-signup handoff to existing auto onboarding. |
| `login.html` successful login | `/` | Client-side post-login handoff to the dashboard/home route. |
| `oauth_callback.html` saved token | JSON `next` or `/` | Client-side OAuth callback follows the server-provided next route, defaulting to home. |
| `/setup/one-shot` and `/setup/one-shot/status` | `/feed` when feed items exist; `/feed` fallback action otherwise | JSON handoff keeps slow first collection from stranding setup and makes feed the default delivery target. |

## User-Visible Supporting Endpoints

These routes are not standalone HTML pages, but they back visible controls on the pages above and must remain available.

| Endpoint(s) | Visible feature supported |
| --- | --- |
| `POST /setup/save`, `POST /setup/required/save`, `POST /setup/model-backend/save`, `POST /setup/test`, `POST /setup/create-tables`, `POST /setup/one-shot`, `GET /setup/one-shot/status`, `POST /setup/source-settings/save` | Setup persistence, environment tests, optional Supabase table creation, one-shot local first run, progress polling, and setup source toggles. |
| `POST /onboarding/start`, `POST /onboarding/respond` | Socratic onboarding conversation lifecycle. |
| `GET /signals/export`, `GET /signals/search`, `GET /signals/{signal_id}/trace` | Signal export, search, and trace/why inspection. |
| `GET /dashboard/stats`, `GET /health` | Dashboard stats cards and health checks. |
| `POST /ask`, `POST /qa/feedback` | Home/on-demand Q&A and feedback learning loop. |
| `POST /criteria/propose`, `POST /criteria/apply`, `POST /criteria/save` | Natural-language criteria preview/apply and raw criteria editor save. |
| `POST /algorithm/propose`, `POST /algorithm/apply`, `GET /algorithm/export`, `POST /algorithm/import/dry-run`, `POST /algorithm/import` | Natural-language algorithm editing plus export/import bundle ownership flow. |
| `GET /evolution/timeline`, `POST /meta/cycle`, `POST /sandbox/simulate`, `GET /policy/personal-algorithm`, `POST /policy/natural-language`, `POST /policy/rollback` | Evolution timeline data, meta-evolution run, sandbox simulation, policy inspection/editing/rollback. |
| `GET /chat/conversations`, `GET /chat/conversations/{conv_id}/messages`, `DELETE /chat/conversations/{conv_id}`, `POST /chat/message` | Chat history, message retrieval, deletion, and natural-language command execution. |
| `GET /feed/list`, `GET /feed/api`, `POST /events/beacon`, `GET /feed/metrics` | Feed stream metadata, paginated feed data, passive behavior/event tracking, feed mode metrics. |
| `GET /ambient/surfaces`, `GET /ambient/{surface}/api` | Ambient surface registry and ambient item API. |
| `POST /feedback/{signal_id}/{vote}` | Direct up/down signal feedback from dashboard lists. |
| `POST /run/daily`, `POST /run/dry`, `POST /run/weekly`, `POST /run/critical` | Manual pipeline execution controls and critical alert run. |
| `POST /settings/save`, `POST /settings/model-backend/save` | Detailed source toggle and model/backend settings persistence. |
| `POST /admin/reset`, `POST /demo/seed`, `POST /demo/reset` | Admin reset and demo seed/reset controls. |
| `GET /auth/oauth/{provider}`, `POST /auth/oauth/save-token`, `POST /auth/signup`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` | SaaS OAuth, signup/login/logout, and current-user checks. |
| `POST /billing/checkout`, `POST /billing/webhook`, `GET /billing/portal` | SaaS checkout, webhook handling, and billing portal entry. |

## Manual Verification Checklist For Preserved Paths

Automated tests cover the route inventory, global header reachability, setup defaults, source defaults, onboarding route independence, and first-run execution behavior. The paths below still need manual browser verification because they depend on progressive-disclosure UI state, client-side JavaScript handoffs, optional external providers, or visual confirmation that advanced features remain reachable without blocking the one-shot setup flow.

Recommended local command:

```bash
HEDWIG_DB_PATH=/tmp/hedwig-issue32-manual.db python -m hedwig --dashboard --port 8765
```

Recommended SaaS/account command for account, OAuth, billing, and invite surfaces:

```bash
HEDWIG_DB_PATH=/tmp/hedwig-issue32-manual-saas.db python -m hedwig --dashboard --saas --port 8766
```

| Preserved feature path | Manual steps | Expected result | Why this remains manual |
| --- | --- | --- | --- |
| Setup progressive-disclosure shell (`/setup`) | Open `/setup` in a fresh browser session. Confirm the OpenAI/local SQLite card is first, interest text is optional, sources use registry defaults, and Advanced setup sections are collapsed. Expand every Advanced section, then collapse them again. | Minimum setup remains OpenAI-only local SQLite. Supabase, delivery, source/API keys, export/import, profile polish, status/settings, and model/backend controls are visible but non-blocking. | Browser state, native `<details>` behavior, and visual ordering are better verified interactively than through string assertions alone. |
| Setup one-shot progress and feed handoff (`/setup`) | With a disposable valid `OPENAI_API_KEY`, submit `/setup` with blank interest. Start first collection, leave the page open during collection, and watch progress/polling until completion or partial readiness. Click the visible feed fallback if the run is slow or empty. | Blank interest uses `AI agents, LLM tooling, and research papers`; setup writes local SQLite mode, keeps the user on `/setup` while waiting, and exposes `/feed` as the default completion/fallback target. | End-to-end OpenAI calls, network timing, and slow/empty collection states are intentionally not required in unit tests. |
| Global dashboard navigation after setup | From `/setup`, use the shared header to visit `/chat`, `/feed`, `/profile`, `/status`, `/settings`, `/sources`, `/criteria`, `/onboarding`, `/onboarding/auto`, `/brief`, `/ambient/pwa`, `/evolution`, `/meta`, `/sandbox`, `/sovereignty`, `/admin`, and `/demo`. | Each preserved page opens without being replaced by the one-shot setup flow; empty states point back to setup/settings/status where appropriate. | Automated tests assert route reachability, but a human should verify the visible navigation labels, layout, and recovery copy. |
| Natural-language steering paths | Open `/chat`, `/criteria`, `/onboarding`, and `/onboarding/auto`. Start Socratic onboarding, inspect the optional auto-context form, and confirm criteria remain editable from `/criteria`. | Setup does not remove or require these steering paths; they remain optional follow-up controls after the first feed. | Chat/onboarding interactions can depend on LLM availability and browser-side form behavior. |
| Source and backend power controls | Expand `/setup` source/API and model/backend sections. Visit `/sources` and `/settings`, toggle a source in a disposable run, save settings, and return to `/setup`. | Source registry visibility, detailed source toggles, and model/backend settings remain reachable; saving advanced settings does not make Supabase or external delivery mandatory for local setup. | The preserved behavior spans multiple pages and form redirects that are easiest to confirm in a real browser session. |
| Delivery surfaces | Visit `/feed`, `/brief`, and `/ambient/pwa` before and after first collection. In `/setup`, expand delivery configuration and inspect Slack, Discord, and SMTP controls without filling them. | Dashboard `/feed` remains the default delivery target. Brief, ambient, Slack, Discord, and SMTP options are available as optional advanced delivery paths. | Empty-state visuals and optional external delivery credentials are intentionally not exercised by automated tests. |
| Ownership, export/import, and sovereignty | Open `/profile`, `/sovereignty`, and `/algorithm/export`. On a disposable database, inspect `/profile` import dry-run controls without importing production data. | Profile polish, criteria preview, export/import, and algorithm sovereignty surfaces remain available after setup consolidation. | Exported bundle contents and import confirmation are manual ownership checks, not core setup assertions. |
| Evolution and experimentation tools | Open `/evolution`, `/meta`, and `/sandbox`. Confirm meta-evolution, algorithm edit, timeline, and sandbox controls are still visible but not required during setup. | Advanced algorithm sovereignty and experimentation tools remain layered behind setup rather than removed. | These controls are high-power and context-dependent; manual review avoids mutating algorithm state during routine setup tests. |
| SaaS/account/legal surfaces | Start the SaaS/account command and visit `/landing`, `/signup`, `/login`, `/auth/callback`, `/billing`, `/invite`, `/ko`, `/zh`, `/terms`, `/privacy`, and `/about`. Do not complete real checkout or OAuth unless using test providers. | SaaS discovery, auth, billing, invite, localization, and legal pages remain preserved outside the local SQLite minimum setup path. | OAuth, checkout, and localized public pages require browser/provider confirmation beyond local route assertions. |

## Setup UX Implications

The single `/setup` page should layer the existing product surface rather than replacing it:

| Layer | Existing routes to preserve |
| --- | --- |
| Essential first run | `/setup`, `/feed`, `/status` |
| Natural-language steering | `/chat`, `/criteria`, `/onboarding`, `/onboarding/auto` |
| Feed and signal consumption | `/feed`, `/signals`, `/brief`, `/ambient/{surface}` |
| Monitoring and recovery | `/status`, `/dashboard/stats`, `/health`, `/signals/{signal_id}/trace` |
| Source and backend controls | `/sources`, `/settings`, `/setup/source-settings/save`, `/settings/model-backend/save` |
| Ownership/export/profile | `/profile`, `/algorithm/export`, `/algorithm/import/dry-run`, `/algorithm/import`, `/sovereignty` |
| Evolution and experimentation | `/evolution`, `/meta`, `/sandbox`, `/policy/personal-algorithm`, `/policy/natural-language`, `/policy/rollback` |
| SaaS/account/legal | `/landing`, `/signup`, `/login`, `/auth/callback`, `/billing`, `/invite`, `/ko`, `/zh`, `/terms`, `/privacy`, `/about` |
