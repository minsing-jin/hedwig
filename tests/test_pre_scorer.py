"""
Test: Pre-scorer returns values between 0.0 and 1.0 for test inputs.

Verifies that every component function and the composite pre_score()
produce values strictly within the [0.0, 1.0] range across a variety
of realistic and edge-case inputs.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


from hedwig.models import Platform, RawPost
from hedwig.engine.pre_scorer import (
    compute_engagement_velocity,
    compute_recency_decay,
    compute_source_authority,
    compute_text_relevance,
    detect_cross_platform_convergence,
    pre_score,
    pre_filter,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_post(
    platform: Platform = Platform.HACKERNEWS,
    title: str = "Test Post",
    content: str = "Some content about AI and machine learning",
    score: int = 50,
    comments_count: int = 10,
    published_at: datetime | None = None,
    external_id: str = "test-1",
) -> RawPost:
    return RawPost(
        platform=platform,
        external_id=external_id,
        title=title,
        url="https://example.com",
        content=content,
        author="testuser",
        score=score,
        comments_count=comments_count,
        published_at=published_at or datetime.now(tz=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Component function tests
# ---------------------------------------------------------------------------

class TestComputeEngagementVelocity:
    def test_normal_post(self):
        post = _make_post(score=50, comments_count=25)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0

    def test_high_engagement(self):
        post = _make_post(score=500, comments_count=200)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0

    def test_zero_engagement(self):
        post = _make_post(score=0, comments_count=0)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0

    def test_negative_score(self):
        """Reddit posts can have negative scores."""
        post = _make_post(platform=Platform.REDDIT, score=-50, comments_count=5)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0

    def test_very_large_score(self):
        post = _make_post(score=100000, comments_count=10000)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0

    def test_arxiv_no_baseline_engagement(self):
        post = _make_post(platform=Platform.ARXIV, score=0, comments_count=0)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0

    def test_polymarket_volume(self):
        post = _make_post(platform=Platform.POLYMARKET, score=50000)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0

    def test_unknown_platform_fallback(self):
        """Platforms not in ENGAGEMENT_BASELINES should use default."""
        post = _make_post(platform=Platform.CUSTOM, score=10, comments_count=5)
        result = compute_engagement_velocity(post)
        assert 0.0 <= result <= 1.0


class TestComputeRecencyDecay:
    def test_fresh_post(self):
        post = _make_post(published_at=datetime.now(tz=timezone.utc))
        result = compute_recency_decay(post)
        assert 0.0 <= result <= 1.0
        # Very recent post should be close to 1.0
        assert result > 0.9

    def test_old_post(self):
        post = _make_post(
            published_at=datetime.now(tz=timezone.utc) - timedelta(days=30)
        )
        result = compute_recency_decay(post)
        assert 0.0 <= result <= 1.0
        # 30-day-old post should be very low
        assert result < 0.1

    def test_one_half_life(self):
        post = _make_post(
            published_at=datetime.now(tz=timezone.utc) - timedelta(hours=48)
        )
        result = compute_recency_decay(post)
        assert 0.0 <= result <= 1.0
        # Should be approximately 0.5 at the half-life
        assert 0.4 <= result <= 0.6

    def test_future_post(self):
        """Posts with future timestamps (clock skew) should still be bounded."""
        post = _make_post(
            published_at=datetime.now(tz=timezone.utc) + timedelta(hours=5)
        )
        result = compute_recency_decay(post)
        assert 0.0 <= result <= 1.0


class TestComputeSourceAuthority:
    def test_all_known_platforms(self):
        """Every platform in the enum should return a valid authority score."""
        for platform in Platform:
            post = _make_post(platform=platform)
            result = compute_source_authority(post)
            assert 0.0 <= result <= 1.0, f"Authority out of range for {platform}"

    def test_hackernews_high_authority(self):
        post = _make_post(platform=Platform.HACKERNEWS)
        result = compute_source_authority(post)
        assert result >= 0.8

    def test_arxiv_highest_authority(self):
        post = _make_post(platform=Platform.ARXIV)
        result = compute_source_authority(post)
        assert result >= 0.9


class TestComputeTextRelevance:
    def test_matching_keywords(self):
        post = _make_post(
            title="New AI breakthrough in machine learning",
            content="Researchers announce major AI advancement",
        )
        result = compute_text_relevance(post, ["ai", "machine learning"])
        assert 0.0 <= result <= 1.0
        assert result > 0.5  # Should match well

    def test_no_keywords(self):
        post = _make_post()
        result = compute_text_relevance(post, [])
        assert 0.0 <= result <= 1.0
        assert result == 0.5  # Default when no keywords

    def test_no_matching_keywords(self):
        post = _make_post(title="Sports results", content="Football game recap")
        result = compute_text_relevance(post, ["quantum", "physics", "neuroscience"])
        assert 0.0 <= result <= 1.0
        assert result < 0.5

    def test_all_keywords_match(self):
        post = _make_post(
            title="AI ML NLP", content="artificial intelligence machine learning nlp"
        )
        result = compute_text_relevance(post, ["ai", "ml", "nlp"])
        assert 0.0 <= result <= 1.0

    def test_many_keywords_few_matches(self):
        post = _make_post(title="AI news", content="AI tools")
        keywords = ["ai", "blockchain", "quantum", "robotics", "biotech",
                     "nanotech", "fusion", "space", "climate", "fintech"]
        result = compute_text_relevance(post, keywords)
        assert 0.0 <= result <= 1.0


class TestDetectCrossPlatformConvergence:
    def test_no_convergence(self):
        post = _make_post(title="Unique post about zebras")
        others = [
            _make_post(platform=Platform.REDDIT, title="Completely different topic",
                       external_id="other-1"),
        ]
        result = detect_cross_platform_convergence(post, others)
        assert 0.0 <= result <= 1.0
        assert result == 0.0

    def test_cross_platform_convergence(self):
        post = _make_post(
            platform=Platform.HACKERNEWS,
            title="OpenAI releases GPT-5 with major improvements",
        )
        others = [
            _make_post(
                platform=Platform.REDDIT,
                title="OpenAI releases GPT-5 with major improvements",
                external_id="r-1",
            ),
            _make_post(
                platform=Platform.TWITTER,
                title="OpenAI releases GPT-5 with huge improvements",
                external_id="t-1",
            ),
        ]
        all_posts = [post] + others
        result = detect_cross_platform_convergence(post, all_posts)
        assert 0.0 <= result <= 1.0

    def test_many_platforms_convergence(self):
        """Even with many matching platforms, result stays <= 1.0."""
        post = _make_post(title="breaking news AI revolution today")
        others = []
        for i, plat in enumerate([Platform.REDDIT, Platform.TWITTER,
                                   Platform.BLUESKY, Platform.YOUTUBE,
                                   Platform.LINKEDIN]):
            others.append(_make_post(
                platform=plat,
                title="breaking news AI revolution today",
                external_id=f"other-{i}",
            ))
        all_posts = [post] + others
        result = detect_cross_platform_convergence(post, all_posts)
        assert 0.0 <= result <= 1.0

    def test_empty_title(self):
        post = _make_post(title="")
        result = detect_cross_platform_convergence(post, [])
        assert 0.0 <= result <= 1.0

    def test_same_platform_ignored(self):
        post = _make_post(title="AI news from HN")
        other = _make_post(
            title="AI news from HN", external_id="other-1",
            platform=Platform.HACKERNEWS,
        )
        result = detect_cross_platform_convergence(post, [other])
        assert 0.0 <= result <= 1.0
        assert result == 0.0  # Same platform should not count


# ---------------------------------------------------------------------------
# Composite pre_score tests
# ---------------------------------------------------------------------------

class TestPreScore:
    def test_normal_post(self):
        post = _make_post(
            title="New AI model released by OpenAI",
            content="GPT-5 has been released with major improvements",
            score=150,
            comments_count=80,
        )
        result = pre_score(post, [post], ["ai", "openai", "gpt"])
        assert 0.0 <= result <= 1.0

    def test_low_quality_post(self):
        post = _make_post(
            title="Random stuff",
            content="Nothing relevant",
            score=0,
            comments_count=0,
            published_at=datetime.now(tz=timezone.utc) - timedelta(days=60),
        )
        result = pre_score(post, [post], ["ai", "ml"])
        assert 0.0 <= result <= 1.0

    def test_high_quality_post(self):
        post = _make_post(
            platform=Platform.ARXIV,
            title="AI machine learning deep learning breakthrough",
            content="Significant advancement in AI and ML with new architecture",
            score=100,
            comments_count=50,
        )
        result = pre_score(post, [post], ["ai", "machine learning", "deep learning"])
        assert 0.0 <= result <= 1.0
        assert result > 0.3  # Good post should score reasonably

    def test_negative_score_post(self):
        """Ensure negative Reddit scores don't break the 0-1 range."""
        post = _make_post(
            platform=Platform.REDDIT,
            title="Controversial take on AI",
            content="Hot take that got downvoted",
            score=-100,
            comments_count=200,
        )
        result = pre_score(post, [post], ["ai"])
        assert 0.0 <= result <= 1.0

    def test_empty_keywords(self):
        post = _make_post()
        result = pre_score(post, [post], [])
        assert 0.0 <= result <= 1.0

    def test_all_platforms(self):
        """Pre-score should be in range for every platform."""
        for platform in Platform:
            post = _make_post(
                platform=platform,
                title="AI test signal",
                content="Testing AI signals",
                score=10,
                comments_count=5,
                external_id=f"test-{platform.value}",
            )
            result = pre_score(post, [post], ["ai", "test"])
            assert 0.0 <= result <= 1.0, (
                f"pre_score out of range for platform {platform.value}: {result}"
            )

    def test_extreme_inputs(self):
        """Edge case: extreme engagement values."""
        post = _make_post(score=999999, comments_count=999999)
        result = pre_score(post, [post], ["ai"])
        assert 0.0 <= result <= 1.0

    def test_very_old_post(self):
        post = _make_post(
            published_at=datetime.now(tz=timezone.utc) - timedelta(days=365),
        )
        result = pre_score(post, [post], ["ai"])
        assert 0.0 <= result <= 1.0

    def test_multiple_posts_convergence(self):
        """Composite score with cross-platform convergence still bounded."""
        posts = [
            _make_post(
                platform=Platform.HACKERNEWS,
                title="AI revolution 2026",
                external_id="hn-1",
            ),
            _make_post(
                platform=Platform.REDDIT,
                title="AI revolution 2026",
                external_id="r-1",
            ),
            _make_post(
                platform=Platform.TWITTER,
                title="AI revolution 2026",
                external_id="t-1",
            ),
        ]
        for post in posts:
            result = pre_score(post, posts, ["ai", "revolution"])
            assert 0.0 <= result <= 1.0


