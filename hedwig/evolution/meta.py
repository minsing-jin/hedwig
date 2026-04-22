"""Meta-Evolution — autoresearch-pattern self-improvement on algorithm.yaml.

Every `cadence_days` the engine:
  1. Measures baseline fitness of current algorithm.yaml
  2. Generates N mutation candidates (weight perturb / feature toggle / etc.)
  3. Runs each candidate through sandbox.run_sandbox (shadow mode)
  4. Adopts the winner if fitness improvement > adoption_threshold
  5. Records every decision in algorithm_log.jsonl + algorithm_versions

See docs/VISION_v3.md §9 for the full specification. This is the most
novel layer in Hedwig: the recommendation algorithm *itself* is under
evolutionary pressure, not just the criteria.
"""
from __future__ import annotations

import copy
import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hedwig.config import ALGORITHM_LOG_PATH, ALGORITHM_PATH, load_algorithm_config

logger = logging.getLogger(__name__)


MUTATION_STRATEGIES = [
    "weight_perturbation",
    "feature_toggle",
    "structural_change",
    "feature_suggest_from_papers",
]


# ---------------------------------------------------------------------------
# Mutation strategies
# ---------------------------------------------------------------------------

def _mutate_weight_perturbation(cfg: dict, magnitude: float = 0.2) -> dict:
    """Randomly jitter enabled ranking component weights by ±magnitude."""
    out = copy.deepcopy(cfg)
    comps = out.get("ranking", {}).get("components", {}) or {}
    for name, spec in comps.items():
        if not spec.get("enabled"):
            continue
        current = float(spec.get("weight", 0.0))
        jitter = random.uniform(-magnitude, magnitude) * max(current, 0.1)
        spec["weight"] = max(0.01, round(current + jitter, 4))
    return out


def _mutate_feature_toggle(cfg: dict) -> dict:
    """Flip the enabled state of one random ranking component."""
    out = copy.deepcopy(cfg)
    comps = out.get("ranking", {}).get("components", {}) or {}
    if not comps:
        return out
    target = random.choice(list(comps.keys()))
    comps[target]["enabled"] = not bool(comps[target].get("enabled"))
    # If the toggle turned something on with weight 0, give it a small weight
    if comps[target].get("enabled") and not comps[target].get("weight"):
        comps[target]["weight"] = 0.1
    return out


def _mutate_structural_change(cfg: dict) -> dict:
    """Adjust pipeline shape: top_n / top_k."""
    out = copy.deepcopy(cfg)
    retr = out.setdefault("retrieval", {})
    rank = out.setdefault("ranking", {})
    current_n = int(retr.get("top_n", 200))
    current_k = int(rank.get("top_k", 30))
    retr["top_n"] = max(50, current_n + random.choice([-50, 50, 100, -100]))
    rank["top_k"] = max(10, current_k + random.choice([-10, 10, 20, -5]))
    return out


def _mutate_feature_suggest_from_papers(cfg: dict) -> dict:
    """Use an LLM to propose a NEW ranking feature, drawing from the
    absorption backlog of recent rec-system papers.

    The proposal is added to the ``ltr.features`` list and the ``ltr``
    component is enabled with a small weight so Meta-Evolution's shadow
    mode can stress-test it.

    Silent no-op when no OpenAI key is available.
    """
    import os
    from hedwig.config import OPENAI_API_KEY
    if not OPENAI_API_KEY:
        return cfg

    # Pull a few recent absorption candidates (arxiv_recsys signals) for context
    backlog_hint = ""
    try:
        from hedwig.storage import get_recent_signals
        recents = get_recent_signals(days=14) or []
        papers = [
            r for r in recents
            if str(r.get("title", "")).startswith("[RECSYS]")
        ][:6]
        backlog_hint = "\n".join(
            f"- {p.get('title', '')}: {p.get('content', '')[:200]}"
            for p in papers
        )
    except Exception:
        backlog_hint = ""

    try:
        from openai import OpenAI
    except ImportError:
        return cfg

    client = OpenAI(api_key=OPENAI_API_KEY)
    current_features = list(
        cfg.get("ranking", {}).get("components", {}).get("ltr", {}).get("features") or []
    )
    prompt = f"""You are Hedwig's Meta-Evolution feature proposer.

Current LTR feature set:
{chr(10).join('- ' + f for f in current_features)}

Recent rec-system papers in the absorption backlog (optional hints):
{backlog_hint or '(no papers collected yet)'}

Propose ONE new ranking feature name (snake_case, < 40 chars) that is
NOT already in the list and that is plausibly computable from the data
Hedwig has (posts with title/content/author/score/published_at/platform +
feedback history). Respond with JSON only: {{"feature": "name"}}.
"""
    try:
        resp = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL_FAST", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=80,
            response_format={"type": "json_object"},
        )
        import json as _json
        data = _json.loads(resp.choices[0].message.content or "{}")
        feature = str(data.get("feature", "")).strip()
    except Exception as e:
        logger.warning("feature_suggest_from_papers LLM failed: %s", e)
        return cfg

    if not feature or feature in current_features:
        return cfg

    out = copy.deepcopy(cfg)
    ltr_spec = out.setdefault("ranking", {}).setdefault("components", {}).setdefault("ltr", {
        "enabled": False, "weight": 0.0, "features": [],
    })
    ltr_spec.setdefault("features", []).append(feature)
    # Enable ltr with a small probe weight so shadow mode can evaluate it
    ltr_spec["enabled"] = True
    ltr_spec["weight"] = max(0.1, float(ltr_spec.get("weight", 0.0)))
    return out


