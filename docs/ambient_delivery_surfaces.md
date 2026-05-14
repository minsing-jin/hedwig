# Ambient Delivery Surfaces

Issue #20 adds ambient delivery surfaces downstream of the PR #18 / Gen 9
personal algorithm ranking core. These surfaces make a small set of
already-ranked items visible in daily life without requiring a user to open the
manual web feed first.

## Ownership Boundary

Ambient delivery owns only post-ranking metadata:

- `delivery_decision`
- `delivery_policy`
- `post_ranking_decisions.delivery`
- display-only `explanation`
- raw `delivery_event` capture and separately derived `delivery_reward`

Ambient delivery does not own ranking inputs or ranking outputs. It must not
mutate `ensemble_score`, `final_score`, `pre_layer_ranking.input_rank`,
`pre_layer_ranking.input_order`, or `pre_layer_ranking.rank_identifiers`.
In short, ambient delivery must not mutate `ensemble_score`, `final_score`, or
pre-layer rank identity.
Explanations can help a user understand why an item appeared, but they are not
ranking inputs, scores, weights, labels, or authority for reordering.

## Ranking Boundary: Ranked Output In, Routing Metadata Out

Ambient routing starts only after the PR #18 / Gen 9 ranking core has emitted
completed ranked outputs. The ambient layer consumes those ranked outputs as
read-only input and appends routing metadata for delivery surfaces.

Routing consumes existing ranked outputs only. It must not alter PR #18 /
Gen 9 ranking logic, score computation, score ordering, or the ranked item
order emitted by the existing ranking core. Any change to ranking logic or
score ordering is outside issue #20 and must be handled as separate ranking
work, not as an ambient delivery surface change.

Required upstream ranked-output fields:

- `ensemble_score`
- `final_score`
- rank evidence such as `ensemble_rank`, `rank`, `rank_position`, or
  `pre_layer_ranking.input_rank`
- stable rank identity such as `id`, `signal_id`, `feed_position`, and
  `pre_layer_ranking.rank_identifiers`

Ambient routing may read the completed score fields, urgency context,
exploration flag, and copied `pre_layer_ranking` snapshot to decide which
surface receives an item. It may then add `delivery_decision`,
`delivery_policy`, `post_ranking_decisions.delivery`, display-only
`explanation`, and raw delivery events.

Ambient routing must not:

- compute, normalize, round, overwrite, or backfill `ensemble_score`
- compute, normalize, round, overwrite, or backfill `final_score`
- reorder the ranked item list or rewrite pre-layer order
- change `ensemble_rank`, `rank`, `rank_position`, `feed_position`, or
  `pre_layer_ranking.rank_identifiers`
- use explanation text, display reason text, delivery events, or delivery
  rewards as ranking inputs
- promote delivery metadata into ranking features, labels, model-training data,
  composite-fitness optimization, or score-like authority in issue #20

The routing contract is therefore:

1. Ranking core produces ranked items.
2. Ambient routing validates that ranking has completed.
3. Ambient routing copies score and rank identity into immutable snapshots.
4. Ambient routing appends delivery metadata and filters small surface item
   sets while preserving the existing ranked order within each selected set.
5. Raw delivery behavior events are stored separately from derived rewards.

## Surface Semantics

| Surface | Entry kind | Trigger expectation | Routing semantics | Default limit |
| --- | --- | --- | --- | --- |
| `critical` | receiver | A scheduler, notification sender, service worker push, or native bridge receives the next urgent handoff. | Select items whose post-ranking `delivery_decision.surface == "critical"`. Current policy routes explicit `urgency == "alert"` or `ensemble_score >= 0.85` after ranking has completed. | 3 |
| `daily` | receiver | The daily digest runner receives the next high-value non-critical digest batch. | Select items whose post-ranking `delivery_decision.surface == "daily"`. Current policy routes ranked items with `ensemble_score >= 0.65` that did not qualify as critical. | 5 |
| `weekly` | receiver | The weekly review runner receives lower-urgency catch-up items. | Select items whose post-ranking `delivery_decision.surface == "weekly"`. Current policy routes lower-score ranked items that remain eligible for ambient catch-up. | 8 |
| `pwa` | requester | The installable PWA shell requests currently routable ambient cards and can cache them for low-energy exposure. | Select items whose post-ranking `delivery_decision.surface == "pwa"`. Current policy uses this for already-ranked exploration items. | 5 |
| `tray` / `native` | requester | A native tray or compact glance client requests immediately useful items. | Select critical, daily, and PWA-routed items while preserving pre-layer item order. `native`, `native_notification`, and `notification` are aliases to tray/critical entry points as implemented by the ambient surface adapter. | 4 |

