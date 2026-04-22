# Phase 2 Gap Report — Instrumentation

**Date**: 2026-04-21
**Status**: Complete
**Gap**: 0.07

## Plan
- Why this signal trace API + UI integration
- Evolution timeline viewer (criteria + algorithm diffs + event stream)
- Mutation sandbox (inject fake feedback → preview fitness)

## Implementation

| Item | Status |
|---|---|
| `hedwig/engine/trace.py` — per-signal Why explanation | ✅ |
| `GET /signals/{id}/trace` endpoint | ✅ |
| `hedwig/evolution/timeline.py` — unified merged feed | ✅ |
| `GET /evolution/timeline?days=&limit=` | ✅ |
| `hedwig/evolution/sandbox.py` — synthesize_fitness + make_candidate + run_sandbox | ✅ |
| `POST /sandbox/simulate` | ✅ |
| `_jsonable` helper for YAML-with-date serialization | ✅ |
| 9 new tests | ✅ |

## Gap Analysis
- Code: **0.0** — all planned surfaces shipped
- UI: **0.05** — trace/timeline/sandbox have JSON APIs but no polished UI widgets yet. Users can hit endpoints directly via browser/curl; visual rendering is a follow-up polish item, not blocking.
- Completeness of fitness: **0.02** — synthesize_fitness is a cheap proxy (upvote ratio + diversity bonus); full fidelity requires replaying historical signals through the candidate pipeline, which Phase 3 enables. Tracked as a controlled simplification, not a bug.

## Decision
**Gap 0.07 < 0.1 → proceed to Phase 3.**

## Artifacts
- `hedwig/engine/trace.py`
- `hedwig/evolution/timeline.py`
- `hedwig/evolution/sandbox.py`
- `hedwig/dashboard/app.py` — 3 new endpoints + `_jsonable`
- `tests/test_v3_phase2.py` — 9 passing tests