def generate_candidate(baseline: dict, strategy: str | None = None) -> tuple[dict, str]:
    """Produce one mutation candidate, chosen strategy or random."""
    strategy = strategy or random.choice(MUTATION_STRATEGIES)
    if strategy == "weight_perturbation":
        return _mutate_weight_perturbation(baseline), strategy
    if strategy == "feature_toggle":
        return _mutate_feature_toggle(baseline), strategy
    if strategy == "structural_change":
        return _mutate_structural_change(baseline), strategy
    if strategy == "feature_suggest_from_papers":
        return _mutate_feature_suggest_from_papers(baseline), strategy
    return _mutate_weight_perturbation(baseline), "weight_perturbation"


# ---------------------------------------------------------------------------
# Shadow evaluation + adoption
# ---------------------------------------------------------------------------

def _append_audit_log(entry: dict) -> None:
    try:
        ALGORITHM_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(ALGORITHM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning("algorithm_log write failed: %s", e)


def _bump_version(cfg: dict) -> int:
    return int(cfg.get("version", 0)) + 1


def _yaml_diff(before: dict, after: dict) -> str:
    import difflib as _difflib
    a = yaml.safe_dump(before, allow_unicode=True, sort_keys=False).splitlines()
    b = yaml.safe_dump(after, allow_unicode=True, sort_keys=False).splitlines()
    return "\n".join(_difflib.unified_diff(
        a, b, fromfile="before", tofile="after", lineterm="",
    ))


def adopt(new_cfg: dict, reason: str, fitness_delta: float) -> dict:
    """Persist ``new_cfg`` as the active algorithm.yaml and record a diff-backed
    ``algorithm_versions`` row so the Evolution timeline can show exactly what
    changed between versions.
    """
    # Snapshot the current yaml so we can diff against it
    try:
        from hedwig.config import load_algorithm_config
        before_cfg = load_algorithm_config()
    except Exception:
        before_cfg = {}

    new_cfg = copy.deepcopy(new_cfg)
    new_cfg["version"] = _bump_version(new_cfg)
    new_cfg["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    new_cfg["origin"] = reason

    Path(ALGORITHM_PATH).write_text(
        yaml.safe_dump(new_cfg, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    diff = _yaml_diff(before_cfg, new_cfg)

    try:
        from hedwig.storage import save_algorithm_version
        save_algorithm_version(
            version=new_cfg["version"],
            config=new_cfg,
            created_by="meta_evolution",
            origin=reason,
            fitness_score=fitness_delta,
            diff_from_previous=diff,
        )
    except Exception as e:
        logger.warning("algorithm_versions insert failed: %s", e)

    _append_audit_log({
        "event": "adopt",
        "version": new_cfg["version"],
        "reason": reason,
        "fitness_delta": fitness_delta,
        "diff": diff,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    })
    return new_cfg


def run_meta_cycle(
    n_candidates: int = 3,
    strategies: list[str] | None = None,
    force: bool = False,
) -> dict:
    """One cycle of mutate → shadow-evaluate → adopt/reject.

    Args:
        n_candidates: how many mutations to generate
        strategies: optional explicit list of strategy names to cycle through
        force: if True, run even when meta_evolution.enabled is false

    Returns:
        {
          "adopted": bool,
          "chosen_strategy": str | None,
          "fitness_delta": float,
          "candidates": [ {strategy, fitness_delta, recommend} ]
        }
    """
    from hedwig.evolution.sandbox import run_sandbox

    baseline_cfg = load_algorithm_config()
    meta_cfg = baseline_cfg.get("meta_evolution", {}) or {}
    if not force and not meta_cfg.get("enabled", False):
        _append_audit_log({
            "event": "skipped",
            "reason": "meta_evolution.enabled=false",
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        })
        return {"adopted": False, "reason": "disabled", "candidates": []}

    adoption_threshold = float(baseline_cfg.get("fitness", {}).get("adoption_threshold", 0.05))

    strategies_seq = strategies or MUTATION_STRATEGIES
    candidates_info: list[dict] = []
    best = None
    best_delta = 0.0

    for i in range(n_candidates):
        strat = strategies_seq[i % len(strategies_seq)]
        cand_cfg, used_strat = generate_candidate(baseline_cfg, strategy=strat)
        sandbox = run_sandbox(cand_cfg, baseline_cfg)
        candidates_info.append({
            "strategy": used_strat,
            "fitness_delta": sandbox["delta"],
            "recommend": sandbox["recommend"],
        })
        _append_audit_log({
            "event": "candidate",
            "strategy": used_strat,
            "delta": sandbox["delta"],
            "recommend": sandbox["recommend"],
            "ts": datetime.now(tz=timezone.utc).isoformat(),
        })
        if sandbox["delta"] > best_delta:
            best = (cand_cfg, used_strat, sandbox["delta"])
            best_delta = sandbox["delta"]

    if best and best[2] >= adoption_threshold:
        adopted_cfg = adopt(best[0], reason=f"meta_evolution:{best[1]}", fitness_delta=best[2])
        return {
            "adopted": True,
            "chosen_strategy": best[1],
            "fitness_delta": best[2],
            "new_version": adopted_cfg["version"],
            "candidates": candidates_info,
        }

    _append_audit_log({
        "event": "no_adoption",
        "best_delta": best_delta,
        "threshold": adoption_threshold,
        "ts": datetime.now(tz=timezone.utc).isoformat(),
    })
    return {
        "adopted": False,
        "chosen_strategy": None,
        "fitness_delta": best_delta,
        "threshold": adoption_threshold,
        "candidates": candidates_info,
    }
