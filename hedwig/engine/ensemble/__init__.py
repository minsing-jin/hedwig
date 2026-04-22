"""Hybrid Ensemble — user-owned recommendation algorithm.

Reads algorithm.yaml and composes ranking scores from multiple components.
LLM is one component (top-K judge), not the entire engine.

Components (Phase 3 onwards):
  - llm_judge      : qualitative relevance + devil's advocate (top-K only)
  - ltr            : LightGBM learning-to-rank on past feedback features
  - content_based  : embedding similarity (criteria × post)
  - popularity     : source authority × recency prior
  - bandit         : Thompson sampling for exploration

Meta-Evolution mutates weights/features/structure. See evolution/meta.py (Phase 4).

This module is currently a scaffold — see docs/VISION_v3.md section 8 for the
target architecture and Phase 3 implementation plan.
"""
from __future__ import annotations

from hedwig.config import load_algorithm_config


def get_enabled_components(stage: str) -> dict[str, dict]:
    """Return {name: config} for enabled components in the given stage.

    Args:
        stage: "retrieval" or "ranking"
    """
    cfg = load_algorithm_config()
    components = cfg.get(stage, {}).get("components", {}) or {}
    return {
        name: spec
        for name, spec in components.items()
        if isinstance(spec, dict) and spec.get("enabled")
    }


def get_ensemble_weights(stage: str) -> dict[str, float]:
    """Return {name: weight} for enabled components, normalized to sum 1.0."""
    enabled = get_enabled_components(stage)
    raw = {name: float(spec.get("weight", 0.0)) for name, spec in enabled.items()}
    total = sum(raw.values()) or 1.0
    return {name: w / total for name, w in raw.items()}
