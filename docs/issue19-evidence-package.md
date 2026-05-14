# Issue #19 Evidence Package: Issue #7 / PR #18 Feed Moat

## Scope

This artifact packages evaluator-visible evidence for Hedwig issue #19. It is
limited to documenting the accepted implementation evidence for issue #7 and
PR #18; it does not introduce new product scope.

In scope:

- Evidence references for issue #7, PR #18, and issue #19.
- Checkpoint context for the accepted Ouroboros Gen 9 result.
- Pointers to the implementation files and tests present at the accepted base.
- Explicit limitations and follow-up boundaries that must not be represented as
  implemented behavior.

Out of scope:

- Ranking behavior changes.
- Feed behavior changes.
- Storage schema changes.
- Delivery behavior changes.
- Model training behavior changes.
- Policy logic changes.

## Accepted Checkpoint

- Accepted checkpoint: Ouroboros Gen 9 / PR #18.
- Accepted commit: `471e9e6` (`feat: add bounded personal algorithm feed layers`).
- Accepted full commit: `471e9e654e73097dcf620b1c1e4f0f0b26156051`.
- PR under review: PR #18, as the accepted pull-request checkpoint for issue
  #7 verification.
- Product issue being evidenced: issue #7.
- Evidence-packaging issue: issue #19.

Ralph Gen 10 through Gen 13 are explicitly rejected for this package because
they were marked `grade_regressing`. Their uncommitted changes are not part of
the evidence base and should not be incorporated into PR #18 verification.

Accepted checkpoint metadata for stale-reference validation:

- `algorithm.yaml`
- `hedwig/dashboard/app.py`
- `hedwig/dashboard/templates/feed.html`
- `hedwig/onboarding/nl_algo_editor.py`
- `hedwig/personal_algorithm.py`
- `hedwig/storage/local.py`
- `hedwig/storage/supabase.py`
- `migrations/002_personal_algorithm_engine.sql`
- `sovereignty.yaml`
- `tests/test_personal_algorithm_engine.py`

Evidence-only artifacts introduced for issue #19 are intentionally outside
commit `471e9e6` and are excluded from stale-checkpoint reference failures:
`docs/issue19-evidence-package.md`, `docs/issue19-pr-summary.md`, and
`tests/test_issue19_evidence_package.py`.

## Verification Evidence Section Structure

Evaluator verification should use the following structure when reviewing this
package against issue #7 and PR #18:

- Accepted checkpoint: confirm the evidence base is Ouroboros Gen 9 at commit
  `471e9e6`, with Ralph Gen 10-13 excluded as `grade_regressing`.
- Evidence map: inspect the implementation files and tests that demonstrate the
  bounded personal algorithm layer without changing ranking, feed, storage,
  delivery, model training, or policy behavior.
- Acceptance-criteria mapping: trace each issue #7 criterion to current files,
  verification tests, and runtime evidence artifacts or observations in the
  accepted checkpoint.
- Verification command: run the canonical test command listed below, with the
  broader suite as optional regression coverage when evaluator time permits.
- Follow-up gaps: keep future work separate from the implemented PR #18 scope.

## PR #18 Implemented Behaviors Available for Issue #7 Verification

The accepted PR #18 checkpoint implements the following evaluator-visible
behaviors that are available for issue #7 verification.
This section describes evidence surfaces only; it does not add or change product behavior.

