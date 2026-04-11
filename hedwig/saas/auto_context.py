"""
Auto Context Inference — zero-config criteria generation.

Given SNS handles, free-text bio, and optional links, the engine:
1. Uses r.jina.ai web search to fetch public profile data for each SNS
2. Analyzes content patterns (topics, vocabulary, engagement patterns)
3. Infers role, interests, anti-patterns
4. Generates a complete criteria.yaml automatically

This replaces the manual Socratic onboarding for users who just want
to start without answering questions. Socratic is still available
for users who want fine control.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

INFERENCE_PROMPT = """\
You are Hedwig's Auto Context Inference Engine.

A new user just signed up. Instead of going through Socratic onboarding,
they gave you their SNS handles and a free-text bio. Your job: figure out
what kind of AI signals they care about and generate a complete criteria
profile.

USER INPUT:
Free-text bio: {bio}

SNS handles:
{handles}

Public profile data (fetched from web):
{profile_data}

YOUR TASK:
1. Identify the user's role/profession (developer, founder, researcher, designer, PM, etc.)
2. Identify their domain focus (AI agents, ML research, dev tools, design, business, etc.)
3. Identify content patterns from their SNS activity:
   - What topics do they post about?
   - What kind of accounts do they follow?
   - What language/jargon do they use?
4. Infer what AI signals would be valuable to them
5. Infer what they would NOT want (anti-patterns)
6. Generate a complete criteria profile

OUTPUT (strict JSON):
```json
{{
  "inferred_role": "string — best guess at role/profession",
  "inferred_focus": ["array of focus areas"],
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation of how you inferred this",
  "criteria": {{
    "identity": {{
      "role": "...",
      "focus": ["...", "..."]
    }},
    "signal_preferences": {{
      "care_about": [
        "specific topics this user likely cares about"
      ],
      "ignore": [
        "topics this user likely wants filtered out"
      ]
    }},
    "urgency_rules": {{
      "alert": ["conditions that warrant immediate alerts"],
      "digest": ["conditions for daily digest"],
      "skip": ["conditions to skip"]
    }},
    "context": {{
      "current_projects": ["inferred current work"],
      "interests": ["broader interests"]
    }},
    "source_priorities": {{
      "high": ["sources that match this user best"],
      "low": ["sources less relevant"]
    }}
  }},
  "first_questions": [
    "1-3 quick questions the user could answer to refine this further (optional)"
  ]
}}
```

