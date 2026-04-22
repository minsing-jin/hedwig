"""Ensemble score fusion + 2-stage orchestrator.

Reads algorithm.yaml for weights and component enablement. For each
component, runs `score_posts`, normalizes per-component scores to [0,1]
via min-max, then produces a weighted sum as the final score.

The orchestrator implements the Stage A → Stage B pipeline documented in
docs/VISION_v3.md §5:

  Retrieval (pre_scorer + enrichment) → top_n candidates
  Ranking   (ensemble)                 → top_k signals for delivery
"""
from __future__ import annotations

import logging

from hedwig.config import load_algorithm_config
from hedwig.engine.ensemble.base import minmax_normalize
from hedwig.models import RawPost

logger = logging.getLogger(__name__)


def _registry() -> dict:
    """Map component name → builder lambda for lazy construction.

    We avoid importing LLM-dependent components until the moment they are
    enabled, keeping the base path lightweight.
    """
    return {
        "llm_judge": lambda: _import_and_build("hedwig.engine.ensemble.llm_judge", "LLMJudge"),
        "ltr": lambda: _import_and_build("hedwig.engine.ensemble.ltr", "LTRRanker"),
        "content_based": lambda: _import_and_build("hedwig.engine.ensemble.content", "ContentRanker"),
        "popularity_prior": lambda: _import_and_build("hedwig.engine.ensemble.popularity", "PopularityRanker"),
        "bandit": lambda: _import_and_build("hedwig.engine.ensemble.bandit", "BanditRanker"),
    }


def _import_and_build(module: str, cls_name: str):
    try:
        mod = __import__(module, fromlist=[cls_name])
        cls = getattr(mod, cls_name)
        return cls()
    except Exception as e:
        logger.warning("ensemble component %s/%s not buildable: %s", module, cls_name, e)
        return None


def _enabled_components(cfg: dict) -> dict[str, dict]:
    return {
        name: spec
        for name, spec in (cfg.get("ranking", {}).get("components", {}) or {}).items()
        if isinstance(spec, dict) and spec.get("enabled")
    }


def _is_topk_only(spec: dict) -> bool:
    """Components with ``apply_to: top_k`` are reserved for the rerank pass."""
    return str(spec.get("apply_to", "")).strip().lower() == "top_k"


async def _score_component(
    name: str,
    comp: object,
    candidates: list[RawPost],
    context: dict | None,
) -> list[float]:
    try:
        raw = await comp.score_posts(candidates, context=context)
    except Exception as e:
        logger.warning("Ensemble component %s failed: %s", name, e)
        raw = [0.0] * len(candidates)
    if len(raw) != len(candidates):
        logger.warning(
            "Ensemble component %s length mismatch %d vs %d; padding",
            name, len(raw), len(candidates),
        )
        raw = list(raw)[: len(candidates)] + [0.0] * max(0, len(candidates) - len(raw))
    return raw


