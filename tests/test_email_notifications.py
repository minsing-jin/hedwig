"""
AC-3: alert-level signals trigger SMTP email notifications.
"""
from __future__ import annotations

from email.message import EmailMessage

import pytest


def _build_signal(*, signal_id: str, urgency: str = "alert"):
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel

    raw = RawPost(
        platform=Platform.REDDIT,
        external_id=signal_id,
        title="Major AI model release",
        url="https://example.com/ai-model",
        content="A frontier model launch with pricing and API changes.",
        author="hedwig",
    )
    return ScoredSignal(
        raw=raw,
        relevance_score=0.94,
        urgency=UrgencyLevel(urgency),
        why_relevant="This changes the competitive baseline for AI products.",
        devils_advocate="Early benchmarks could be overstated.",
    )


def test_check_required_keys_accepts_smtp_alert_delivery(monkeypatch):
    """Daily and full runs should accept SMTP as the configured delivery channel."""
    from hedwig import config as config_mod

    monkeypatch.setattr(config_mod, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config_mod, "SLACK_WEBHOOK_ALERTS", "")
    monkeypatch.setattr(config_mod, "DISCORD_WEBHOOK_ALERTS", "")
    monkeypatch.setattr(config_mod, "SLACK_WEBHOOK_DAILY", "")
    monkeypatch.setattr(config_mod, "DISCORD_WEBHOOK_DAILY", "")
    monkeypatch.setattr(config_mod, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(config_mod, "SUPABASE_KEY", "supabase-service-key")
    monkeypatch.setattr(config_mod, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(config_mod, "SMTP_PORT", "587")
    monkeypatch.setattr(config_mod, "SMTP_USER", "alerts@example.com")
    monkeypatch.setattr(config_mod, "SMTP_PASS", "top-secret")
    monkeypatch.setattr(config_mod, "SMTP_FROM", "alerts@example.com")

    assert config_mod.check_required_keys("daily") == []
    assert config_mod.check_required_keys("full") == []


@pytest.mark.asyncio
async def test_email_alert_sends_message_via_smtp(monkeypatch):
    """send_alert should compose and send a plaintext SMTP message."""
    from hedwig.delivery import email as email_mod

    signal = _build_signal(signal_id="sig-alert")
    calls: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 10):
            calls["connect"] = (host, port, timeout)

        def __enter__(self):
            calls["entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb):
            calls["exited"] = True
            return False

        def ehlo(self):
            calls["ehlo"] = calls.get("ehlo", 0) + 1

        def has_extn(self, name: str) -> bool:
            calls["has_extn"] = name
            return True

        def starttls(self):
            calls["starttls"] = True

        def login(self, username: str, password: str):
            calls["login"] = (username, password)

        def send_message(self, message: EmailMessage):
            calls["message"] = message

    monkeypatch.setattr(email_mod, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_mod, "SMTP_PORT", "2525")
    monkeypatch.setattr(email_mod, "SMTP_USER", "alerts@example.com")
    monkeypatch.setattr(email_mod, "SMTP_PASS", "top-secret")
    monkeypatch.setattr(email_mod, "SMTP_FROM", "alerts@example.com")
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)

    delivered = await email_mod.send_alert(signal)

    assert delivered is True
    assert calls["connect"] == ("smtp.example.com", 2525, 10)
    assert calls["ehlo"] == 2
    assert calls["has_extn"] == "starttls"
    assert calls["starttls"] is True
    assert calls["login"] == ("alerts@example.com", "top-secret")

    message = calls["message"]
    assert isinstance(message, EmailMessage)
    assert message["From"] == "alerts@example.com"
    assert message["To"] == "alerts@example.com"
    assert "Major AI model release" in message["Subject"]
    body = message.get_content()
    assert "A frontier model launch with pricing and API changes." in body
    assert "Why it matters:" in body
    assert "Devil's advocate:" in body


@pytest.mark.asyncio
async def test_email_alert_sanitizes_header_injection_in_titles(monkeypatch):
    """send_alert should sanitize CR/LF in subjects instead of raising."""
    from hedwig.delivery import email as email_mod

    signal = _build_signal(signal_id="sig-malformed")
    signal.raw.title = "Major AI model release\r\n한글 Δ 🚀\nBcc: victim@example.com"
    calls: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 10):
            calls["connect"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            return None

        def has_extn(self, name: str) -> bool:
            return False

        def send_message(self, message: EmailMessage):
            calls["message"] = message

    monkeypatch.setattr(email_mod, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_mod, "SMTP_PORT", "2525")
    monkeypatch.setattr(email_mod, "SMTP_USER", "")
    monkeypatch.setattr(email_mod, "SMTP_PASS", "")
    monkeypatch.setattr(email_mod, "SMTP_FROM", "alerts@example.com")
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)

    delivered = await email_mod.send_alert(signal)

    assert delivered is True
    message = calls["message"]
    assert isinstance(message, EmailMessage)
    assert "\n" not in message["Subject"]
    assert "\r" not in message["Subject"]
    assert "한글 Δ 🚀" in message["Subject"]
    assert "Bcc: victim@example.com" in message["Subject"]


