"""Natural-language criteria editor (v3, Phase 1).

User types intent in natural language ("MoE 피로, agent 위주로 바꿔") →
LLM proposes a YAML diff against criteria.yaml → user confirms → applied.

The applied edit is recorded as an 'explicit' evolution_signal so the
Meta-Evolution layer can correlate explicit edits with fitness changes.
"""
from __future__ import annotations

import copy
import difflib
import json
import logging
from typing import Any

import yaml

from hedwig.config import CRITERIA_PATH, OPENAI_API_KEY, OPENAI_MODEL_FAST, load_criteria

logger = logging.getLogger(__name__)


PROPOSE_PROMPT = """당신은 Hedwig의 criteria editor입니다.
사용자의 자연어 요청에 따라 현재 criteria YAML을 조심스럽게 수정하세요.

## 현재 criteria
```yaml
{current_yaml}
```

## 사용자 요청
{user_intent}

## 규칙
- YAML 구조는 유지하세요 (identity, signal_preferences, context, delivery 등)
- signal_preferences.care_about / ignore 는 리스트
- 추가/삭제/수정을 명확히 구분할 수 있게 제안하세요
- 너무 큰 변경은 피하고, 요청 범위 내에서만 편집하세요
- 근거가 불확실하면 제안을 보수적으로 하세요

## 출력 포맷 (JSON만, 다른 텍스트 금지)
```json
{{
  "summary": "사용자 요청을 요약한 한 문장",
  "changes": [
    {{"op": "add",    "path": "signal_preferences.care_about", "value": "agent frameworks"}},
    {{"op": "remove", "path": "signal_preferences.care_about", "value": "MoE"}},
    {{"op": "set",    "path": "identity.role", "value": "AI builder"}}
  ],
  "rationale": "왜 이렇게 제안했는지 한 문장"
}}
```
"""


def _get_path(obj: dict, path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _set_path(obj: dict, path: str, value: Any) -> None:
    parts = path.split(".")
    cur: Any = obj
    for part in parts[:-1]:
        if not isinstance(cur.get(part), dict):
            cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value


def _list_add(obj: dict, path: str, value: Any) -> None:
    existing = _get_path(obj, path)
    if existing is None:
        _set_path(obj, path, [value])
    elif isinstance(existing, list):
        if value not in existing:
            existing.append(value)
    else:
        _set_path(obj, path, [existing, value])


def _list_remove(obj: dict, path: str, value: Any) -> None:
    existing = _get_path(obj, path)
    if isinstance(existing, list) and value in existing:
        existing.remove(value)


def apply_changes(base: dict, changes: list[dict]) -> dict:
    """Apply a list of {op, path, value} ops to a copy of base, returning the result."""
    result = copy.deepcopy(base)
    for ch in changes:
        op = ch.get("op")
        path = ch.get("path", "")
        value = ch.get("value")
        if not op or not path:
            continue
        if op == "set":
            _set_path(result, path, value)
        elif op == "add":
            _list_add(result, path, value)
        elif op == "remove":
            _list_remove(result, path, value)
    return result


def yaml_diff(before: dict, after: dict) -> str:
    a = yaml.safe_dump(before, allow_unicode=True, sort_keys=False).splitlines()
    b = yaml.safe_dump(after, allow_unicode=True, sort_keys=False).splitlines()
    return "\n".join(difflib.unified_diff(a, b, fromfile="before", tofile="after", lineterm=""))


async def propose_edit(user_intent: str) -> dict:
    """Ask the LLM to propose a criteria change set.

    Returns:
        {
          "ok": bool,
          "summary": str,
          "rationale": str,
          "changes": [{"op","path","value"}, ...],
          "preview": {"before": dict, "after": dict, "diff": str},
          "error": optional str,
        }
    """
    user_intent = (user_intent or "").strip()
    if not user_intent:
        return {"ok": False, "error": "empty intent"}

    current = load_criteria() or {}
    current_yaml = yaml.safe_dump(current, allow_unicode=True, sort_keys=False)

    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY missing — cannot propose edit"}

    try:
        from openai import AsyncOpenAI
    except ImportError:
        return {"ok": False, "error": "openai package missing"}

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    prompt = PROPOSE_PROMPT.format(current_yaml=current_yaml, user_intent=user_intent)

    try:
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL_FAST,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        logger.warning("propose_edit LLM failed: %s", e)
        return {"ok": False, "error": str(e)}

    changes = data.get("changes") or []
    if not isinstance(changes, list):
        changes = []

    after = apply_changes(current, changes)
    preview = {
        "before": current,
        "after": after,
        "diff": yaml_diff(current, after),
    }
    return {
        "ok": True,
        "summary": data.get("summary", ""),
        "rationale": data.get("rationale", ""),
        "changes": changes,
        "preview": preview,
    }


def confirm_edit(changes: list[dict], intent: str = "") -> dict:
    """Apply a set of changes to criteria.yaml, bump a CriteriaVersion, and
    log an explicit evolution_signal.

    Algorithm Sovereignty requires that every user-driven criteria change is
    versioned and auditable. This function is the single choke-point for
    explicit edits originating in the NL editor UI.

    Returns:
        {"ok": bool, "path": str, "version": int|None, "diff": str, "error": optional}
    """
    if not CRITERIA_PATH.exists():
        current: dict = {}
    else:
        current = load_criteria() or {}

    after = apply_changes(current, changes)
    diff = yaml_diff(current, after)

    try:
        with open(CRITERIA_PATH, "w") as f:
            yaml.safe_dump(after, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    new_version: int | None = None
    try:
        from hedwig.models import CriteriaVersion
        from hedwig.storage import save_criteria_version
        from hedwig.evolution.engine import EvolutionEngine  # has version helpers

        latest = _latest_criteria_version()
        new_version = (latest + 1) if latest else 1
        cv = CriteriaVersion(
            version=new_version,
            criteria=after,
            created_by="user_nl_editor",
            diff_from_previous=diff,
        )
        save_criteria_version(cv)
    except Exception as e:
        logger.warning("criteria_version persist failed: %s", e)

    try:
        from hedwig.storage import save_evolution_signal

        save_evolution_signal(
            channel="explicit",
            kind="criteria_edit",
            payload={
                "intent": intent,
                "changes": changes,
                "diff": diff,
                "criteria_version": new_version,
            },
            weight=2.0,
        )
    except Exception as e:
        logger.warning("evolution_signal log failed: %s", e)

    return {
        "ok": True,
        "path": str(CRITERIA_PATH),
        "version": new_version,
        "diff": diff,
    }


def _latest_criteria_version() -> int | None:
    """Return the highest existing criteria_versions.version or None."""
    try:
        from hedwig.storage import get_criteria_versions
        rows = get_criteria_versions(limit=1) or []
        if rows:
            return int(rows[0].get("version", 0))
    except Exception:
        pass
    return None
