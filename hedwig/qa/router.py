"""Q&A router — dispatch to RAG over DB + optional live search fallback.

Philosophy: answer from collected signals first (cheap, already-filtered),
fall back to live search (exa / r.jina.ai) only when DB is insufficient.

This is the on-demand layer of the 4-tier temporal lattice.
Accept/reject events from the UI feed back into evolution as semi-explicit
feedback (see qa/feedback.py).
"""
from __future__ import annotations

import logging

from hedwig.config import OPENAI_API_KEY, OPENAI_MODEL_FAST, load_criteria
from hedwig.qa.retrieval import format_context, retrieve_from_db

logger = logging.getLogger(__name__)


ANSWER_PROMPT = """당신은 Hedwig의 on-demand Q&A 어시스턴트입니다.
사용자의 현재 관심사와 수집된 신호들을 바탕으로 답변하세요.

## 사용자 맥락
{criteria_summary}

## 수집된 관련 신호들
{context}

## 질문
{question}

## 지침
- 수집된 신호 기반으로 답하고, 근거가 되는 항목은 [번호]로 인용
- 신호가 불충분하면 솔직히 말하고 live search가 필요한지 제안
- 한국어. 간결하게.
"""


async def answer(question: str, top_k: int = 8) -> dict:
    """Answer a user question using RAG over collected signals.

    Returns:
        {"answer": str, "sources": list[dict], "fallback_suggested": bool}
    """
    rows = retrieve_from_db(question, limit=top_k)

    if not OPENAI_API_KEY:
        return {
            "answer": "OpenAI API 키가 없어 RAG 답변을 생성할 수 없습니다. "
                      "수집된 관련 신호만 표시합니다.",
            "sources": rows,
            "fallback_suggested": False,
        }

    if not rows:
        return {
            "answer": "수집된 신호에서 관련 내용을 찾지 못했습니다. "
                      "live search(exa)로 확장해볼까요?",
            "sources": [],
            "fallback_suggested": True,
        }

    try:
        from openai import AsyncOpenAI
    except ImportError:
        return {
            "answer": "openai 패키지를 import 할 수 없습니다.",
            "sources": rows,
            "fallback_suggested": False,
        }

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    criteria = load_criteria()
    criteria_summary = (
        f"관심사: {criteria.get('signal_preferences', {}).get('care_about', [])}\n"
        f"프로젝트: {criteria.get('context', {}).get('current_projects', [])}"
    )

    prompt = ANSWER_PROMPT.format(
        criteria_summary=criteria_summary,
        context=format_context(rows),
        question=question,
    )

    try:
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL_FAST,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
        )
        answer_text = resp.choices[0].message.content or ""
    except Exception as e:
        logger.warning("Q&A LLM call failed: %s", e)
        answer_text = "답변 생성 중 오류가 발생했습니다."

    return {
        "answer": answer_text,
        "sources": rows,
        "fallback_suggested": False,
    }
