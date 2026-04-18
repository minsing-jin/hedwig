# Hedwig — Resume Point (2026-04-18)

**Status**: Paused mid-evolve. All committed work safe. Ready to continue.

## Current State

- Branch: `main`
- Latest commit: `a2c3ff0` style: ruff auto-fix repo-wide
- Tests: **339 passing, 0 failing**
- Lint: clean (ruff passes)
- 17 source plugins registered
- 6 gap ACs filled (Stripe webhook DB, run_history, source reliability,
  exploration_tags, native icon + updater, generative UI)

## What Was Running When Paused

**Ouroboros evolve loop — cancelled at Gen 5 wondering**

- Lineage ID: `lin_hedwig_v3`
- Generations completed: 1-4 (all action=continue, similarity 100%
  but ontology unchanged → withheld convergence)
- Cancelled job: `job_a5c8fde698c2` (Gen 5 wondering)

## Skills / Loops Status

| Command | Status | Result |
|---|---|---|
| `ouroboros:evaluate` | DONE | Stage 1 — lint PASS, build PASS, test PASS; static + coverage FAIL (tools missing, not code) |
| `ouroboros:evolve` | PAUSED at Gen 5 | 4 generations revealed 10 ontological gaps (see below) |
| `ouroboros:ralph` | DEFERRED | Codex orchestrator ran equivalent 3x already (feature build, fix, gap-fill) |

## Ontology Gaps Identified by Evolve Wonder (for future seed.yaml v3.1)

1. `signal` internal structure — score/rationale/devil_advocate should be sub-fields
2. `exploration_tag` placement — field on signal? dimension on criteria? separate axis?
3. `interpretation` is evolvable but missing from ontology
4. feedback → criteria / source_plugin causal edges not modeled
5. `evolution_log` is polymorphic — should split daily-micro vs weekly-macro
6. `user_memory` snapshot target unclear (criteria? feedback? narrative?)
7. User sovereignty boundary (user-editable vs system-mutated) not expressed
8. `delivery` / `dispatch` entity missing (feedback ↔ delivered_signal binding)
9. `criteria` provenance/lineage (onboarding vs daily vs weekly) not tracked
10. Devil's Advocate first-class entity vs signal field — not decided

## How to Resume

### Option A — Continue evolve loop
```bash
# MCP must be connected (Ouroboros plugin active)
# Then in Claude Code:
ouroboros_start_evolve_step(
    lineage_id="lin_hedwig_v3",
    project_dir="/Users/jinminseong/Desktop/hedwig",
    execute=false,
    skip_qa=true,
)
# Then poll with ouroboros_job_wait
# Will hit formal stagnation around Gen 6-7 since ontology unchanged
```

### Option B — Enrich seed.yaml ontology first (recommended)
Update `seed.yaml` ontology_schema to address the 10 gaps above, then:
```bash
ouroboros run workflow seed.yaml --no-qa
```

### Option C — Fix evaluate Stage 1 tooling
Install static analysis + coverage tools so Ouroboros evaluate passes Stage 1:
```bash
uv pip install mypy pytest-cov
# Add [tool.mypy] and [tool.coverage] to pyproject.toml
# Then re-run ouroboros_evaluate
```

### Option D — Run native Ouroboros Ralph (full execute)
```bash
# From Claude Code with MCP connected:
# Set up lineage with execute=true for full Execute→Evaluate each generation
ouroboros_start_evolve_step(
    lineage_id="lin_hedwig_v3",
    project_dir="/Users/jinminseong/Desktop/hedwig",
    execute=true,
    skip_qa=false,   # get QA verdict
)
```

## Quick Commands

```bash
# Check current tests
.venv/bin/python -m pytest tests/ --tb=no -q

# Check lint
ruff check .

# Run quickstart
.venv/bin/python -m hedwig --quickstart

# Run dashboard
.venv/bin/python -m hedwig --dashboard

# Check running orchestrators
ps aux | grep codex_orchestrator | grep -v grep

# Latest log
tail /tmp/orchestrator_gaps2.log
```

## Background Processes — None Currently Running

All gap-fill orchestrator processes completed. Evolve cancelled cleanly.
Safe to resume anytime.

## Repo Health Snapshot

- Latest 5 commits:
  - `a2c3ff0` style: ruff auto-fix repo-wide
  - `2449cc4` style: ruff auto-fix (26 lint errors)
  - `b1497a5` feat: close remaining gaps — AC 3, 5, 6
  - `7e0a12f` feat(ralph-codex): AC 7 — zero regressions
  - `692636d` feat(ralph-codex): AC 4 — exploration_tags

- Files tracked: 150+ (hedwig/, tests/, scripts/, docs/, migrations/, assets/)
- Storage backends: SQLite (default) + Supabase (opt-in)
- Deployment: Procfile + Dockerfile + railway.toml + nixpacks.toml
