"""Demo-mode seed data.

Populates the local SQLite store with synthetic-but-realistic signals,
feedback, Q&A events, criteria versions and algorithm versions so the
concept demo page shows meaningful state on first open — without
touching the user's real feedback or running the pipeline.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from hedwig.models import (
    CriteriaVersion,
    Feedback,
    Platform,
    RawPost,
    ScoredSignal,
    UrgencyLevel,
    VoteType,
)


DEMO_SIGNALS = [
    # (title, platform, urgency, relevance, why, devils)
    ("SWE-bench-Verified: GPT-5 agent breaks 90% on first try", "hackernews", "alert", 0.92,
     "당신의 current_projects(agent 자동화)와 직접 연결. SOTA 벤치마크 돌파는 drift 신호.",
     "벤치마크 과적합 가능성. 실제 production use case와 괴리 있을 수 있음."),
    ("OpenAI o3-mini becomes default for Codex", "twitter", "alert", 0.88,
     "도구 경제 변화 — 당신의 AI builder 포지션에 직접 영향.",
     "모델 이름 브랜딩이라 실제 역량 차이는 과장될 수 있음."),
    ("LLM-as-judge achieves 94% agreement with humans on code review", "arxiv", "alert", 0.85,
     "Hedwig LLM judge 컴포넌트의 근거 강화. 직접 인용 가능.",
     "특정 도메인(Python) 한정 결과. general화 어려울 수 있음."),
    ("Thompson sampling beats epsilon-greedy in LLM routing", "arxiv", "digest", 0.72,
     "Hedwig bandit 컴포넌트 weight 재조정 근거로 사용 가능.",
     "실험 규모가 작음 (N=3k). replication 필요."),
    ("Anthropic releases Claude Skills marketplace API", "hackernews", "alert", 0.83,
     "Absorption Gradient L1 타겟 폭증 예상.",
     "marketplace 성숙도 불명. locked-in 위험."),
    ("PyTorch 2.5 released with async eager", "reddit", "digest", 0.55,
     "core deps 업데이트, 직접 impact 낮음.",
     "급하게 migrate 할 이유 없음."),
    ("New paper: Retrieval-augmented meta-learning for recsys", "arxiv", "alert", 0.89,
     "Hedwig Meta-Evolution feature_suggest_from_papers 후보로 체화 가능.",
     "실제 배포 사례 부족. academic에서 멈출 수도."),
    ("GitHub Copilot monthly usage hits 15M devs", "twitter", "digest", 0.48,
     "시장 수요 확인 지표 — 직접 action item 아님.",
     "metric 정의가 자사 발표라 편향."),
    ("[RECSYS] Large-scale LLM Personalization via RAG (SIGIR oral)", "arxiv", "alert", 0.94,
     "자기참조 파이프라인이 잡은 SIGIR oral. Hedwig Q&A 층위에 바로 적용 가능.",
     "RAG latency cost 검증 필요."),
    ("Hacker News thread: Devin 대안 OSS 비교", "hackernews", "digest", 0.66,
     "빌더 실무 관점. 저장해서 나중에 dive.",
     "리스트 기사 성격. signal-to-noise 낮음."),
    ("Meta AI proposes hybrid ensemble for ranking (RecSys 2026 oral)", "arxiv", "alert", 0.90,
     "Hedwig ensemble 설계 직접 검증. feature 추가 후보.",
     "Meta 스케일 전용일 수도 — 개인 사이즈 generalize 검증 필요."),
    ("Jack Clark Import AI #461: compute → policy", "newsletter", "digest", 0.71,
     "macro trend 관심사 — weekly brief 수렴 가능성.",
     "정책 분석이라 단기 action 어려움."),
]


PLATFORM_BY_NAME = {p.value: p for p in Platform}


def _platform(name: str) -> Platform:
    return PLATFORM_BY_NAME.get(name, Platform.CUSTOM)


def _published_at(hours_ago: int) -> datetime:
    return datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago)


def _build_scored_signal(i: int, spec: tuple) -> ScoredSignal:
    title, platform, urgency, score, why, devils = spec
    return ScoredSignal(
        raw=RawPost(
            platform=_platform(platform),
            external_id=f"demo-{i}",
            title=title,
            url=f"https://example.com/demo/{i}",
            content=f"{title} — synthesized demo content for Hedwig conceptual walkthrough.",
            author="demo",
            score=random.randint(20, 500),
            comments_count=random.randint(5, 80),
            published_at=_published_at(random.randint(1, 72)),
        ),
        relevance_score=score,
        urgency=UrgencyLevel(urgency),
        why_relevant=why,
        devils_advocate=devils,
        exploration_tags=["demo"],
    )


def seed_demo(reset: bool = False) -> dict:
    """Seed the demo dataset. If reset=True, clears previous demo rows first."""
    from hedwig.storage import (
        init_db,
        save_algorithm_version,
        save_criteria_version,
        save_evolution_signal,
        save_feedback,
        save_signals,
    )
    from hedwig.storage.local import _conn  # low-level reset

    init_db()

    if reset:
        with _conn() as c:
            c.execute("DELETE FROM signals WHERE external_id LIKE 'demo-%'")
            c.execute("DELETE FROM feedback WHERE signal_id LIKE 'demo-%'")
            c.execute("DELETE FROM evolution_signal WHERE json_extract(payload, '$.demo') = 1")
            c.execute("DELETE FROM criteria_versions WHERE created_by = 'demo'")
            c.execute("DELETE FROM algorithm_versions WHERE created_by = 'demo'")

    # 1. Signals
    scored = [_build_scored_signal(i, s) for i, s in enumerate(DEMO_SIGNALS)]
    signals_saved = save_signals(scored)

    # 2. Feedback — 70% upvote ratio demo
    feedback_saved = 0
    for i in range(len(DEMO_SIGNALS)):
        vote = VoteType.UP if random.random() < 0.7 else VoteType.DOWN
        fb = Feedback(signal_id=f"demo-{i}", vote=vote, source_channel="demo")
        if save_feedback(fb):
            feedback_saved += 1

    # 3. Triple-Input events — explicit / semi / implicit exemplars
    ev_payloads = [
        ("explicit", "criteria_edit", {
            "demo": 1, "intent": "agent 위주로 비중 높이고 crypto는 빼줘",
            "changes": [
                {"op": "add", "path": "signal_preferences.care_about", "value": "agent frameworks"},
                {"op": "add", "path": "signal_preferences.ignore", "value": "crypto"},
            ],
            "criteria_version": 2,
        }, 2.0),
        ("semi", "qa_accept", {
            "demo": 1, "question": "이번 주 agent 툴 중 뭐가 제일 빠르게 떴어?",
        }, 2.0),
        ("semi", "qa_ask", {
            "demo": 1, "question": "SWE-bench 최신 리더보드 요약해줘",
        }, 0.3),
        ("semi", "qa_reject", {
            "demo": 1, "question": "crypto trading bot 관련 논문 알려줘",
        }, 1.5),
        ("implicit", "upvote", {"demo": 1, "signal_id": "demo-0"}, 1.0),
        ("implicit", "upvote", {"demo": 1, "signal_id": "demo-2"}, 1.0),
        ("implicit", "downvote", {"demo": 1, "signal_id": "demo-7"}, 1.0),
    ]
    for channel, kind, payload, weight in ev_payloads:
        save_evolution_signal(channel=channel, kind=kind, payload=payload, weight=weight)

    # 4. Criteria version history — two demo edits
    crit_v1 = {"signal_preferences": {"care_about": ["LLM tooling"], "ignore": []}}
    crit_v2 = {
        "signal_preferences": {
            "care_about": ["LLM tooling", "agent frameworks"],
            "ignore": ["crypto"],
        }
    }
    save_criteria_version(CriteriaVersion(
        version=1, criteria=crit_v1, created_by="demo",
        diff_from_previous=None,
    ))
    save_criteria_version(CriteriaVersion(
        version=2, criteria=crit_v2, created_by="demo",
        diff_from_previous=(
            "--- before\n+++ after\n@@\n-care_about: [LLM tooling]\n"
            "+care_about: [LLM tooling, agent frameworks]\n+ignore: [crypto]"
        ),
    ))

    # 5. Algorithm version history — a mutation adopted, then another
    algo_v1 = {
        "version": 1,
        "ranking": {
            "top_k": 30,
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.40},
                "popularity_prior": {"enabled": True, "weight": 0.10},
            },
        },
    }
    algo_v2 = {
        "version": 2,
        "ranking": {
            "top_k": 30,
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.35},
                "ltr": {"enabled": True, "weight": 0.25},
                "content_based": {"enabled": True, "weight": 0.20},
                "popularity_prior": {"enabled": True, "weight": 0.10},
            },
        },
    }
    save_algorithm_version(
        version=1, config=algo_v1, created_by="demo",
        origin="initial_default", diff_from_previous=None, fitness_score=None,
    )
    save_algorithm_version(
        version=2, config=algo_v2, created_by="demo",
        origin="meta_evolution:weight_perturbation",
        diff_from_previous=(
            "--- before\n+++ after\n@@\n"
            "-llm_judge.weight: 0.40\n"
            "+llm_judge.weight: 0.35\n"
            "+ltr: {enabled: true, weight: 0.25}\n"
            "+content_based: {enabled: true, weight: 0.20}"
        ),
        fitness_score=0.08,
    )

    return {
        "signals_seeded": signals_saved,
        "feedback_seeded": feedback_saved,
        "evolution_signals_seeded": len(ev_payloads),
        "criteria_versions_seeded": 2,
        "algorithm_versions_seeded": 2,
    }


def reset_demo() -> dict:
    from hedwig.storage.local import _conn, init_db
    init_db()
    with _conn() as c:
        c.execute("DELETE FROM signals WHERE external_id LIKE 'demo-%'")
        c.execute("DELETE FROM feedback WHERE signal_id LIKE 'demo-%'")
        c.execute("DELETE FROM evolution_signal WHERE json_extract(payload, '$.demo') = 1")
        c.execute("DELETE FROM criteria_versions WHERE created_by = 'demo'")
        c.execute("DELETE FROM algorithm_versions WHERE created_by = 'demo'")
    return {"reset": True}
