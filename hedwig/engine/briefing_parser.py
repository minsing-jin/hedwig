"""Parse Hedwig briefing markdown into structured ontology fields (G10).

seed.yaml briefing entity declares structured fields:
  trend_patterns, opportunity_hypotheses, exploration_suggestions,
  evolution_report

The current briefing pipeline emits a single markdown string — readers
get raw text. This parser walks the markdown and pulls section bullets
into typed lists so consumers (UI cards, analytics, exports) get the
structured shape declared in the spec.

The parser is intentionally tolerant — it looks for canonical section
headings used in engine/briefing.py prompts and returns empty lists for
sections that don't appear.
"""
from __future__ import annotations

import re

# Map of canonical regex → ontology field
SECTION_PATTERNS = {
    "alerts":        re.compile(r"^#{2,3}\s*(?:🔴|즉시 주목|Alert)", re.IGNORECASE),
    "trend_patterns": re.compile(r"^#{2,3}\s*(?:🟡|오늘의 주요 흐름|핵심 트렌드|주요 흐름|trend)", re.IGNORECASE),
    "highlights":    re.compile(r"^#{2,3}\s*(?:🟢|참고할 만한|Top|highlight)", re.IGNORECASE),
    "weak_signals":  re.compile(r"^#{2,3}\s*(?:📈|약신호|weak signal)", re.IGNORECASE),
    "opportunity_hypotheses": re.compile(r"^#{2,3}\s*(?:🎯|기회 포착|기회|opportunity)", re.IGNORECASE),
    "exploration_suggestions": re.compile(r"^#{2,3}\s*(?:💡|인사이트|exploration|insight)", re.IGNORECASE),
    "overheating_warnings":   re.compile(r"^#{2,3}\s*(?:⚖️|과열 경고|overheat)", re.IGNORECASE),
}

BULLET_RE = re.compile(r"^\s*[-•*]\s+(.*)")


def parse_briefing(markdown: str) -> dict:
    """Return a structured dict matching seed.yaml briefing ontology fields.

    Result shape:
        {
          "alerts": [str],
          "trend_patterns": [str],
          "highlights": [str],
          "weak_signals": [str],
          "opportunity_hypotheses": [str],
          "exploration_suggestions": [str],
          "overheating_warnings": [str],
          "raw_sections": {section_name: text}
        }
    """
    out: dict[str, list[str] | dict] = {k: [] for k in SECTION_PATTERNS}
    raw_sections: dict[str, str] = {}

    if not markdown:
        out["raw_sections"] = raw_sections
        return out

    lines = markdown.splitlines()
    current_field: str | None = None
    current_buf: list[str] = []

    def flush():
        nonlocal current_field, current_buf
        if current_field and current_buf:
            text = "\n".join(current_buf).strip()
            if text:
                raw_sections[current_field] = text
                # Also extract bullets as list items
                bullets: list[str] = []
                for ln in current_buf:
                    m = BULLET_RE.match(ln)
                    if m:
                        bullets.append(m.group(1).strip())
                if bullets:
                    out[current_field] = bullets
                else:
                    # No bullets — keep prose as a single-item list
                    out[current_field] = [text[:500]]
        current_buf = []

    for line in lines:
        matched_field: str | None = None
        for field, pat in SECTION_PATTERNS.items():
            if pat.search(line):
                matched_field = field
                break
        if matched_field is not None:
            flush()
            current_field = matched_field
            continue
        if current_field is not None:
            current_buf.append(line)
    flush()

    out["raw_sections"] = raw_sections
    return out
