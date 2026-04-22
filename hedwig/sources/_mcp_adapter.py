"""Generic MCP-server → Hedwig Source adapter (v3, Phase 1 + post-Phase completion).

Speaks JSON-RPC 2.0 over HTTP to invoke an MCP server's ``tools/call``
method. The server's response is mapped to :class:`RawPost` objects using
the declared ``mapping`` dict (JSONPath-ish dotted selectors).

This is the Absorption Gradient L1 path: any MCP server exposing a
"list posts" shaped tool can be plugged in with zero bespoke code.

Example
-------
    adapter = MCPSourceAdapter(
        mcp_url="http://localhost:8123/mcp",
        tool_name="list_recent_items",
        mapping={
            "external_id": "$.id",
            "title":       "$.title",
            "url":         "$.link",
            "content":     "$.summary",
            "author":      "$.author",
            "score":       "$.points",
        },
        platform=Platform.CUSTOM,
    )
    posts = await adapter.fetch(limit=20)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from hedwig.models import Platform, RawPost

logger = logging.getLogger(__name__)


def _select(obj: Any, selector: str) -> Any:
    """Resolve a ``$.a.b.c`` selector against a nested dict/list."""
    if selector is None:
        return None
    if not selector.startswith("$"):
        return obj.get(selector) if isinstance(obj, dict) else None
    parts = selector.lstrip("$").lstrip(".").split(".")
    cur: Any = obj
    for p in parts:
        if p == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(p)
        elif isinstance(cur, list):
            try:
                cur = cur[int(p)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


@dataclass
class MCPSourceAdapter:
    """Wrap an MCP server's ``tools/call`` method as a Hedwig Source.

    Attributes:
        mcp_url: HTTP endpoint of the MCP server (JSON-RPC 2.0).
        tool_name: MCP tool to invoke.
        mapping: Field map from response item → RawPost fields, e.g.
            ``{"title": "$.title", "url": "$.link"}``.
        arguments: Extra ``arguments`` passed to the MCP ``tools/call``.
        platform: Hedwig Platform enum to tag emitted posts with.
        timeout_seconds: HTTP timeout per request.
        items_path: Dotted selector for the list of items inside the tool
            result (defaults to ``$.content.0.text`` → ``$.items`` search).
    """

    mcp_url: str
    tool_name: str
    mapping: dict[str, str] = field(default_factory=dict)
    arguments: dict[str, Any] = field(default_factory=dict)
    platform: Platform = Platform.CUSTOM
    timeout_seconds: float = 20.0
    items_path: str = "$.items"

    async def _rpc(self, client: httpx.AsyncClient, method: str, params: dict | None = None) -> dict:
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": method,
            "params": params or {},
        }
        resp = await client.post(self.mcp_url, json=payload)
        resp.raise_for_status()
        return resp.json()

    async def probe(self) -> list[str]:
        """Return available tool names from ``tools/list`` (diagnostic)."""
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            data = await self._rpc(client, "tools/list")
        tools = (data.get("result") or {}).get("tools") or []
        return [t.get("name", "") for t in tools]

    async def fetch(self, limit: int = 20, **kwargs: Any) -> list[RawPost]:
        args = dict(self.arguments)
        args.setdefault("limit", limit)
        args.update({k: v for k, v in kwargs.items() if v is not None})
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                data = await self._rpc(
                    client, "tools/call",
                    params={"name": self.tool_name, "arguments": args},
                )
        except Exception as e:
            logger.warning("MCP %s tools/call failed: %s", self.mcp_url, e)
            return []

        if data.get("error"):
            logger.warning("MCP %s error: %s", self.mcp_url, data.get("error"))
            return []

        result = data.get("result") or {}
        items = _select(result, self.items_path) or []
        if not isinstance(items, list):
            return []

        posts: list[RawPost] = []
        for item in items[:limit]:
            if not isinstance(item, dict):
                continue
            posts.append(self._to_raw_post(item))
        return posts

    def _to_raw_post(self, item: dict) -> RawPost:
        def _get(field: str, default: Any = "") -> Any:
            selector = self.mapping.get(field)
            if not selector:
                return default
            value = _select(item, selector)
            return default if value is None else value

        return RawPost(
            platform=self.platform,
            external_id=str(_get("external_id") or _get("url") or ""),
            title=str(_get("title") or "")[:500],
            url=str(_get("url") or ""),
            content=str(_get("content") or "")[:5000],
            author=str(_get("author") or ""),
            score=int(_get("score", 0) or 0),
            comments_count=int(_get("comments_count", 0) or 0),
            published_at=_parse_datetime(_get("published_at")),
            extra={"mcp_url": self.mcp_url, "tool": self.tool_name},
        )

    @classmethod
    def metadata(cls) -> dict:
        return {
            "id": "mcp_generic",
            "name": "Generic MCP Adapter",
            "description": "Wraps any MCP server exposing a list-posts tool (JSON-RPC 2.0 over HTTP)",
            "absorption_level": 1,
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
