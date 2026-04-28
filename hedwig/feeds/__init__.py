"""feeds.yaml loader + override merge (Phase 7 S4).

Each feed is a (criteria + algorithm) overlay on the base configs. Calls
that need a "feed-aware" view of criteria/algorithm should go through
:func:`get_feed_config`.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

FEEDS_PATH = Path(__file__).resolve().parent.parent.parent / "feeds.yaml"


def load_feeds() -> dict:
    if not FEEDS_PATH.exists():
        return {"version": 1, "default_feed": "default",
                "feeds": [{"id": "default", "name": "메인 피드"}]}
    try:
        return yaml.safe_load(FEEDS_PATH.read_text()) or {}
    except Exception as e:
        logger.warning("feeds.yaml parse failed: %s", e)
        return {}


def list_feeds() -> list[dict]:
    return list(load_feeds().get("feeds") or [])


def find_feed(feed_id: str) -> dict | None:
    for f in list_feeds():
        if f.get("id") == feed_id:
            return f
    return None


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursive dict merge — overlay wins for scalar values, recurses
    on nested dicts. Lists are replaced wholesale (not extended)."""
    out = copy.deepcopy(base)
    for k, v in (overlay or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def get_feed_config(feed_id: str = "default") -> dict:
    """Compose the effective criteria + algorithm for a feed.

    Returns:
        {
          "feed": {id, name, description},
          "criteria": <merged criteria.yaml>,
          "algorithm": <merged algorithm.yaml>,
        }
    """
    from hedwig.config import load_algorithm_config, load_criteria
    feed = find_feed(feed_id) or find_feed("default") or {"id": feed_id}
    base_crit = load_criteria() or {}
    base_algo = load_algorithm_config() or {}
    merged_crit = _deep_merge(base_crit, feed.get("criteria_overrides") or {})
    merged_algo = _deep_merge(base_algo, feed.get("algorithm_overrides") or {})
    return {"feed": feed, "criteria": merged_crit, "algorithm": merged_algo}
