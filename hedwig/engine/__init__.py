"""Hedwig Engine — the recommendation core.

This package is the **extraction target** for a future `hedwig-engine`
standalone library. It must not import from:
  - hedwig.dashboard (UI)
  - hedwig.saas (billing, auth)
  - hedwig.delivery (Slack/Discord/email — acceptable to pass in as callbacks)
  - hedwig.native (desktop)

When these rules are broken, Phase 6 library extraction becomes harder.
See docs/phase_reports/phase6.md for the extraction plan.

Public API (stable for v3):
    from hedwig.engine import (
        pre_score, pre_filter,                # engine.pre_scorer
        score_posts,                           # engine.scorer   (LLM)
        generate_daily_briefing,               # engine.briefing
        normalize_content, normalize_batch,    # engine.normalizer
        rank_with_ensemble, run_two_stage,     # engine.ensemble
        critical_score, filter_critical,       # engine.critical
        trace_signal,                          # engine.trace
        enrich_score,                          # engine.absorbed.last30days
    )
"""
from __future__ import annotations

from hedwig.engine.pre_scorer import pre_filter, pre_score  # noqa: F401
from hedwig.engine.normalizer import normalize_batch, normalize_content  # noqa: F401

# LLM-dependent symbols load lazily to keep import-time cost low.
_LAZY_NAMES = {
    "score_posts": ("hedwig.engine.scorer", "score_posts"),
    "generate_daily_briefing": ("hedwig.engine.briefing", "generate_daily_briefing"),
    "generate_weekly_briefing": ("hedwig.engine.briefing", "generate_weekly_briefing"),
    "rank_with_ensemble": ("hedwig.engine.ensemble.combine", "rank_with_ensemble"),
    "rank_and_build_signals": ("hedwig.engine.ensemble.combine", "rank_and_build_signals"),
    "run_two_stage": ("hedwig.engine.ensemble.combine", "run_two_stage"),
    "run_two_stage_as_signals": ("hedwig.engine.ensemble.combine", "run_two_stage_as_signals"),
    "critical_score": ("hedwig.engine.critical", "critical_score"),
    "filter_critical": ("hedwig.engine.critical", "filter_critical"),
    "trace_signal": ("hedwig.engine.trace", "trace_signal"),
    "enrich_score": ("hedwig.engine.absorbed.last30days", "enrich_score"),
}


def __getattr__(name: str):
    target = _LAZY_NAMES.get(name)
    if not target:
        raise AttributeError(f"module hedwig.engine has no attribute {name!r}")
    module_path, attr = target
    from importlib import import_module
    mod = import_module(module_path)
    return getattr(mod, attr)


def __dir__() -> list[str]:
    return sorted(list(_LAZY_NAMES) + [
        "pre_filter", "pre_score", "normalize_batch", "normalize_content",
    ])