@pytest.mark.asyncio
async def test_email_alert_refuses_authenticated_smtp_without_starttls(monkeypatch):
    """send_alert must not send credentials or mail over plaintext SMTP."""
    from hedwig.delivery import email as email_mod

    signal = _build_signal(signal_id="sig-no-starttls")
    calls: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int = 10):
            calls["connect"] = (host, port, timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def ehlo(self):
            calls["ehlo"] = calls.get("ehlo", 0) + 1

        def has_extn(self, name: str) -> bool:
            calls["has_extn"] = name
            return False

        def login(self, username: str, password: str):
            calls["login"] = (username, password)

        def send_message(self, message: EmailMessage):
            calls["message"] = message

    monkeypatch.setattr(email_mod, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_mod, "SMTP_PORT", "2525")
    monkeypatch.setattr(email_mod, "SMTP_USER", "alerts@example.com")
    monkeypatch.setattr(email_mod, "SMTP_PASS", "top-secret")
    monkeypatch.setattr(email_mod, "SMTP_FROM", "alerts@example.com")
    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)

    delivered = await email_mod.send_alert(signal)

    assert delivered is False
    assert calls["connect"] == ("smtp.example.com", 2525, 10)
    assert calls["ehlo"] == 1
    assert calls["has_extn"] == "starttls"
    assert "login" not in calls
    assert "message" not in calls


