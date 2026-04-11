"""Test that get_operator_openai_key raises a clear error when the key is missing."""

import pytest

from hedwig.saas.operator_keys import get_operator_openai_key


def test_get_operator_openai_key_raises_when_missing(monkeypatch):
    """get_operator_openai_key must raise RuntimeError with a helpful message
    when OPERATOR_OPENAI_KEY is not set."""
    monkeypatch.delenv("OPERATOR_OPENAI_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # The module reads the env var at import time, so patch the module-level constant
    import hedwig.saas.operator_keys as mod
    monkeypatch.setattr(mod, "OPERATOR_OPENAI_KEY", "")

    with pytest.raises(RuntimeError) as excinfo:
        get_operator_openai_key()

    message = str(excinfo.value)
    assert "OPERATOR_OPENAI_KEY" in message
    assert "SaaS mode" in message
    assert "shared OpenAI key" in message
