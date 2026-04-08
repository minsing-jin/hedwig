"""
User Memory Store — long-horizon preference model.

Accumulates weekly snapshots of user preferences, taste trajectory,
confirmed interests, and rejected topics. Used by the weekly evolution
loop to make better decisions over time.

Storage: local JSONL file + optional Supabase sync.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from hedwig.models import UserMemory

logger = logging.getLogger(__name__)


class MemoryStore:
    """Persistent user preference memory across evolution cycles."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or Path("user_memory.jsonl")

    def save_snapshot(self, memory: UserMemory):
        """Append a weekly memory snapshot."""
        with open(self._path, "a") as f:
            f.write(memory.model_dump_json() + "\n")
        logger.info(f"Memory snapshot saved for week {memory.snapshot_week}")

    def get_latest(self) -> Optional[UserMemory]:
        """Get the most recent memory snapshot."""
        if not self._path.exists():
            return None
        lines = self._path.read_text().strip().split("\n")
        if not lines or not lines[-1].strip():
            return None
        try:
            data = json.loads(lines[-1])
            return UserMemory(**data)
        except (json.JSONDecodeError, Exception):
            return None

    def get_all(self) -> list[UserMemory]:
        """Get all memory snapshots (for trajectory analysis)."""
        if not self._path.exists():
            return []
        memories = []
        for line in self._path.read_text().strip().split("\n"):
            if not line.strip():
                continue
            try:
                memories.append(UserMemory(**json.loads(line)))
            except (json.JSONDecodeError, Exception):
                continue
        return memories

    def get_taste_trajectory(self) -> list[str]:
        """Extract taste trajectory narratives across all weeks."""
        return [m.taste_trajectory for m in self.get_all() if m.taste_trajectory]

    def get_confirmed_interests(self) -> list[str]:
        """Aggregate all confirmed interests across weeks (deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for m in self.get_all():
            for interest in m.confirmed_interests:
                if interest not in seen:
                    seen.add(interest)
                    result.append(interest)
        return result

    def get_rejected_topics(self) -> list[str]:
        """Aggregate all rejected topics across weeks (deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for m in self.get_all():
            for topic in m.rejected_topics:
                if topic not in seen:
                    seen.add(topic)
                    result.append(topic)
        return result