@pytest.mark.asyncio
async def test_run_daily_sends_email_for_alert_signals(monkeypatch):
    """run_daily should fan alert-level signals into the SMTP notifier."""
    from hedwig import config as config_mod
    from hedwig.delivery import discord as discord_mod
    from hedwig.delivery import email as email_mod
    from hedwig.delivery import slack as slack_mod
    from hedwig.engine import briefing as briefing_mod
    from hedwig.engine import scorer as scorer_mod
    from hedwig.storage import supabase as supabase_mod
    import hedwig.main as main_mod

    alert_signal = _build_signal(signal_id="sig-alert", urgency="alert")
    digest_signal = _build_signal(signal_id="sig-digest", urgency="digest")
    email_calls: list[str] = []
    briefing_calls: list[list[str]] = []
    saved_counts: list[int] = []

    async def fake_collect_all(enabled_only: bool = True) -> list[object]:
        return [object()]

    async def fake_normalize_and_prescore(posts: list[object], criteria_keywords: list[str]) -> list[object]:
        return posts

    async def fake_score_posts(posts: list[object]) -> list[object]:
        return [alert_signal, digest_signal]

    async def fake_email_alert(signal):
        email_calls.append(signal.raw.external_id)
        return True

    async def fake_noop(*args, **kwargs):
        return True

    async def fake_generate_daily_briefing(signals):
        briefing_calls.append([signal.raw.external_id for signal in signals])
        return "Daily briefing text"

    async def fake_run_evolution_daily():
        return None

    monkeypatch.setattr(config_mod, "check_required_keys", lambda mode="full": [])
    monkeypatch.setattr(config_mod, "SLACK_WEBHOOK_ALERTS", "")
    monkeypatch.setattr(config_mod, "DISCORD_WEBHOOK_ALERTS", "")
    monkeypatch.setattr(config_mod, "SLACK_WEBHOOK_DAILY", "")
    monkeypatch.setattr(config_mod, "DISCORD_WEBHOOK_DAILY", "")
    monkeypatch.setattr(config_mod, "smtp_alerts_configured", lambda: True)
    monkeypatch.setattr(main_mod, "collect_all", fake_collect_all)
    monkeypatch.setattr(main_mod, "_extract_keywords_from_criteria", lambda: ["ai"])
    monkeypatch.setattr(main_mod, "normalize_and_prescore", fake_normalize_and_prescore)
    monkeypatch.setattr(main_mod, "run_evolution_daily", fake_run_evolution_daily)
    monkeypatch.setattr(scorer_mod, "score_posts", fake_score_posts)
    monkeypatch.setattr(email_mod, "send_alert", fake_email_alert)
    monkeypatch.setattr(slack_mod, "send_alert", fake_noop)
    monkeypatch.setattr(discord_mod, "send_alert", fake_noop)
    monkeypatch.setattr(slack_mod, "send_daily_briefing", fake_noop)
    monkeypatch.setattr(discord_mod, "send_daily_briefing", fake_noop)
    monkeypatch.setattr(briefing_mod, "generate_daily_briefing", fake_generate_daily_briefing)
    monkeypatch.setattr(
        supabase_mod,
        "save_signals",
        lambda signals: saved_counts.append(len(signals)) or len(signals),
    )

    await main_mod.run_daily()

    assert email_calls == ["sig-alert"]
    assert briefing_calls == [["sig-alert", "sig-digest"]]
    assert saved_counts == [2]


@pytest.mark.asyncio
async def test_run_daily_sends_email_for_digest_only_briefings(monkeypatch):
    """run_daily should use SMTP for digest-only daily briefings when SMTP is standalone."""
    from hedwig import config as config_mod
    from hedwig.delivery import discord as discord_mod
    from hedwig.delivery import email as email_mod
    from hedwig.delivery import slack as slack_mod
    from hedwig.engine import briefing as briefing_mod
    from hedwig.engine import scorer as scorer_mod
    from hedwig.storage import supabase as supabase_mod
    import hedwig.main as main_mod

    digest_signal = _build_signal(signal_id="sig-digest-only", urgency="digest")
    email_calls: list[str] = []
    briefing_calls: list[list[str]] = []
    saved_counts: list[int] = []

    async def fake_collect_all(enabled_only: bool = True) -> list[object]:
        return [object()]

    async def fake_normalize_and_prescore(posts: list[object], criteria_keywords: list[str]) -> list[object]:
        return posts

    async def fake_score_posts(posts: list[object]) -> list[object]:
        return [digest_signal]

    async def fake_email_daily(briefing_text: str):
        email_calls.append(briefing_text)
        return True

    async def fake_noop(*args, **kwargs):
        return True

    async def fake_generate_daily_briefing(signals):
        briefing_calls.append([signal.raw.external_id for signal in signals])
        return "Daily SMTP briefing text"

    async def fake_run_evolution_daily():
        return None

    monkeypatch.setattr(config_mod, "check_required_keys", lambda mode="full": [])
    monkeypatch.setattr(config_mod, "SLACK_WEBHOOK_ALERTS", "")
    monkeypatch.setattr(config_mod, "DISCORD_WEBHOOK_ALERTS", "")
    monkeypatch.setattr(config_mod, "SLACK_WEBHOOK_DAILY", "")
    monkeypatch.setattr(config_mod, "DISCORD_WEBHOOK_DAILY", "")
    monkeypatch.setattr(config_mod, "smtp_alerts_configured", lambda: True)
    monkeypatch.setattr(main_mod, "collect_all", fake_collect_all)
    monkeypatch.setattr(main_mod, "_extract_keywords_from_criteria", lambda: ["ai"])
    monkeypatch.setattr(main_mod, "normalize_and_prescore", fake_normalize_and_prescore)
    monkeypatch.setattr(main_mod, "run_evolution_daily", fake_run_evolution_daily)
    monkeypatch.setattr(scorer_mod, "score_posts", fake_score_posts)
    monkeypatch.setattr(email_mod, "send_alert", fake_noop)
    monkeypatch.setattr(email_mod, "send_daily_briefing", fake_email_daily)
    monkeypatch.setattr(slack_mod, "send_alert", fake_noop)
    monkeypatch.setattr(discord_mod, "send_alert", fake_noop)
    monkeypatch.setattr(slack_mod, "send_daily_briefing", fake_noop)
    monkeypatch.setattr(discord_mod, "send_daily_briefing", fake_noop)
    monkeypatch.setattr(briefing_mod, "generate_daily_briefing", fake_generate_daily_briefing)
    monkeypatch.setattr(
        supabase_mod,
        "save_signals",
        lambda signals: saved_counts.append(len(signals)) or len(signals),
    )

    await main_mod.run_daily()

    assert briefing_calls == [["sig-digest-only"]]
    assert email_calls == ["Daily SMTP briefing text"]
    assert saved_counts == [1]


