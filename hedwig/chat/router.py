"""Chat router — drives the OpenAI tool-use loop and persists turns.

Loop:
  1. Append user message to conversation history.
  2. Send full history + tool schemas to LLM.
  3. If LLM emits tool_calls, execute each → append tool result → loop.
  4. When LLM returns plain content, append assistant message, return.

Bounded by max_iterations (default 4) so tool storms can't run forever.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from hedwig.chat.tools import HANDLERS, TOOL_SCHEMAS, call_tool
from hedwig.config import OPENAI_API_KEY, OPENAI_MODEL_FAST
from hedwig.storage import (
    append_chat_message,
    create_conversation,
    get_chat_messages,
    update_conversation_title,
)

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """당신은 Hedwig — 사용자 본인이 소유한 추천 알고리즘의 Chat 인터페이스입니다.

## 핵심 원칙
1. 정보 홍수에서 핵심만 — 크로스플랫폼 데이터를 사용자에게 통합 전달
2. 자가진화 추천 + 사용자 자연어 주도권 — 사용자가 방향을 말하면 그대로 반영
3. 인지 부하 0 — 사용자가 한 곳에서 모든 정보를 받을 수 있도록

## 도구 사용
- 사용자가 시그널/콘텐츠를 묻거나 요청하면 search_signals / get_brief 사용.
- URL 또는 YouTube 링크가 보이면 summarize_url 사용.
- "X 관심 늘려줘" 같은 자연어 알고리즘 명령은 propose_criteria → 사용자 확인 → apply_criteria.
- "bandit 비중 올려" 같은 알고리즘 가중치 명령은 propose_algorithm → apply_algorithm.
- 사용자가 daily/weekly/critical 파이프라인 실행을 요청하면 trigger_pipeline.
- 수집 DB에 없을 것 같은 정보는 live_search 사용.

## 답변 스타일
- 한국어로, 간결하게.
- 인용 시 시그널 ID 또는 URL 명시.
- propose 결과의 diff는 사용자에게 보여준 뒤 'Apply' 버튼을 누르도록 안내. 자동 적용 금지.
"""


def new_conversation_id() -> str:
    return f"chat-{uuid.uuid4().hex[:12]}"


def _maybe_title_from_first_user_message(text: str) -> str:
    return (text or "New chat").strip().splitlines()[0][:60] or "New chat"


def _build_history_for_llm(conversation_id: str) -> list[dict]:
    """Convert stored chat_messages into OpenAI-style messages."""
    rows = get_chat_messages(conversation_id, limit=60)
    out: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    pending_assistant: dict | None = None
    for r in rows:
        role = r["role"]
        if role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": r.get("content") or ""}
            if r.get("tool_calls"):
                msg["tool_calls"] = r["tool_calls"]
            out.append(msg)
            pending_assistant = msg
        elif role == "tool":
            # Match to last assistant tool_call by name
            tool_call_id = None
            if pending_assistant and pending_assistant.get("tool_calls"):
                for tc in pending_assistant["tool_calls"]:
                    if tc.get("function", {}).get("name") == r.get("tool_name"):
                        tool_call_id = tc.get("id")
                        break
            out.append({
                "role": "tool",
                "tool_call_id": tool_call_id or r.get("tool_name") or "tool",
                "name": r.get("tool_name") or "tool",
                "content": r.get("content") or "",
            })
        else:
            out.append({"role": role, "content": r.get("content") or ""})
    return out


async def handle_user_message(
    conversation_id: str,
    user_text: str,
    *,
    max_iterations: int = 4,
) -> dict:
    """Append user message, run tool-use loop, append assistant final message."""
    if not user_text or not user_text.strip():
        return {"error": "empty message"}

    create_conversation(conversation_id)
    append_chat_message(conversation_id, "user", user_text.strip())

    # Auto-title with the first user message
    history_count = len(get_chat_messages(conversation_id, limit=2))
    if history_count <= 1:
        update_conversation_title(conversation_id,
                                   _maybe_title_from_first_user_message(user_text))

    if not OPENAI_API_KEY:
        msg = "OpenAI API 키가 설정되지 않아 LLM 응답을 생성할 수 없습니다. .env에 OPENAI_API_KEY 추가 후 다시 시도해주세요."
        append_chat_message(conversation_id, "assistant", msg)
        return {"conversation_id": conversation_id, "answer": msg, "tool_calls": []}

    try:
        from openai import AsyncOpenAI
    except ImportError:
        msg = "openai 패키지를 import할 수 없습니다."
        append_chat_message(conversation_id, "assistant", msg)
        return {"conversation_id": conversation_id, "answer": msg, "tool_calls": []}

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    tool_log: list[dict] = []

    for _ in range(max_iterations):
        messages = _build_history_for_llm(conversation_id)
        try:
            resp = await client.chat.completions.create(
                model=OPENAI_MODEL_FAST,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                temperature=0.3,
                max_tokens=1200,
            )
        except Exception as e:
            err = f"LLM 호출 실패: {e}"
            append_chat_message(conversation_id, "assistant", err)
            return {"conversation_id": conversation_id, "answer": err,
                    "tool_calls": tool_log, "error": str(e)}

        choice = resp.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            tc_payload = []
            for tc in tool_calls:
                tc_payload.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            append_chat_message(
                conversation_id, "assistant",
                content=message.content or "",
                tool_calls=tc_payload,
            )
            for tc in tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = await call_tool(name, args)
                tool_log.append({"name": name, "args": args, "result": result})
                append_chat_message(
                    conversation_id, "tool",
                    content=json.dumps(result, ensure_ascii=False, default=str)[:6000],
                    tool_name=name,
                )
            continue  # next iteration with tool results in history

        # Final plain reply
        final_text = (message.content or "").strip()
        append_chat_message(conversation_id, "assistant", final_text)
        return {
            "conversation_id": conversation_id,
            "answer": final_text,
            "tool_calls": tool_log,
        }

    # Max iterations exceeded — emit a graceful fallback
    fallback = "도구 호출이 너무 많아 종료했습니다. 더 구체적으로 다시 물어봐주세요."
    append_chat_message(conversation_id, "assistant", fallback)
    return {"conversation_id": conversation_id, "answer": fallback,
            "tool_calls": tool_log, "max_iterations_exceeded": True}
