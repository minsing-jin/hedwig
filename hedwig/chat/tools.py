"""Chat tool definitions + sync handlers.

Each tool maps to an existing Hedwig capability so the chat just becomes
the unified surface (한 화면) for everything users were doing across
multiple pages. The OpenAI-compatible JSON-schema is generated alongside
each handler so the LLM can choose tools without us hand-rolling prompt
templates.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Individual handlers — each returns a JSON-serialisable dict
# ---------------------------------------------------------------------------

def t_search_signals(query: str = "", days: int = 7, limit: int = 10) -> dict:
    """Search recently-collected signals."""
    from hedwig.storage import get_recent_signals, search_signals
    rows = []
    if query:
        rows = search_signals(query=query, limit=limit) or []
    if not rows:
        rows = (get_recent_signals(days=days) or [])[:limit]
    return {
        "count": len(rows),
        "items": [
            {
                "id": r.get("id"),
                "title": r.get("title"),
                "url": r.get("url"),
                "platform": r.get("platform"),
                "score": r.get("relevance_score"),
                "why_relevant": r.get("why_relevant"),
                "devils_advocate": r.get("devils_advocate"),
            }
            for r in rows
        ],
    }


def t_get_brief(cycle: str = "daily") -> dict:
    from hedwig.storage import get_briefings
    if cycle not in ("daily", "weekly", "critical"):
        cycle = "daily"
    rows = get_briefings(cycle_type=cycle, limit=1)
    if not rows:
        return {"cycle": cycle, "found": False, "hint": f"Run `python -m hedwig{' --weekly' if cycle == 'weekly' else ''}` first."}
    b = rows[0]
    return {
        "cycle": cycle,
        "found": True,
        "generated_at": b.get("generated_at"),
        "signal_count": b.get("signal_count"),
        "content": b.get("content", "")[:6000],
        "structured": b.get("structured") or {},
    }


async def t_summarize_url(url: str = "") -> dict:
    """Fetch + summarise a single URL. Detects YouTube and pulls transcript."""
    from hedwig.config import OPENAI_API_KEY, OPENAI_MODEL_FAST
    if not url.strip():
        return {"error": "url required"}

    text = await _fetch_clean_text(url)
    if not text:
        return {"url": url, "summary": "", "error": "could not fetch content"}

    if not OPENAI_API_KEY:
        snippet = text[:1500]
        return {"url": url, "summary": f"(no OpenAI key — raw excerpt)\n\n{snippet}",
                "fetched_chars": len(text)}

    try:
        from openai import AsyncOpenAI
    except ImportError:
        return {"url": url, "summary": text[:1500], "fetched_chars": len(text)}

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    prompt = (
        "다음 콘텐츠를 한국어로 5-7줄 핵심 요약 + 'Devil's Advocate(반대 관점)' 1줄로 마무리:\n\n"
        + text[:8000]
    )
    try:
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL_FAST,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, max_tokens=600,
        )
        return {
            "url": url,
            "summary": (resp.choices[0].message.content or "").strip(),
            "fetched_chars": len(text),
        }
    except Exception as e:
        return {"url": url, "summary": text[:1500], "fetched_chars": len(text), "error": str(e)}


async def _fetch_clean_text(url: str) -> str:
    """YouTube → transcript via yt-dlp; everything else → Jina with trafilatura fallback."""
    if _is_youtube(url):
        try:
            return await _fetch_youtube_transcript(url)
        except Exception as e:
            logger.debug("youtube transcript failed: %s", e)
    # Generic fetch
    try:
        from hedwig.engine.normalizer import fetch_clean_markdown
        return (await fetch_clean_markdown(url)) or ""
    except Exception as e:
        logger.warning("fetch_clean_markdown failed: %s", e)
        return ""


_YT_PATTERNS = [
    re.compile(r"^https?://(?:www\.)?youtube\.com/watch\?v=([\w-]{6,})"),
    re.compile(r"^https?://(?:www\.)?youtu\.be/([\w-]{6,})"),
    re.compile(r"^https?://(?:www\.)?youtube\.com/shorts/([\w-]{6,})"),
]


def _is_youtube(url: str) -> bool:
    return any(p.match(url) for p in _YT_PATTERNS)


async def _fetch_youtube_transcript(url: str) -> str:
    """Use yt-dlp to download auto-generated subtitles. Returns text."""
    import json as _json
    import os
    import shutil
    import tempfile
    proc = await asyncio.create_subprocess_exec(
        "yt-dlp", "--skip-download", "--write-auto-sub", "--sub-lang", "ko,en",
        "--sub-format", "json3", "--print-json", "-o",
        os.path.join(tempfile.gettempdir(), "hedwig_yt_%(id)s.%(ext)s"), url,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return ""
    try:
        meta = _json.loads(stdout.decode("utf-8").splitlines()[0])
    except Exception:
        return ""
    title = meta.get("title", "")
    description = (meta.get("description") or "")[:500]
    # Look for sidecar transcript files in tempdir
    tid = meta.get("id", "")
    sub_text = ""
    for ext in ("ko.json3", "en.json3", "ko.vtt", "en.vtt"):
        candidate = os.path.join(tempfile.gettempdir(), f"hedwig_yt_{tid}.{ext}")
        if os.path.exists(candidate):
            try:
                if candidate.endswith(".json3"):
                    blob = _json.loads(open(candidate, "r", encoding="utf-8").read())
                    sub_text = " ".join(
                        seg.get("utf8", "") for ev in (blob.get("events") or [])
                        for seg in (ev.get("segs") or [])
                    )
                else:
                    raw = open(candidate, "r", encoding="utf-8").read()
                    sub_text = " ".join(
                        line.strip() for line in raw.splitlines()
                        if line.strip() and "-->" not in line and not line.startswith("WEBVTT")
                    )
            except Exception:
                pass
            try:
                os.remove(candidate)
            except Exception:
                pass
            break
    return f"# {title}\n\n{description}\n\n---\n\n{sub_text}"[:12000]


async def t_propose_criteria(intent: str = "") -> dict:
    from hedwig.onboarding.nl_editor import propose_edit
    if not intent.strip():
        return {"ok": False, "error": "intent required"}
    return await propose_edit(intent)


async def t_apply_criteria(changes: list[dict] | None = None, intent: str = "") -> dict:
    from hedwig.onboarding.nl_editor import confirm_edit
    return confirm_edit(changes or [], intent=intent)


async def t_propose_algorithm(intent: str = "") -> dict:
    from hedwig.onboarding.nl_algo_editor import propose_edit
    if not intent.strip():
        return {"ok": False, "error": "intent required"}
    return await propose_edit(intent)


async def t_apply_algorithm(changes: list[dict] | None = None, intent: str = "") -> dict:
    from hedwig.onboarding.nl_algo_editor import confirm_edit
    return confirm_edit(changes or [], intent=intent)


def t_trigger_pipeline(mode: str = "daily") -> dict:
    """Kick off daily/weekly/critical/dry pipelines (background subprocess)."""
    import subprocess, sys
    from pathlib import Path
    valid = {"daily": [], "weekly": ["--weekly"], "dry": ["--dry-run"],
             "critical": ["--critical-loop", "--critical-interval", "1200"],
             "meta": ["--meta-cycle"]}
    if mode not in valid:
        return {"error": f"mode must be one of {sorted(valid)}"}
    try:
        subprocess.Popen([sys.executable, "-m", "hedwig", *valid[mode]],
                          cwd=str(Path.cwd()))
        return {"ok": True, "mode": mode, "started": True}
    except Exception as e:
        return {"error": str(e)}


def t_get_status() -> dict:
    from hedwig.qa.exit_conditions import compute_exit_progress
    return {"exit_conditions": compute_exit_progress()}


def t_get_evolution_timeline(days: int = 30, limit: int = 30) -> dict:
    from hedwig.evolution.timeline import build_timeline
    return {"events": build_timeline(days=days, limit=limit)}


async def t_live_search(query: str = "", num: int = 5) -> dict:
    """exa.ai semantic web search (configured via EXA_API_KEY)."""
    if not query.strip():
        return {"error": "query required"}
    try:
        from hedwig.engine.normalizer import search_web
        results = await search_web(query=query, num_results=num)
        return {"query": query, "count": len(results), "items": results}
    except Exception as e:
        return {"error": str(e)}


async def t_delegate_to_manus(prompt: str = "", title: str = "") -> dict:
    """Delegate a bounded task to Manus when the advanced integration is enabled."""
    if not prompt.strip():
        return {"ok": False, "error": "prompt required"}
    from hedwig.integrations.manus import ManusClient, ManusConfig

    cfg = ManusConfig.from_env()
    if not cfg.ready:
        return {"ok": False, "error": cfg.readiness_error()}
    client = ManusClient(config=cfg)
    return await client.create_task(prompt=prompt, title=title or None)


# ---------------------------------------------------------------------------
# OpenAI-compatible tool schemas
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "function": {
        "name": "search_signals",
        "description": "수집된 시그널을 검색합니다. 사용자가 '최근 X 관련' 같은 질문 시 사용.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "days": {"type": "integer", "default": 7},
            "limit": {"type": "integer", "default": 10},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_brief",
        "description": "최근 daily / weekly 브리핑 본문을 반환합니다.",
        "parameters": {"type": "object", "properties": {
            "cycle": {"type": "string", "enum": ["daily", "weekly", "critical"]},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "summarize_url",
        "description": "특정 URL을 fetch하고 요약. YouTube URL이면 자막 추출.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"},
        }, "required": ["url"]},
    }},
    {"type": "function", "function": {
        "name": "propose_criteria",
        "description": "criteria.yaml(무엇을 추천할지) 자연어 편집 제안. 변경 적용 전 사용자 확인.",
        "parameters": {"type": "object", "properties": {
            "intent": {"type": "string"},
        }, "required": ["intent"]},
    }},
    {"type": "function", "function": {
        "name": "apply_criteria",
        "description": "propose_criteria 결과의 changes를 그대로 받아 적용.",
        "parameters": {"type": "object", "properties": {
            "changes": {"type": "array", "items": {"type": "object"}},
            "intent": {"type": "string"},
        }, "required": ["changes"]},
    }},
    {"type": "function", "function": {
        "name": "propose_algorithm",
        "description": "algorithm.yaml(어떻게 추천할지) 자연어 편집 제안.",
        "parameters": {"type": "object", "properties": {
            "intent": {"type": "string"},
        }, "required": ["intent"]},
    }},
    {"type": "function", "function": {
        "name": "apply_algorithm",
        "description": "propose_algorithm 결과의 changes 적용.",
        "parameters": {"type": "object", "properties": {
            "changes": {"type": "array", "items": {"type": "object"}},
            "intent": {"type": "string"},
        }, "required": ["changes"]},
    }},
    {"type": "function", "function": {
        "name": "trigger_pipeline",
        "description": "background로 daily / weekly / dry / critical / meta 파이프라인 시작.",
        "parameters": {"type": "object", "properties": {
            "mode": {"type": "string",
                      "enum": ["daily", "weekly", "dry", "critical", "meta"]},
        }, "required": ["mode"]},
    }},
    {"type": "function", "function": {
        "name": "get_status",
        "description": "Hedwig MVP exit conditions 진행도.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_evolution_timeline",
        "description": "criteria/algorithm 변경, Q&A, 진화 사이클 통합 timeline.",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "default": 30},
            "limit": {"type": "integer", "default": 30},
        }, "required": []},
    }},
    {"type": "function", "function": {
        "name": "live_search",
        "description": "exa.ai로 즉시 웹 검색 (수집 DB에 없는 질문 시).",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "num": {"type": "integer", "default": 5},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "delegate_to_manus",
        "description": "Advanced opt-in: Manus API로 장기/브라우저/리서치 작업을 외부 위임. HEDWIG_MANUS_ENABLED=1과 MANUS_API_KEY가 있을 때만 성공.",
        "parameters": {"type": "object", "properties": {
            "prompt": {"type": "string"},
            "title": {"type": "string"},
        }, "required": ["prompt"]},
    }},
]


HANDLERS: dict[str, Callable[..., Any]] = {
    "search_signals": t_search_signals,
    "get_brief": t_get_brief,
    "summarize_url": t_summarize_url,
    "propose_criteria": t_propose_criteria,
    "apply_criteria": t_apply_criteria,
    "propose_algorithm": t_propose_algorithm,
    "apply_algorithm": t_apply_algorithm,
    "trigger_pipeline": t_trigger_pipeline,
    "get_status": t_get_status,
    "get_evolution_timeline": t_get_evolution_timeline,
    "live_search": t_live_search,
    "delegate_to_manus": t_delegate_to_manus,
}


def available_tool_schemas() -> list[dict]:
    """Return tool schemas exposed to the LLM for the current environment."""
    from hedwig.integrations.manus import ManusConfig

    schemas: list[dict] = []
    manus_ready = ManusConfig.from_env().ready
    for schema in TOOL_SCHEMAS:
        name = schema.get("function", {}).get("name")
        if name == "delegate_to_manus" and not manus_ready:
            continue
        schemas.append(schema)
    return schemas


async def call_tool(name: str, arguments: dict) -> dict:
    handler = HANDLERS.get(name)
    if handler is None:
        return {"error": f"unknown tool: {name}"}
    try:
        if asyncio.iscoroutinefunction(handler):
            return await handler(**(arguments or {}))
        return handler(**(arguments or {}))
    except TypeError as e:
        return {"error": f"bad args for {name}: {e}"}
    except Exception as e:
        logger.exception("tool %s failed", name)
        return {"error": str(e)}