Receiver surfaces are expected to be called by jobs or notification-capable
clients. Requester surfaces are expected to be polled or fetched by UI clients.
Neither trigger style authorizes the surface to re-rank, promote, suppress, or
rewrite score fields.

## Delivery Policy Config Schema

Ambient steering is represented by `delivery_policy_config.v1`, implemented by
`DeliveryPolicyConfig` and exposed through `delivery_policy_config_schema()`.
The schema covers the steerable policy dimensions for this issue:

- `timing`: critical timing, daily digest time, weekly digest day/time,
  timezone, and whether quiet hours defer non-critical delivery
- `repeat`: enabled state, maximum repeats, minimum repeat interval, and
  snooze duration
- `quiet_hours`: enabled state, start/end time, timezone, and critical override
  behavior
- `urgency`: critical urgency labels, critical/daily thresholds, and the
  exploration fallback surface
- `preferred_surfaces`: user-preferred ambient surfaces, normalized through the
  same surface vocabulary as `critical`, `daily`, `weekly`, `pwa`, and `tray`

Preferred surfaces are applied only after a canonical delivery intent has been
derived from already-ranked output. The delivery layer records
`canonical_surface`, `eligible_surfaces`, `preferred_surfaces`, and
`surface_preference` metadata, then chooses the first user-preferred surface
that is eligible for that item. If the canonical surface is disabled, the layer
falls back to an enabled ambient surface instead of the manual web feed. This is
exposure routing metadata only and must not mutate rank order or score fields.

This config is delivery metadata only. Its boundary fields require
`post_ranking_only == true`, `ranking_input == false`,
`mutates_scores == false`, and `mutates_rank_identity == false`.

### Natural-Language Delivery Steering

`delivery_policy_steering_interface.v1` defines the supported natural-language
delivery controls. The local parser maps user intents onto
`personal_algorithm.delivery.*` paths only, validates the result through
`DeliveryPolicyConfig`, and classifies the edit as post-ranking delivery policy
state. Supported intents include daily digest time, weekly digest schedule,
quiet hours, preferred ambient surfaces, bounded repeat/snooze policy, and
post-ranking urgency thresholds.

Ranking-like requests are not translated into delivery edits. Mentions of
ranking, retrieval, score mutation, `ensemble_score`, `final_score`, or
`pre_layer_ranking` are reported as unsupported boundary violations so ambient
delivery steering cannot become a ranking input or mutate pre-layer identity.

## Critical Surface Contract

The critical surface is the only immediate urgency surface in issue #20. Its
trigger is a completed ranking run followed by post-ranking delivery routing.
Notification clients may then read `/ambient/critical` or
`/ambient/critical/api`.

Critical routing expectations:

- Input items already contain completed ranking output: `ensemble_score`,
  `final_score`, and rank evidence such as `ensemble_rank` or
  `pre_layer_ranking.input_rank`.
- The routing rule is post-ranking metadata only:
  `delivery_decision.surface == "critical"`.
- Current default trigger eligibility is `urgency == "alert"` or
  `ensemble_score >= 0.85`.
- Delivery metadata copies a read-only `ranking_snapshot` for display and
  audit; it does not become a new ranking source.
- The endpoint returns `ambient_delivery_item_set.v1` with a small default
  limit of 3 items.

If a future change wants critical delivery to affect exposure distribution
beyond this post-ranking route, classify it as `risky_post_ranking` and require
shadow approval. If it wants to affect ranking scores, ranking features, model
training, or composite-fitness optimization, keep it out of issue #20 and
classify it as `future_ranking_experimental`.

## Daily Surface Contract

The daily surface is the normal high-value digest handoff. Its cadence is the
next daily digest run after ranking has completed; it is not a feed-opening
shortcut and it is not allowed to re-run or reinterpret ranking.

Daily routing expectations:

- Input items already contain completed ranking output: `ensemble_score`,
  `final_score`, and rank evidence such as `ensemble_rank` or
  `pre_layer_ranking.input_rank`.
- The routing rule is post-ranking metadata only:
  `delivery_decision.surface == "daily"`.
- Current default trigger eligibility is `ensemble_score >= 0.65` after an
  item has not qualified for critical routing through `urgency == "alert"` or
  `ensemble_score >= 0.85`.