@pytest.mark.asyncio
async def test_run_weekly_sends_email_briefing_when_smtp_is_standalone(monkeypatch):
    """run_weekly should use SMTP when it is the only configured delivery channel."""
    from hedwig import config as config_mod
    from hedwig.delivery import discord as discord_mod
    from hedwig.delivery import email as email_mod
    from hedwig.delivery import slack as slack_mod
    from hedwig.engine import briefing as briefing_mod
    from hedwig.storage import supabase as supabase_mod
    import hedwig.main as main_mod

    weekly_rows = [
        {
            "platform": "reddit",
            "external_id": "sig-weekly",
            "title": "Weekly AI infrastructure shift",
            "url": "https://example.com/weekly",
            "content": "A week of major infra changes.",
            "author": "hedwig",
            "platform_score": 10,
            "relevance_score": 0.81,
            "urgency": "digest",
            "why_relevant": "Infrastructure cost curves changed this week.",
            "devils_advocate": "Short-term hype may fade.",
        }
    ]
    email_calls: list[str] = []
    briefing_calls: list[list[str]] = []

    async def fake_email_weekly(briefing_text: str):
        email_calls.append(briefing_text)
        return True

    async def fake_noop(*args, **kwargs):
        return True

    async def fake_generate_weekly_briefing(signals):
        briefing_calls.append([signal.raw.external_id for signal in signals])
        return "Weekly SMTP briefing text"

    async def fake_run_evolution_weekly(total_signals: int = 0):
        return None

    monkeypatch.setattr(config_mod, "check_required_keys", lambda mode="full": [])
    monkeypatch.setattr(config_mod, "smtp_alerts_configured", lambda: True)
    monkeypatch.setattr(supabase_mod, "get_recent_signals", lambda days=7: weekly_rows)
    monkeypatch.setattr(briefing_mod, "generate_weekly_briefing", fake_generate_weekly_briefing)
    monkeypatch.setattr(email_mod, "send_weekly_briefing", fake_email_weekly)
    monkeypatch.setattr(slack_mod, "send_weekly_briefing", fake_noop)
    monkeypatch.setattr(discord_mod, "send_weekly_briefing", fake_noop)
    monkeypatch.setattr(main_mod, "run_evolution_weekly", fake_run_evolution_weekly)

    await main_mod.run_weekly()

    assert briefing_calls == [["sig-weekly"]]
    assert email_calls == ["Weekly SMTP briefing text"]
