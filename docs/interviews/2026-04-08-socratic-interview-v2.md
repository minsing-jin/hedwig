# Ouroboros Socratic Interview v2 — Hedwig Self-Evolving Signal Radar

**Date:** 2026-04-08
**Interviewer:** Claude Code (Ouroboros Socratic pattern)
**Interviewee:** 진민성
**Prior interview:** 2026-03-16 (seed.yaml v1.0, ambiguity 0.15)
**Result:** seed.yaml v2.0, ambiguity 0.12

---

## Interview Context

All prior artifacts consolidated before interview:
- seed.yaml v1.0 (2026-03-16)
- criteria.yaml (user preferences)
- docs/plans/2026-03-26-ouroboros-interview-recovery.md
- docs/plans/2026-03-22-codex-local-orchestration-design.md (recovered from git)
- docs/plans/2026-03-22-codex-local-orchestration.md (recovered from git)
- docs/plans/2026-03-22-claude-limit-auto-resume-design.md
- Memory: project_hedwig.md, user_profile.md
- External reference: mvanhorn/last30days-skill, karpathy/autoresearch

## Converged Decisions (23)

### From Interview v1 (confirmed, not re-asked)
1. AI 분야 시그널 레이더
2. LLM 기반 필터링 (키워드 아님)
3. Devil's Advocate 관점 포함
4. 단일 사용자 (인증 불필요)

### From Interview v2 (new)
5. Slack + Discord 채널별 배달
6. 소스 15개+ 내장 + 사용자 확장 가능 (plugin architecture)
7. 통제권 A/B/C 전부 지원 (직접 수정, 교정, 로직 투명성)
8. 소크라틱 철학으로 사용자 기준 구체화 (Ouroboros 구현 직접 사용 아님, 철학 녹임)
9. 온보딩: 처음 깊게(A) + 원할 때 재조정(D)
10. criteria 자동 진화 (피드백 기반)
11. 긴급도 분류도 소크라틱 + LLM 분석으로 결정
12. 채널 = Alert / Daily Brief / Weekly Brief (긴급도 기준)
13. 1차 Slack/Discord, Future work: 네이티브 앱 (생성형 UI)
14. 진화 범위 = 전부 (criteria + 소스 + 해석 + 탐색 방향)
15. 자동 진화는 온보딩 기준 기반 자율 작동
16. 피드백 = boolean only (upvote/downvote, 틴더식 swipe)
17. 사용자 자발 개입 시에만 소크라틱 질문 생성
18. 1차 개인 도구 → 검증 후 제품화
19. 하이브리드 재구축 (엔진/배달/모델/저장소 살리고, 소스/진화/온보딩 새로)
20. 일간 진화 사이클 (short horizon)
21. 피드백 = boolean + 자연어 (사용자 자발적 방향 제시)
22. 주간 진화 사이클 (long horizon) — 메모리 축적, 취향 모델링
23. 핵심 해자 = 사용자 통제권 있는 자기진화 추천 알고리즘 아키텍처

## Dropped / Not Relevant
- 축 3 (AI 개발 워크플로우 메타 문제) — 사용자가 명시적으로 불필요 판정
- claude_auto_resume — Hedwig와 무관
- Codex/OMX 로컬 설정 — 이미 제거됨

## Key Design Decisions

### Autoresearch Pattern (Karpathy) Applied
```
소크라틱 온보딩 결과 (= program.md)
     ↓
시스템이 알고리즘 변수 수정 (= agent modifies train.py)
     ↓
배달 → upvote/downvote (= val_bpb measurement)
     ↓
개선 유지 / 퇴보 폐기
     ↓
반복 (일간: 미세조정, 주간: 대폭 진화)
```

### Feedback → Evolution Mapping
- 구체 알고리즘은 YouTube/X/Instagram 추천 시스템 논문 리서치 기반으로 설계
- 일간: boolean 피드백 패턴 → LLM 분석 → criteria 미세 조정
- 주간: 전체 피드백 + 자연어 + 시그널 분석 → 소스/해석/탐색 대폭 진화

### Source Architecture
- 15개+ 내장 (SNS 7 + Tech 4 + Academic 3 + Web 1 + Newsletters)
- Plugin interface for user-added sources (RSS, Discord, Telegram, custom API)
- Source reliability auto-scored and evolved weekly

## Remaining Ambiguity (0.12)
All in "implementation design detail" category, not directional:
- Socratic onboarding: exact question flow (0.15)
- Evolution engine: concrete algorithm after rec-sys paper research (0.15)
- Source plugin: interface spec (0.1)
- Memory storage: schema detail (0.1)

## References
- karpathy/autoresearch — self-improvement loop pattern
- mvanhorn/last30days-skill — source coverage, smart discovery, multi-signal scoring
- YouTube/X/Instagram recommendation algorithm papers — feedback-to-evolution mapping
