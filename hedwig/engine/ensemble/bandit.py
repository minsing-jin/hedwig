"""Thompson-sampling bandit over platforms — exploration component.

Maintains per-platform Beta(α, β) posteriors driven by historical
upvote/downvote feedback on signals from each platform. Each call draws
a sample from each posterior and scores candidate posts accordingly.
This reserves a slice of the ranking budget for surprising-but-plausible
sources we haven't learned to fully trust yet.

Pure Python — uses `random.betavariate`, no numpy dependency.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from hedwig.models import RawPost


def _load_platform_posteriors(days: int = 60) -> dict[str, tuple[float, float]]:
    """Aggregate per-platform Beta(α, β) from historical feedback."""
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    platform_counts: dict[str, list[int]] = {}

    try:
        from hedwig.storage import get_feedback_since, get_signal_platforms
    except ImportError:
        return {}

    try:
        rows = get_feedback_since(since=since) or []
    except Exception:
        rows = []

    signal_ids = [str(r.get("signal_id", "")) for r in rows if r.get("signal_id")]
    platform_map = get_signal_platforms(signal_ids) if signal_ids else {}

    for r in rows:
        platform = platform_map.get(str(r.get("signal_id", "")), "")
        if not platform:
            continue
        pc = platform_counts.setdefault(platform, [0, 0])
        if r.get("vote") == "up":
            pc[0] += 1
        elif r.get("vote") == "down":
            pc[1] += 1

    # Beta(α, β) starts at Beta(1, 1) (uniform prior)
    return {p: (1 + up, 1 + down) for p, (up, down) in platform_counts.items()}


class BanditRanker:
    """Thompson-sampling bandit over platforms. Reads the exploration_rate
    from ``algorithm.yaml.ranking.components.bandit.exploration_rate`` so the
    user (and meta-evolution) can tune it."""

    name = "bandit"

    def __init__(self, exploration_rate: float | None = None) -> None:
        if exploration_rate is None:
            exploration_rate = self._load_exploration_rate()
        self.exploration_rate = float(exploration_rate)

    @staticmethod
    def _load_exploration_rate() -> float:
        try:
            from hedwig.config import load_algorithm_config
            cfg = load_algorithm_config()
            val = (
                cfg.get("ranking", {})
                .get("components", {})
                .get("bandit", {})
                .get("exploration_rate")
            )
            if val is not None:
                return float(val)
        except Exception:
            pass
        return 0.1

    async def score_posts(self, posts: list[RawPost], context: dict | None = None) -> list[float]:
        if not posts:
            return []
        posteriors = (context or {}).get("platform_posteriors") or _load_platform_posteriors()

        samples = {
            p: random.betavariate(max(1e-3, a), max(1e-3, b))
            for p, (a, b) in posteriors.items()
        }
        out = []
        for post in posts:
            base = samples.get(post.platform.value, 0.5)
            if random.random() < self.exploration_rate:
                out.append(min(1.0, base + 0.2))
            else:
                out.append(base)
        return out