RULES:
- Be specific, not generic. "AI" is too broad. "AI agent frameworks like LangChain, CrewAI" is good.
- If profile data is sparse, lean on the bio. If bio is sparse, lean on SNS patterns.
- Confidence below 0.5 means you should suggest the user run Socratic onboarding.
- Always include Devil's Advocate friendly anti-patterns (hype, marketing fluff, etc.)
- Match Korean output if the user's bio/handles are Korean.
"""


class AutoContextInference:
    """Infer user context from SNS handles + bio, generate criteria."""

    def __init__(self, llm_client=None):
        self._llm = llm_client

    async def infer(
        self,
        bio: str = "",
        sns_handles: dict[str, str] | None = None,
        extra_links: list[str] | None = None,
    ) -> dict:
        """Run inference and return criteria + metadata.

        Args:
            bio: Free-text bio from user
            sns_handles: {"x": "@username", "github": "username", ...}
            extra_links: Additional URLs to fetch (portfolio, blog, etc.)

        Returns:
            {
                "criteria": {...},
                "inferred_role": "...",
                "confidence": 0.0-1.0,
                "reasoning": "...",
                "first_questions": [...]
            }
        """
        sns_handles = sns_handles or {}
        extra_links = extra_links or []

        # Step 1: Fetch public profile data from SNS handles + extra links
        profile_data = await self._fetch_profile_data(sns_handles, extra_links)

        # Step 2: Use LLM to infer context and generate criteria
        if not self._llm:
            return self._fallback_inference(bio, sns_handles)

        prompt = INFERENCE_PROMPT.format(
            bio=bio or "(not provided)",
            handles=self._format_handles(sns_handles),
            profile_data=profile_data or "(none fetched)",
        )

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.4,
                max_tokens=2500,
            )
            reply = response.choices[0].message.content or ""
            result = self._parse_json(reply)
            if result:
                return result
        except Exception as e:
            logger.warning(f"Auto context inference failed: {e}")

        return self._fallback_inference(bio, sns_handles)

    async def _fetch_profile_data(
        self,
        sns_handles: dict[str, str],
        extra_links: list[str],
    ) -> str:
        """Fetch public profile data via r.jina.ai for each SNS handle."""
        from hedwig.engine.normalizer import normalize_content
        from hedwig.models import Platform, RawPost
        from datetime import datetime, timezone
        import asyncio

        # Build URLs from handles
        urls: list[tuple[str, str]] = []
        for platform, handle in sns_handles.items():
            handle = handle.lstrip("@")
            if not handle:
                continue
            if platform == "x" or platform == "twitter":
                urls.append(("x", f"https://x.com/{handle}"))
            elif platform == "github":
                urls.append(("github", f"https://github.com/{handle}"))
            elif platform == "linkedin":
                urls.append(("linkedin", f"https://linkedin.com/in/{handle}"))
            elif platform == "instagram":
                urls.append(("instagram", f"https://instagram.com/{handle}"))
            elif platform == "threads":
                urls.append(("threads", f"https://threads.net/@{handle}"))
            elif platform == "bluesky":
                urls.append(("bluesky", f"https://bsky.app/profile/{handle}"))
            elif platform == "tiktok":
                urls.append(("tiktok", f"https://tiktok.com/@{handle}"))
            elif platform == "youtube":
                urls.append(("youtube", f"https://youtube.com/@{handle}"))
            elif platform == "medium":
                urls.append(("medium", f"https://medium.com/@{handle}"))
            elif platform == "substack":
                urls.append(("substack", f"https://{handle}.substack.com"))

        for link in extra_links:
            urls.append(("extra", link))

        # Fetch all in parallel via r.jina.ai
        async def fetch_one(label: str, url: str) -> str:
            fake_post = RawPost(
                platform=Platform.WEB_SEARCH,
                external_id=url,
                title="",
                url=url,
                published_at=datetime.now(tz=timezone.utc),
            )
            content = await normalize_content(fake_post, timeout=15.0)
            return f"\n=== {label} ({url}) ===\n{content[:3000]}\n"

        if not urls:
            return ""

        results = await asyncio.gather(
            *[fetch_one(label, url) for label, url in urls],
            return_exceptions=True,
        )
        chunks = [r for r in results if isinstance(r, str)]
        return "\n".join(chunks)

    def _format_handles(self, handles: dict[str, str]) -> str:
        if not handles:
            return "(none provided)"
        lines = []
        for platform, handle in handles.items():
            if handle:
                lines.append(f"  {platform}: {handle}")
        return "\n".join(lines) if lines else "(none provided)"

    def _parse_json(self, text: str) -> Optional[dict]:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            logger.warning("Failed to parse auto-context LLM response as JSON")
            return None

    def _fallback_inference(self, bio: str, handles: dict[str, str]) -> dict:
        """Minimal fallback when LLM is unavailable."""
        return {
            "inferred_role": "AI builder",
            "inferred_focus": ["AI"],
            "confidence": 0.3,
            "reasoning": "Fallback: no LLM available, using generic AI builder profile",
            "criteria": {
                "identity": {
                    "role": "AI builder",
                    "focus": ["AI agents", "LLM tooling"],
                },
                "signal_preferences": {
                    "care_about": [
                        "Real adoption signals (not hype)",
                        "New tool releases",
                        "Practical paper applications",
                    ],
                    "ignore": [
                        "Pure marketing fluff",
                        "Unsubstantiated predictions",
                        "Repeated old news",
                    ],
                },
                "urgency_rules": {
                    "alert": ["Major model release", "Breaking API change"],
                    "digest": ["Interesting technical discussion"],
                    "skip": ["Hype-driven speculation"],
                },
                "context": {
                    "current_projects": [],
                    "interests": ["AI agents", "LLM tooling"],
                },
                "source_priorities": {
                    "high": ["x", "github", "hackernews"],
                    "low": ["instagram", "tiktok"],
                },
            },
            "first_questions": [
                "What's your main project right now?",
                "What kind of AI tools do you build?",
            ],
        }
