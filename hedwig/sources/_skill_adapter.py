"""Claude Skill → Hedwig Source adapter (v3, Phase 1 + post-Phase completion).

Loads a Claude Skill repository (e.g. mvanhorn/last30days-skill) and uses
its collect logic inside Hedwig's pipeline.

Discovery contract — the adapter looks for, in order:
  1. ``{skill_path}/<entry_module>.py`` exposing ``async def collect(limit=...)``
     returning a list of dicts.
  2. ``{skill_path}/SKILL.md`` with a matching ``entry_module`` (metadata only).
  3. ``{skill_path}/{entry_module}/__init__.py`` (package form).

If the returned dicts don't match RawPost's fields, provide ``field_map``
to translate.

Absorption Gradient Level 2: the skill is loaded at runtime (white-box use)
rather than reimplemented.
"""
from __future__ import annotations

import asyncio
import importlib.util
import inspect
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hedwig.models import Platform, RawPost

logger = logging.getLogger(__name__)


DEFAULT_FIELD_MAP = {
    "external_id": "id",
    "title": "title",
    "url": "url",
    "content": "content",
    "author": "author",
    "score": "score",
    "comments_count": "comments_count",
    "published_at": "published_at",
}


@dataclass
class SkillSourceAdapter:
    """Load a cloned Claude Skill directory and invoke its ``collect`` function.

    Attributes:
        skill_path: Local filesystem path to the cloned skill repo.
        entry_module: Python module within the skill. Defaults to ``collect``.
        platform: Tag applied to fetched posts.
        field_map: How to translate skill output dict keys to RawPost fields.
    """

    skill_path: Path
    entry_module: str = "collect"
    platform: Platform = Platform.CUSTOM
    field_map: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_FIELD_MAP))

    def _load_callable(self):
        """Import the skill's entry module and return its ``collect`` callable."""
        path = Path(self.skill_path)
        candidates = [
            path / f"{self.entry_module}.py",
            path / self.entry_module / "__init__.py",
        ]
        module_file = next((c for c in candidates if c.exists()), None)
        if module_file is None:
            raise FileNotFoundError(
                f"Skill adapter: no {self.entry_module}[.py|/] under {path}"
            )

        module_name = f"hedwig_skill_{path.name}_{self.entry_module}"
        spec = importlib.util.spec_from_file_location(module_name, str(module_file))
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot build import spec for {module_file}")
        module = importlib.util.module_from_spec(spec)
        # Allow the skill to do its own relative imports
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        fn = getattr(module, "collect", None) or getattr(module, "fetch", None)
        if fn is None:
            raise AttributeError(
                f"Skill {path} {self.entry_module} exposes neither 'collect' nor 'fetch'"
            )
        return fn

    async def fetch(self, limit: int = 20, **kwargs: Any) -> list[RawPost]:
        try:
            fn = self._load_callable()
        except Exception as e:
            logger.warning("SkillSourceAdapter load failed (%s): %s", self.skill_path, e)
            return []

        try:
            if inspect.iscoroutinefunction(fn):
                raw = await fn(limit=limit, **kwargs)
            else:
                raw = await asyncio.to_thread(fn, limit=limit, **kwargs)
        except Exception as e:
            logger.warning("SkillSourceAdapter call failed: %s", e)
            return []

        if not isinstance(raw, list):
            logger.warning("SkillSourceAdapter: expected list, got %s", type(raw).__name__)
            return []

        posts: list[RawPost] = []
        for item in raw[:limit]:
            if isinstance(item, RawPost):
                posts.append(item)
                continue
            if not isinstance(item, dict):
                continue
            posts.append(self._to_raw_post(item))
        return posts

    def _to_raw_post(self, item: dict) -> RawPost:
        def _get(field: str, default: Any = "") -> Any:
            key = self.field_map.get(field)
            if not key:
                return default
            value = item.get(key, default)
            return default if value is None else value

        return RawPost(
            platform=self.platform,
            external_id=str(_get("external_id") or _get("url") or item.get("title", ""))[:200],
            title=str(_get("title") or "")[:500],
            url=str(_get("url") or ""),
            content=str(_get("content") or "")[:5000],
            author=str(_get("author") or ""),
            score=int(_get("score", 0) or 0),
            comments_count=int(_get("comments_count", 0) or 0),
            published_at=_parse_datetime(_get("published_at")),
            extra={"skill": str(self.skill_path), "entry": self.entry_module},
        )

    @classmethod
    def metadata(cls) -> dict:
        return {
            "id": "skill_generic",
            "name": "Generic Claude Skill Adapter",
            "description": "Loads a cloned Claude Skill directory and invokes its collect() function",
            "absorption_level": 2,
        }


def _parse_datetime(value: Any) -> datetime:
    if not value:
        return datetime.now(tz=timezone.utc)
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(tz=timezone.utc)