| Implemented PR #18 behavior | Evaluator-visible evidence surface | Issue #7 verification value |
|---|---|---|
| Bounded post-ranking personal algorithm layer | `/feed/api` item metadata includes immutable `pre_layer_ranking`, preserved `ensemble_score` and `final_score`, exploration labels, media profile, and delivery metadata. | Verifies the layer annotates and routes after ranking instead of replacing the accepted ranking pipeline. |
| Feed mode UI and instrumentation | `/feed` renders Grid, Detail Swipe, and Dense Reader controls and ships behavior-event beacon wiring for impressions, viewed cards, opens, dwell/save/not-interested, swipes, and feed mode. | Verifies evaluator-visible feed modes and usage events required by issue #7 are present. |
| Raw behavior events and derived rewards separation | `/events/beacon` persists raw behavior events and derived reward rows separately, with derivation rule metadata and source event IDs. | Verifies reward interpretation is traceable without conflating raw user actions with derived training or preference signals. |
| Swipe defaults and natural-language edit guardrails | `get_personal_algorithm_policy()`, `interpret_behavior_event(...)`, `propose_local_policy_edit(...)`, and `confirm_edit(...)` expose immutable swipe defaults, safe local feed edits, risky shadow-test gating, and future-ranking classification. | Verifies user-editable policy surfaces are bounded and risky ranking-oriented changes are not applied directly. |
| Policy rollback and shadow fitness evidence | `confirm_edit(...)`, `restore_algorithm_version(1)`, `shadow_test_policy_edit(...)`, and `composite_fitness(...)` expose rollback and shadow-test evidence. | Verifies local policy edits can be reverted and composite fitness remains evidence for shadow testing rather than production ranking behavior. |
| Sovereignty and future-work boundaries | `algorithm.yaml` and `sovereignty.yaml` declare editable, system-mutable, readonly, and future-work boundaries. | Verifies issue #7 implementation claims remain scoped to the accepted Gen 9 checkpoint and do not absorb rejected Ralph Gen 10-13 scope. |

## Evidence Map

| Evidence area | Repository evidence at `471e9e6` | Verification value |
|---|---|---|
| Additive post-ranking boundary | `hedwig/personal_algorithm.py` module docstring and `DEFAULT_PERSONAL_ALGORITHM["ranking_boundary"]`; `algorithm.yaml` `personal_algorithm` section | Shows the personal algorithm layer consumes already-ranked signals and annotates/routes after ranking without overwriting `ensemble_score` or `final_score`. |
| Feed modes and behavior events | `hedwig/dashboard/app.py`; `hedwig/dashboard/templates/feed.html`; `tests/test_personal_algorithm_engine.py::test_feed_modes_exploration_delivery_and_metrics` | Shows evaluator-visible feed modes, behavior beacon events, mode metrics, and preservation of pre-layer ranking fields. |
| Reward interpretation separation | `hedwig/personal_algorithm.py::interpret_behavior_event`; storage helpers in `hedwig/storage/local.py` and `hedwig/storage/supabase.py`; `tests/test_personal_algorithm_engine.py::test_raw_events_and_rewards_are_separate` | Shows raw behavior events and derived reward rows remain separate, with derivation metadata. |
| Swipe defaults and policy classification | `hedwig/personal_algorithm.py::classify_policy_edit`; `hedwig/onboarding/nl_algo_editor.py`; `tests/test_personal_algorithm_engine.py::test_swipe_defaults_and_policy_parser` | Shows left/right/next swipe defaults, safe feed-mode edits, risky post-ranking policy edits, and future ranking experiments are classified rather than applied as production ranking changes. |
| Exploration and delivery metadata | `hedwig/personal_algorithm.py::apply_exploration_layer`, `choose_delivery`, and `route_items_after_ranking`; `tests/test_personal_algorithm_engine.py::test_feed_modes_exploration_delivery_and_metrics` | Shows bounded exploration and delivery decisions are attached as metadata after ranking. |
| Shadow fitness, media boundary, and rollback | `hedwig/personal_algorithm.py::shadow_test_policy_edit`, `media_profile_for_item`; `hedwig/onboarding/nl_algo_editor.py`; `tests/test_personal_algorithm_engine.py::test_shadow_fitness_media_and_rollback` | Shows composite fitness remains a shadow-test metric, full media understanding is gated, and local algorithm edits can be restored. |
| Sovereignty boundary | `sovereignty.yaml`; `algorithm.yaml` `personal_algorithm` policy fields | Shows user-editable, system-mutable, readonly, and future-work boundaries for the personal algorithm layer. |

## Issue #7 Acceptance-Criteria Mapping

