from __future__ import annotations

from collections import Counter
from typing import Literal

from pydantic import BaseModel, Field


CardType = Literal["stat", "trend", "opportunity", "source_highlight"]


class DashboardCard(BaseModel):
    type: CardType
    data: dict[str, object] = Field(default_factory=dict)


class DashboardLayoutSpec(BaseModel):
    cards: list[DashboardCard] = Field(default_factory=list)


class GenerativeDashboard:
    """Rule-based dashboard skeleton for future generative UI work."""

    def build_layout(
        self,
        *,
        user_criteria: dict | None,
        recent_signals: list[dict] | None,
        dashboard_stats: dict | None = None,
    ) -> dict[str, object]:
        signals = list(recent_signals or [])
        stats = dict(dashboard_stats or {})
        focus_summary = self._focus_summary(user_criteria or {})
        source_counts = Counter(self._source_name(signal) for signal in signals if self._source_name(signal))
        total_recent = len(signals)
        top_source = self._top_source(source_counts, stats)
        top_source_signals = [
            signal for signal in signals if self._source_name(signal) == top_source
        ] if top_source else []
        opportunity_signal = self._pick_opportunity_signal(signals)

        layout = DashboardLayoutSpec(
            cards=[
                DashboardCard(
                    type="stat",
                    data={
                        "title": "Dashboard Pulse",
                        "total_signals": int(stats.get("total_signals", total_recent) or total_recent),
                        "signals_considered": total_recent,
                        "upvote_ratio": round(float(stats.get("upvote_ratio", 0.0) or 0.0), 2),
                        "days_active": int(stats.get("days_active", 0) or 0),
                        "focus_summary": focus_summary,
                    },
                ),
                DashboardCard(
                    type="trend",
                    data={
                        "title": "Current Trend",
                        "source": top_source or "No source data",
                        "count": int(source_counts.get(top_source or "", 0)),
                        "share_percent": self._share_percent(
                            count=int(source_counts.get(top_source or "", 0)),
                            total=total_recent,
                        ),
                        "examples": [
                            str(signal.get("title") or "").strip()
                            for signal in top_source_signals[:3]
                            if str(signal.get("title") or "").strip()
                        ],
                        "summary": self._trend_summary(
                            top_source=top_source,
                            count=int(source_counts.get(top_source or "", 0)),
                            total_recent=total_recent,
                            focus_summary=focus_summary,
                        ),
                    },
                ),
                DashboardCard(
                    type="opportunity",
                    data={
                        "title": str(opportunity_signal.get("title") or "No standout opportunity yet"),
                        "source": self._source_name(opportunity_signal) or "Awaiting signals",
                        "url": str(opportunity_signal.get("url") or ""),
                        "note": self._opportunity_note(opportunity_signal),
                        "relevance_score": round(
                            float(opportunity_signal.get("relevance_score", 0.0) or 0.0), 2
                        ),
                    },
                ),
                DashboardCard(
                    type="source_highlight",
                    data={
                        "title": "Source Highlight",
                        "source": top_source or "No source data",
                        "signal_count": int(source_counts.get(top_source or "", 0)),
                        "share_percent": self._share_percent(
                            count=int(source_counts.get(top_source or "", 0)),
                            total=total_recent,
                        ),
                        "sample_titles": [
                            str(signal.get("title") or "").strip()
                            for signal in top_source_signals[:2]
                            if str(signal.get("title") or "").strip()
                        ],
                    },
                ),
            ]
        )
        return layout.model_dump()

    def _focus_summary(self, user_criteria: dict) -> str:
        for key in ("interests", "focus_areas", "topics", "projects"):
            values = user_criteria.get(key)
            if isinstance(values, list):
                items = [str(item).strip() for item in values if str(item).strip()]
                if items:
                    return ", ".join(items[:2])
            if isinstance(values, str) and values.strip():
                return values.strip()
        return "No saved focus areas"

    def _source_name(self, signal: dict) -> str:
        return str(signal.get("platform") or signal.get("source") or "").strip()

    def _top_source(self, source_counts: Counter[str], dashboard_stats: dict) -> str:
        if source_counts:
            return source_counts.most_common(1)[0][0]

        top_sources = dashboard_stats.get("top_5_sources") or []
        if isinstance(top_sources, list):
            for entry in top_sources:
                if not isinstance(entry, dict):
                    continue
                value = str(entry.get("source") or entry.get("platform") or "").strip()
                if value:
                    return value
        return ""

    def _pick_opportunity_signal(self, signals: list[dict]) -> dict:
        if not signals:
            return {}

        ranked = sorted(
            signals,
            key=lambda signal: (
                1 if str(signal.get("opportunity_note") or "").strip() else 0,
                float(signal.get("relevance_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        return ranked[0]

    def _opportunity_note(self, signal: dict) -> str:
        for key in ("opportunity_note", "why_relevant", "content"):
            value = str(signal.get(key) or "").strip()
            if value:
                return value
        return "The current signal set does not have a clear opening yet."

    def _trend_summary(
        self,
        *,
        top_source: str,
        count: int,
        total_recent: int,
        focus_summary: str,
    ) -> str:
        if not top_source or count <= 0 or total_recent <= 0:
            return f"Recent activity will appear here once signals align with {focus_summary.lower()}."
        return (
            f"{top_source} produced {count} of the last {total_recent} signals "
            f"while tracking {focus_summary.lower()}."
        )

    def _share_percent(self, *, count: int, total: int) -> int:
        if count <= 0 or total <= 0:
            return 0
        return round((count / total) * 100)
