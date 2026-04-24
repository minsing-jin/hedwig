# Ouroboros Interview ↔ Implementation Gap Audit

**Date**: 2026-04-24
**Sources**:
- `docs/interviews/2026-03-16-socratic-interview-v1.md`
- `docs/interviews/2026-04-08-socratic-interview-v2.md`
- `seed.yaml` v2.0 (ontology + evaluation_principles + exit_conditions)

## Method
Walk every entity in `seed.yaml` ontology_schema + every converged decision
from interview v2 (23 items) + seed.yaml evaluation_principles, and flag
what the v3 implementation covers, partially covers, or leaves open.

## Gap Matrix

| # | Gap | Interview / Seed reference | v3 state | Priority |
|---|---|---|---|---|
| G1 | `judgment` not a first-class separate entity; scored fields live inline on signals | ontology_schema.judgment — "guaranteed present on every signal (schema-level requirement, not runtime hope)" + `produced_by_criteria_version` + `produced_by_interpretation_style_id` | Inline columns. No cross-version tracking | 🟠 med |
| **G2** | **`interpretation_style` entity missing** | ontology_schema.interpretation_style — "First-class evolvable artifact that controls HOW signals are explained. Fields: id, version, tone, depth, jargon_level, prompt_template. Evolved weekly (AC 4) separately from criteria" | Scorer prompt hardcoded string. No style entity. Weekly evolution doesn't mutate style | 🔴 **high** |
| **G3** | **`user_memory` weekly snapshots not written** | Interview v2 #22 + ontology_schema.user_memory — "Weekly append-only; never overwritten. Portable identity anchor" | Table exists, nothing writes to it | 🔴 **high** |
| **G4** | **`sovereignty` boundary not expressed** | ontology_schema.sovereignty + interview v2 #23 (core moat) — "user_editable (list of paths the user can directly edit), system_mutable (paths the evolution loops may mutate), readonly_history, export_contract" | No sovereignty.yaml, no enforcement; anyone can edit anything | 🔴 **high** |
| G5 | `feedback.attribution` field not populated | ontology_schema.feedback — "attribution (list of criterion_ids and source_plugin_id influenced by this vote)" | Feedback table lacks attribution | 🟠 med |
| G6 | `delivery` entity with its own id so feedback binds to a specific delivery | ontology_schema.delivery — "Delivered_signal entity with its own identity so feedback can bind to a specific delivery" | Feedback binds to signal_id only | 🟡 low |
| G7 | `cycle` structured ontology partially covered | ontology_schema.cycle — scope (micro/macro), axis (criteria/source/interpretation/exploration), inputs/outputs | evolution_logs has cycle_type/number/mutations but missing scope, axis, structured inputs/outputs | 🟠 med |
| G8 | `exit_conditions` progress not surfaced | seed.yaml.exit_conditions (4 gates) | Not shown in dashboard; no progress tracking | 🟡 low |
| G9 | `evaluation_principles` weights not applied | seed.yaml 6 principles with explicit weights | fitness uses upvote_ratio + retention×acceptance (different metric) | 🟡 low |
| G10 | `briefing` structured fields absent | ontology_schema.briefing — trend_patterns, opportunity_hypotheses, exploration_suggestions, evolution_report | Briefings stored as raw text only (via just-added /brief) | 🟡 low |
| G11 | `interpretation_evolution` axis has no code path | seed.yaml self_improvement_dimensions (4 axes) | criteria_evolution yes; source_evolution partial; **interpretation_evolution none**; exploration_evolution partial | 🔴 **high** (couples with G2) |

## Resolution Plan

### This turn — G2/G11, G3, G4 (core sovereignty + self-improvement axes)

**G2 + G11** — First-class `interpretation_style`:
- `models.InterpretationStyle` (version, tone, depth, jargon_level, prompt_template)
- `interpretation_styles` SQLite table with v1 seed (current hardcoded prompt extracted)
- `load_active_style()` helper
- `scorer._build_scoring_prompt` reads active style's template
- `evolution/interpretation.py` with weekly `evolve_style` that mutates tone/depth/jargon under LLM analysis of recent feedback
- weekly cycle calls `evolve_style` — fills the missing 4th self_improvement axis

**G3** — User memory weekly snapshots:
- `hedwig/memory/snapshot.py` with `create_weekly_snapshot` that aggregates 7-day feedback + LLM-produced taste trajectory
- Called from `run_weekly` after evolution
- Persists via existing `save_user_memory`

**G4** — Sovereignty boundary:
- `sovereignty.yaml` at repo root with `user_editable` / `system_mutable` / `readonly_history` path lists
- `hedwig/sovereignty.py` with `can_edit(path, actor)` and `enforce(path, actor)` helpers
- `nl_editor.confirm_edit` + `nl_algo_editor.confirm_edit` consult sovereignty; illegal edits return 403-style error
- Meta-evolution `adopt()` consults sovereignty before overwriting
- `/sovereignty` read-only page listing current boundaries

### Next turn (documented, not closed now)
- G1 judgment split (refactor-heavy)
- G5 feedback.attribution (requires evolution engine pipeline tap)
- G6 delivery entity (AC6 correctness; current cross-channel works via signal_id but not perfectly)
- G7 cycle structured fields (ALTER TABLE + evolution engine rewrite)
- G8 exit_conditions dashboard panel
- G9 evaluation_principles weighted fitness
- G10 briefing structured fields