This section maps each issue #7 acceptance criterion to the relevant
automated or manual verification in the accepted Gen 9 checkpoint at commit
`471e9e6`.

| Issue #7 criterion | Runtime evidence artifact or observation | Automated verification | Manual evaluator check | Relevant implementation files |
|---|---|---|---|---|
| Raw events and derived rewards are stored separately. | POST `/events/beacon` returns separate `saved` and `rewards` counts; `get_behavior_events(signal_id=...)` returns raw event types while `get_behavior_rewards(signal_id=...)` returns derived reward rows with `derivation_rule_version` and `source_event_ids`. | `pytest tests/test_personal_algorithm_engine.py::test_raw_events_and_rewards_are_separate -q` | Inspect the test assertions for separate behavior-event and behavior-reward reads, derivation metadata, and distinct event/reward signal strength fields. | `hedwig/personal_algorithm.py`; `hedwig/storage/local.py`; `hedwig/storage/supabase.py`; `migrations/002_personal_algorithm_engine.sql` |
| Existing feedback and `behavior_events` paths continue to work. | `/events/beacon` accepts behavior-event batches and persists them through the existing storage adapter paths; legacy feedback behavior is covered by the broader existing suite. | `pytest tests/test_personal_algorithm_engine.py::test_raw_events_and_rewards_are_separate -q`; optional broader regression: `pytest tests/ -q` | Confirm `/events/beacon` posts behavior events without replacing existing feedback/storage paths; use the broader suite as regression coverage for legacy behavior. | `hedwig/dashboard/app.py`; `hedwig/storage/local.py`; `hedwig/storage/supabase.py` |
| Grid overview is the default feed mode, Detail Swipe opens from cards, Dense Reader remains available. | GET `/feed` renders `data-mode="grid"` plus visible Detail Swipe and Dense Reader controls. | `pytest tests/test_personal_algorithm_engine.py::test_feed_modes_exploration_delivery_and_metrics -q` | Inspect `/feed` rendering for `data-mode="grid"`, Detail Swipe, and Dense Reader labels without changing feed ranking semantics. | `algorithm.yaml`; `hedwig/personal_algorithm.py`; `hedwig/dashboard/app.py`; `hedwig/dashboard/templates/feed.html` |
| Impressions, viewed cards/session, dwell, saves, opens, skips, swipes, and feed mode are instrumented. | Feed JavaScript queues `card_impression`, `viewed_card`, `open`, swipe, dwell/save/not-interested events with `feed_mode`; GET `/feed/metrics` reports mode-level event counts and normalized rates. | `pytest tests/test_personal_algorithm_engine.py::test_feed_modes_exploration_delivery_and_metrics tests/test_personal_algorithm_engine.py::test_raw_events_and_rewards_are_separate -q` | Inspect beacon wiring and mode metrics for `card_impression`, `viewed_card`, `open`, `swipe_left`, dwell/save/not-interested events, and `feed_mode` capture. | `hedwig/dashboard/app.py`; `hedwig/dashboard/templates/feed.html`; `hedwig/storage/local.py`; `hedwig/storage/supabase.py` |
| Left swipe defaults to save/later; right/next defaults to weak skip/near-neutral; explicit not-interested is strong negative. | `get_personal_algorithm_policy()` exposes immutable swipe defaults; `interpret_behavior_event(...)` maps `swipe_left`, `swipe_right`, and `not_interested` into the expected reward values and strengths. | `pytest tests/test_personal_algorithm_engine.py::test_swipe_defaults_and_policy_parser -q` | Inspect `algorithm.yaml` and `get_personal_algorithm_policy()` output for immutable swipe defaults and reward interpretation boundaries. | `algorithm.yaml`; `hedwig/personal_algorithm.py` |
| Risky natural-language changes shadow-test before applying. | `propose_local_policy_edit(...)` and `classify_policy_edit(...)` classify risky post-ranking and future-ranking edits; `confirm_edit(...)` requires shadow testing for risky exploration edits rather than applying them directly. | `pytest tests/test_personal_algorithm_engine.py::test_swipe_defaults_and_policy_parser tests/test_personal_algorithm_engine.py::test_shadow_fitness_media_and_rollback -q` | Inspect `propose_local_policy_edit`, `classify_policy_edit`, and `confirm_edit` paths to verify risky/future-ranking edits are classified or shadow-tested rather than applied as production ranking changes. | `hedwig/onboarding/nl_algo_editor.py`; `hedwig/personal_algorithm.py` |
| `algorithm.yaml`/policy changes have versioned rollback. | `confirm_edit(...)` can apply a safe local policy edit against `algorithm.yaml`; `restore_algorithm_version(1)` returns `ok` and restores the seeded policy version in the test-isolated algorithm file. | `pytest tests/test_personal_algorithm_engine.py::test_shadow_fitness_media_and_rollback -q` | Confirm a safe local policy edit can be applied and restored with `restore_algorithm_version(1)` while leaving production behavior outside this package unchanged. | `hedwig/onboarding/nl_algo_editor.py`; `algorithm.yaml` |
| Exploration/anomaly exposure defaults around 10% within 5-15% and is subtly labeled. | GET `/feed/api?limit=20` returns items with `is_exploration`, `anomaly_label.reason`, and immutable `pre_layer_ranking` metadata while preserving `ensemble_score` and `final_score`. | `pytest tests/test_personal_algorithm_engine.py::test_feed_modes_exploration_delivery_and_metrics -q` | Inspect `algorithm.yaml` exploration settings and `/feed/api` metadata for labeled exploration items that preserve `ensemble_score`, `final_score`, and immutable pre-layer ranking fields. | `algorithm.yaml`; `hedwig/personal_algorithm.py` |
| Delivery policy chooses surface/channel/timing/repeat after ranking. | GET `/feed/api?limit=20` returns each item with `delivery_policy` and `delivery_decision` metadata, including `delivery_policy.does_not_mutate_ensemble == true`. | `pytest tests/test_personal_algorithm_engine.py::test_feed_modes_exploration_delivery_and_metrics -q` | Inspect `/feed/api` items for `delivery_policy.does_not_mutate_ensemble` and post-ranking delivery metadata rather than ranking or delivery-behavior changes. | `algorithm.yaml`; `hedwig/personal_algorithm.py`; `hedwig/dashboard/app.py` |

