# Multimodal Fitness Future-Work Issue

Plan for issue 7 Sub-AC 24.4.1. This is a GitHub-ready future-work issue for
Multimodal Fitness. It defines the future scope, dependencies, and deferral
rationale for using optional media-understanding signals in fitness evaluation
without changing the current hybrid/SOTA ensemble ranking, feed order, reward
interpretation, or delivery routing behavior.

## Issue: Explore Multimodal Fitness As A Shadow-Only Evaluation Layer

**Stage:** Future experimental evaluation after Data, Feed, Natural Language,
and Delivery foundations

**Goal:** Define a safe path for evaluating whether optional media metadata can
improve Composite Fitness and user satisfaction while preserving existing
ensemble `final_score`, default Text + Thumbnail + Transcript behavior, and
user-owned policy control through `algorithm.yaml`.

**Parent:** #7

**GitHub Issue:** #16

## Scope

- Define Multimodal Fitness as a future shadow-only evaluation layer that may
  consume text, thumbnail, transcript, and optional Full Media Understanding
  metadata.
- Preserve the existing hybrid/SOTA ensemble `final_score` as the ranking source
  of truth until a later gated issue explicitly approves production use.
- Compare candidate multimodal fitness metrics against baseline Composite
  Fitness metrics using the same raw behavior events, derived rewards, explicit
  feedback, feed mode, delivery surface, and policy-version context.
- Require Full Media Understanding to remain optional and off by default behind
  env/settings and `algorithm.yaml` controls.
- Keep raw behavior events, derived rewards, learning inputs, media profiles,
  delivery decisions, and fitness evaluations as separate auditable records.
- Define evaluation slices for `grid`, `detail_swipe`, `dense_reader`, critical
  delivery, daily delivery, weekly delivery, PWA, and tray surfaces when data is
  available.
- Track whether multimodal context improves saves, opens, dwell, skips,
  diversity, exploration acceptance, and explicit feedback agreement without
  overfitting to passive media signals.

## Out Of Scope

- Enabling Full Media Understanding by default.
- Reordering `/feed/api`, changing retrieval, changing `top_k`, mutating stored
  `relevance_score`, or replacing ensemble `final_score`.
- Applying multimodal fitness directly to production ranking, source weights,
  delivery routing, reward strengths, or swipe/skip policy.
- Collapsing media metadata into raw behavior events or derived reward rows.
- Training or enabling a learned optimizer in production.
- Enabling automatic rollback on metric degradation.
- Making advanced media analysis a prerequisite for Grid, Detail Swipe, Dense
  Reader, or delivery surfaces.

## Proposed Evaluation Contract

Multimodal Fitness should be computed from immutable source records and stored
as an experimental evaluation result.

Minimum inputs:

- Ranked item snapshot with `signal_id`, ensemble score, feed position, source,
  and collection time.
- Media profile with Text + Thumbnail + Transcript availability and optional
  Full Media Understanding metadata only when explicitly enabled.
- Raw behavior events for impressions, opens, saves, skips, swipes, dwell, and
  not-interested actions.
- Derived reward signals with polarity, strength, confidence, reason, and reward
  policy version.
- Explicit feedback records from existing feedback paths.
- Feed mode, delivery surface, exploration label, anomaly reason, and active
  `algorithm.yaml` policy version.

Suggested output fields:

```json
{
  "evaluation_id": "multimodal-fitness-shadow-2026-05-12",
  "mode": "shadow_only",
  "baseline_policy_version": "algorithm-policy-v3",
  "candidate_policy_version": "multimodal-fitness-v0",
  "data_window": "rolling_30_days",
  "fitness_components": {
    "explicit_feedback_agreement": 0.0,
    "save_open_lift": 0.0,
    "dwell_quality": 0.0,
    "skip_reduction": 0.0,
    "diversity_preservation": 0.0,
    "exploration_acceptance": 0.0,
    "media_context_coverage": 0.0
  },
  "recommendation": "needs_more_data"
}
```

## Safety Gates

- Run only in shadow mode until a later issue defines production gates,
  rollback behavior, and user approval flow.
- Require baseline and candidate policy versions for every evaluation.
- Require a versioned rollback snapshot before any future policy mutation is
  applied.
- Reject evaluations that lack required raw-event, reward, media-profile, or
  policy-version lineage.
- Treat passive media signals as weak evidence unless they agree with explicit
  feedback, saves, opens, or not-interested actions.
- Report confidence and data sparsity separately for each feed mode and delivery
  surface.
- Preserve the existing default media strategy: Text + Thumbnail + Transcript.
- Keep Full Media Understanding data invalid unless the env/settings flag and
  user-owned policy both allow it.

## Dependencies

- Behavior Event Capture staged issue for raw event taxonomy, storage, privacy,
  and mode-scoped instrumentation.
- Reward Modeling staged issue for conservative derived rewards and configurable
  swipe/skip strength.
- Learning Inputs Pipeline staged issue for immutable feature provenance,
  leakage checks, and read-only evaluation datasets.
- Feed Consumption Controls staged issues for Grid, Detail Swipe, Dense Reader,
  media profile presentation, and exploration labels.
- Natural-Language Policy Expression and Policy Enforcement staged issues for
  user-owned edits, risky-change classification, shadow-test routing, and
  rollback versions.
- Delivery Routing Policy staged issues for post-ranking surface, channel,
  timing, repeat, and delivery outcome context.
- Optional Full Media Understanding implementation that remains disabled by
  default behind env/settings and `algorithm.yaml` controls.

## Deferral Rationale

- Multimodal Fitness depends on trustworthy raw behavior events, derived
  rewards, learning inputs, feed-mode metrics, and delivery context; without
  those foundations it would overfit sparse or noisy media interactions.
- Advanced media analysis may be expensive and privacy-sensitive, so it must
  remain opt-in and user-owned before it can influence evaluation.
- Current Hedwig quality depends on the existing hybrid/SOTA ensemble
  `final_score`; introducing multimodal fitness into production ranking before
  shadow testing would violate the additive-compatibility boundary.
- Composite Fitness improvement is explicitly future experimental work in the
  issue 7 seed, so this issue tracks the work without expanding the current
  implementation scope.
- Delivery routing and natural-language policy controls need stable data and
  rollback contracts before a multimodal evaluation can safely recommend policy
  changes.

## Acceptance Criteria

- The future-work issue defines Multimodal Fitness as shadow-only experimental
  evaluation, not production ranking.
- Scope includes Text + Thumbnail + Transcript and optional Full Media
  Understanding metadata while keeping Full Media Understanding off by default.
- Dependencies cover behavior events, reward modeling, learning inputs, feed
  modes, natural-language policy enforcement, delivery context, rollback, and
  optional media understanding.
- Deferral rationale explains why Multimodal Fitness is not implemented in the
  current feed-moat work.
- Safety gates require policy versions, source lineage, shadow testing,
  rollback readiness, and preservation of ensemble `final_score` and `/feed/api`
  order.
- The issue leaves room for later Composite Fitness experiments without
  applying fitness changes to production ranking, reward weights, or delivery
  routing.

## Unblocks

- Future shadow-test implementation for multimodal Composite Fitness.
- Future dashboard reporting for media-context coverage and multimodal quality
  deltas.
- Future natural-language requests such as "use video transcripts more when
  evaluating my feed" with validation and shadow-test routing.
- Future gated issue for applying proven multimodal evaluation insights to
  policy suggestions.
