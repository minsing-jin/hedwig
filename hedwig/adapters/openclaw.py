"""
Hedwig ↔ OpenClaw Adapter

Exposes Hedwig as OpenAI function-calling compatible tools so OpenClaw
(and any OpenAI Agents SDK-based agent) can use Hedwig's signal radar.

Three integration modes:

1. **Python SDK** — import and use directly:
       from hedwig.adapters.openclaw import HedwigToolkit
       toolkit = HedwigToolkit()
       result = await toolkit.call("hedwig_signals", {"top": 5})

2. **OpenAI Function Calling** — register tools with any agent framework:
       from hedwig.adapters.openclaw import openai_tools, handle_tool_call
       # Pass openai_tools() to your agent's tool definitions
       # Route tool calls through handle_tool_call(name, args)

3. **REST API** — run as HTTP server for remote agents:
       python -m hedwig.adapters.openclaw --serve --port 8400
       # GET  /tools          → list available tools
       # POST /call           → {"tool": "hedwig_signals", "args": {...}}
       # GET  /health         → server status
       # GET  /signals        → shortcut: top 20 scored signals
       # GET  /signals/raw    → shortcut: raw posts (no scoring)
       # GET  /briefing/daily → shortcut: daily briefing text
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

logger = logging.getLogger("hedwig.adapters.openclaw")


# ---------------------------------------------------------------------------
# Tool Definitions (OpenAI function calling format)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "hedwig_signals",
            "description": (
                "Collect and score AI signals from multiple platforms "
                "(HackerNews, Reddit, GeekNews, X, LinkedIn, Threads, YouTube). "
                "Returns scored signals with relevance, urgency, analysis, "
                "and devil's advocate perspectives."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "hackernews", "reddit", "geeknews",
                                "twitter", "linkedin", "threads", "youtube",
                            ],
                        },
                        "description": "Platforms to collect from. Default: all.",
                    },
                    "top": {
                        "type": "integer",
                        "description": "Return top N signals by relevance. Default: 20.",
                        "default": 20,
                    },
                    "raw": {
                        "type": "boolean",
                        "description": "If true, return raw posts without LLM scoring. Default: false.",
                        "default": False,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hedwig_briefing",
            "description": (
                "Generate an AI signal briefing in Korean. "
                "Daily: alerts + trends + insights. "
                "Weekly: trend patterns + opportunity hypotheses + hype warnings."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["daily", "weekly"],
                        "description": "Briefing type. Default: daily.",
                        "default": "daily",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hedwig_source_status",
            "description": (
                "Check which signal sources are currently available and working. "
                "Returns a quick connectivity test for each platform."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hedwig_criteria",
            "description": (
                "View current signal filtering criteria — user profile, "
                "what to care about, what to ignore, urgency rules, and context."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def openai_tools() -> list[dict]:
    """Return tool definitions in OpenAI function-calling format.

    Usage with OpenAI SDK:
        tools = openai_tools()
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=tools,
        )
    """
    return TOOL_DEFINITIONS


# ---------------------------------------------------------------------------
# Toolkit Class — Python SDK integration
# ---------------------------------------------------------------------------

class HedwigToolkit:
    """High-level wrapper for using Hedwig in agent code.

    Example:
        toolkit = HedwigToolkit()

        # List available tools
        toolkit.list_tools()

        # Call a tool
        result = await toolkit.call("hedwig_signals", {"top": 5})

        # Get OpenAI-format tool definitions
        toolkit.openai_tools()
    """

    def __init__(self):
        self._handlers = {
            "hedwig_signals": self._handle_signals,
            "hedwig_briefing": self._handle_briefing,
            "hedwig_source_status": self._handle_source_status,
            "hedwig_criteria": self._handle_criteria,
        }

    def list_tools(self) -> list[str]:
        """Return list of available tool names."""
        return list(self._handlers.keys())

    def openai_tools(self) -> list[dict]:
        """Return OpenAI function-calling format tool definitions."""
        return TOOL_DEFINITIONS

    async def call(self, tool_name: str, args: dict | None = None) -> dict[str, Any]:
        """Execute a tool call. Returns {"ok": bool, "data": ...}."""
        args = args or {}
        handler = self._handlers.get(tool_name)
        if not handler:
            return {
                "ok": False,
                "error": f"Unknown tool: {tool_name}",
                "available": self.list_tools(),
            }
        try:
            data = await handler(args)
            return {"ok": True, "data": data}
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return {"ok": False, "error": str(e)}

    async def _handle_signals(self, args: dict) -> Any:
        from hedwig.agent import collect, pipeline

        sources = args.get("sources")
        top = int(args.get("top", 20))
        raw = args.get("raw", False)

        if raw:
            posts = await collect(sources)
            return posts[:top]
        return await pipeline(sources=sources, top=top)

    async def _handle_briefing(self, args: dict) -> str:
        from hedwig.agent import briefing
        kind = args.get("type", "daily")
        return await briefing(kind)

    async def _handle_source_status(self, _args: dict) -> dict:
        from hedwig.sources.hackernews import HackerNewsSource
        from hedwig.sources.reddit import RedditSource
        from hedwig.sources.geeknews import GeekNewsSource
        from hedwig.sources.twitter import TwitterSource
        from hedwig.sources.linkedin import LinkedInSource
        from hedwig.sources.threads import ThreadsSource
        from hedwig.sources.youtube import YouTubeSource

        sources = {
            "hackernews": HackerNewsSource,
            "reddit": RedditSource,
            "geeknews": GeekNewsSource,
            "twitter": TwitterSource,
            "linkedin": LinkedInSource,
            "threads": ThreadsSource,
            "youtube": YouTubeSource,
        }
        status = {}
        for name, cls in sources.items():
            try:
                src = cls()
                posts = await src.fetch(limit=1)
                status[name] = {"ok": True, "sample_count": len(posts)}
            except Exception as e:
                status[name] = {"ok": False, "error": str(e)}
        return status

    async def _handle_criteria(self, _args: dict) -> dict:
        from hedwig.config import load_criteria
        return load_criteria()


# ---------------------------------------------------------------------------
# Standalone function-call handler (framework-agnostic)
# ---------------------------------------------------------------------------

_toolkit = HedwigToolkit()


async def handle_tool_call(name: str, arguments: dict | str) -> str:
    """Handle an OpenAI-style tool call. Returns JSON string.

    Compatible with OpenAI SDK tool_call parsing:
        for tool_call in response.choices[0].message.tool_calls:
            result = await handle_tool_call(
                tool_call.function.name,
                tool_call.function.arguments,
            )
    """
    if isinstance(arguments, str):
        arguments = json.loads(arguments) if arguments else {}

    result = await _toolkit.call(name, arguments)
    return json.dumps(result, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# REST API Server (stdlib only — no extra dependencies)
# ---------------------------------------------------------------------------

class _HedwigAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler for the Hedwig REST API."""

    def log_message(self, format, *args):
        logger.info(format % args)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        path = self.path.rstrip("/")

        if path == "/health":
            self._send_json({
                "status": "ok",
                "service": "hedwig",
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            })

        elif path == "/tools":
            self._send_json({"tools": TOOL_DEFINITIONS})

        elif path == "/signals":
            result = asyncio.run(_toolkit.call("hedwig_signals", {"top": 20}))
            self._send_json(result)

        elif path == "/signals/raw":
            result = asyncio.run(_toolkit.call("hedwig_signals", {"raw": True, "top": 50}))
            self._send_json(result)

        elif path == "/briefing/daily":
            result = asyncio.run(_toolkit.call("hedwig_briefing", {"type": "daily"}))
            self._send_json(result)

        elif path == "/briefing/weekly":
            result = asyncio.run(_toolkit.call("hedwig_briefing", {"type": "weekly"}))
            self._send_json(result)

        elif path == "/criteria":
            result = asyncio.run(_toolkit.call("hedwig_criteria", {}))
            self._send_json(result)

        elif path == "/status":
            result = asyncio.run(_toolkit.call("hedwig_source_status", {}))
            self._send_json(result)

        else:
            self._send_json({"error": "Not found", "endpoints": [
                "GET /health", "GET /tools", "GET /signals", "GET /signals/raw",
                "GET /briefing/daily", "GET /briefing/weekly",
                "GET /criteria", "GET /status", "POST /call",
            ]}, status=404)

    def do_POST(self):
        path = self.path.rstrip("/")

        if path == "/call":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                self._send_json({"error": "Invalid JSON"}, status=400)
                return

            tool_name = payload.get("tool") or payload.get("name", "")
            args = payload.get("args") or payload.get("arguments", {})

            if not tool_name:
                self._send_json({"error": "Missing 'tool' field"}, status=400)
                return

            result = asyncio.run(_toolkit.call(tool_name, args))
            self._send_json(result)

        else:
            self._send_json({"error": "Not found"}, status=404)


