# 🧠 Hybrid Ensemble — 추천 알고리즘 구조 한 페이지

**Date**: 2026-05-05
**Source of truth**: `hedwig/engine/ensemble/combine.py`
**User-owned config**: `algorithm.yaml`

이 문서는 사용자 질문 *"하이브리드 구조가 어떻게 되는거지?"* 에 대한
정답이자, 신규 기여자가 30초 안에 추천 파이프라인의 모양을 잡을 수 있게 하는
한 페이지 다이어그램입니다.

---

## 한눈에

```
┌─────────────────────────────────────────────────────────────────┐
│  20개 소스 (병렬 asyncio.gather, ~30초)                          │
│  ai_labs · arxiv · arxiv_recsys · hackernews · twitter ·         │
│  reddit · linkedin · threads · bluesky · youtube · …             │
└─────────────────────────────────────────────────────────────────┘
                          ↓ 수백 posts
┌─────────────────────────────────────────────────────────────────┐
│  STAGE A — RETRIEVAL (저렴, 빠른 후보 생성)                      │
│  • pre_scorer (5-factor numeric)                                 │
│  • last30days enrichment (persistence/saturation/velocity)       │
│  • [optional] embedding similarity                                │
└─────────────────────────────────────────────────────────────────┘
                          ↓ top_n = 200
┌─────────────────────────────────────────────────────────────────┐
│  STAGE B — RANKING ENSEMBLE (algorithm.yaml 로 사용자 제어)      │
│                                                                  │
│  ┌─ Cheap pass (전체 200개에 적용) ──────────────────────┐       │
│  │  🌳 LTR        LightGBM LambdaMART / logistic SGD     │       │
│  │  🔡 content    OpenAI embedding cosine / Jaccard      │       │
│  │  📈 popularity authority × recency                     │       │
│  │  🎰 bandit     Thompson sampling per platform          │       │
│  │  🧵 sequential SASRec-inspired Jaccard sequence        │       │
│  └────────────────────────────────────────────────────────┘       │
│           ↓ 가중합 + min-max normalize                            │
│           ↓ top_k = 30 추출                                       │
│  ┌─ Expensive rerank pass (top_k 30 만에 적용) ──┐                │
│  │  🧠 LLM judge (apply_to: top_k)                │                │
│  │     - 한국어 why_relevant + Devil's Advocate   │                │
│  │     - exploration_tags                          │                │
│  └─────────────────────────────────────────────────┘                │
│           ↓ cheap + expensive 재가중합                            │
│           ↓ [optional] IPS debias 보정                            │
│                                                                  │
│  최종: final_score = Σ wᵢ · normalize(scoreᵢ)                    │
└─────────────────────────────────────────────────────────────────┘
                          ↓ 30개 ScoredSignal
              ┌───────┬───────┬───────┬───────┐
              ↓       ↓       ↓       ↓
         Daily   Weekly  Critical  Feed
         brief   brief   alert     stream
```

---

## "Hybrid"인 4가지 이유

| 혼합 차원 | 무엇과 무엇이 섞이나 |
|---|---|
| **모델 유형** | Tree-based (LightGBM) + Linear (logistic) + Embedding (cosine) + Bayesian (bandit) + Heuristic (popularity) + LLM |
| **비용 / 정확도** | 저렴한 cheap-everything 패스 + 비싼 top_k 재랭킹 패스 |
| **신호 종류** | Behavior(LTR feature) + Semantic(embedding) + Temporal(recency) + Exploration(bandit) + Sequence(SASRec) + Reasoning(LLM) |
| **소유권** | 사용자 yaml 으로 제어 + 시스템이 진화 |

---

## 6개 컴포넌트 — 역할 매트릭스

