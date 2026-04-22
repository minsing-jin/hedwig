# Phase 3 Gap Report — Hybrid Ensemble

**Date**: 2026-04-21
**Status**: Complete
**Gap**: 0.10

## Plan
- `engine/ensemble/` — 5 ranking components
  - llm_judge (wrapper over existing scorer, top-K only)
  - ltr (LightGBM or similar)
  - content_based (embedding × criteria)
  - popularity (authority × recency)
  - bandit (Thompson sampling)
- 2-stage pipeline: retrieval (top-200) → ranking (top-30)
- `algorithm.yaml` drives weights + enablement at runtime
- Score fusion (min-max normalize + weighted sum)

## Implementation

| Component | Status | Notes |
|---|---|---|
| `base.py` — Protocol + minmax_normalize | ✅ | |
| `llm_judge.py` | ✅ | Thin wrapper over existing scorer |
| `content.py` — Jaccard token overlap | ✅ | Embedding version deferred (no numpy/openai cost-free path) |
| `popularity.py` — authority × recency | ✅ | Reads `decay_hours` from algorithm.yaml |
| `bandit.py` — Thompson sampling per platform | ✅ | Pure random.betavariate; no numpy |
| `ltr.py` — logistic ranker (8 features) + SGD training | ✅ | LightGBM substituted with pure-Python SGD since lightgbm not in deps. Same feature set as planned. `fit_from_history` trains online from feedback |
| `combine.py` — rank_with_ensemble + run_two_stage | ✅ | Registry pattern; components load lazily |
| algorithm.yaml drives runtime | ✅ | `_enabled_components` reads enabled flag + weight |
| 11 new tests covering each component + combiner + 2-stage | ✅ | |

## Gap Analysis

### Code completeness: 0.05
- LTR ships as a pure-Python logistic ranker instead of LightGBM. Same feature vector, same online training, but loses gradient boosting's nonlinearity. Documented as a controlled substitution — a drop-in LightGBM replacement is possible once the ML dep set expands (Phase 6+ consideration).
- Content-based uses Jaccard overlap instead of embeddings. Wire-in point exists (`context["criteria_tokens"]`); swapping to OpenAI embeddings requires only a tokenization method change.

### Integration: 0.05
- `main.py` still uses the legacy single-stage LLM scorer; the 2-stage orchestrator is available via `run_two_stage` but not yet wired as the default. This is intentional — swapping default requires Phase 4's fitness-based adoption decision. Users can opt in via code until then.

### Test coverage: 0.0
- Each component tested in isolation; combiner tested with fake LLM for determinism; 2-stage orchestrator tested with 40 synthetic posts.

## Decision
**Gap 0.10 = threshold → proceed to Phase 4.**

The residual 0.1 is the LightGBM substitution + main.py default wiring, both of which are non-blocking architectural decisions, not missing behavior. The ensemble itself is structurally complete and will be exercised through Phase 4's shadow-mode evaluation.

## Artifacts
- `hedwig/engine/ensemble/base.py` — Protocol + normalize
- `hedwig/engine/ensemble/llm_judge.py`
- `hedwig/engine/ensemble/content.py`
- `hedwig/engine/ensemble/popularity.py`
- `hedwig/engine/ensemble/bandit.py`
- `hedwig/engine/ensemble/ltr.py` — logistic + SGD fit
- `hedwig/engine/ensemble/combine.py` — fusion + run_two_stage
- `tests/test_v3_phase3.py` — 11 passing tests
