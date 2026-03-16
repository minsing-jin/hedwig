"""
Hedwig MCP Server

Exposes Hedwig as MCP tools so AI agents (Claude Code, OpenClaw, etc.)
can call it directly.

Usage:
    python -m hedwig.mcp_server

Register in ~/.claude/mcp.json:
    {
        "mcpServers": {
            "hedwig": {
                "command": "python",
                "args": ["-m", "hedwig.mcp_server"],
                "cwd": "/path/to/hedwig"
            }
        }
    }
"""
from __future__ import annotations

import asyncio
import json
import sys


async def handle_request(request: dict) -> dict:
    """Handle a JSON-RPC request."""
    method = request.get("method", "")
    params = request.get("params", {})
    req_id = request.get("id")

    if method == "initialize":
        return _response(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "hedwig", "version": "0.1.0"},
        })

    elif method == "notifications/initialized":
        return None  # No response needed for notifications

    elif method == "tools/list":
        return _response(req_id, {"tools": TOOLS})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        args = params.get("arguments", {})
        result = await _call_tool(tool_name, args)
        return _response(req_id, {
            "content": [{"type": "text", "text": result}]
        })

    return _error(req_id, -32601, f"Unknown method: {method}")


async def _call_tool(name: str, args: dict) -> str:
    from hedwig.agent import collect, score, briefing, pipeline

    if name == "hedwig_collect":
        sources = args.get("sources")
        if isinstance(sources, str):
            sources = [sources]
        result = await collect(sources)
        return json.dumps(result[:int(args.get("limit", 50))], ensure_ascii=False, indent=2)

    elif name == "hedwig_score":
        top = int(args.get("top", 20))
        sources = args.get("sources")
        if isinstance(sources, str):
            sources = [sources]
        posts = await collect(sources)
        result = await score(posts, top=top)
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif name == "hedwig_briefing":
        kind = args.get("type", "daily")
        return await briefing(kind)

    elif name == "hedwig_pipeline":
        top = int(args.get("top", 20))
        sources = args.get("sources")
        if isinstance(sources, str):
            sources = [sources]
        result = await pipeline(sources=sources, top=top)
        return json.dumps(result, ensure_ascii=False, indent=2)

    return f"Unknown tool: {name}"


TOOLS = [
    {
        "name": "hedwig_collect",
        "description": "Collect raw AI posts from platforms (HN, Reddit, GeekNews, blogs). No LLM scoring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["hackernews", "reddit", "geeknews", "twitter", "linkedin", "threads"]},
                    "description": "Which sources to collect from. Default: all.",
                },
                "limit": {"type": "integer", "description": "Max posts to return. Default: 50."},
            },
        },
    },
    {
        "name": "hedwig_score",
        "description": "Collect and score AI signals with LLM. Returns relevance scores, urgency, why it matters, and devil's advocate perspective.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["hackernews", "reddit", "geeknews", "twitter", "linkedin", "threads"]},
                    "description": "Which sources to collect from. Default: all.",
                },
                "top": {"type": "integer", "description": "Return top N signals. Default: 20."},
            },
        },
    },
    {
        "name": "hedwig_briefing",
        "description": "Generate a daily or weekly AI signal briefing in Korean. Includes trends, opportunities, and counter-perspectives.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {
                    "type": "string",
                    "enum": ["daily", "weekly"],
                    "description": "Briefing type. Default: daily.",
                },
            },
        },
    },
    {
        "name": "hedwig_pipeline",
        "description": "Full pipeline: collect from all sources, score with LLM, return top signals as structured JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sources": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["hackernews", "reddit", "geeknews", "twitter", "linkedin", "threads"]},
                    "description": "Which sources. Default: all.",
                },
                "top": {"type": "integer", "description": "Top N signals. Default: 20."},
            },
        },
    },
]


def _response(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def run_server():
    """Run MCP server over stdin/stdout."""
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    buf = b""
    while True:
        try:
            chunk = await reader.read(65536)
            if not chunk:
                break
            buf += chunk

            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                request = json.loads(line)
                response = await handle_request(request)
                if response is not None:
                    out = json.dumps(response) + "\n"
                    sys.stdout.buffer.write(out.encode())
                    sys.stdout.buffer.flush()
        except Exception as e:
            sys.stderr.write(f"MCP Error: {e}\n")
            sys.stderr.flush()


def main():
    asyncio.run(run_server())


if __name__ == "__main__":
    main()
