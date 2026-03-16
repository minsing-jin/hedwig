from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from hedwig.config import OPENAI_API_KEY, OPENAI_MODEL_DEEP, load_criteria
from hedwig.models import ScoredSignal

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=OPENAI_API_KEY)


async def generate_daily_briefing(signals: list[ScoredSignal]) -> str:
    """Generate a daily briefing summary from scored signals."""
    if not signals:
        return "오늘은 주목할 만한 AI 신호가 없었습니다."

    criteria = load_criteria()
    context_projects = criteria.get("context", {}).get("current_projects", [])
    context_interests = criteria.get("context", {}).get("interests", [])

    signal_text = "\n".join(
        f"- [{s.raw.platform.value}] {s.raw.title} (relevance: {s.relevance_score:.2f}, urgency: {s.urgency.value})\n"
        f"  Why: {s.why_relevant}\n"
        f"  Counter: {s.devils_advocate}\n"
        f"  URL: {s.raw.url}"
        for s in signals
    )

    prompt = f"""당신은 AI 분야 개인 인텔리전스 시스템의 브리핑 작성자입니다.

## 사용자 현재 맥락
프로젝트: {json.dumps(context_projects, ensure_ascii=False)}
관심사: {json.dumps(context_interests, ensure_ascii=False)}

## 오늘의 신호들
{signal_text}

## 작성 지침
아래 형식으로 한국어 일일 브리핑을 작성하세요:

### 🔴 즉시 주목 (Alert 레벨)
- 가장 중요한 신호 1-3개, 왜 중요한지 + 반대 관점

### 🟡 오늘의 주요 흐름
- 공통 주제/패턴을 묶어서 설명

### 🟢 참고할 만한 것
- 나머지 의미 있는 신호 간단 정리

### 💡 오늘의 인사이트
- 이 신호들을 종합했을 때 보이는 패턴이나 시사점 1-2개

간결하게. 링크 포함. 불필요한 서론 없이 바로 본론."""

    resp = await client.chat.completions.create(
        model=OPENAI_MODEL_DEEP,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2000,
    )
    return resp.choices[0].message.content or ""


async def generate_weekly_briefing(signals: list[ScoredSignal]) -> str:
    """Generate a weekly briefing with trends and opportunity notes."""
    if not signals:
        return "이번 주는 주목할 만한 AI 신호가 없었습니다."

    criteria = load_criteria()
    context_projects = criteria.get("context", {}).get("current_projects", [])
    context_interests = criteria.get("context", {}).get("interests", [])

    signal_text = "\n".join(
        f"- [{s.raw.platform.value}] {s.raw.title} (relevance: {s.relevance_score:.2f})\n"
        f"  {s.why_relevant}"
        for s in signals[:50]
    )

    prompt = f"""당신은 AI 분야 개인 인텔리전스 시스템의 주간 전략 브리핑 작성자입니다.

## 사용자 맥락
프로젝트: {json.dumps(context_projects, ensure_ascii=False)}
관심사: {json.dumps(context_interests, ensure_ascii=False)}

## 이번 주 신호들 (상위)
{signal_text}

## 작성 지침
아래 형식으로 한국어 주간 브리핑을 작성하세요:

### 📊 이번 주 핵심 트렌드
- 반복적으로 등장한 주제/패턴 3-5개

### 🔥 가장 중요했던 신호 Top 5
- 각각 왜 중요했는지 + 반대 관점

### 📈 약신호 추적
- 아직 크지 않지만 다음 주에도 지켜봐야 할 신호

### 🎯 기회 포착 (Opportunity Notes)
사용자의 현재 프로젝트와 관심사에 연결해서:
- 이 흐름에서 만들 수 있는 제품/기능은?
- 새로 떠오르는 pain point는?
- 내 강점과 맞는 진입 포인트는?

### ⚖️ 이번 주의 과열 경고
- 화제성은 높았지만 실체가 부족했던 것들

간결하고 실행 가능하게. 한국어로."""

    resp = await client.chat.completions.create(
        model=OPENAI_MODEL_DEEP,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=3000,
    )
    return resp.choices[0].message.content or ""
