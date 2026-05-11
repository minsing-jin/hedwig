"""Advanced optional Manus API integration.

Manus is external delegation, not Hedwig's recommendation core. The client is
disabled unless the user explicitly sets HEDWIG_MANUS_ENABLED=1 and MANUS_API_KEY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any

import httpx


DEFAULT_BASE_URL = "https://api.manus.ai"


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str | None) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


@dataclass(frozen=True)
class ManusConfig:
    enabled: bool = False
    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    agent_profile: str | None = None
    project_id: str | None = None
    locale: str | None = None
    share_visibility: str | None = None
    connectors: list[str] = field(default_factory=list)
    enable_skills: list[str] = field(default_factory=list)
    force_skills: list[str] = field(default_factory=list)
    hide_in_task_list: bool | None = None

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "ManusConfig":
        source = env if env is not None else os.environ
        return cls(
            enabled=_truthy(source.get("HEDWIG_MANUS_ENABLED")),
            api_key=str(source.get("MANUS_API_KEY") or "").strip(),
            base_url=str(source.get("MANUS_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            agent_profile=str(source.get("MANUS_AGENT_PROFILE") or "").strip() or None,
            project_id=str(source.get("MANUS_PROJECT_ID") or "").strip() or None,
            locale=str(source.get("MANUS_LOCALE") or "").strip() or None,
            share_visibility=str(source.get("MANUS_SHARE_VISIBILITY") or "").strip() or None,
            connectors=_split_csv(source.get("MANUS_CONNECTORS")),
            enable_skills=_split_csv(source.get("MANUS_ENABLE_SKILLS")),
            force_skills=_split_csv(source.get("MANUS_FORCE_SKILLS")),
            hide_in_task_list=(
                _truthy(source.get("MANUS_HIDE_IN_TASK_LIST"))
                if source.get("MANUS_HIDE_IN_TASK_LIST") is not None
                else None
            ),
        )

    @property
    def ready(self) -> bool:
        return self.enabled and bool(self.api_key)

    def readiness_error(self) -> str | None:
        if not self.enabled:
            return "Manus integration is disabled. Set HEDWIG_MANUS_ENABLED=1 in Advanced setup."
        if not self.api_key:
            return "MANUS_API_KEY is required when Manus integration is enabled."
        return None


class ManusClient:
    """Small async wrapper around Manus v2 task endpoints."""

    def __init__(
        self,
        config: ManusConfig | None = None,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config or ManusConfig.from_env()
        self._client = http_client

    def _headers(self) -> dict[str, str]:
        if not self.config.api_key:
            return {}
        return {
            "x-manus-api-key": self.config.api_key,
            "Content-Type": "application/json",
        }

    def _task_payload(self, prompt: str, title: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "message": {
                "content": [{"type": "text", "text": prompt}],
            },
        }
        message = payload["message"]
        if self.config.connectors:
            message["connectors"] = self.config.connectors
        if self.config.enable_skills:
            message["enable_skills"] = self.config.enable_skills
        if self.config.force_skills:
            message["force_skills"] = self.config.force_skills
        if title:
            payload["title"] = title
        optional = {
            "agent_profile": self.config.agent_profile,
            "project_id": self.config.project_id,
            "locale": self.config.locale,
            "share_visibility": self.config.share_visibility,
            "hide_in_task_list": self.config.hide_in_task_list,
        }
        payload.update({k: v for k, v in optional.items() if v is not None})
        return payload

    async def create_task(self, prompt: str, title: str | None = None) -> dict[str, Any]:
        err = self.config.readiness_error()
        if err:
            return {"ok": False, "error": err}
        if not prompt.strip():
            return {"ok": False, "error": "prompt required"}

        url = f"{self.config.base_url}/v2/task.create"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            resp = await client.post(
                url,
                headers=self._headers(),
                json=self._task_payload(prompt=prompt, title=title),
            )
            data = _safe_json(resp)
            if resp.status_code >= 400:
                return {"ok": False, "status_code": resp.status_code, "error": data or resp.text}
            return {"ok": True, "status_code": resp.status_code, "task": data}
        finally:
            if owns_client:
                await client.aclose()

    async def list_messages(self, task_id: str, limit: int = 20) -> dict[str, Any]:
        err = self.config.readiness_error()
        if err:
            return {"ok": False, "error": err}
        if not task_id.strip():
            return {"ok": False, "error": "task_id required"}

        url = f"{self.config.base_url}/v2/task.listMessages"
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            resp = await client.get(
                url,
                headers=self._headers(),
                params={"task_id": task_id, "limit": limit, "order": "desc"},
            )
            data = _safe_json(resp)
            if resp.status_code >= 400:
                return {"ok": False, "status_code": resp.status_code, "error": data or resp.text}
            return {"ok": True, "status_code": resp.status_code, "messages": data}
        finally:
            if owns_client:
                await client.aclose()


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return None
