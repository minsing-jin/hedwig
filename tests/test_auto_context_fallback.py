"""Tests for AutoContextInference fallback — AC 2.

Verifies that when no LLM client is provided, the fallback
returns a valid criteria dict with all required keys and structure.
"""
from __future__ import annotations

import pytest

from hedwig.saas.auto_context import AutoContextInference


class TestAutoContextFallback:
    """AutoContextInference._fallback_inference returns valid criteria."""

    def setup_method(self):
        # No LLM client → always uses fallback path
        self.engine = AutoContextInference(llm_client=None)

    def _run_fallback(self, bio: str = "", handles: dict | None = None) -> dict:
        return self.engine._fallback_inference(bio, handles or {})

    # ── Top-level keys ──────────────────────────────────────────────

    def test_fallback_has_required_top_keys(self):
        result = self._run_fallback()
        for key in ("inferred_role", "inferred_focus", "confidence", "reasoning", "criteria"):
            assert key in result, f"Missing top-level key: {key}"

    def test_fallback_has_first_questions(self):
        result = self._run_fallback()
        assert "first_questions" in result
        assert isinstance(result["first_questions"], list)
        assert len(result["first_questions"]) >= 1

    # ── Confidence ──────────────────────────────────────────────────

    def test_fallback_confidence_is_low(self):
        """Fallback should signal low confidence so UI can suggest Socratic."""
        result = self._run_fallback()
        assert 0.0 <= result["confidence"] <= 0.5

    # ── Criteria structure ──────────────────────────────────────────

    def test_criteria_has_identity(self):
        criteria = self._run_fallback()["criteria"]
        assert "identity" in criteria
        assert "role" in criteria["identity"]
        assert "focus" in criteria["identity"]
        assert isinstance(criteria["identity"]["focus"], list)

    def test_criteria_has_signal_preferences(self):
        criteria = self._run_fallback()["criteria"]
        prefs = criteria["signal_preferences"]
        assert "care_about" in prefs
        assert "ignore" in prefs
        assert isinstance(prefs["care_about"], list)
        assert isinstance(prefs["ignore"], list)
        assert len(prefs["care_about"]) >= 1
        assert len(prefs["ignore"]) >= 1

    def test_criteria_has_urgency_rules(self):
        criteria = self._run_fallback()["criteria"]
        rules = criteria["urgency_rules"]
        for key in ("alert", "digest", "skip"):
            assert key in rules, f"Missing urgency_rules.{key}"
            assert isinstance(rules[key], list)

    def test_criteria_has_context(self):
        criteria = self._run_fallback()["criteria"]
        ctx = criteria["context"]
        assert "current_projects" in ctx
        assert "interests" in ctx
        assert isinstance(ctx["interests"], list)

    def test_criteria_has_source_priorities(self):
        criteria = self._run_fallback()["criteria"]
        priorities = criteria["source_priorities"]
        assert "high" in priorities
        assert "low" in priorities
        assert isinstance(priorities["high"], list)
        assert isinstance(priorities["low"], list)
        assert len(priorities["high"]) >= 1

    # ── Values are non-empty strings ────────────────────────────────

    def test_inferred_role_is_nonempty_string(self):
        result = self._run_fallback()
        assert isinstance(result["inferred_role"], str)
        assert len(result["inferred_role"]) > 0

    def test_reasoning_is_nonempty_string(self):
        result = self._run_fallback()
        assert isinstance(result["reasoning"], str)
        assert len(result["reasoning"]) > 0

    # ── Async .infer() also falls back when no LLM ──────────────────

    @pytest.mark.asyncio
    async def test_infer_without_llm_uses_fallback(self):
        """Calling .infer() with no LLM client returns the fallback."""
        result = await self.engine.infer(bio="AI builder", sns_handles={})
        assert result["confidence"] <= 0.5
        assert "criteria" in result
        assert result["criteria"]["identity"]["role"]
