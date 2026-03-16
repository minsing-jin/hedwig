from __future__ import annotations

import abc

from hedwig.models import RawPost


class Source(abc.ABC):
    """Base class for all platform sources."""

    @abc.abstractmethod
    async def fetch(self, limit: int = 50) -> list[RawPost]:
        ...
