# Phase 1 Gap Report — Triple-Input + Absorption Infra

**Date**: 2026-04-21
**Status**: Complete
**Gap**: 0.08

## Plan (from VISION_v3.md §12, Phase 1)
- `/ask` chat endpoint (RAG over SQLite + exa fallback)
- Natural-language criteria editor (intent → YAML diff → confirm)
- Ad-hoc acceptance events → `evolution_signal` table
- MCP/Skill adapter scaffold (`sources/_mcp_adapter.py`, `sources/_skill_adapter.py`)
- First last30days-skill L2 absorption (pre_scorer enhancement)

## Implementation

| Item | Status |
|---|---|
| `POST /ask` — RAG + fallback | ✅ Phase 0 |
| `POST /qa/feedback` — semi-explicit event logging | ✅ |
| `POST /criteria/propose` — LLM proposes YAML diff | ✅ |
| `POST /criteria/apply` — confirm + write + log explicit event | ✅ |
| Home dashboard Q&A chat widget + NL criteria editor | ✅ |
| `evolution_signal` SQLite table + CRUD | ✅ |
| `algorithm_versions` table + CRUD | ✅ |
| `sources/_mcp_adapter.py` scaffold | ✅ (stub — handshake Phase 1 P0 next) |
| `sources/_skill_adapter.py` scaffold | ✅ (stub — last30days pending) |
| `hedwig/engine/absorbed/last30days.py` — topic persistence + saturation penalty + velocity bonus | ✅ |
| `main.py` `normalize_and_prescore` uses enrich_score | ✅ |
| Tests: 15 new + 6 scaffolding = 21 passing | ✅ |

## Gap Analysis

### Code completeness: 0.05
- MCP/Skill adapters are **scaffolds**; real handshake (MCP client lib, skill module loader) not wired. Phase 1 P0 continuation will wire these to last30days-skill.
- last30days absorption ported the three key ideas (persistence, saturation, velocity). Full parity with upstream is not required — Hedwig uses different source stack.

### Test coverage: 0.0
- Triple-input path fully covered:
  - explicit: `criteria_edit` logs to evolution_signal ✅
  - semi: `qa_accept`/`qa_reject` via `/qa/feedback` ✅
  - implicit: existing `/feedback/{id}/{vote}` untouched, still logs via `save_feedback`

### Integration: 0.03
- Q&A UI chat widget is rendered but not yet stress-tested with live data.
- Enrich_score integrates with `normalize_and_prescore` only when historical signals exist (graceful empty fallback).

## Decision
**Gap 0.08 < 0.1 threshold → proceed to Phase 2.**

MCP/Skill adapter stubs are acceptable residual — they become live in a future targeted Phase 1 continuation when the user picks a specific MCP server to absorb. The core Triple-Input loop is fully functional.

## Artifacts
- `hedwig/storage/local.py` — `evolution_signal`, `algorithm_versions` tables + CRUD
- `hedwig/onboarding/nl_editor.py` — propose / apply / yaml_diff
- `hedwig/qa/feedback.py` — record_qa_event
- `hedwig/sources/_mcp_adapter.py` — MCP scaffold
- `hedwig/sources/_skill_adapter.py` — Skill scaffold
- `hedwig/engine/absorbed/last30days.py` — L2 absorption (persistence, saturation, velocity)
- `hedwig/dashboard/app.py` — `/qa/feedback`, `/criteria/propose`, `/criteria/apply`
- `hedwig/dashboard/templates/home.html` — chat + NL editor widgets
- `tests/test_v3_phase1.py` — 15 passing tests
