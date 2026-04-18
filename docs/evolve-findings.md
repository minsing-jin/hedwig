# Hedwig Ontology Evolution — Wonder Findings (Gen 1-7 total)

Two Ouroboros evolve lineages run, 7 generations total. Convergence
withheld each gen because the engine requires actual seed mutations
between generations (which execute=false skipped). Wonder questions
are the real output.

## Lineage lin_hedwig_v3 (Gens 1-4) — Initial ontology
Identified **10 foundational gaps**, all addressed in seed.yaml v3.1:
1. signal → judgment sub-object (score, rationale, devil_advocate, confidence)
2. exploration_tags placement (now field on signal)
3. interpretation_style as first-class evolvable artifact
4. feedback → criteria/source causal edges (attribution list)
5. cycle entity replaces polymorphic evolution_log (scope + axis)
6. user_memory snapshot target made explicit
7. sovereignty entity for user control boundary
8. delivery entity for channel-specific dispatch
9. criteria.origin + parent_version lineage
10. Devil Advocate as schema-level guaranteed field

**Committed**: seed.yaml v3.1 (51ef667)

## Lineage lin_hedwig_v31 (Gens 1-3) — After enrichment
New deeper gaps identified (next iteration):

11. **Tenant/account entity missing** — AC 7 multi-tenant SaaS requires
    explicit user/tenant/subscription/billing_state ontology (scoping
    currently implicit)
12. **Generative UI surface contract** — AC 9 needs schema for what
    gets generated, from what inputs, against what schema (first-class
    artifact with version lineage)
13. **App release/version state** — AC 8 pywebview + GitHub updater
    needs release artifact for auditability under sovereignty
14. **Devil Advocate validity contract** — field is mandatory but no
    validity criterion (non-empty? semantically opposed? grounded?)
    Quality of devil_advocate itself should be subject to feedback
15. **Version-time attribution** — when feedback arrives after criteria
    advanced, does it attribute to judgment-time version, delivery-time,
    or vote-time? Ontology needs explicit temporal binding
16. **Exploration as policy** — AC 4 + AC 13 imply exploration is both
    a tag and an axis; needs explicit `exploration_policy` artifact
    with budget / coverage / decay curves
17. **Deployment mode as ontological dimension** — sovereignty's
    export_contract may need to vary between local SQLite and hosted
    Supabase modes
18. **Attribution computation** — how is feedback.attribution computed?
    By judgment rationale? By active criteria at judgment-time? By
    LLM post-hoc analysis? The computation itself should be versioned
19. **user_memory editability** — weekly append-only vs sovereignty's
    user-editable paths — potential conflict requires explicit rule
    (e.g., corrections are new append records, not edits to history)

## Recommendation

**Option A** — Address gaps 11-19 in seed.yaml v3.2 and run evolve
with `execute=true` for 3+ generations. Execute mode triggers the
Reflect→Seed mutation step that execute=false skips, so the ontology
actually evolves automatically.

**Option B** — Accept current state as "documented ontology frontier"
and move to implementation. The 9 new gaps are mostly about
edge-case formalization (validity contracts, version-time binding,
attribution computation) that can be handled as implementation
details rather than seed changes.

## Files

- `seed.yaml` — v3.1, 11 entities (signal, judgment, criteria,
  interpretation_style, user_memory, sovereignty, feedback, delivery,
  briefing, source_plugin, cycle)
- `docs/resume.md` — resume point snapshot
- This file — evolve findings log

## Current Implementation vs Ontology v3.1

| Entity | Implementation | Gap |
|---|---|---|
| signal | `hedwig/models.py ScoredSignal` | has exploration_tags, relevance_score, urgency, why_relevant, devils_advocate — matches but judgment is inlined, not separate entity |
| judgment | inlined in ScoredSignal | separation deferred |
| criteria | `criteria.yaml` + versioned history | origin/lineage not yet tracked |
| interpretation_style | part of scorer prompt | not yet first-class |
| user_memory | `hedwig/memory/store.py` | snapshot_of fields partial |
| sovereignty | implicit (config file edits) | not modeled |
| feedback | `hedwig/feedback/collector.py` | attribution list missing |
| delivery | `hedwig/delivery/*.py` calls | not persisted as entity |
| briefing | `hedwig/engine/briefing.py` | not persisted |
| source_plugin | `hedwig/sources/base.py` + reliability | matches |
| cycle | `hedwig/evolution/engine.py EvolutionLog` | polymorphic scope not explicit |

## Next Gen Seed Prep

If resuming evolve, the seed_content should add entities 11-19 above.
Or accept current 11-entity ontology as sufficient for v3.1 MVP scope.