| 컴포넌트 | 무엇을 잡나 | 모델 유형 | 학습 방식 | 비용 |
|---|---|---|---|---|
| 🧠 **llm_judge** | 의미적 적합성 + 반대 관점 | GPT-4o-mini | 프롬프트 (학습 없음) | 높음 (top_k 만) |
| 🌳 **ltr** | 과거 피드백 패턴 (8 feature) | LambdaMART / logistic | weekly REINFORCE + monthly LightGBM 재학습 | 낮음 |
| 🔡 **content_based** | criteria ↔ post 의미 거리 | OpenAI embedding cosine | 학습 없음 (인스턴스 caching) | 중간 (1회 cache) |
| 📈 **popularity_prior** | 권위 × 최신성 | 수식 | 없음 (decay 파라미터) | 거의 없음 |
| 🎰 **bandit** | 탐험 / 미지의 플랫폼 발견 | Thompson sampling | 자동 (Beta 사후분포) | 거의 없음 |
| 🧵 **sequential** | 직전 dwell 시퀀스와 유사도 | recency-weighted Jaccard | 학습 없음 | 낮음 |

---

## 산업 SOTA와의 매핑

| 패턴 | 산업 표준 | Hedwig |
|---|---|---|
| 2-stage retrieval → ranking | YouTube · Twitter · Instagram | ✅ 동일 구조 |
| LambdaMART (LTR) | LinkedIn · Microsoft | ✅ LightGBM |
| Two-tower DSSM | Pinterest | ⚠️ embedding cosine 으로 lite 대체 |
| MMOE multi-task | YouTube ranker | ✅ multi_task fitness (lite) |
| Sequential transformer | TikTok · SASRec · BERT4Rec | ⚠️ Jaccard sequential lite |
| Contextual bandit | Yahoo · Spotify | ✅ Thompson sampling |
| LLM-as-recommender | P5 · RecLLM (학계) | ✅ llm_rec 컴포넌트 |
| RLHF for personalization | 새로 등장 중 | ✅ REINFORCE-lite |
| IPS debias | Schnabel et al | ✅ opt-in |

---

## 자기진화는 어디서

```
🌅 Daily      → criteria.yaml 가중치 미세조정
📈 Weekly     → interpretation_style + REINFORCE on LTR + multi-task snapshot
              + user_memory append
🔬 Monthly    → algorithm.yaml 구조 (weight·feature·top_k·on/off) mutate + shadow test
              + LightGBM 재학습 (28-day lookback)        ← _retrain_sota_models
              + Sequential 자동 history 갱신
              + REINFORCE 재실행 (28-day lookback)
              + interpretation_style 월간 재진화
```

→ **Hybrid는 정적이 아님**. 매 사이클마다 컴포넌트 가중치, feature 목록, 구조 자체가 진화.

---

## 한 줄 요약

> **6개 모델 유형이 각자 다른 신호를 잡아 서로 보완하고, `algorithm.yaml`이 그들의 비율을 정하며, 그 비율과 모델 파라미터 자체가 사용자 피드백 + 논문 + fitness 로 매 사이클마다 진화한다.**

---

## 코드 진입점

```python
# 사용자가 거의 항상 보는 entry
from hedwig.engine.ensemble.combine import run_two_stage_as_signals
signals, stats = await run_two_stage_as_signals(posts, criteria_keywords)

# 컴포넌트 등록
hedwig.engine.ensemble.combine._registry()
# → llm_judge / llm_rec / ltr / content_based / popularity_prior / bandit / sequential

# 월간 자기진화 + 모델 재학습
from hedwig.evolution.meta import run_meta_cycle
result = run_meta_cycle(force=True)
# → result["candidates"] / result["adopted"] / result["models_retrained"]
```

---

## 더 읽기

- [`docs/VISION_v3.md`](VISION_v3.md) §8 — Hybrid Ensemble 원칙
- [`docs/phase8_prd.md`](phase8_prd.md) — SOTA 추천 모델 도입 PRD (S8.1~S8.6)
- [`algorithm.yaml`](../algorithm.yaml) — 활성 컴포넌트 + 가중치
- `hedwig/engine/ensemble/*.py` — 각 컴포넌트 구현