async def rank_with_ensemble(
    candidates: list[RawPost],
    context: dict | None = None,
    return_state: bool = False,
    top_k: int | None = None,
):
    """Run cheap components on all candidates, then rerank top_k with expensive
    (``apply_to: top_k``) components like the LLM judge.

    Returns a list of (post, final_score, component_scores) tuples, sorted
    by final_score descending. When ``return_state=True``, also returns the
    component instances so callers can introspect (e.g., ``LLMJudge.last_scored``).
    """
    if not candidates:
        return ([], {}) if return_state else []

    cfg = load_algorithm_config()
    enabled = _enabled_components(cfg)
    if not enabled:
        fallback = [(p, 0.5, {}) for p in candidates]
        return (fallback, {}) if return_state else fallback

    if top_k is None:
        top_k = int(cfg.get("ranking", {}).get("top_k", 30))

    cheap: dict[str, dict] = {n: s for n, s in enabled.items() if not _is_topk_only(s)}
    expensive: dict[str, dict] = {n: s for n, s in enabled.items() if _is_topk_only(s)}

    registry = _registry()
    component_instances: dict[str, object] = {}
    raw_cheap: dict[str, list[float]] = {}

    for name, spec in cheap.items():
        builder = registry.get(name)
        if builder is None:
            logger.warning("Ensemble: unknown component %s (skipping)", name)
            continue
        comp = builder()
        if comp is None:
            continue
        component_instances[name] = comp
        raw_cheap[name] = await _score_component(name, comp, candidates, context)

    if not raw_cheap and not expensive:
        fallback = [(p, 0.5, {}) for p in candidates]
        return (fallback, component_instances) if return_state else fallback

    # Fuse cheap-component scores to order the full candidate pool
    def _fuse(idx_range: range, weight_map: dict[str, float], norm_map: dict[str, list[float]]):
        total_w = sum(weight_map.values()) or 1.0
        out: list[float] = []
        for i in idx_range:
            s = 0.0
            for n, norm in norm_map.items():
                s += (weight_map[n] / total_w) * norm[i]
            out.append(max(0.0, min(1.0, s)))
        return out

    cheap_weights = {n: float(cheap[n].get("weight", 0.0)) for n in raw_cheap}
    cheap_normalized = {n: minmax_normalize(raw) for n, raw in raw_cheap.items()}
    cheap_final = (
        _fuse(range(len(candidates)), cheap_weights, cheap_normalized)
        if cheap_normalized else [0.5] * len(candidates)
    )

    order = sorted(range(len(candidates)), key=lambda i: cheap_final[i], reverse=True)
    top_indices = order[:top_k]
    top_candidates = [candidates[i] for i in top_indices]

    # Run expensive components only on the shortlist
    raw_expensive: dict[str, list[float]] = {}
    for name, spec in expensive.items():
        builder = registry.get(name)
        if builder is None:
            continue
        comp = builder()
        if comp is None:
            continue
        component_instances[name] = comp
        raw_expensive[name] = await _score_component(name, comp, top_candidates, context)

    # Blend expensive scores into the top_k only; outside top_k we keep cheap score.
    exp_weights = {n: float(expensive[n].get("weight", 0.0)) for n in raw_expensive}
    exp_normalized = {n: minmax_normalize(raw) for n, raw in raw_expensive.items()}

    final_by_idx: dict[int, float] = {i: cheap_final[i] for i in range(len(candidates))}
    if exp_normalized:
        # Re-normalize weights using cheap + expensive
        all_weights = {**cheap_weights, **exp_weights}
        total_w = sum(all_weights.values()) or 1.0
        for rank, i in enumerate(top_indices):
            s = 0.0
            for n, norm in cheap_normalized.items():
                s += (cheap_weights[n] / total_w) * norm[i]
            for n, norm in exp_normalized.items():
                s += (exp_weights[n] / total_w) * norm[rank]
            final_by_idx[i] = max(0.0, min(1.0, s))

    # Per-candidate breakdown (cheap for all; expensive only for top_k)
    enriched: list[tuple[RawPost, float, dict]] = []
    for i in range(len(candidates)):
        breakdown: dict[str, float] = {n: raw_cheap[n][i] for n in raw_cheap}
        if i in top_indices and raw_expensive:
            rank = top_indices.index(i)
            for n in raw_expensive:
                breakdown[n] = raw_expensive[n][rank]
        enriched.append((candidates[i], final_by_idx[i], breakdown))
    enriched.sort(key=lambda t: t[1], reverse=True)
    return (enriched, component_instances) if return_state else enriched


async def rank_and_build_signals(
    candidates: list[RawPost],
    criteria_keywords: list[str],
):
    """Run the ensemble on an already-retrieved candidate set.

    The caller is responsible for Stage A (pre_filter + history enrichment).
    This function runs Stage B only — ranking + score fusion + ScoredSignal
    construction. Use this from main.py after normalize_and_prescore so
    history enrichment is preserved.

    Returns: ``(list[ScoredSignal], stats dict)``
    """
    from hedwig.models import ScoredSignal, UrgencyLevel

    cfg = load_algorithm_config()
    top_k = int(cfg.get("ranking", {}).get("top_k", 30))
    top_n = int(cfg.get("retrieval", {}).get("top_n", 200))

    # Cap candidate list at top_n (caller already ordered; be defensive)
    retrieval_candidates = candidates[:top_n]

    context = {"criteria_keywords": criteria_keywords}
    ranked, components_state = await rank_with_ensemble(
        retrieval_candidates, context=context, return_state=True, top_k=top_k,
    )
    top_ranked = ranked[:top_k]

    llm_cache = {}
    llm_inst = components_state.get("llm_judge")
    if llm_inst is not None and getattr(llm_inst, "last_scored", None):
        llm_cache = llm_inst.last_scored

    signals: list[ScoredSignal] = []
    for post, final_score, component_scores in top_ranked:
        if post.external_id in llm_cache:
            base: ScoredSignal = llm_cache[post.external_id]
            base.relevance_score = final_score
            signals.append(base)
            continue

        if final_score >= 0.7:
            urgency = UrgencyLevel.ALERT
        elif final_score >= 0.4:
            urgency = UrgencyLevel.DIGEST
        else:
            urgency = UrgencyLevel.SKIP

        breakdown = ", ".join(f"{k}={v:.2f}" for k, v in sorted(component_scores.items()))
        signals.append(ScoredSignal(
            raw=post,
            relevance_score=final_score,
            urgency=urgency,
            why_relevant=f"Ensemble score {final_score:.2f}. Contributions: {breakdown}",
            devils_advocate="(ensemble path — no LLM counter-perspective; enable llm_judge for critique)",
        ))

    stats = {
        "input": len(candidates),
        "retrieval_kept": len(retrieval_candidates),
        "ranking_kept": len(top_ranked),
        "components_used": list(components_state.keys()),
        "top_n": top_n,
        "top_k": top_k,
        "signals_produced": len(signals),
    }
    return signals, stats


