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

## ⚠️ 답변 형식 (반드시 지킬 것)
- **사용자에게는 항상 자연스러운 한국어 문장으로 답하세요. JSON, raw dict, 코드 블록만 던지면 안 됩니다.**
- 도구를 호출했더라도 도구 결과를 받은 다음 턴에 반드시 한국어 요약을 작성하세요. 빈 응답 금지.
- 도구 결과의 핵심 항목 (제목 / URL / 점수 등) 을 골라 1~5줄로 요약하고, 필요하면 bullet 사용.
- 시그널 인용 시 [번호] 또는 짧은 제목을 그대로 표기. 사용자가 클릭할 수 있게 URL은 그대로 노출.
- propose_* 결과의 diff는 사용자에게 보여준 뒤 'Apply' 버튼을 누르도록 안내. 자동 적용 금지.
- 정보가 부족하면 "더 자세한 검색이 필요한가요?" 식으로 물어보세요.
"""

FORCE_SUMMARY_PROMPT = (
    "위 도구 결과를 바탕으로 사용자에게 한국어로 자연스러운 답변을 작성하세요. "
    "JSON 그대로 보여주지 말고, 핵심을 1~5줄로 요약 + 인용. "
    "추가 도구 호출은 하지 마세요."
)


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

        # If LLM returned an empty/very short reply after tool calls, force
        # one more summarization pass — this is the "json만 나옴" case.
        if (not final_text or len(final_text) < 12) and tool_log:
            try:
                messages2 = _build_history_for_llm(conversation_id) + [
                    {"role": "user", "content": FORCE_SUMMARY_PROMPT},
                ]
                resp2 = await client.chat.completions.create(
                    model=OPENAI_MODEL_FAST,
                    messages=messages2,
                    temperature=0.3,
                    max_tokens=800,
                )
                forced = (resp2.choices[0].message.content or "").strip()
                if forced:
                    final_text = forced
            except Exception as e:
                logger.debug("forced summary failed: %s", e)

        if not final_text:
            final_text = "죄송합니다. 답변을 생성하지 못했습니다. 더 구체적으로 다시 물어봐주세요."

        append_chat_message(conversation_id, "assistant", final_text)
        return {
            "conversation_id": conversation_id,
            "answer": final_text,
            "tool_calls": tool_log,
        }

    # Max iterations exceeded — try one final summarization before giving up
    try:
        messages_final = _build_history_for_llm(conversation_id) + [
            {"role": "user", "content": FORCE_SUMMARY_PROMPT},
        ]
        resp_final = await client.chat.completions.create(
            model=OPENAI_MODEL_FAST,
            messages=messages_final,
            temperature=0.3,
            max_tokens=800,
        )
        final_text = (resp_final.choices[0].message.content or "").strip()
    except Exception:
        final_text = ""

    fallback = final_text or "도구 호출이 너무 많아 종료했습니다. 더 구체적으로 다시 물어봐주세요."
    append_chat_message(conversation_id, "assistant", fallback)
    return {"conversation_id": conversation_id, "answer": fallback,
            "tool_calls": tool_log, "max_iterations_exceeded": True}


# ---------------------------------------------------------------------------
# Streaming variant — yields SSE-friendly dict events instead of returning once.
# ---------------------------------------------------------------------------

async def stream_user_message(
    conversation_id: str,
    user_text: str,
    *,
    max_iterations: int = 4,
):
    """Async generator yielding event dicts for SSE.

    Event shapes (all dicts; the dashboard endpoint serializes to SSE):
      {"event": "ready", "conversation_id": ...}
      {"event": "tool_start", "name": ..., "args": ...}
      {"event": "tool_result", "name": ..., "result_preview": ...}
      {"event": "token", "delta": "..."}
      {"event": "done", "answer": "...", "tool_calls": [...]}
      {"event": "error", "message": "..."}
    """
    if not user_text or not user_text.strip():
        yield {"event": "error", "message": "empty message"}
        return

    create_conversation(conversation_id)
    append_chat_message(conversation_id, "user", user_text.strip())

    history_count = len(get_chat_messages(conversation_id, limit=2))
    if history_count <= 1:
        update_conversation_title(
            conversation_id,
            _maybe_title_from_first_user_message(user_text),
        )
    yield {"event": "ready", "conversation_id": conversation_id}

    if not OPENAI_API_KEY:
        msg = "OpenAI API 키가 설정되지 않아 LLM 응답을 생성할 수 없습니다. .env에 OPENAI_API_KEY 추가 후 다시 시도해주세요."
        append_chat_message(conversation_id, "assistant", msg)
        yield {"event": "token", "delta": msg}
        yield {"event": "done", "answer": msg, "tool_calls": []}
        return

    try:
        from openai import AsyncOpenAI
    except ImportError:
        msg = "openai 패키지를 import할 수 없습니다."
        append_chat_message(conversation_id, "assistant", msg)
        yield {"event": "token", "delta": msg}
        yield {"event": "done", "answer": msg, "tool_calls": []}
        return

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    tool_log: list[dict] = []

    for iteration in range(max_iterations):
        messages = _build_history_for_llm(conversation_id)
        # Tool-call iterations stay non-streaming — the OpenAI tool_calls
        # delta protocol is finicky and we don't gain UX from streaming
        # function arguments. We only stream the FINAL natural-language reply.
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
            yield {"event": "error", "message": err}
            return

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
                yield {"event": "tool_start", "name": name, "args": args}
                result = await call_tool(name, args)
                tool_log.append({"name": name, "args": args, "result": result})
                append_chat_message(
                    conversation_id, "tool",
                    content=json.dumps(result, ensure_ascii=False, default=str)[:6000],
                    tool_name=name,
                )
                preview = json.dumps(result, ensure_ascii=False, default=str)[:400]
                yield {"event": "tool_result", "name": name, "result_preview": preview}
            continue

        # Final reply — STREAM tokens this time.
        try:
            stream = await client.chat.completions.create(
                model=OPENAI_MODEL_FAST,
                messages=messages,
                temperature=0.3,
                max_tokens=1200,
                stream=True,
            )
        except Exception as e:
            err = f"LLM 스트리밍 실패: {e}"
            append_chat_message(conversation_id, "assistant", err)
            yield {"event": "error", "message": err}
            return

        buf: list[str] = []
        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta
                piece = getattr(delta, "content", None)
            except Exception:
                piece = None
            if piece:
                buf.append(piece)
                yield {"event": "token", "delta": piece}

        final_text = ("".join(buf)).strip()

        if (not final_text or len(final_text) < 12) and tool_log:
            try:
                messages2 = _build_history_for_llm(conversation_id) + [
                    {"role": "user", "content": FORCE_SUMMARY_PROMPT},
                ]
                stream2 = await client.chat.completions.create(
                    model=OPENAI_MODEL_FAST,
                    messages=messages2,
                    temperature=0.3,
                    max_tokens=800,
                    stream=True,
                )
                buf2: list[str] = []
                async for chunk in stream2:
                    try:
                        piece = chunk.choices[0].delta.content
                    except Exception:
                        piece = None
                    if piece:
                        buf2.append(piece)
                        yield {"event": "token", "delta": piece}
                forced = ("".join(buf2)).strip()
                if forced:
                    final_text = forced
            except Exception as e:
                logger.debug("forced stream summary failed: %s", e)

        if not final_text:
            final_text = "죄송합니다. 답변을 생성하지 못했습니다. 더 구체적으로 다시 물어봐주세요."
            yield {"event": "token", "delta": final_text}

        append_chat_message(conversation_id, "assistant", final_text)
        yield {"event": "done", "answer": final_text, "tool_calls": tool_log}
        return

    # Max iterations exceeded
    fallback = "도구 호출이 너무 많아 종료했습니다. 더 구체적으로 다시 물어봐주세요."
    append_chat_message(conversation_id, "assistant", fallback)
    yield {"event": "token", "delta": fallback}
    yield {"event": "done", "answer": fallback, "tool_calls": tool_log,
           "max_iterations_exceeded": True}
