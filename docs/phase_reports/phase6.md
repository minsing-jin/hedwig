# Phase 6 Gap Report — Library Extraction Signals

**Date**: 2026-04-21
**Status**: Complete
**Gap**: 0.05

## Plan
- Scope `hedwig-engine` extraction boundaries
- Mark dashboard as reference implementation (not hard extraction yet)
- Update positioning
- Publish extraction plan doc

## Implementation

| Item | Status |
|---|---|
| `hedwig/engine/__init__.py` — public stable API with lazy-loading | ✅ |
| `docs/LIBRARY_EXTRACTION.md` — full extraction plan + boundary rules | ✅ |
| Boundary enforcement test (AST-walk forbidding dashboard/saas/delivery/native imports) | ✅ |
| Caught + fixed boundary violation: `engine/critical.py` imported `hedwig.delivery.*` | ✅ refactored to deliver-callback pattern |
| Dashboard wires delivery as callback into `run_critical_cycle(deliver=...)` | ✅ |
| 5 boundary + lazy-API tests | ✅ |

## Gap Analysis

### Code completeness: 0.0
- Public API exported and lazy-loadable. Boundary test caught the real violation and a fix shipped. Extraction mechanics are now a packaging operation, not a rewrite.

### Physical extraction: deferred by design
- We are intentionally **not** splitting the repo right now. Running Hedwig v3 for 4-8 weeks will reveal which seams are actually load-bearing. Premature extraction would force interface guesses.
- This is documented in `LIBRARY_EXTRACTION.md` §"Not-yet-decided" as an explicit trade-off, not a gap.

### Documentation: 0.05
- The plan captures the target, but the hosting-side extraction script (rename imports, publish to PyPI) is not yet written. It's a mechanical ~1-day task when v3 soaks.

## Decision
**Gap 0.05 < 0.1 → Phase 6 complete.**

## Artifacts
- `hedwig/engine/__init__.py` — stable public API
- `docs/LIBRARY_EXTRACTION.md` — extraction plan
- `tests/test_v3_phase6.py` — boundary tests
- `hedwig/engine/critical.py` — refactored to delivery-callback pattern
- `hedwig/dashboard/app.py` — wires delivery callback
