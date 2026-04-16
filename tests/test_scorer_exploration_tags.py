from __future__ import annotations

import pytest

from hedwig.models import Platform, RawPost, UrgencyLevel


def _build_post(external_id: str) -> RawPost:
    return RawPost(
        platform=Platform.REDDIT,
        external_id=external_id,
        title=f"Signal {external_id}",
        url=f"https://example.com/{external_id}",
        content="New adjacent category emerging in AI tooling.",
        author="hedwig",
    )


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [type("Choice", (), {"message": type("Message", (), {"content": content})()})()]


class _FakeCompletions:
    def __init__(self, content: str, calls: list[dict]):
        self._content = content
        self._calls = calls

    async def create(self, **kwargs):
        self._calls.append(kwargs)
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content: str, calls: list[dict]):
        self.completions = _FakeCompletions(content, calls)


class _FakeClient:
    def __init__(self, content: str, calls: list[dict]):
        self.chat = _FakeChat(content, calls)


@pytest.mark.asyncio
async def test_score_posts_attaches_exploration_tags_from_llm(monkeypatch):
    from hedwig.engine import scorer as scorer_mod

    calls: list[dict] = []
    response = """
    {
      "results": [
        {
          "relevance_score": 0.83,
          "urgency": "digest",
          "why_relevant": "사용자 관심사에 인접한 새 카테고리입니다.",
          "devils_advocate": "초기 과열일 수 있습니다.",
          "exploration_tags": ["agent infra", "eval tooling", "voice ai"]
        }
      ]
    }
    """

    monkeypatch.setattr(scorer_mod, "load_criteria", lambda: {})
    monkeypatch.setattr(scorer_mod, "client", _FakeClient(response, calls))

    scored = await scorer_mod.score_posts([_build_post("with-tags")])

    assert len(scored) == 1
    assert scored[0].urgency == UrgencyLevel.DIGEST
    assert scored[0].exploration_tags == ["agent infra", "eval tooling", "voice ai"]
    assert "exploration_tags" in calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_score_posts_defaults_exploration_tags_to_empty_list(monkeypatch):
    from hedwig.engine import scorer as scorer_mod

    calls: list[dict] = []
    response = """
    {
      "results": [
        {
          "relevance_score": 0.41,
          "urgency": "skip",
          "why_relevant": "관련성이 낮습니다.",
          "devils_advocate": "추가 확인이 필요합니다."
        }
      ]
    }
    """

    monkeypatch.setattr(scorer_mod, "load_criteria", lambda: {})
    monkeypatch.setattr(scorer_mod, "client", _FakeClient(response, calls))

    scored = await scorer_mod.score_posts([_build_post("without-tags")])

    assert len(scored) == 1
    assert scored[0].urgency == UrgencyLevel.SKIP
    assert scored[0].exploration_tags == []