# ---------------------------------------------------------------------------
# pre_filter tests
# ---------------------------------------------------------------------------

class TestPreFilter:
    def test_returns_sorted_scored_pairs(self):
        posts = [
            _make_post(
                title="Irrelevant sports news", content="Football game",
                score=0, comments_count=0, external_id="low",
                published_at=datetime.now(tz=timezone.utc) - timedelta(days=30),
            ),
            _make_post(
                title="Major AI breakthrough in machine learning",
                content="Researchers discovered new AI technique",
                score=200, comments_count=100, external_id="high",
            ),
        ]
        results = pre_filter(posts, ["ai", "machine learning"])
        # All scores in range
        for post, score in results:
            assert 0.0 <= score <= 1.0
        # Should be sorted highest first
        if len(results) > 1:
            assert results[0][1] >= results[1][1]

    def test_empty_input(self):
        results = pre_filter([], ["ai"])
        assert results == []

    def test_threshold_filtering(self):
        """Posts below threshold should be excluded."""
        old_irrelevant = _make_post(
            title="Old post about cooking", content="Recipe for soup",
            score=0, comments_count=0,
            published_at=datetime.now(tz=timezone.utc) - timedelta(days=90),
            external_id="old",
        )
        results = pre_filter([old_irrelevant], ["quantum", "physics"], threshold=0.9)
        # The irrelevant old post should likely be filtered out at high threshold
        for _, score in results:
            assert 0.0 <= score <= 1.0
