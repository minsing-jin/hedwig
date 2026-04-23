"""Natural-language editor for **algorithm.yaml** (the HOW-to-recommend half
of the recommendation algorithm).

Peers with :mod:`hedwig.onboarding.nl_editor`, which covers criteria.yaml
(the WHAT-to-recommend half). Together they give the user a single
unified "text command → recommendation algorithm mutates" experience
that the v3 vision promises.

Flow:
  1. propose_edit(intent) — LLM reads algorithm.yaml + user intent,
     returns a JSON diff ({op, path, value}).
  2. UI shows diff + 'Apply'
  3. confirm_edit(changes, intent) —
     - writes new algorithm.yaml
     - bumps algorithm_versions (origin='user_nl_editor')
     - logs evolution_signal(channel='explicit', kind='algorithm_edit')

The key difference from meta-evolution: meta uses shadow-mode fitness to
decide adoption; this path is user-authored and trusted — no shadow test.
"""
from __future__ import annotations

import copy
import difflib
import json
import logging
from typing import Any

import yaml

from hedwig.config import ALGORITHM_PATH, OPENAI_API_KEY, OPENAI_MODEL_FAST, load_algorithm_config

logger = logging.getLogger(__name__)


PROPOSE_PROMPT = """당신은 Hedwig 추천 알고리즘의 설정 편집자입니다.
사용자의 자연어 요청에 따라 algorithm.yaml 을 조심스럽게 수정하세요.

## 현재 algorithm.yaml
```yaml
{current_yaml}
```

## 사용자 요청
{user_intent}

## 구조 규칙
- `retrieval` (top_n, threshold, components.pre_scorer/embed_sim/…)
- `ranking` (top_k, components.llm_judge/ltr/content_based/popularity_prior/bandit)
- 각 ranking component: enabled(bool), weight(float 0~1), 추가 sub-key
- `fitness` (short_horizon.weight, long_horizon.weight, diversity_bonus, adoption_threshold)
- `meta_evolution` (enabled, cadence_days, mutation_strategies)

## 안전 규칙
- weight 는 0.0~1.0 사이. 0.5 이상은 조심스럽게 제안.
- top_n 은 50~500, top_k 는 10~100 사이 유지.
- `enabled: true` 로 켠 컴포넌트는 weight > 0 로 세팅.
- 요청 범위를 벗어나는 변경 금지. 큰 구조 재편은 하지 말고, 요청된 부분만 편집.

## 출력 포맷 (JSON만, 다른 텍스트 금지)
```json
{{
  "summary": "사용자 요청을 한 문장으로 요약",
  "changes": [
    {{"op": "set", "path": "ranking.components.bandit.enabled", "value": true}},
    {{"op": "set", "path": "ranking.components.bandit.weight", "value": 0.2}}
  ],
  "rationale": "왜 이렇게 제안했는지 한 문장"
}}
```
"""


def _get_path(obj: Any, path: str) -> Any:
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
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
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
    user_intent = (user_intent or "").strip()
    if not user_intent:
        return {"ok": False, "error": "empty intent"}

    current = load_algorithm_config() or {}
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
        logger.warning("propose_edit (algorithm) LLM failed: %s", e)
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
    """Apply changes to algorithm.yaml, bump algorithm_versions, log event."""
    current = load_algorithm_config() or {}
    after = apply_changes(current, changes)
    diff = yaml_diff(current, after)

    # bump version inside the yaml itself so load_algorithm_config reflects it
    after["version"] = int(current.get("version", 0)) + 1
    from datetime import datetime, timezone
    after["updated_at"] = datetime.now(tz=timezone.utc).isoformat()
    after["origin"] = "user_nl_editor"

    try:
        with open(ALGORITHM_PATH, "w") as f:
            yaml.safe_dump(after, f, allow_unicode=True, sort_keys=False)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    try:
        from hedwig.storage import save_algorithm_version
        save_algorithm_version(
            version=after["version"],
            config=after,
            created_by="user_nl_editor",
            origin="user_nl_editor",
            diff_from_previous=diff,
        )
    except Exception as e:
        logger.warning("algorithm_versions persist failed: %s", e)

    try:
        from hedwig.storage import save_evolution_signal
        save_evolution_signal(
            channel="explicit",
            kind="algorithm_edit",
            payload={
                "intent": intent,
                "changes": changes,
                "diff": diff,
                "algorithm_version": after["version"],
            },
            weight=2.0,
        )
    except Exception as e:
        logger.warning("evolution_signal log failed: %s", e)

    return {
        "ok": True,
        "path": str(ALGORITHM_PATH),
        "version": after["version"],
        "diff": diff,
    }
