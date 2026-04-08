"""
Socratic Interviewer — crystallizes user's information criteria through questioning.

Inspired by Ouroboros philosophy: question until ambiguity <= 0.2.
The system asks one question at a time, drills into ambiguous areas,
and produces structured criteria output at the end.

Two modes:
  - Initial onboarding: deep interview from scratch
  - Re-calibration: user-initiated, only asks about changed areas
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are Hedwig's Socratic Interviewer. Your job is to understand exactly what
kind of information the user wants to receive from their AI Signal Radar.

PHILOSOPHY:
- Ask ONE question at a time
- Drill into ambiguous areas — don't accept vague answers
- Never assume — always verify
- Goal: reduce ambiguity to <= 0.2 across all dimensions

DIMENSIONS TO COVER:
1. IDENTITY: Who is the user? Role, expertise level, domain
2. TOPICS: What specific AI topics matter? (agents, papers, tools, business...)
3. DEPTH: Surface news vs deep technical analysis vs both?
4. SOURCES: Any preferred platforms or authors to prioritize?
5. ANTI-PATTERNS: What to explicitly filter OUT? (hype, marketing, old news...)
6. URGENCY: What warrants an immediate alert vs daily digest vs weekly summary?
7. CONTEXT: Current projects, goals, what they're building
8. OPPORTUNITIES: What kind of opportunities to watch for? (business, technical, hiring...)

RULES:
- Ask in the user's language (Korean if user speaks Korean)
- Be direct and concise — no filler
- After each answer, assess which dimensions still have ambiguity > 0.2
- When all dimensions are clear, output the structured criteria

OUTPUT FORMAT (when interview is complete):
When you've gathered enough information, output a JSON block with:
```json
{
  "interview_complete": true,
  "criteria": {
    "identity": { "role": "...", "focus": ["..."] },
    "topics": { "care_about": ["..."], "depth": "..." },
    "sources": { "priority": ["..."], "custom_feeds": ["..."] },
    "anti_patterns": ["..."],
    "urgency_rules": { "alert": ["..."], "digest": ["..."], "skip": ["..."] },
    "context": { "projects": ["..."], "goals": ["..."] },
    "opportunities": ["..."]
  },
  "ambiguity_score": 0.xx
}
```
"""

RECALIBRATE_PROMPT = """\
You are Hedwig's Socratic Interviewer in RECALIBRATION mode.

The user already has existing criteria (shown below). They want to adjust it.
Ask what changed — don't re-ask settled questions.
Focus only on deltas.

CURRENT CRITERIA:
{current_criteria}

Ask the user what they'd like to change. One question at a time.
When done, output the updated criteria in the same JSON format.
"""


class SocraticInterviewer:
    """Manages the Socratic interview flow for criteria generation."""

    def __init__(self, llm_client=None, criteria_path: Optional[Path] = None):
        self._llm = llm_client
        self._criteria_path = criteria_path or Path("criteria.yaml")
        self._history: list[dict] = []
        self._complete = False
        self._result: Optional[dict] = None

    @property
    def is_complete(self) -> bool:
        return self._complete

    @property
    def result(self) -> Optional[dict]:
        return self._result

    def start_initial(self) -> str:
        """Start a fresh onboarding interview. Returns the first question."""
        self._history = [{"role": "system", "content": SYSTEM_PROMPT}]
        first_msg = (
            "안녕하세요! Hedwig AI Signal Radar 설정을 시작합니다.\n\n"
            "먼저, 본인에 대해 알려주세요. "
            "어떤 분야에서 일하시고, AI에서 특히 관심 있는 영역이 뭔가요?"
        )
        self._history.append({"role": "assistant", "content": first_msg})
        return first_msg

    def start_recalibrate(self) -> str:
        """Start a recalibration interview based on existing criteria."""
        current = self._load_current_criteria()
        criteria_str = yaml.dump(current, allow_unicode=True) if current else "없음"
        system = RECALIBRATE_PROMPT.format(current_criteria=criteria_str)
        self._history = [{"role": "system", "content": system}]
        first_msg = (
            "현재 기준을 확인했습니다. 어떤 부분을 바꾸고 싶으세요?\n"
            "예: 새로운 관심사 추가, 필터 기준 변경, 소스 추가/제거 등"
        )
        self._history.append({"role": "assistant", "content": first_msg})
        return first_msg

    async def respond(self, user_input: str) -> str:
        """Process user's answer and return next question or final criteria."""
        self._history.append({"role": "user", "content": user_input})

        if not self._llm:
            return self._no_llm_fallback(user_input)

        response = await self._llm.chat.completions.create(
            model="gpt-4o",
            messages=self._history,
            temperature=0.7,
            max_tokens=1000,
        )
        reply = response.choices[0].message.content or ""
        self._history.append({"role": "assistant", "content": reply})

        # Check if interview is complete (LLM outputs JSON with interview_complete)
        if '"interview_complete": true' in reply or '"interview_complete":true' in reply:
            self._complete = True
            self._result = self._extract_criteria(reply)
            if self._result:
                self._save_criteria(self._result)

        return reply

    def _extract_criteria(self, text: str) -> Optional[dict]:
        """Extract criteria JSON from LLM response."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            return data.get("criteria", data)
        except (ValueError, json.JSONDecodeError):
            return None

    def _save_criteria(self, criteria: dict):
        """Save generated criteria to criteria.yaml."""
        output = {
            "identity": criteria.get("identity", {}),
            "signal_preferences": {
                "care_about": criteria.get("topics", {}).get("care_about", []),
                "ignore": criteria.get("anti_patterns", []),
            },
            "urgency_rules": criteria.get("urgency_rules", {}),
            "context": criteria.get("context", {}),
            "opportunities": criteria.get("opportunities", []),
            "source_priorities": criteria.get("sources", {}),
            "metadata": {
                "generated_by": "socratic_onboarding",
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "ambiguity_score": criteria.get("ambiguity_score", 0.2),
            },
        }
        with open(self._criteria_path, "w") as f:
            yaml.dump(output, f, default_flow_style=False, allow_unicode=True)
        logger.info(f"Criteria saved to {self._criteria_path}")

    def _load_current_criteria(self) -> Optional[dict]:
        """Load existing criteria file if it exists."""
        if self._criteria_path.exists():
            return yaml.safe_load(self._criteria_path.read_text())
        return None

    def _no_llm_fallback(self, user_input: str) -> str:
        """Simple fallback when no LLM client is available."""
        step = len([m for m in self._history if m["role"] == "user"])
        questions = [
            "어떤 AI 토픽에 가장 관심이 많으세요? (예: agents, LLM tooling, 논문, 비즈니스...)",
            "실시간 알림이 필요한 상황은? (예: 새 모델 출시, 중요 논문, API 변경...)",
            "반대로 절대 보고 싶지 않은 정보는? (예: 근거 없는 과대광고, 마케팅 발표...)",
            "현재 진행 중인 프로젝트나 목표가 있다면 알려주세요.",
            "마지막으로, 특별히 팔로우하고 싶은 사람이나 소스가 있나요?",
        ]
        if step <= len(questions):
            return questions[step - 1]
        self._complete = True
        return "감사합니다! 기준이 설정되었습니다."

    def get_history(self) -> list[dict]:
        return list(self._history)
