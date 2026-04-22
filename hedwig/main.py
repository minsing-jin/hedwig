"""
Hedwig v2.0 — Self-Evolving Personal AI Signal Radar

Pipeline: Agent Strategy → Collect → Normalize → Pre-score → LLM Score → Deliver → Evolve

Usage:
    python -m hedwig                  # Daily: agent-driven collect + score + deliver + evolve
    python -m hedwig --weekly         # Weekly: deep analysis + macro-evolution
    python -m hedwig --dry-run        # Collect only (no API keys needed)
    python -m hedwig --collect        # Collect + score (needs OPENAI_API_KEY)
    python -m hedwig --onboard        # Run Socratic onboarding interview
    python -m hedwig --evolve         # Run evolution cycle manually
    python -m hedwig --sources        # List all registered source plugins
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

from hedwig.models import ScoredSignal, UrgencyLevel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("hedwig")


# ---------------------------------------------------------------------------
# Collection — agent-driven intelligent strategy
# ---------------------------------------------------------------------------

async def collect_all(enabled_only: bool = True) -> list:
    """Fallback: collect from all sources without agent strategy."""
    from hedwig.sources import get_registered_sources

    registry = get_registered_sources()
    all_posts = []

    tasks = []
    names = []
    for plugin_id, cls in registry.items():
        names.append(plugin_id)
        instance = cls()
        tasks.append(instance.fetch())

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for name, result in zip(names, results):
        if isinstance(result, Exception):
            logger.warning(f"[{name}] failed: {result}")
        else:
            logger.info(f"[{name}] {len(result)} posts collected")
            all_posts.extend(result)

    logger.info(f"Total: {len(all_posts)} posts from {len(registry)} sources")
    return all_posts


async def agent_collect(llm_client=None) -> tuple[list, dict]:
    """Agent-driven collection: LLM generates strategy, then executes it.

    Returns (posts, strategy_dict).
    """
    from hedwig.config import CRITERIA_PATH, USER_MEMORY_PATH
    from hedwig.engine.agent_collector import AgentCollector
    from hedwig.memory import MemoryStore
    from hedwig.storage import get_source_reliability

    logger.info("Agent generating collection strategy...")

    # Load user memory for context
    memory_store = MemoryStore(path=USER_MEMORY_PATH)
    latest_memory = memory_store.get_latest()
    memory_summary = ""
    if latest_memory:
        memory_summary = (
            f"Interests: {latest_memory.confirmed_interests}\n"
            f"Rejected: {latest_memory.rejected_topics}\n"
            f"Trajectory: {latest_memory.taste_trajectory}"
        )
    source_reliability = get_source_reliability()

    collector = AgentCollector(llm_client=llm_client, criteria_path=CRITERIA_PATH)
    strategy = await collector.generate_strategy(
        source_reliability=source_reliability,
        user_memory_summary=memory_summary,
    )

    focus = strategy.get("focus_keywords", [])
    explore = strategy.get("exploration_queries", [])
    if focus:
        logger.info(f"Focus keywords: {focus[:5]}")
    if explore:
        logger.info(f"Exploration: {explore[:3]}")

    posts = await collector.collect_with_strategy(strategy)
    return posts, strategy


async def normalize_and_prescore(posts: list, criteria_keywords: list[str]) -> list:
    """Normalize content via r.jina.ai, then pre-score to filter noise.

    Returns top posts sorted by pre-score (above threshold).
    """
    from hedwig.engine.normalizer import normalize_batch
    from hedwig.engine.pre_scorer import pre_filter
    from hedwig.engine.absorbed.last30days import enrich_score

    # Normalize content (r.jina.ai for richer LLM input)
    logger.info(f"Normalizing {len(posts)} posts via r.jina.ai...")
    posts = await normalize_batch(posts, max_concurrent=3)

    # Pre-score: numeric filtering before expensive LLM calls.
    # Threshold + top_n come from algorithm.yaml so the user (and meta-evolution)
    # can tune them without a code change.
    from hedwig.config import load_algorithm_config as _load_algo
    retrieval_cfg = _load_algo().get("retrieval", {}) or {}
    threshold = float(retrieval_cfg.get("threshold", 0.10))
    top_n = int(retrieval_cfg.get("top_n", 200))
    logger.info(
        "Pre-scoring (threshold=%.2f top_n=%d)...", threshold, top_n,
    )
    scored = pre_filter(posts, criteria_keywords, threshold=threshold)

    # L2-absorbed enrichment (last30days-style persistence + saturation)
    try:
        from hedwig.storage import get_recent_signals
        recent_rows = get_recent_signals(days=14) or []
        historical_posts = _rows_to_posts(recent_rows)
    except Exception:
        historical_posts = []

    enriched: list = []
    for post, base_score in scored:
        new_score = enrich_score(
            post,
            base_score=base_score,
            same_cycle_posts=[p for p, _ in scored],
            historical_posts=historical_posts,
        )
        enriched.append((post, new_score))
    enriched.sort(key=lambda x: x[1], reverse=True)
    enriched = enriched[:top_n]

    logger.info(
        "Pre-filter + enrich: %d → %d posts (threshold=%.2f, cap=%d)",
        len(posts), len(enriched), threshold, top_n,
    )
    return [post for post, score in enriched]


def _rows_to_posts(rows: list[dict]) -> list:
    """Convert historical signal rows back into RawPost objects for enrichment."""
    from hedwig.models import Platform, RawPost
    out = []
    for row in rows:
        try:
            out.append(
                RawPost(
                    platform=Platform(row.get("platform", "other")),
                    external_id=str(row.get("external_id") or row.get("id") or ""),
                    title=row.get("title") or "",
                    url=row.get("url") or "",
                    content=row.get("content") or "",
                    author=row.get("author") or "",
                    score=row.get("platform_score") or 0,
                )
            )
        except Exception:
            continue
    return out


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def filter_signals(scored: list[ScoredSignal]) -> tuple[list[ScoredSignal], list[ScoredSignal]]:
    alerts = [s for s in scored if s.urgency == UrgencyLevel.ALERT and s.relevance_score >= 0.6]
    digest = [s for s in scored if s.urgency == UrgencyLevel.DIGEST and s.relevance_score >= 0.4]
    alerts.sort(key=lambda s: s.relevance_score, reverse=True)
    digest.sort(key=lambda s: s.relevance_score, reverse=True)
    return alerts, digest


def print_signal(s: ScoredSignal, prefix: str = ""):
    p = s.raw.platform.value.upper()[:8].ljust(8)
    logger.info(f"  {prefix} [{p}] {s.raw.title[:70]}")
    logger.info(f"           relevance={s.relevance_score:.2f} urgency={s.urgency.value}")
    if s.why_relevant:
        logger.info(f"           > {s.why_relevant[:100]}")
    if s.devils_advocate:
        logger.info(f"           ! {s.devils_advocate[:100]}")


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

async def run_onboard():
    """Run Socratic onboarding interview interactively."""
    from hedwig.config import CRITERIA_PATH
    from hedwig.onboarding import SocraticInterviewer

    # Try to use OpenAI for real interview
    llm = None
    try:
        from hedwig.config import OPENAI_API_KEY
        if OPENAI_API_KEY:
            from openai import AsyncOpenAI
            llm = AsyncOpenAI(api_key=OPENAI_API_KEY)
    except ImportError:
        pass

    interviewer = SocraticInterviewer(llm_client=llm, criteria_path=CRITERIA_PATH)

    if CRITERIA_PATH.exists():
        print("\n기존 criteria가 있습니다. 재조정 모드로 시작합니다.\n")
        question = interviewer.start_recalibrate()
    else:
        print("\n처음 오셨군요! Hedwig 소크라틱 온보딩을 시작합니다.\n")
        question = interviewer.start_initial()

    print(f"Hedwig: {question}\n")

    while not interviewer.is_complete:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n온보딩을 중단합니다.")
            return

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("온보딩을 중단합니다.")
            return

        response = await interviewer.respond(user_input)
        print(f"\nHedwig: {response}\n")

    if interviewer.result:
        print(f"\nCriteria가 {CRITERIA_PATH}에 저장되었습니다!")
    else:
        print("\n인터뷰가 완료되었지만 criteria 생성에 실패했습니다.")


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

async def run_dry():
    logger.info("━━━ Hedwig v2.0 Dry Run (collect only) ━━━")
    posts = await collect_all()
    if not posts:
        logger.warning("No posts collected.")
        return

    posts.sort(key=lambda p: p.score, reverse=True)
    logger.info("\nTop posts by platform score:")
    for p in posts[:20]:
        plat = p.platform.value.upper()[:8].ljust(8)
        logger.info(f"  [{plat}] {p.title[:70]}")
        logger.info(f"           score={p.score} url={p.url[:80]}")

    logger.info(f"\n━━━ Collected {len(posts)} posts. ━━━")


# ---------------------------------------------------------------------------
# Daily pipeline (with evolution)
# ---------------------------------------------------------------------------

async def run_daily(collect_only: bool = False):
    """Daily pipeline: Agent Strategy → Collect → Normalize → Pre-score → LLM Score → Deliver → Evolve."""
    logger.info(f"━━━ Hedwig v2.0 Daily Run — {datetime.now(tz=timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ━━━")

    # 0. Setup LLM client
    llm = None
    from hedwig.config import OPENAI_API_KEY, check_required_keys
    if OPENAI_API_KEY:
        try:
            from openai import AsyncOpenAI
            llm = AsyncOpenAI(api_key=OPENAI_API_KEY)
        except ImportError:
            pass

    # 1. Agent-driven collection (LLM generates strategy)
    if llm and not collect_only:
        posts, strategy = await agent_collect(llm_client=llm)
        focus_keywords = strategy.get("focus_keywords", [])
        if not posts:
            logger.warning("Agent collection returned no posts. Falling back to baseline collection.")
            posts = await collect_all()
            focus_keywords = _extract_keywords_from_criteria()
    else:
        posts = await collect_all()
        focus_keywords = _extract_keywords_from_criteria()

    if not posts:
        logger.warning("No posts collected. Exiting.")
        return

    # 2. Normalize content via r.jina.ai + pre-score
    posts = await normalize_and_prescore(posts, focus_keywords)

    if not posts:
        logger.warning("All posts filtered out by pre-scorer.")
        return

    # 3. Check keys for LLM scoring
    mode = "score" if collect_only else "daily"
    missing = check_required_keys(mode)
    if missing:
        logger.error(f"Missing env vars: {', '.join(missing)}")
        return
    from hedwig.config import check_optional_keys
    for gap in check_optional_keys(mode):
        logger.warning(f"Skipping optional capability — {gap}")

    # 4. Scoring — ensemble (default) or legacy single-stage LLM
    import os
    pipeline_mode = os.getenv("HEDWIG_PIPELINE", "ensemble").lower()
    if pipeline_mode == "ensemble":
        # normalize_and_prescore already ran retrieval (pre_filter + history enrichment).
        # rank_and_build_signals runs only the Stage B ranking so we don't duplicate work.
        from hedwig.engine.ensemble.combine import rank_and_build_signals
        logger.info(f"Ensemble ranking {len(posts)} retrieved candidates...")
        scored, ensemble_stats = await rank_and_build_signals(posts, focus_keywords)
        logger.info(
            "Ensemble stats: %s components=%s",
            {k: ensemble_stats[k] for k in ("retrieval_kept", "ranking_kept", "top_k")},
            ensemble_stats["components_used"],
        )
    else:
        from hedwig.engine.scorer import score_posts
        logger.info(f"LLM scoring {len(posts)} pre-filtered posts (legacy single-stage)...")
        scored = await score_posts(posts)

    # 5. Filter into channels
    alerts, digest = filter_signals(scored)
    skipped = len(scored) - len(alerts) - len(digest)
    logger.info(f"Results: {len(alerts)} alerts, {len(digest)} digest, {skipped} skipped")

    if collect_only:
        for s in alerts[:10]:
            print_signal(s, "ALERT")
        for s in digest[:15]:
            print_signal(s, "DIGEST")
        return

    # 6. Deliver to Slack + Discord + SMTP email (only configured channels)
    from hedwig.config import (
        SLACK_WEBHOOK_ALERTS,
        SLACK_WEBHOOK_DAILY,
        DISCORD_WEBHOOK_ALERTS,
        DISCORD_WEBHOOK_DAILY,
        smtp_alerts_configured,
    )
    from hedwig.delivery.slack import send_alert as slack_alert, send_daily_briefing as slack_daily
    from hedwig.delivery.discord import send_alert as discord_alert, send_daily_briefing as discord_daily
    from hedwig.delivery.email import (
        send_alert as email_alert,
        send_daily_briefing as email_daily,
    )
    smtp_enabled = smtp_alerts_configured()
    for signal in alerts[:10]:
        if SLACK_WEBHOOK_ALERTS:
            await slack_alert(signal)
        if DISCORD_WEBHOOK_ALERTS:
            await discord_alert(signal)
        if smtp_enabled:
            await email_alert(signal)

    # 7. Daily briefing
    from hedwig.engine.briefing import generate_daily_briefing
    briefing_signals = alerts + digest[:15]
    if briefing_signals:
        logger.info("Generating daily briefing...")
        briefing_text = await generate_daily_briefing(briefing_signals)
        if SLACK_WEBHOOK_DAILY:
            await slack_daily(briefing_text)
        if DISCORD_WEBHOOK_DAILY:
            await discord_daily(briefing_text)
        if smtp_enabled:
            await email_daily(briefing_text)
        logger.info("Daily briefing generated")

    # 8. Save signals
    from hedwig.storage import save_signals, get_backend_name
    relevant = [s for s in scored if s.relevance_score >= 0.3]
    saved = save_signals(relevant)
    logger.info(f"Saved {saved} signals to {get_backend_name()}")

    # 9. Daily evolution (self-improvement)
    await run_evolution_daily()

    logger.info("━━━ Hedwig v2.0 Daily Run Complete ━━━")


def _extract_keywords_from_criteria() -> list[str]:
    """Extract focus keywords from criteria.yaml for pre-scoring."""
    from hedwig.config import load_criteria
    criteria = load_criteria()
    keywords = []
    prefs = criteria.get("signal_preferences", {})
    keywords.extend(prefs.get("care_about", []))
    ctx = criteria.get("context", {})
    keywords.extend(ctx.get("interests", []))
    # Flatten any nested structures to strings
    return [str(k) for k in keywords if k]


# ---------------------------------------------------------------------------
# Weekly pipeline (with macro-evolution)
# ---------------------------------------------------------------------------

async def run_weekly():
    """Weekly pipeline: deep analysis + macro-evolution."""
    logger.info("━━━ Hedwig v2.0 Weekly Briefing + Evolution ━━━")

    from hedwig.config import check_required_keys
    missing = check_required_keys("full")
    if missing:
        logger.error(f"Missing env vars: {', '.join(missing)}")
        return

    from hedwig.storage import get_recent_signals
    recent = get_recent_signals(days=7)
    if not recent:
        logger.warning("No signals from the past week.")
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

    # Generate and deliver weekly briefing
    from hedwig.engine.briefing import generate_weekly_briefing
    logger.info(f"Generating weekly briefing from {len(signals)} signals...")
    briefing_text = await generate_weekly_briefing(signals)

    from hedwig.config import (
        SLACK_WEBHOOK_DAILY,
        DISCORD_WEBHOOK_DAILY,
        smtp_alerts_configured,
    )
    from hedwig.delivery.slack import send_weekly_briefing as slack_weekly
    from hedwig.delivery.discord import send_weekly_briefing as discord_weekly
    from hedwig.delivery.email import send_weekly_briefing as email_weekly
    if SLACK_WEBHOOK_DAILY:
        await slack_weekly(briefing_text)
    if DISCORD_WEBHOOK_DAILY:
        await discord_weekly(briefing_text)
    if smtp_alerts_configured():
        await email_weekly(briefing_text)
    logger.info("Weekly briefing generated")

    # Weekly evolution
    await run_evolution_weekly(total_signals=len(signals))

    logger.info("━━━ Hedwig v2.0 Weekly Run Complete ━━━")


# ---------------------------------------------------------------------------
# Evolution runners
# ---------------------------------------------------------------------------

async def run_evolution_daily():
    """Run the daily micro-evolution cycle."""
    logger.info("Running daily evolution cycle...")
    try:
        from hedwig.config import CRITERIA_PATH, EVOLUTION_LOG_PATH, OPENAI_API_KEY
        from hedwig.evolution import EvolutionEngine
        from hedwig.models import Feedback, VoteType
        from hedwig.storage import get_feedback_since, save_evolution_log

        llm = None
        if OPENAI_API_KEY:
            from openai import AsyncOpenAI
            llm = AsyncOpenAI(api_key=OPENAI_API_KEY)

        engine = EvolutionEngine(
            llm_client=llm,
            criteria_path=CRITERIA_PATH,
            evolution_log_path=EVOLUTION_LOG_PATH,
        )

        # Load today's feedback from Supabase
        raw_feedback = get_feedback_since(days=1)
        feedbacks = [
            Feedback(
                signal_id=f.get("signal_id", ""),
                vote=VoteType(f.get("vote", "up")),
                natural_language=f.get("natural_language"),
                source_channel=f.get("source_channel", ""),
            )
            for f in raw_feedback
        ]

        log = await engine.run_daily(feedbacks)
        if not save_evolution_log(log):
            logger.warning("Failed to persist daily evolution log to storage backend")
        logger.info(f"Daily evolution: {log.analysis_summary[:100]}")
    except Exception as e:
        logger.warning(f"Daily evolution skipped: {e}")


async def run_evolution_weekly(total_signals: int = 0):
    """Run the weekly macro-evolution cycle."""
    logger.info("Running weekly evolution cycle...")
    try:
        from hedwig.config import CRITERIA_PATH, EVOLUTION_LOG_PATH, OPENAI_API_KEY, USER_MEMORY_PATH
        from hedwig.evolution import EvolutionEngine
        from hedwig.memory import MemoryStore
        from hedwig.models import Feedback, VoteType
        from hedwig.storage import get_feedback_since, get_signal_platforms, save_evolution_log

        llm = None
        if OPENAI_API_KEY:
            from openai import AsyncOpenAI
            llm = AsyncOpenAI(api_key=OPENAI_API_KEY)

        engine = EvolutionEngine(
            llm_client=llm,
            criteria_path=CRITERIA_PATH,
            evolution_log_path=EVOLUTION_LOG_PATH,
        )
        memory_store = MemoryStore(path=USER_MEMORY_PATH)

        # Load week's feedback
        raw_feedback = get_feedback_since(days=7)
        signal_ids = [
            str(row.get("signal_id") or "").strip()
            for row in raw_feedback
            if str(row.get("signal_id") or "").strip()
        ]
        signal_platform_by_id = get_signal_platforms(signal_ids)
        platform_feedback_counts: dict[str, dict[str, int]] = {}
        for row in raw_feedback:
            signal_id = str(row.get("signal_id") or "").strip()
            platform = signal_platform_by_id.get(signal_id)
            if not platform:
                continue

            vote = str(row.get("vote") or "").strip().lower()
            counts = platform_feedback_counts.setdefault(
                platform,
                {"upvotes": 0, "downvotes": 0},
            )
            if vote == VoteType.UP.value:
                counts["upvotes"] += 1
            elif vote == VoteType.DOWN.value:
                counts["downvotes"] += 1

        feedbacks = [
            Feedback(
                signal_id=f.get("signal_id", ""),
                vote=VoteType(f.get("vote", "up")),
                natural_language=f.get("natural_language"),
                source_channel=f.get("source_channel", ""),
            )
            for f in raw_feedback
        ]

        user_memory = memory_store.get_latest()

        log, new_memory = await engine.run_weekly(
            week_feedbacks=feedbacks,
            total_signals=total_signals,
            user_memory=user_memory,
            platform_feedback_counts=platform_feedback_counts,
        )
        if not save_evolution_log(log):
            logger.warning("Failed to persist weekly evolution log to storage backend")

        if new_memory:
            memory_store.save_snapshot(new_memory)

        logger.info(f"Weekly evolution: {log.analysis_summary[:100]}")
    except Exception as e:
        logger.warning(f"Weekly evolution skipped: {e}")


# ---------------------------------------------------------------------------
# Source listing
# ---------------------------------------------------------------------------

def list_sources():
    """Print all registered source plugins."""
    from hedwig.sources import get_registered_sources
    registry = get_registered_sources()
    print(f"\n{len(registry)} source plugins registered:\n")
    for plugin_id, cls in sorted(registry.items()):
        meta = cls.metadata()
        status = "enabled"
        print(f"  {plugin_id:<20s} {meta['display_name']:<30s} [{meta['fetch_method']}] {status}")
    print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def run_critical_loop(interval: int = 1200) -> None:
    """Continuous critical-tier polling loop. SIGINT-safe."""
    import signal as _signal
    from hedwig.engine.critical import run_critical_cycle
    from hedwig.config import (
        SLACK_WEBHOOK_ALERTS,
        DISCORD_WEBHOOK_ALERTS,
        smtp_alerts_configured,
    )

    stop_flag = {"stop": False}

    def _handler(signum, _frame):
        logger.info("Critical loop received signal %s — stopping", signum)
        stop_flag["stop"] = True

    try:
        _signal.signal(_signal.SIGINT, _handler)
        _signal.signal(_signal.SIGTERM, _handler)
    except Exception:
        pass

    async def _deliver(signal):
        if SLACK_WEBHOOK_ALERTS:
            try:
                from hedwig.delivery.slack import send_alert
                await send_alert(signal)
            except Exception as e:
                logger.warning("slack alert failed: %s", e)
        if DISCORD_WEBHOOK_ALERTS:
            try:
                from hedwig.delivery.discord import send_alert
                await send_alert(signal)
            except Exception as e:
                logger.warning("discord alert failed: %s", e)
        if smtp_alerts_configured():
            try:
                from hedwig.delivery.email import send_alert
                await send_alert(signal)
            except Exception as e:
                logger.warning("email alert failed: %s", e)

    logger.info("Critical loop starting — interval=%ds. Ctrl+C to stop.", interval)
    while not stop_flag["stop"]:
        try:
            res = await run_critical_cycle(deliver=_deliver)
            logger.info(
                "Critical cycle: scanned=%d qualified=%d delivered=%d",
                res.get("scanned", 0), res.get("qualified", 0), res.get("delivered", 0),
            )
        except Exception as e:
            logger.warning("Critical cycle failed: %s", e)

        # Sleep in 1s slices so SIGINT is honored quickly
        for _ in range(max(1, interval)):
            if stop_flag["stop"]:
                break
            await asyncio.sleep(1)

    logger.info("Critical loop stopped.")


async def run_meta_cycle_cli() -> None:
    from hedwig.evolution.meta import run_meta_cycle
    logger.info("Running one Meta-Evolution cycle (force=True)...")
    result = run_meta_cycle(force=True)
    logger.info("Meta cycle result: %s", result)


def main():
    parser = argparse.ArgumentParser(description="Hedwig v3.0 — Self-Evolving AI Signal Radar")
    parser.add_argument("--weekly", action="store_true", help="Weekly briefing + macro-evolution")
    parser.add_argument("--dry-run", action="store_true", help="Collect only (no API keys needed)")
    parser.add_argument("--collect", action="store_true", help="Collect + score (needs OPENAI_API_KEY)")
    parser.add_argument("--onboard", action="store_true", help="Run Socratic onboarding interview")
    parser.add_argument("--evolve", action="store_true", help="Run evolution cycle manually")
    parser.add_argument("--sources", action="store_true", help="List all source plugins")
    parser.add_argument("--dashboard", action="store_true", help="Start web dashboard UI")
    parser.add_argument("--saas", action="store_true", help="Enable SaaS mode (landing, auth, billing)")
    parser.add_argument("--native", action="store_true", help="Run as native desktop app")
    parser.add_argument("--tray", action="store_true", help="Run as macOS menubar tray app")
    parser.add_argument("--quickstart", action="store_true", help="Zero-config local mode (SQLite, only OpenAI key needed)")
    parser.add_argument("--port", type=int, default=8765, help="Dashboard port (default: 8765)")
    parser.add_argument("--critical-loop", action="store_true",
                        help="Run the Critical-tier polling loop (default every 20 min)")
    parser.add_argument("--critical-interval", type=int, default=1200,
                        help="Critical poll interval in seconds (default 1200 = 20 min)")
    parser.add_argument("--meta-cycle", action="store_true",
                        help="Run one Meta-Evolution cycle and exit")
    args = parser.parse_args()

    if args.quickstart:
        from hedwig.quickstart import run_quickstart
        run_quickstart()
        return

    if args.native:
        from hedwig.native import run_native
        run_native()
    elif args.tray:
        from hedwig.native.tray import run_tray
        run_tray()
    elif args.dashboard:
        from hedwig.dashboard import run as run_dashboard
        run_dashboard(port=args.port, saas=args.saas)
    elif args.sources:
        list_sources()
    elif args.onboard:
        asyncio.run(run_onboard())
    elif args.evolve:
        asyncio.run(run_evolution_daily())
    elif args.weekly:
        asyncio.run(run_weekly())
    elif args.dry_run:
        asyncio.run(run_dry())
    elif args.collect:
        asyncio.run(run_daily(collect_only=True))
    elif args.critical_loop:
        asyncio.run(run_critical_loop(interval=args.critical_interval))
    elif args.meta_cycle:
        asyncio.run(run_meta_cycle_cli())
    else:
        asyncio.run(run_daily())


if __name__ == "__main__":
    main()