- Selection inputs are limited to copied ranking outputs and delivery context:
  `ensemble_score`, `final_score`, `urgency`, immutable
  `pre_layer_ranking`, and the computed `delivery_decision.surface`.
- The endpoint returns `ambient_delivery_item_set.v1` with a small default
  limit of 5 items for the next digest batch.
- The daily surface preserves pre-layer item order and must not mutate
  `ensemble_score`, `final_score`, or `pre_layer_ranking`.

Explanation text on daily cards is display-only. It can summarize
`why_relevant` or delivery context, but it must not become a score, ranking
feature, authority label, or input to reorder the daily batch.

## Weekly Surface Contract

The weekly surface is the lower-urgency catch-up handoff. Its cadence is the
next weekly review run after ranking has completed; it aggregates already-ranked
items that were not urgent enough for critical delivery and not high-value
enough for the daily digest. Weekly aggregation is a delivery packaging step,
not a second ranking pass.

Weekly routing expectations:

- Input items already contain completed ranking output: `ensemble_score`,
  `final_score`, and rank evidence such as `ensemble_rank` or
  `pre_layer_ranking.input_rank`.
- The routing rule is post-ranking metadata only:
  `delivery_decision.surface == "weekly"`.
- Current default trigger eligibility is a lower-urgency catch-up item that
  remains routable after critical and daily delivery decisions have been made.
- Aggregation behavior is limited to grouping the selected weekly items into a
  compact review batch for `/ambient/weekly` and `/ambient/weekly/api`.
- Aggregation must preserve pre-layer item order and must not deduplicate,
  promote, suppress, cluster, or summarize items in a way that changes rank
  identity.
- Selection inputs are limited to copied ranking outputs and delivery context:
  `ensemble_score`, `final_score`, `urgency`, immutable
  `pre_layer_ranking`, and the computed `delivery_decision.surface`.
- The endpoint returns `ambient_delivery_item_set.v1` with a small default
  limit of 8 items for the next weekly review batch.
- The weekly surface must not mutate `ensemble_score`, `final_score`, or
  `pre_layer_ranking`.

Explanation text on weekly cards is display-only. It can say that an item was
kept for weekly review, but it must not become a score, ranking feature,
authority label, or input to reorder the weekly batch.

## PWA Surface Contract

The PWA surface is the installable ambient shelf for low-friction discovery.
It is reached through the app manifest shortcut at `/ambient/pwa`, backed by
`/ambient/pwa/api`, and cached by the service worker as an ambient shell path.
The PWA shelf is not a replacement for `/feed`: it requests a small set of
already-routed ambient cards so installed clients can expose useful items
without requiring manual feed entry.

PWA exposure is eligible only when all of these conditions hold:

- Ranking has already completed and the item contains `ensemble_score`,
  `final_score`, and rank evidence such as `ensemble_rank` or
  `pre_layer_ranking.input_rank`.
- The post-ranking exploration layer has marked the item with
  `is_exploration == true`, or an equivalent future post-ranking delivery
  policy explicitly routes the item to `delivery_decision.surface == "pwa"`.
- The item can be represented in the small ambient card contract without
  requiring raw body content, media understanding, or a new model pass.
- The PWA request is for ambient exposure through `/ambient/pwa` or
  `/ambient/pwa/api`; manual `/feed` entry is not required.

PWA routing expectations:

- The routing rule is post-ranking metadata only:
  `delivery_decision.surface == "pwa"`.
- The current default trigger eligibility is an already-ranked exploration
  item. In implementation terms, `choose_delivery` routes
  `is_exploration == true` items to the PWA surface after ranking and after the
  exploration layer has preserved rank identity.
- The endpoint returns `ambient_delivery_item_set.v1` with a small default
  limit of 5 items.
- The manifest shortcut named `Ambient` points to `/ambient/pwa`, and the
  service worker includes `/ambient/pwa` and `/ambient/pwa/api` as shell/cache
  entry points for installed clients.
- Installed or standalone clients continue to resolve to the PWA shelf. Browsers
  that explicitly report unsupported PWA capabilities fall back to the daily
  ambient surface, not to `/feed`.
- The PWA surface preserves pre-layer item order within the selected shelf and
  must not mutate `ensemble_score`, `final_score`, or `pre_layer_ranking`.

PWA routing metadata is represented on each selected item as appended
post-ranking metadata:

