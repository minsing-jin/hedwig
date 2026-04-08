from __future__ import annotations

from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

POLYMARKET_API = "https://gamma-api.polymarket.com/events"

AI_KEYWORDS = [
    "AI", "artificial intelligence", "GPT", "OpenAI", "Google DeepMind",
    "Anthropic", "Claude", "LLM", "machine learning", "AGI",
]


@register_source
class PolymarketSource(Source):
    """AI-related prediction markets from Polymarket."""
    platform = Platform.POLYMARKET
    plugin_id = "polymarket"
    display_name = "Polymarket"
    fetch_method = FetchMethod.API

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        posts: list[RawPost] = []
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    POLYMARKET_API,
                    params={"limit": 100, "active": True, "order": "volume24hr", "ascending": False},
                )
                if resp.status_code != 200:
                    return []
                events = resp.json()
                for event in events:
                    title = event.get("title", "")
                    desc = event.get("description", "")
                    text = f"{title} {desc}".lower()
                    if not any(kw.lower() in text for kw in AI_KEYWORDS):
                        continue
                    markets = event.get("markets", [])
                    market_info = ""
                    for m in markets[:3]:
                        outcome = m.get("outcomePrices", "")
                        market_info += f"  - {m.get('question', '')}: {outcome}\n"
                    created = event.get("createdAt", "")
                    try:
                        published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        published = datetime.now(tz=timezone.utc)
                    posts.append(RawPost(
                        platform=Platform.POLYMARKET,
                        external_id=str(event.get("id", "")),
                        title=title,
                        url=f"https://polymarket.com/event/{event.get('slug', '')}",
                        content=f"{desc}\n\nMarkets:\n{market_info}"[:2000],
                        author="polymarket",
                        score=int(event.get("volume24hr", 0)),
                        published_at=published,
                        extra={"volume_24h": event.get("volume24hr", 0)},
                    ))
            except Exception:
                pass
        return posts[:limit]