async def run_two_stage_as_signals(
    raw_posts: list[RawPost],
    criteria_keywords: list[str],
):
    """Full flow for callers that have NOT pre-filtered posts.

    Runs retrieval (pre_filter + enrich) then ranking. Use
    ``rank_and_build_signals`` when you've already done the retrieval stage.
    """
    from hedwig.engine.pre_scorer import pre_filter
    from hedwig.engine.absorbed.last30days import enrich_score

    cfg = load_algorithm_config()
    threshold = float(cfg.get("retrieval", {}).get("threshold", 0.10))
    top_n = int(cfg.get("retrieval", {}).get("top_n", 200))

    prefiltered = pre_filter(raw_posts, criteria_keywords, threshold=threshold)
    enriched: list[tuple[RawPost, float]] = []
    for post, score in prefiltered:
        enriched.append(
            (post, enrich_score(post, base_score=score, same_cycle_posts=[p for p, _ in prefiltered]))
        )
    enriched.sort(key=lambda t: t[1], reverse=True)
    retrieval_candidates = [p for p, _ in enriched[:top_n]]
    return await rank_and_build_signals(retrieval_candidates, criteria_keywords)


async def run_two_stage(
    raw_posts: list[RawPost],
    criteria_keywords: list[str],
) -> tuple[list[tuple[RawPost, float, dict]], dict]:
    """Orchestrate Stage A (retrieval) → Stage B (ensemble ranking).

    Returns:
        (ranked_list, stats_dict)
        ranked_list: list of (post, score, component_breakdown) for top_k
        stats_dict: {
          "input": N, "retrieval_kept": M, "ranking_kept": K,
          "components_used": [names], "top_n": cfg_top_n, "top_k": cfg_top_k
        }
    """
    from hedwig.engine.pre_scorer import pre_filter
    from hedwig.engine.absorbed.last30days import enrich_score

    cfg = load_algorithm_config()
    top_n = int(cfg.get("retrieval", {}).get("top_n", 200))
    top_k = int(cfg.get("ranking", {}).get("top_k", 30))

    # Stage A — cheap retrieval
    prefiltered = pre_filter(raw_posts, criteria_keywords, threshold=0.10)
    # Apply last30days-style enrichment without history (same cycle only)
    enriched: list[tuple[RawPost, float]] = []
    for post, score in prefiltered:
        enriched.append(
            (post, enrich_score(post, base_score=score, same_cycle_posts=[p for p, _ in prefiltered]))
        )
    enriched.sort(key=lambda t: t[1], reverse=True)
    retrieval_candidates = [p for p, _ in enriched[:top_n]]

    # Stage B — ensemble ranking
    context = {"criteria_keywords": criteria_keywords}
    ranked = await rank_with_ensemble(retrieval_candidates, context=context)
    top_ranked = ranked[:top_k]

    stats = {
        "input": len(raw_posts),
        "retrieval_kept": len(retrieval_candidates),
        "ranking_kept": len(top_ranked),
        "components_used": list(_enabled_components(cfg).keys()),
        "top_n": top_n,
        "top_k": top_k,
    }
    return top_ranked, stats