- `delivery_decision.surface == "pwa"`
- `delivery_decision.timing` copied from the post-ranking routing decision
- `delivery_decision.channel` copied from the configured delivery channel, with
  the ambient client contract exposing it as `delivery_channel`
- `delivery_decision.ranking_snapshot.input_ensemble_score` copied from
  `ensemble_score`
- `delivery_decision.ranking_snapshot.input_final_score` copied from
  `final_score`
- `delivery_decision.ranking_snapshot.input_ensemble_rank`,
  `input_order`, and `rank_identifiers` copied from immutable
  `pre_layer_ranking`
- `post_ranking_decisions.delivery` containing the same delivery decision for
  downstream display/audit consumers
- `explanation` and card `reason` as display-only copy

The PWA surface may render explanation copy such as why an exploration item was
reserved for ambient discovery. That copy is only a user-facing explanation; it
must not become a ranking feature, score proxy, authority label, or input to
the PWA shelf order. Raw PWA delivery behavior events, when captured, stay in
the behavior-event schema with ambient feed identifiers such as
`feed_id == "ambient:pwa"` and remain separate from derived reward signals.

## Tray / Native Surface Contract

The tray/native surface is the compact desktop glance for already-routed
ambient items. It is reached through `/ambient/tray` and `/ambient/tray/api`;
`native` and `native_notification` normalize to the same tray requester
surface. It is not a separate ranking pass and it is not a notification model:
it asks for a small post-ranking shelf that a menu-bar, tray, or native shell
can display without requiring the user to open `/feed`.

Tray/native exposure is eligible only when all of these conditions hold:

- Ranking has already completed and the item contains `ensemble_score`,
  `final_score`, and rank evidence such as `ensemble_rank` or
  `pre_layer_ranking.input_rank`.
- Post-ranking delivery has already routed the item to one of the tray-eligible
  surfaces: `delivery_decision.surface in {"critical", "daily", "pwa"}`.
- The item can be represented in the small ambient card contract without raw
  body content, media understanding, Manus integration, LiteLLM routing, or a
  new model pass.
- The request comes through the ambient tray/native entry point:
  `/ambient/tray`, `/ambient/tray/api`, or an alias normalized from `native` or
  `native_notification`.

Tray/native routing expectations:

- The tray requester reads post-ranking metadata only:
  `delivery_decision.surface in {"critical", "daily", "pwa"}`.
- Current default eligibility admits immediately useful critical items,
  high-value daily digest items, and installable-shelf PWA exploration items.
  Weekly catch-up items are intentionally excluded because the tray is a
  compact glance, not a weekly review batch.
- The endpoint returns `ambient_delivery_item_set.v1` with a small default
  limit of 4 items.
- Selection preserves pre-layer item order across the mixed critical, daily,
  and PWA set; critical items must not jump ahead of earlier ranked daily or
  PWA items.
- The tray/native surface must not mutate `ensemble_score`, `final_score`, or
  `pre_layer_ranking`.

Tray/native routing metadata is represented on each selected item as appended
post-ranking metadata:

- `surface == "tray"` on the returned `AmbientDeliveryItemSet`
- `entry_point.selection_rule == "delivery_decision.surface in {critical, daily, pwa}, preserving pre-layer rank order"`
- `entry_point.aliases == ["native", "native_notification"]`
- `entry_point.eligible_surfaces == ["critical", "daily", "pwa"]`
- each item retains its original `delivery_decision.surface`, such as
  `"critical"`, `"daily"`, or `"pwa"`, rather than rewriting it to `"tray"`
- `delivery_decision.timing` and `delivery_decision.channel` copied from the
  post-ranking routing decision
- `delivery_decision.ranking_snapshot.input_ensemble_score` copied from
  `ensemble_score`
- `delivery_decision.ranking_snapshot.input_final_score` copied from
  `final_score`
- `delivery_decision.ranking_snapshot.input_ensemble_rank`,
  `input_order`, and `rank_identifiers` copied from immutable
  `pre_layer_ranking`
- `post_ranking_decisions.delivery` containing the same delivery decision for
  downstream display/audit consumers
- `explanation` and card `reason` as display-only copy

Tray/native explanation copy may say why a critical, daily, or PWA item is
available at a glance. That copy is display-only: it must not become a ranking
feature, score proxy, authority label, or input to tray ordering. Raw tray
behavior events, when captured, stay in the behavior-event schema with ambient
feed identifiers such as `feed_id == "ambient:tray"` and remain separate from
derived reward signals.