## Verification Command

Canonical verification for this evidence package and current behavior:

```bash
pytest tests/test_personal_algorithm_engine.py -q
```

Latest clean personal algorithm test result on 2026-05-14:

The canonical command above was attempted in this local sandbox and was blocked
before test collection by the globally installed `pytest_rerunfailures` plugin
attempting to bind a localhost socket (`PermissionError: [Errno 1] Operation
not permitted`). The clean result corresponding to the same canonical test
target was therefore captured with only that external rerun plugin disabled:

```bash
pytest -p no:rerunfailures tests/test_personal_algorithm_engine.py -q
```

Result: exited `0` with `4 passed in 1.12s`.

Canonical syntax verification for the evidence-related Python surface:

```bash
python -m py_compile hedwig/personal_algorithm.py hedwig/dashboard/app.py hedwig/onboarding/nl_algo_editor.py hedwig/storage/local.py hedwig/storage/supabase.py tests/test_personal_algorithm_engine.py tests/test_issue19_evidence_package.py
```

Latest clean `py_compile` result on 2026-05-14: exited `0` with no output.

Evidence-package reference validation:

```bash
pytest tests/test_issue19_evidence_package.py -q
```

Lightweight entrypoint for evaluator-visible evidence validation:

```bash
sh scripts/verify_issue19_evidence.sh
```

Execute this command from the repository root. The script changes into the
root directory itself, so it also works when launched by relative path from a
subdirectory that can resolve `scripts/verify_issue19_evidence.sh`.

