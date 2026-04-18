"""
GitHub Trending source — fetches trending repos from GitHub.

GitHub has no official trending API. Strategy:
  1. Scrape github.com/trending via r.jina.ai (clean markdown)
  2. Parse repo names/descriptions from the markdown
  3. Optionally use GitHub Search API for AI-related repos with recent stars

Filters for AI-related repos by default.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

GITHUB_TRENDING_URL = "https://github.com/trending"
GITHUB_SEARCH_API = "https://api.github.com/search/repositories"
JINA_READER = "https://r.jina.ai/"

AI_KEYWORDS = [
    "llm", "ai", "gpt", "transformer", "machine-learning", "deep-learning",
    "agent", "rag", "langchain", "openai", "anthropic", "diffusion",
    "neural", "nlp", "embedding", "fine-tune", "inference",
]


@register_source
class GitHubTrendingSource(Source):
    """AI-related trending repos from GitHub."""
    platform = Platform.CUSTOM
    plugin_id = "github_trending"
    display_name = "GitHub Trending"
    fetch_method = FetchMethod.SCRAPE

    def __init__(self, languages: list[str] | None = None, since: str = "daily"):
        self.languages = languages or ["python", "typescript", "rust", ""]
        self.since = since  # daily, weekly, monthly

    async def fetch(self, limit: int = 30) -> list[RawPost]:
        posts: list[RawPost] = []

        # Strategy 1: GitHub Search API (structured, reliable)
        api_posts = await self._fetch_from_search_api(limit)
        posts.extend(api_posts)

        # Strategy 2: Scrape trending page via r.jina.ai (catches non-API trending)
        if len(posts) < limit:
            scrape_posts = await self._fetch_from_trending_page(limit - len(posts))
            # Deduplicate
            seen = {p.external_id for p in posts}
            for p in scrape_posts:
                if p.external_id not in seen:
                    posts.append(p)
                    seen.add(p.external_id)

        return posts[:limit]

    async def _fetch_from_search_api(self, limit: int) -> list[RawPost]:
        """Use GitHub Search API to find recently-created AI repos with stars."""
        posts: list[RawPost] = []
        queries = [
            "topic:artificial-intelligence stars:>50 pushed:>2026-04-07",
            "topic:llm stars:>20 pushed:>2026-04-07",
            "topic:machine-learning stars:>50 pushed:>2026-04-07",
            "ai agent framework stars:>10 created:>2026-03-14",
        ]

        async with httpx.AsyncClient(timeout=15) as client:
            for query in queries:
                try:
                    resp = await client.get(
                        GITHUB_SEARCH_API,
                        params={
                            "q": query,
                            "sort": "stars",
                            "order": "desc",
                            "per_page": min(limit, 10),
                        },
                        headers={"Accept": "application/vnd.github.v3+json"},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for repo in data.get("items", []):
                        created = repo.get("created_at", "")
                        try:
                            published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            published = datetime.now(tz=timezone.utc)

                        posts.append(RawPost(
                            platform=Platform.CUSTOM,
                            external_id=repo.get("full_name", ""),
                            title=f"{repo.get('full_name', '')} — {repo.get('description', '')}"[:200],
                            url=repo.get("html_url", ""),
                            content=self._build_content(repo),
                            author=repo.get("owner", {}).get("login", ""),
                            score=repo.get("stargazers_count", 0),
                            comments_count=repo.get("forks_count", 0),
                            published_at=published,
                            extra={
                                "source": "github_trending",
                                "language": repo.get("language", ""),
                                "stars": repo.get("stargazers_count", 0),
                                "forks": repo.get("forks_count", 0),
                                "topics": repo.get("topics", []),
                            },
                        ))
                except Exception:
                    continue

        # Deduplicate
        seen: set[str] = set()
        unique: list[RawPost] = []
        for p in posts:
            if p.external_id not in seen:
                seen.add(p.external_id)
                unique.append(p)
        return unique[:limit]

    async def _fetch_from_trending_page(self, limit: int) -> list[RawPost]:
        """Scrape GitHub trending page via r.jina.ai and parse repos."""
        posts: list[RawPost] = []

        for lang in self.languages[:3]:
            url = GITHUB_TRENDING_URL
            if lang:
                url += f"/{lang}"
            url += f"?since={self.since}"

            try:
                async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                    resp = await client.get(
                        f"{JINA_READER}{url}",
                        headers={"Accept": "text/markdown", "x-respond-with": "markdown"},
                    )
                    if resp.status_code != 200:
                        continue

                    parsed = self._parse_trending_markdown(resp.text, lang)
                    posts.extend(parsed)
            except Exception:
                continue

        # Filter for AI-related
        ai_posts = [p for p in posts if self._is_ai_related(p)]
        return ai_posts[:limit]

    def _parse_trending_markdown(self, markdown: str, language: str) -> list[RawPost]:
        """Parse repo entries from trending page markdown."""
        posts: list[RawPost] = []

        # Look for repo patterns: owner/name or [owner/name](url)
        repo_pattern = re.compile(
            r'\[([a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+)\]\(https://github\.com/([^)]+)\)'
        )

        for match in repo_pattern.finditer(markdown):
            repo_name = match.group(1)
            repo_url = f"https://github.com/{match.group(2)}"

            # Try to extract description (text after the link)
            start = match.end()
            desc_text = markdown[start:start + 300].strip()
            # Clean up
            desc_text = desc_text.split("\n")[0][:200]

            posts.append(RawPost(
                platform=Platform.CUSTOM,
                external_id=repo_name,
                title=f"{repo_name} — {desc_text}"[:200] if desc_text else repo_name,
                url=repo_url,
                content=desc_text[:2000],
                author=repo_name.split("/")[0],
                published_at=datetime.now(tz=timezone.utc),
                extra={
                    "source": "github_trending",
                    "language": language,
                    "method": "trending_page_scrape",
                },
            ))

        return posts

    def _build_content(self, repo: dict) -> str:
        """Build a rich content string from GitHub API repo data."""
        parts = []
        if repo.get("description"):
            parts.append(repo["description"])
        parts.append(f"Stars: {repo.get('stargazers_count', 0)}")
        parts.append(f"Language: {repo.get('language', 'N/A')}")
        parts.append(f"Forks: {repo.get('forks_count', 0)}")
        if repo.get("topics"):
            parts.append(f"Topics: {', '.join(repo['topics'][:10])}")
        if repo.get("license", {}).get("name"):
            parts.append(f"License: {repo['license']['name']}")
        return "\n".join(parts)[:2000]

    def _is_ai_related(self, post: RawPost) -> bool:
        """Check if a post is AI-related based on title/content."""
        text = f"{post.title} {post.content}".lower()
        return any(kw in text for kw in AI_KEYWORDS)
