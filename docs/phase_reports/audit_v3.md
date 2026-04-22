# v3 Drift Audit (2026-04-22)

Cross-checking VISION_v3.md / algorithm.yaml / principles vs shipped code, after Phase 0-6 + residual completion. Eight drift/concept-fidelity items found; all fixed in the same pass.

| # | Drift | Where | Severity | Fix |
|---|---|---|---|---|
| D1 | Default ensemble only runs 2 components (llm_judge, popularity_prior) — contradicts "Hybrid Ensemble" principle #8 and differentiator #5 | `algorithm.yaml` | 🔴 high | Enable `ltr` + `content_based` by default. Bandit remains off until feedback history accrues |
| D2 | Explicit channel edits via `/criteria/apply` bypass `criteria_versions` table — Algorithm Sovereignty (audit/export) broken for user's own edits | `hedwig/onboarding/nl_editor.py` | 🔴 high | `confirm_edit` saves a new CriteriaVersion with diff |
| D3 | `synthesize_fitness` ignores the metric names declared in `algorithm.yaml.fitness` (`retention_x_acceptance`, weighted short+long horizon) — spec/code mismatch | `hedwig/evolution/sandbox.py` | 🟠 med | Read fitness spec from config, compute retention + acceptance when available, fall back gracefully |
| D4 | `Platform` enum has no `PODCAST`; podcasts emitted as `Platform.NEWSLETTER` — multimodal fidelity leak | `hedwig/models.py`, `hedwig/sources/podcast.py`, `hedwig/engine/pre_scorer.py` | 🟡 low | Add `Platform.PODCAST`, wire baselines/authority |
| D5 | `algorithm_versions` table starts empty — no v1 seed; Evolution timeline shows no algorithm history until a meta cycle runs | `hedwig/config.py` loader | 🟡 low | Seed v1 lazily on first `load_algorithm_config` call if table empty |
| D6 | LLM judge runs on all `top_n` (200) candidates — contradicts `algorithm.yaml.ranking.components.llm_judge.apply_to: top_k` | `hedwig/engine/ensemble/combine.py` | 🟠 med | Two-pass rank: cheap components rank full set → take top_k → LLM judge reranks K |
| D7 | `meta.adopt()` writes `updated_at` as date-string; algorithm.yaml originally uses date | `hedwig/evolution/meta.py` | 🟢 cosmetic | Use ISO date consistently |
| D8 | `rank_with_ensemble` passes `criteria_keywords` in context; ContentRanker inspects `criteria_tokens` — harmless but inconsistent | `hedwig/engine/ensemble/*` | 🟢 cosmetic | Unify on `criteria_keywords`; derive tokens per-component |

## Principle re-verification (after fixes)

| Principle | State |
|---|---|
| 1 Algorithm Sovereignty | ✅ criteria_versions now captures user explicit edits (D2) |
| 2 Self-Evolving Fitness | ✅ daily/weekly + monthly Meta, with correct fitness spec (D3) |
| 3 Triple-Input | ✅ explicit via NL editor (newly versioned), semi via Q&A feedback, implicit via upvote |
| 4 4-Tier Temporal | ✅ critical / daily / weekly / on-demand |
| 5 Absorption Gradient | ✅ MCP HTTP + Skill loader + last30days enrichment |
| 6 Engine 계기판 | ✅ /evolution /sandbox /meta visual widgets; no commercial shell |
| 7 Cognitive Augmentation | ✅ pre-scorer + Devil's Advocate (LLM judge restored via D1) + Q&A RAG + timeline |
| 8 Hybrid Ensemble | ✅ 4 components enabled by default after D1; LLM judge now reranks top_k per spec (D6) |

## Post-fix test target
- All previous 414 tests continue to pass
- New tests: criteria-version save, fitness spec respect, podcast platform enum, top-k rerank ordering, algorithm v1 seeding

See FINAL.md "Residual Completion Artifacts" — updated with audit pass.

---

## Refactor Pass (2026-04-22, follow-up)

After the first audit a second review found 9 more plan-vs-code gaps of increasing subtlety. All closed.

| # | Refactor | Before | After |
|---|---|---|---|
| R-A | LTR used a fixed positional weight vector (8 features) — `feature_suggest_from_papers` could append to `ltr.features` but the ranker silently ignored new entries | Positional SGD on hardcoded 8-feature array | Name-keyed registry `FEATURE_REGISTRY`; weights stored as `{feature: weight}` + bias; unknown features return a neutral 0.5 so meta-evolution's additions contribute cleanly |
| R-B | `BanditRanker` ignored `algorithm.yaml.ranking.components.bandit.exploration_rate` | Hardcoded 0.1 | Reads config at construction time |
| R-C | `main.py` → `normalize_and_prescore` ran `pre_filter + enrich` with history; ensemble's `run_two_stage` re-ran `pre_filter` (without history) over the same posts | Duplicate work + history signal discarded | Split `rank_and_build_signals` (ranking-only) from `run_two_stage_as_signals` (full flow); main.py calls the former |
| R-D | Historical enrichment dropped in the ensemble path | — | Covered by R-C: history runs once in main.py, candidates forwarded as-is |
| R-E | `pre_filter` threshold hardcoded at 0.10 in main.py | Opaque to user and to meta-evolution | Reads `algorithm.yaml.retrieval.threshold` (default 0.10); also respects `retrieval.top_n` cap in main.py |
| R-F | `detect_cross_platform_convergence` rebuilt trigrams per `(post, other)` pair — O(N²) string work for 200-candidate batches | ~40k string rebuilds per cycle | Memoised `_build_trigram_index` keyed by `id(posts)` with LRU pruning — O(N) total |
| R-G | Meta-evolution adoption recorded `fitness_score` but no YAML diff | Timeline v1→v2 shows "adopted" without the actual change | `adopt()` computes unified diff before writing and persists it in `algorithm_versions.diff_from_previous` |
| R-H | Verified: v1 seed row has `diff_from_previous=NULL`; first real adopt has content | — | Checked in `test_algorithm_version_seeds_on_first_load` + `test_adopt_records_yaml_diff` |
| R-I | `get_algorithm_history` ordered by `created_at DESC` — same-second seed + adopt rows tied non-deterministically | Fragile history ordering | Secondary sort by `version DESC, id DESC` |

**Test delta**: 436 passing (426 → +10 refactor tests). No regressions.

**Public API change**: `hedwig.engine` now exposes `rank_and_build_signals` and `run_two_stage_as_signals` as lazy lazy imports.
