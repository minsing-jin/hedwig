"""IPS (Inverse Propensity Score) debias correction (S8.4).

Major platforms naturally dominate the candidate pool because they post
more, not because they're better. IPS reweights each candidate by
1/sqrt(propensity) where propensity = platform's share of recent
exposures. Disabled by default; opt in via algorithm.yaml:

    ranking:
      ips_debias:
        enabled: true
        lookback_days: 14

Reference: "Recommendations as Treatments" (Schnabel et al, 2016).
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from hedwig.models import RawPost


def compute_platform_propensity(lookback_days: int = 14) -> dict[str, float]:
    """Return {platform: propensity ∈ (0, 1]}. Sum of values ≈ 1."""
    try:
        from hedwig.storage import get_recent_signals
    except ImportError:
        return {}
    rows = get_recent_signals(days=lookback_days) or []
    if not rows:
        return {}
    counts = Counter(r.get("platform", "") for r in rows if r.get("platform"))
    total = sum(counts.values()) or 1
    return {p: max(0.01, c / total) for p, c in counts.items()}


def apply_ips_correction(
    final_scores: list[float],
    candidates: list[RawPost],
    propensity: dict[str, float] | None = None,
    *,
    epsilon: float = 0.05,
) -> list[float]:
    """Multiply each score by 1/sqrt(p), then min-max normalize so the
    resulting list still lives in [0, 1]. epsilon clamps tiny propensities
    to avoid blowing up scores for one-off platforms."""
    if not final_scores or not candidates:
        return list(final_scores)
    if propensity is None:
        propensity = compute_platform_propensity()
    if not propensity:
        return list(final_scores)

    weights = [
        1.0 / math.sqrt(max(epsilon, propensity.get(c.platform.value, epsilon)))
        for c in candidates
    ]
    adjusted = [s * w for s, w in zip(final_scores, weights)]
    lo, hi = min(adjusted), max(adjusted)
    if hi - lo < 1e-9:
        return [0.5] * len(adjusted)
    return [(a - lo) / (hi - lo) for a in adjusted]
