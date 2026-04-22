# hedwig-engine Library Extraction Plan (Phase 6)

## Why
Hedwig's **engine** (`hedwig/engine/`, `hedwig/evolution/`, `hedwig/qa/`) is the novel research artifact — a self-evolving recommendation engine with Algorithm Sovereignty, Triple-Input, Hybrid Ensemble, and Meta-Evolution. The rest (`dashboard`, `saas`, `delivery`, `native`) is derivative infrastructure.

Extracting the engine as a standalone library (`hedwig-engine`) lets the innovation travel independently of Hedwig's product shell, positioning it as a reference implementation of the autoresearch pattern applied to personal recommendation.

## Scope (what moves / what stays)

### Moves to `hedwig-engine`
- `hedwig/engine/` (pre_scorer, scorer, briefing, normalizer, ensemble/*, critical, trace, absorbed/*)
- `hedwig/evolution/` (engine, meta, timeline, sandbox)
- `hedwig/qa/` (retrieval, router, feedback)
- `hedwig/onboarding/nl_editor.py`
- `hedwig/models.py` (domain types only)
- `hedwig/config.py` — split: pure-Python env loader stays with engine; webhook config stays with main app

### Stays in `hedwig` (reference implementation)
- `hedwig/dashboard/` (FastAPI UI — reference consumer)
- `hedwig/saas/` (billing, auth)
- `hedwig/delivery/` (Slack, Discord, email — engine calls out via callbacks)
- `hedwig/sources/` (split: base/registry can live in engine; concrete plugins stay because each has its own network deps)
- `hedwig/native/`, `hedwig/main.py`

## Dependency boundary rules
`hedwig/engine/__init__.py` enforces these via its docstring:

> MUST NOT import from dashboard / saas / delivery / native.

Lint/enforcement (future):
```python
# scripts/check_engine_boundaries.py
forbidden = ("hedwig.dashboard", "hedwig.saas", "hedwig.delivery", "hedwig.native")
# walk hedwig/engine, hedwig/evolution, hedwig/qa and fail on any forbidden import
```

## Public API (stable for v3)

Importable from `hedwig.engine`:
- `pre_score`, `pre_filter` — cheap numeric retrieval
- `score_posts` — LLM judge
- `generate_daily_briefing`, `generate_weekly_briefing` — prose output
- `normalize_content`, `normalize_batch` — HTML→markdown
- `rank_with_ensemble`, `run_two_stage` — ensemble orchestration
- `critical_score`, `filter_critical` — instant-tier gating
- `trace_signal` — Why-this-signal explanation
- `enrich_score` — last30days-style enrichment

Importable from `hedwig.evolution`:
- `EvolutionEngine` — daily/weekly criteria evolution
- `run_meta_cycle`, `adopt`, `generate_candidate` — Meta-Evolution layer
- `build_timeline` — merged history view
- `run_sandbox`, `synthesize_fitness`, `make_candidate` — mutation sandbox

## Extraction steps (post-Phase 6)

1. **Create `hedwig-engine` repo** (separate or monorepo package)
2. Copy the listed modules; adjust imports to remove cross-pkg coupling
3. Define `hedwig_engine.config` loader that takes a dict rather than reading env directly
4. Publish `hedwig-engine` to PyPI with the autoresearch/recsys positioning
5. In `hedwig`, replace local imports with `from hedwig_engine import ...`
6. Maintain `hedwig` as a working reference implementation (dashboard + delivery)
7. Pin `hedwig-engine >= 0.x` as a dep; bump Hedwig to version 4.0

## Not-yet-decided

- Whether the engine ships its own SQLite schema or leaves persistence to the host
- Whether sources (`hedwig/sources/`) live in the engine package or as optional plugins
- Whether LLM client selection (OpenAI vs Anthropic) becomes a pluggable interface in the engine

These resolve after running Hedwig v3 for 4-8 weeks to observe which seams are actually load-bearing.

## Status (2026-04-21)

- `hedwig/engine/__init__.py` exports the stable public API (lazy-loaded)
- Engine/evolution/qa code does not import from dashboard/saas/delivery/native today — verified by reading all touched files during v3 implementation
- No physical extraction yet. The extraction is a pure packaging operation once v3 soaks for several weeks and the real seams stabilize.
