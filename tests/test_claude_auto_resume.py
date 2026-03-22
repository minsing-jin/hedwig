from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from hedwig.claude_auto_resume import (
    DEFAULT_WAIT_SECONDS,
    AutoResumeConfig,
    LimitEvent,
    build_resume_command,
    find_latest_session_id,
    load_config,
    parse_usage_limit_event,
    set_enabled,
    wait_seconds_for_limit_event,
    write_handoff,
)


def test_enable_disable_round_trip(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    config = set_enabled(project_dir, True, wait_seconds=1234)
    assert config.enabled is True
    assert config.wait_seconds == 1234

    loaded = load_config(project_dir)
    assert loaded == AutoResumeConfig(enabled=True, wait_seconds=1234, transcript_lines=400)

    disabled = set_enabled(project_dir, False)
    assert disabled.enabled is False
    assert load_config(project_dir).enabled is False


def test_parse_usage_limit_event_prefers_epoch_marker() -> None:
    now = datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc)
    text = "Claude AI usage limit reached|1774177200"

    event = parse_usage_limit_event(text, now=now)

    assert event is not None
    assert event.reset_at == datetime.fromtimestamp(1774177200, tz=timezone.utc)
    assert event.wait_seconds == int((event.reset_at - now).total_seconds())


def test_parse_usage_limit_event_falls_back_to_default_wait() -> None:
    now = datetime(2026, 3, 22, 10, 0, tzinfo=timezone.utc)
    text = "Claude usage limit reached. Your limit will reset later."

    event = parse_usage_limit_event(text, now=now)

    assert event is not None
    assert event.reset_at is None
    assert event.wait_seconds == DEFAULT_WAIT_SECONDS


def test_find_latest_session_id_matches_project_directory(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()

    old = {
        "pid": 111,
        "sessionId": "old-session",
        "cwd": str(project_dir),
        "startedAt": 10,
    }
    new = {
        "pid": 222,
        "sessionId": "new-session",
        "cwd": str(project_dir),
        "startedAt": 20,
    }
    other = {
        "pid": 333,
        "sessionId": "other-session",
        "cwd": str(tmp_path / "other"),
        "startedAt": 30,
    }

    (sessions_dir / "111.json").write_text(json.dumps(old), encoding="utf-8")
    (sessions_dir / "222.json").write_text(json.dumps(new), encoding="utf-8")
    (sessions_dir / "333.json").write_text(json.dumps(other), encoding="utf-8")

    assert find_latest_session_id(project_dir, sessions_dir=sessions_dir) == "new-session"


def test_write_handoff_captures_recent_transcript(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    project_dir.mkdir()

    handoff_path = write_handoff(
        project_dir,
        session_id="session-123",
        transcript_lines=[
            "User: keep watching the limit",
            "Claude: still working",
            "Claude: usage limit reached",
        ],
        reason="usage-limit",
    )

    body = handoff_path.read_text(encoding="utf-8")
    assert "session-123" in body
    assert "usage-limit" in body
    assert "still working" in body
    assert handoff_path.parent.name == "handoffs"


@pytest.mark.parametrize(
    ("session_id", "expected"),
    [
        ("abc123", ["claude", "--resume", "abc123"]),
        (None, ["claude", "--continue"]),
    ],
)
def test_build_resume_command(session_id: str | None, expected: list[str]) -> None:
    assert build_resume_command("claude", session_id) == expected


def test_wait_seconds_for_limit_event_preserves_zero_second_resume() -> None:
    config = AutoResumeConfig(enabled=True, wait_seconds=18000, transcript_lines=400)
    event = LimitEvent(
        raw_message="Claude AI usage limit reached|1",
        reset_at=datetime.fromtimestamp(1, tz=timezone.utc),
        wait_seconds=0,
    )

    assert wait_seconds_for_limit_event(event, config) == 0
