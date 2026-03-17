"""
Hedwig — Personal AI Signal Radar

Usage:
    python -m hedwig.main              # Daily: collect + score + alert + briefing + save
    python -m hedwig.main --weekly     # Weekly: trend analysis + opportunity notes
    python -m hedwig.main --dry-run    # Collect only (no API keys needed)
    python -m hedwig.main --collect    # Collect + score (needs OPENAI_API_KEY only)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

from hedwig.models import ScoredSignal, UrgencyLevel
from hedwig.sources.geeknews import GeekNewsSource
from hedwig.sources.hackernews import HackerNewsSource
from hedwig.sources.linkedin import LinkedInSource
from hedwig.sources.reddit import RedditSource
from hedwig.sources.threads import ThreadsSource
from hedwig.sources.twitter import TwitterSource
from hedwig.sources.youtube import YouTubeSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hedwig")


async def collect_all() -> list:
    """Collect posts from all sources concurrently."""
    sources = [
        ("HackerNews", HackerNewsSource()),
        ("Reddit", RedditSource()),
        ("GeekNews", GeekNewsSource()),
        ("Twitter/X", TwitterSource()),
        ("LinkedIn", LinkedInSource()),
        ("Threads", ThreadsSource()),
        ("YouTube", YouTubeSource()),
    ]

    all_posts = []
    for name, src in sources:
        try:
            posts = await src.fetch()
            logger.info(f"[{name}] {len(posts)} posts collected")
            all_posts.extend(posts)
        except Exception as e:
            logger.warning(f"[{name}] failed: {e}")

    logger.info(f"Total: {len(all_posts)} posts from {len(sources)} sources")
    return all_posts


def filter_signals(scored: list[ScoredSignal]) -> tuple[list[ScoredSignal], list[ScoredSignal]]:
    """Split into alerts and digest."""
    alerts = [s for s in scored if s.urgency == UrgencyLevel.ALERT and s.relevance_score >= 0.6]
    digest = [s for s in scored if s.urgency == UrgencyLevel.DIGEST and s.relevance_score >= 0.4]
    alerts.sort(key=lambda s: s.relevance_score, reverse=True)
    digest.sort(key=lambda s: s.relevance_score, reverse=True)
    return alerts, digest


def print_signal(s: ScoredSignal, prefix: str = ""):
    """Pretty-print a scored signal to console."""
    p = s.raw.platform.value.upper()[:6].ljust(6)
    score = f"{s.relevance_score:.2f}"
    logger.info(f"  {prefix} [{p}] {s.raw.title[:70]}")
    logger.info(f"         relevance={score} urgency={s.urgency.value}")
    if s.why_relevant:
        logger.info(f"         💡 {s.why_relevant[:100]}")
    if s.devils_advocate:
        logger.info(f"         😈 {s.devils_advocate[:100]}")


async def run_dry(posts=None):
    """Dry run: collect only, no scoring/sending/saving."""
    logger.info("━━━ Hedwig Dry Run (collect only) ━━━")
    if posts is None:
        posts = await collect_all()

    if not posts:
        logger.warning("No posts collected.")
        return posts

    logger.info("")
    logger.info("Top posts by platform score:")
    posts.sort(key=lambda p: p.score, reverse=True)
    for p in posts[:20]:
        plat = p.platform.value.upper()[:6].ljust(6)
        logger.info(f"  [{plat}] {p.title[:70]}")
        logger.info(f"         score={p.score} comments={p.comments_count} url={p.url[:80]}")

    logger.info(f"\n━━━ Collected {len(posts)} posts. Set OPENAI_API_KEY to enable scoring. ━━━")
    return posts


async def run_daily(dry_run: bool = False, collect_only: bool = False):
    """Main daily pipeline."""
    logger.info(f"━━━ Hedwig Daily Run — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ━━━")

    # 1. Collect
    posts = await collect_all()
    if not posts:
        logger.warning("No posts collected. Exiting.")
        return

    if dry_run:
        await run_dry(posts)
        return

    # 2. Check keys for scoring
    from hedwig.config import check_required_keys
    mode = "score" if collect_only else "full"
    missing = check_required_keys(mode)
    if missing:
        logger.error(f"Missing env vars: {', '.join(missing)}")
        logger.error("Set them in .env file. Run with --dry-run to test collection.")
        return

    # 3. Score
    from hedwig.engine.scorer import score_posts
    logger.info(f"Scoring {len(posts)} posts...")
    scored = await score_posts(posts)

    # 4. Filter
    alerts, digest = filter_signals(scored)
    skipped = len(scored) - len(alerts) - len(digest)
    logger.info(f"Results: {len(alerts)} alerts, {len(digest)} digest, {skipped} skipped")

    if collect_only:
        logger.info("\n━━━ Alerts ━━━")
        for s in alerts[:10]:
            print_signal(s, "🔴")
        logger.info("\n━━━ Digest ━━━")
        for s in digest[:15]:
            print_signal(s, "🟡")
        return

    # 5. Send alerts
    from hedwig.delivery.slack import send_alert, send_daily_briefing
    for signal in alerts[:10]:
        ok = await send_alert(signal)
        status = "✓" if ok else "✗"
        logger.info(f"Alert {status}: {signal.raw.title[:50]}")

    # 6. Daily briefing
    from hedwig.engine.briefing import generate_daily_briefing
    briefing_signals = alerts + digest[:15]
    if briefing_signals:
        logger.info("Generating daily briefing...")
        briefing_text = await generate_daily_briefing(briefing_signals)
        ok = await send_daily_briefing(briefing_text)
        logger.info(f"Daily briefing sent {'✓' if ok else '✗'}")

        # Save briefing to DB
        try:
            from hedwig.storage.supabase import _get_client
            client = _get_client()
            client.table("briefings").insert({
                "type": "daily",
                "content": briefing_text,
                "signal_count": len(briefing_signals),
            }).execute()
        except Exception as e:
            logger.warning(f"Failed to save briefing: {e}")

    # 7. Save signals
    from hedwig.storage.supabase import save_signals
    relevant = [s for s in scored if s.relevance_score >= 0.3]
    saved = save_signals(relevant)
    logger.info(f"Saved {saved} signals to Supabase")

    logger.info("━━━ Hedwig Daily Run Complete ━━━")


async def run_weekly(dry_run: bool = False):
    """Weekly pipeline."""
    logger.info("━━━ Hedwig Weekly Briefing ━━━")

    from hedwig.config import check_required_keys
    missing = check_required_keys("full")
    if missing:
        logger.error(f"Missing env vars: {', '.join(missing)}")
        return

    from hedwig.storage.supabase import get_recent_signals
    recent = get_recent_signals(days=7)
    if not recent:
        logger.warning("No signals from the past week. Run daily first.")
        return

    from hedwig.models import Platform, RawPost
    signals = []
    for row in recent:
        raw = RawPost(
            platform=Platform(row["platform"]),
            external_id=row["external_id"],
            title=row["title"],
            url=row.get("url", ""),
            content=row.get("content", ""),
            author=row.get("author", ""),
            score=row.get("platform_score", 0),
        )
        signals.append(ScoredSignal(
            raw=raw,
            relevance_score=row.get("relevance_score", 0),
            urgency=UrgencyLevel(row.get("urgency", "digest")),
            why_relevant=row.get("why_relevant", ""),
            devils_advocate=row.get("devils_advocate", ""),
        ))

    from hedwig.engine.briefing import generate_weekly_briefing
    logger.info(f"Generating weekly briefing from {len(signals)} signals...")
    briefing_text = await generate_weekly_briefing(signals)

    if dry_run:
        print(briefing_text)
        return

    from hedwig.delivery.slack import send_weekly_briefing
    ok = await send_weekly_briefing(briefing_text)
    logger.info(f"Weekly briefing sent {'✓' if ok else '✗'}")

    try:
        from hedwig.storage.supabase import _get_client
        client = _get_client()
        client.table("briefings").insert({
            "type": "weekly",
            "content": briefing_text,
            "signal_count": len(signals),
        }).execute()
    except Exception as e:
        logger.warning(f"Failed to save briefing: {e}")

    logger.info("━━━ Hedwig Weekly Briefing Complete ━━━")


def main():
    parser = argparse.ArgumentParser(description="Hedwig - AI Signal Radar")
    parser.add_argument("--weekly", action="store_true", help="Weekly briefing")
    parser.add_argument("--dry-run", action="store_true", help="Collect only (no API keys needed)")
    parser.add_argument("--collect", action="store_true", help="Collect + score (needs OPENAI_API_KEY)")
    args = parser.parse_args()

    if args.weekly:
        asyncio.run(run_weekly(dry_run=args.dry_run))
    elif args.dry_run:
        asyncio.run(run_dry())
    elif args.collect:
        asyncio.run(run_daily(collect_only=True))
    else:
        asyncio.run(run_daily())


if __name__ == "__main__":
    main()