def serve(host: str = "0.0.0.0", port: int = 8400):
    """Start the Hedwig REST API server."""
    server = HTTPServer((host, port), _HedwigAPIHandler)
    logger.info(f"Hedwig OpenClaw API running at http://{host}:{port}")
    logger.info("Endpoints:")
    logger.info("  GET  /health         — server status")
    logger.info("  GET  /tools          — list tools (OpenAI format)")
    logger.info("  GET  /signals        — top 20 scored signals")
    logger.info("  GET  /signals/raw    — raw posts (no scoring)")
    logger.info("  GET  /briefing/daily — daily briefing")
    logger.info("  GET  /briefing/weekly— weekly briefing")
    logger.info("  GET  /criteria       — current filtering criteria")
    logger.info("  GET  /status         — source connectivity check")
    logger.info("  POST /call           — generic tool call {tool, args}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Hedwig OpenClaw Adapter")
    parser.add_argument("--serve", action="store_true", help="Start REST API server")
    parser.add_argument("--port", type=int, default=8400, help="Server port (default: 8400)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument("--tools", action="store_true", help="Print tool definitions as JSON")
    parser.add_argument("--call", type=str, help="Call a tool by name")
    parser.add_argument("--args", type=str, default="{}", help="Tool arguments as JSON string")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.tools:
        print(json.dumps(TOOL_DEFINITIONS, indent=2, ensure_ascii=False))

    elif args.call:
        tool_args = json.loads(args.args) if args.args else {}
        result = asyncio.run(handle_tool_call(args.call, tool_args))
        print(result)

    elif args.serve:
        serve(host=args.host, port=args.port)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