The combined entrypoint performs the evidence-related Python syntax check first,
then invokes both required evidence-package validation categories: issue #7
acceptance-criteria reference validation and repository/checkpoint reference
validation. A successful run exits `0` and reports the targeted
`tests/test_issue19_evidence_package.py` checks as passing.

Canonical git diff whitespace verification for the evidence package:

```bash
git diff --check
```

Latest clean `git diff --check` result on 2026-05-14: exited `0` with no
output.

Canonical full-suite pytest verification for PR #18 / issue #7 regression coverage:

```bash
pytest tests/ -q
```

This canonical full pytest command does not use `pytest-rerunfailures`,
`--reruns`, or any rerun plugin flag. The local sandbox-only command
`pytest -p no:rerunfailures tests/test_personal_algorithm_engine.py -q`
is recorded above only as an environment workaround for a blocked localhost
socket bind in the installed `pytest_rerunfailures` plugin; it is not the canonical verifier command.

## Known Limitations

These limitations are evaluator-relevant boundaries for issue #7 / PR #18
verification. They describe what the accepted Gen 9 checkpoint does not claim
to implement, and they must not be used to expand the product scope of issue
#19:

- The package verifies bounded post-ranking personal-algorithm evidence; it
  does not prove a new production ranking algorithm, learning-to-rank pipeline,
  or composite-fitness optimizer.
- Composite Fitness is limited to evaluator-visible shadow-test evidence in PR #18.
  Production Composite Fitness optimization, automatic policy selection,
  adoption-threshold changes, and ranking behavior driven by
  `composite_fitness(...)` remain future follow-up work.
- Media understanding remains limited to the existing gated policy surface; this
  package does not validate full multimodal ingestion, transcription, image
  understanding, or media-derived ranking behavior.
- The SOTA/VLM learning loop is not implemented by PR #18. The accepted Gen 9
  checkpoint does not train, tune, or evaluate a vision-language model or
  SOTA recommender loop; those capabilities remain a separate future follow-up
  gap.
- Behavior-event and reward evidence is scoped to the current storage adapter
  paths and tests; it does not claim new retention policy, analytics warehouse,
  migration rollout, or cross-environment backfill behavior.
- Feed-mode evidence covers evaluator-visible Grid, Detail Swipe, and Dense
  Reader controls plus instrumentation; it does not claim ranking semantics,
  source selection, or delivery execution changed for those modes.
- Ambient delivery UX is not implemented by PR #18. The accepted Gen 9
  checkpoint exposes post-ranking delivery metadata only; ambient reminders,
  tray or notification surfaces, repeated delivery experiences, and polished
  cross-surface delivery flows remain future follow-up work.
- Natural-language policy editing evidence covers classification, local safe
  edits, risky-edit shadow-test gating, and rollback; it does not claim
  arbitrary user prompts can safely mutate production ranking or policy logic.
- Ralph Gen 10-13 are excluded because they were rejected as
  `grade_regressing`; any gaps those generations attempted to address remain
  follow-up work unless separately accepted in a future issue.

## Follow-Up Gaps

The following items are future-work buckets and must not be represented as
implemented by PR #18 or this issue #19 evidence package:

- Composite Fitness production optimization: replacing, retraining, or tuning
  the production ranking algorithm with Composite Fitness; using Composite
  Fitness to select policies automatically; changing adoption thresholds; or
  treating `composite_fitness(...)` shadow-test output as production ranking
  behavior.
- SOTA/VLM learning-loop work, including vision-language model evaluation,
  multimodal model training, SOTA recommender experiments, or any feedback loop
  that would change production ranking behavior.
- Enabling full media understanding beyond the existing policy and environment
  gate.
- Changing feed ranking semantics, source selection, storage schema, delivery
  routing, or model training behavior beyond the accepted Gen 9 checkpoint.
- Ambient delivery UX, including notification/tray reminders, repeated
  delivery interactions, or cross-surface delivery polish beyond the
  post-ranking metadata evidenced for PR #18.
- Incorporating Ralph Gen 10-13 changes, because those generations were
  rejected as `grade_regressing`.
