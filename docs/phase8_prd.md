# Phase 8 — SOTA Recommenders (PRD only, implementation deferred)

**Date**: 2026-04-28
**Goal**: 현재 ensemble의 baseline-수준 컴포넌트를 산업 SOTA 수준으로 격상.
**Reference**: docs/absorption_backlog.md Part B (논문 추적)

## Sprint specs (S8.1 ~ S8.6)

### S8.1 — LightGBM LambdaMART (1 SP, ROI 최대)
- **현재**: pure-Python logistic + 8 feature SGD. 비선형 학습 X.
- **목표**: `lightgbm.LGBMRanker(objective="lambdarank")` 로 교체.
- **데이터**: `feedback` + `behavior_events` (dwell/skip) 결합 → ranker label
  - upvote=1.0, dwell≥3s=0.7, skip<2s=0.0, downvote=-1.0
- **API 변경 없음**: `LTRRanker.score_posts(...)` 시그니처 유지, 내부 model만 교체.
- **Fallback**: lightgbm import 실패 시 기존 logistic으로.
- **검증**: NDCG@30 / 평균 upvote_ratio 변화 확인.
- **체화 출처**: microsoft/recommenders LambdaMART 레시피.

### S8.2 — Sequential 추천 (SASRec mini, 2 SP)
- **현재**: 시간 패턴 학습 X. 직전 행동 무관.
- **목표**: 사용자의 최근 N개 viewed/dwelled signal sequence → 다음 후보 예측.
- **모델**: SASRec 미니 (transformer block 1-2개) — `pip install torch` 필요.
- **저장**: `sequence_states` 테이블 (user_id, last_n_signal_ids).
- **Ensemble 통합**: 새 컴포넌트 `sequential` 추가, weight 0.10 진입.
- **체화 출처**: SASRec 논문 + RecBole 레퍼런스.

### S8.3 — LLM-rec (P5/RecLLM 패턴, 1 SP)
- **현재**: LLM-as-judge — top_k에 LLM이 점수 매김.
- **목표**: LLM-as-recommender — 사용자 history + 후보 → 자연어로 ranked list 생성.
- **차이**: judge는 "이 시그널 점수?", recommender는 "이 30개 중 사용자 next-best?"
- **구현**: 새 컴포넌트 `llm_rec` (rerank 단계만), `apply_to: top_k`.
- **체화 출처**: P5 (UC San Diego), InstructRec, RecLLM 논문.

### S8.4 — Causal/Debiased correction (1 SP)
- **현재**: 노출 편향 보정 X. 자주 등장하는 platform이 자연스럽게 우세.
- **목표**: IPS (Inverse Propensity Score) 보정.
- **구현**: 각 platform별 노출 빈도 → propensity → 점수 1/p 가중.
- **체화 출처**: "Recommendations as Treatments" (Schnabel et al), DLA 논문.

### S8.5 — Multi-task MMOE (2 SP)
- **현재**: 단일 fitness (upvote_ratio).
- **목표**: 다중 task 동시 — engage_likelihood / share_likelihood / save_likelihood.
- **MMOE**: shared expert + task-specific gates.
- **체화 출처**: YouTube ranker 논문 (MMOE), ESMM.

### S8.6 — RLHF for personalization (3 SP, 가장 큰 차별화)
- **현재**: 진화는 daily LLM 분석 + monthly meta. RL 없음.
- **목표**: PPO-lite로 ranker 가중치 직접 RL 학습.
- **Reward**: principled_fitness (G9에서 만든 6원칙 가중합).
- **체화 출처**: TRL/RLHF 표준 + 추천 도메인 특화 논문 (RecGPT 등).

## 우선순위
- **즉시 ROI**: S8.1 (LightGBM)
- **차별화**: S8.6 (RLHF)
- **확장성**: S8.2 + S8.3 (sequential + LLM-rec)
- **품질**: S8.4 (debias)
- **고급**: S8.5 (multi-task)

추정 총 작업: 10 SP ≈ 2-3주 (LightGBM은 1일 컷).

## 흡수 vs 자체 구축 전략
- S8.1: 라이브러리 흡수 (lightgbm)
- S8.2: 논문 + RecBole에서 코드 체화 (L2)
- S8.3: 자체 프롬프트 + LLM 호출 (Novelty)
- S8.4: 수식 자체 구현 (간단)
- S8.5: 논문 PyTorch 모델 코드 체화 (L2)
- S8.6: TRL 라이브러리 흡수 + adapt

## 다음 행동
사용자가 "S8.1 즉시" 라고 하면 LightGBM 도입을 한 턴 안에 가능.
"S8 전체 단계적" 이라면 위 순서대로 매주 1 sprint.
