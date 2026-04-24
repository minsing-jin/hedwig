# Hedwig v3 — Self-Evolving Personal Recommendation Engine

> 사용자가 **자연어·upvote·질문**으로 자신의 추천 알고리즘을 조각하는,
> 크로스플랫폼 멀티모달 신호를 **4-tier temporal lattice**로 소비하는,
> **인지 한계를 극복**하는 자기진화 엔진.

**문서 상태**: v3 (2026-04-21, source of truth)
**이전 버전**: `seed.yaml`, `README.md` (v2.0), `docs/evolve-findings.md` (진화 기록)

---

## 1. Problem & Insight

### 문제
- 정보 홍수에 인지 한계가 붕괴 (주의 용량 · 확증 편향 · 작업기억 · 메타인지)
- 기업 알고리즘은 engagement 최적화 → 사용자의 실제 니즈와 diverge
- 기존 "AI news app" 무덤(Artifact 등): 제품 관점으로만 접근해서 실패

### 인사이트
- 단순 "AI 요약 피드"는 commodity. **엔진이 본체**
- 사용자가 알고리즘을 **소유**하고 **조각**할 수 있으면 광고 비즈가 구조적으로 못 만드는 것을 만들 수 있음
- 자기진화 루프(Karpathy autoresearch 정신)를 **알고리즘 구조 자체**에 적용하면 시간 지날수록 경쟁 격차 벌어짐

---

## 2. Positioning (한 줄)

**Hedwig은 사용자가 자연어·upvote·행동·질문으로 자신의 추천 알고리즘을 조각하는, 크로스플랫폼 멀티모달 신호를 critical/daily/weekly/on-demand/**feed**로 소비하는 "내 SNS 플랫폼".**

기업 SNS 알고리즘(engagement 최적화, 플랫폼 소유) ↔ Hedwig(내 니즈 최적화, **내가 소유하는 피드**).

**두 모드 동시 지원**:
- **Pull-to-digest** — 아침 브리프, 주간 브리프 (기존 "Radar" 프레임)
- **Push-to-stream** — 무한 스크롤 feed, 행동신호가 바로 알고리즘에 반영되는 SNS 프레임 (Phase 7에서 구현)

---

## 3. 8 Principles

| # | 원칙 | 의미 |
|---|---|---|
| 1 | **Algorithm Sovereignty** | `criteria.yaml` + `algorithm.yaml` + evolution log 전부 사용자 소유, audit/export 가능 |
| 2 | **Self-Evolving Fitness** | daily micro + weekly macro + **monthly meta** (3-layer 진화) |
| 3 | **Triple-Input** | explicit(자연어 편집) / semi(Q&A 수용) / implicit(upvote/click) |
| 4 | **4-Tier Temporal** | critical(instant) / daily(morning) / weekly(strategy) / on-demand(Q&A) |
| 5 | **Absorption Gradient** | L1 API call → L2 OSS code 체화 → L3 pattern 추출 → Novelty는 최후 수단 |
| 6 | **Web = Engine 계기판** | dogfooding + mutation sandbox. **상업 껍데기(billing/tier/marketing) 금지** |
| 7 | **Cognitive Augmentation** | 주의/편향/작업기억/메타인지 4한계 각각에 메커니즘 매핑 |
| 8 | **Hybrid Ensemble** | LLM + LTR + content + bandit. 가중치·feature·구조 **자체가 진화 대상** |
| **9** | **Personal SNS Platform** | 소비 UX 자체가 알고리즘 표면. Feed는 출력이자 입력 — dwell/skip/share 행동신호가 실시간 피드백. 브리프는 pull, Feed는 push, 같은 엔진의 두 상태 |

### 가드레일
- 새 기능 제안 시 원칙에 매핑 안 되면 **거부**
- 흡수 가능한 걸 자체 구현하면 **거부** (Absorption Gradient 위반)
- 상업 껍데기(Stripe/billing/pricing tier/marketing landing) **deprioritize 유지**

---

## 4. 6 Differentiators

```
1. Algorithm Sovereignty       — 사용자가 알고리즘 소유/감사/이식
2. Quad-Input Sculpting        — 4경로 입력이 하나의 fitness로 수렴
                                 (explicit NL + semi Q&A + implicit vote + passive behavior)
3. Self-Evolving Fitness       — daily/weekly/monthly 3층 진화
4. 5-Tier Temporal Lattice     — critical/daily/weekly/on-demand/FEED 다섯 시간축
5. Hybrid Ensemble + Meta-Evo  — 알고리즘 구조 자체가 mutation 대상
6. Personal SNS Platform       — "내가 소유한 Feed". 소비 UX가 알고리즘 표면이자
                                 행동신호의 입력 채널이 되는 단일 물체
```

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ COLLECTION (MCP/skill/API 흡수 + 멀티모달)                  │
│  X · Reddit · HN · arXiv · YouTube · Podcast · LinkedIn ... │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ NORMALIZE  (r.jina.ai · whisper · yt-dlp)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ STAGE A — Retrieval (빠르고 저렴한 후보 생성)                │
│   • Pre-scorer (5-factor numeric)                           │
│   • Embedding similarity (criteria vs post)                 │
│   • Collaborative filter (미래, 사용자 풀 생기면)            │
└─────────────────────────────────────────────────────────────┘
                            ↓  (top-N 후보)
┌─────────────────────────────────────────────────────────────┐
│ STAGE B — Ranking Ensemble (←→ algorithm.yaml)              │
│   ① LLM-as-judge (top-K만, deep qualitative)                │
│   ② LTR (LightGBM/NN, feature=과거 피드백)                  │
│   ③ Content-based (embedding × criteria vector)             │
│   ④ Popularity prior (source authority × recency)           │
│   ⑤ Bandit (Thompson sampling for exploration)              │
│                                                             │
│   final_score = Σ wᵢ · scoreᵢ                              │
│   wᵢ 와 feature set 자체가 Meta-Evolution 대상               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ DELIVERY — 4-Tier                                           │
│  ⚡ Critical (instant push)                                  │
│  🌅 Daily (morning brief)                                   │
│  📈 Weekly (strategy brief + opportunity notes)             │
│  💬 On-Demand (Q&A over DB + live search)                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ FEEDBACK — Triple-Input                                     │
│  Explicit    : 자연어 criteria/algorithm 편집              │
│  Semi        : Q&A 수용/거절, "이것 더"/"이것 빼"            │
│  Implicit    : upvote/downvote, click, dwell, skip          │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ EVOLUTION — 3-Layer                                         │
│  Daily   (micro)  : criteria weight tuning                  │
│  Weekly  (macro)  : source evolution, exploration direction │
│  Monthly (META)   : ensemble weights + features + structure │
│                     mutate → shadow test → fitness compare  │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Triple-Input Feedback (상세)

| Channel | Time const | Noise | 예 | 구현 |
|---|---|---|---|---|
| **Explicit** (needs) | 느림, 결정적 | 낮음 | "MoE 피로, agent 위주로" | 자연어 → YAML diff → confirm |
| **Semi** (directed) | 중간 | 중간 | Q&A 수용, "deep dive", "다른 관점" | 이벤트 로그 → evolution signal |
| **Implicit** (passive) | 빠름 | 높음 | upvote/downvote, click, dwell | 기존 feedback DB |

**핵심**: 세 경로 모두 **같은 `algorithm.yaml` + `criteria.yaml`**로 수렴. 진화 엔진이 세 입력을 blend.

---

## 7. 4-Tier Temporal Lattice

| Layer | Trigger | 내용 | Channel |
|---|---|---|---|
| ⚡ **Critical** | urgency=alert + convergence + recency | "지금 봐야" | push (Slack/Discord/menu bar) |
| 🌅 **Daily** | 고정 시간 (09:00 default, 학습 가능) | 🔴 Alert / 🟡 흐름 / 🟢 참고 / 💡 인사이트 | 브리프 + 대시보드 |
| 📈 **Weekly** | 주 1회 (월요일 10:00) | 📊 트렌드 / 🔥 Top 5 / 📈 약신호 / 🎯 기회 / ⚖️ 과열 | 긴 브리프 |
| 💬 **On-Demand** | 사용자 질문 | RAG(수집 DB) + exa live search fallback | 대화형 UI |
| 📱 **Feed** (Phase 7) | 사용자가 앱을 열 때 | 무한 스크롤 stream + 행동신호 실시간 피드백 | `/feed` + PWA + 푸시 |

Critical 감지 공식:
```
critical_score = (engagement_velocity / platform_baseline × time_decay)
               + cross_platform_convergence_bonus
               + criteria_match_weight

threshold 초과 → 15-30min poll loop에서 즉시 push
```

---

## 8. Hybrid Ensemble

### 현재 한계 (LLM-only)
- 비용: 시그널당 ~0.01 USD
- 속도: 초 단위
- 결정성: 낮음 (non-deterministic)
- 설명가능성: "왜?"를 또 LLM에 물어야 함
- 개인화 깊이: 프롬프트 window 한계

### 목표: 5-component Ensemble

```yaml
# algorithm.yaml (사용자 소유 자산)
version: 1
retrieval:
  top_n: 200
  components:
    - pre_scorer: { weight: 1.0 }
    - embed_sim:  { weight: 0.8, model: text-embedding-3-small }
ranking:
  top_k: 30
  components:
    - llm_judge:   { weight: 0.40, model: gpt-4o-mini, only_top: 30 }
    - ltr:         { weight: 0.25, model: lightgbm, features: [...] }
    - content:     { weight: 0.15 }
    - popularity:  { weight: 0.10 }
    - bandit:      { weight: 0.10, strategy: thompson, epsilon: 0.1 }
fitness:
  short_horizon: upvote_ratio
  long_horizon:  retention × on_demand_acceptance
```

**핵심**: `algorithm.yaml`은 `criteria.yaml`과 동급의 사용자 자산. 진화 로그로 diff 추적.

---

## 9. Meta-Evolution Layer (Autoresearch 정신)

```
매 N 주 (default N=4):
  1. 현재 ensemble config (v_current) fitness 측정
     fitness = upvote_ratio × retention × acceptance_rate
  2. 돌연변이 후보 생성 (mutation strategies):
       • weight perturbation (±20% random walk)
       • feature 추가/제거 제안 (LLM이 papers backlog 기반 제안)
       • 컴포넌트 on/off toggle
       • pipeline 구조 변경 (top_n, top_k 조정)
  3. Shadow mode: 후보 config들을 동일 데이터에 적용, 가상 스코어 비교
  4. 이긴 후보가 fitness Δ > +5% 이면 채택
  5. 모든 시도 기록 (왜 채택/거부 되었는지 audit log)
```

**이게 "알고리즘이 스스로 진화"의 기술적 정의.**

Karpathy autoresearch가 research paper를 진화시킨 것처럼, Hedwig은 **추천 알고리즘 config를 진화**시킴.

---

## 10. Absorption Gradient (L1 → L2 → L3)

### L1 — Black-box 호출
- MCP server / HTTP API / Python lib import
- 예: exa.ai, r.jina.ai, openai SDK, whisper
- 비용 ↓, 통제 ↓, 학습 ↓

### L2 — White-box 체화
- OSS 레포를 **읽고** 로직·구조·아이디어를 Hedwig으로 이식
- License 존중, fork 또는 reimplement
- 비용 ↑, 통제 ↑, 학습 ↑ (이해도 증대)

### L3 — Pattern 추출
- 여러 OSS + 논문에서 공통 패턴/안티패턴 추상화
- Hedwig의 아키텍처 원칙으로 승격
- 예: "ranking = retrieval → re-rank 2단계"는 Twitter/YouTube/Instagram 공통 → Hedwig core 원칙

### L2 체화 타겟 (우선순위순)

| OSS | 빼올 것 | Hedwig 위치 |
|---|---|---|
| mvanhorn/last30days-skill | platform engagement 정규화, convergence | `engine/pre_scorer.py` |
| karpathy/autoresearch | fitness keep/discard 루프 | `evolution/meta.py` (신규) |
| twitter/the-algorithm | heavy ranker, SimClusters, TwHIN | `engine/ensemble/` 참고 |
| microsoft/recommenders | LightGBM LTR, NCF, BPR | `engine/ensemble/ltr.py` |
| crawl4ai | robust 크롤링 | `sources/_crawl_adapter.py` |

---

## 11. Paper Absorption Strategy (SOTA / Oral Grade)

### Venues (모두 oral / spotlight / best-paper candidate만 필터)

**Core RecSys/IR**
- SIGIR (long papers)
- RecSys (full papers, LBR 제외)
- KDD (research track)
- WWW / WebConf (research track)
- CIKM, WSDM (full papers)

**General ML (rec/ranking tracks)**
- NeurIPS — oral + spotlight (top 3-5%)
- ICLR — oral + spotlight
- ICML — oral
- AAAI — oral

### 추적 토픽 (Hedwig ensemble/meta-evolution 연결)

| 토픽 | 연결 지점 |
|---|---|
| LLM-based recommenders (P5, InstructRec, RecLLM) | `llm_judge` component 고도화 |
| Sequential/session-based (SASRec, BERT4Rec) | user history 활용 방법 |
| Graph neural (LightGCN, NGCF) | 미래 CF 레이어 |
| Contrastive learning (SGL, SimCLR-rec) | embedding 품질 향상 |
| Causal / debiased (IPS, counterfactual) | selection bias 교정 |
| Multi-task / multi-modal (MMOE, DSSM) | 멀티모달 신호 통합 |
| Bandits (contextual, Thompson) | `bandit` component |
| Diversity / calibration (MMR) | delivery 다양성 보장 |
| Conversational recommendation | **Q&A 층위 직접 적용** |
| Explainable recommendation | **"Why this signal" UI** |
| Online / continual learning | evolution 루프 |
| AutoML for recs / NAS | **Meta-Evolution 직접 적용** |

### 추적 Pipeline (자기참조 루프)

```
1. arXiv cs.IR + cs.LG 주간 크롤
   keyword: rec, ranking, retrieval, CF, CTR, bandit, LTR, embedding
2. 컨퍼런스 proceedings 공개 주기 scan
3. OpenReview API로 NeurIPS/ICLR decision 추적
4. LLM triage → {applicable, reference, ignore}
   기준: Hedwig ensemble/meta-evolution에 직접 적용 가능한가?
5. 분기별 top 3 선정 → L2 체화
6. 체화 결과를 algorithm.yaml candidate feature로 편입
7. Meta-Evolution이 shadow mode로 fitness 검증
```

**자기참조**: Hedwig의 pipeline 자체가 이 논문들을 monitoring. `sources/arxiv_recsys.py` 신규 추가. → 도구가 자기 자신을 개선하는 재귀적 구조.

---

## 12. Roadmap

### Phase 0 — 현재 막힌 것 완주 (이번 주)
- [x] Dashboard Starlette 1.0 API 호환
- [x] `check_required_keys` quickstart 호환 (OpenAI 키만 필수)
- [x] Jina 429 완화 (동시성 ↓, API key 지원, backoff)
- [ ] daily 1회 완주 검증, 30개 시그널 피드백, evolution 1 사이클 관찰

### Phase 1 — Triple-Input 완성 + 흡수 인프라 (1-2주)
- [ ] `/ask` 채팅 엔드포인트: RAG(SQLite) + exa fallback
- [ ] 자연어 criteria 편집기: 자연어 → YAML diff → confirm
- [ ] Ad-hoc 수용 이벤트: `evolution_signal` 테이블 (accept/reject 이벤트)
- [ ] MCP/Skill 어댑터: `sources/_mcp_adapter.py`, `sources/_skill_adapter.py`
- [ ] **last30days-skill 첫 L2 체화** (pre_scorer 업그레이드)

### Phase 2 — 계측 / 투명성 / Sandbox (2-3주)
- [ ] "Why this signal" trace UI (매칭 criteria + 최근 피드백 패턴)
- [ ] Evolution timeline viewer (criteria/algorithm diff history)
- [ ] Mutation sandbox (가짜 피드백 주입 → fitness 시뮬레이션)

### Phase 3 — Hybrid Ensemble 도입 (3-4주)  ⭐ 핵심
- [ ] `engine/ensemble/` 모듈 신설
  - `ltr.py` — LightGBM ranker (feature: 과거 upvote history)
  - `content.py` — embedding × criteria
  - `popularity.py` — authority × recency
  - `bandit.py` — Thompson sampling
  - `llm_judge.py` — 기존 scorer를 top-K에만 적용
- [ ] `algorithm.yaml` 도입 (version, weights, features)
- [ ] 2-stage 리팩토링: retrieval(top-200) → ranking(top-30)

### Phase 4 — Meta-Evolution Layer (4-5주)  ⭐ autoresearch 핵심
- [ ] `evolution/meta.py`: weight mutation + shadow mode
- [ ] Fitness function: upvote_ratio × retention × acceptance
- [ ] Monthly cron: mutate → shadow → fitness compare → adopt/reject
- [ ] Mutation audit log (사용자가 볼 수 있게)

### Phase 5 — 멀티모달 + Critical 강화 (5-6주)
- [ ] `sources/podcast.py` (whisper transcription)
- [ ] `sources/arxiv_recsys.py` (논문 자기참조 crawl)
- [ ] Critical 15-30min polling 루프 분리
- [ ] Cross-platform convergence scoring 개선

### Phase 6 — 라이브러리 분리 + OSS 공개 (6주+)
- [ ] `hedwig-engine` 패키지 분리
- [ ] 대시보드는 reference implementation
- [ ] "Self-evolving personal recommendation engine" 레퍼런스로 포지셔닝

### Phase 7 — Personal SNS Platform (6-10주)
_see `docs/phase_reports/sns_platform_gap.md` for the S1~S11 full breakdown_
- [ ] 7.1 `behavior_events` 테이블 + JS beacon + `/feed` 무한 스크롤 + keyboard/swipe
- [ ] 7.2 LTR feature registry에 dwell / skip / share similarity 추가
- [ ] 7.3 Feeds 추상 (Deck) — per-feed criteria/algorithm override
- [ ] 7.4 `/profile` 페이지 + algorithm export/import bundle
- [ ] 7.5 PWA + in-app Notification API
- [ ] 7.6 Feed personality weekly report
- [ ] 7.7 (선택) Social subscribe — 타인 알고리즘 overlay

---

## 13. Guardrails & Anti-Patterns

### DO
- 새 기능 제안 시 9원칙 중 어디에 속하는지 명시
- 흡수 가능하면 흡수 (Absorption Gradient 순서)
- `algorithm.yaml` 변경은 반드시 diff + confirm
- LLM 호출은 top-K 심사 + criteria 진화 제안 + Q&A에만

### DON'T
- ❌ Stripe / billing / pricing tier / marketing landing
- ❌ 모바일 전용 앱 (Slack/Discord/email이 이미 모바일)
- ❌ 소스 개수 자랑 (깊이가 차별점)
- ❌ LLM 전수 스코어링 (비싸고 느리고 결정 못함)
- ❌ 흡수 가능한 것 자체 구현
- ❌ 엔진 검증 전 껍데기 폴리싱

---

## 14. Open Questions

1. **Cold-start**: 새 사용자 첫 주 피드백 없을 때 algorithm.yaml 초기값은? (논문 흡수 대상)
2. **Exploration vs exploitation**: bandit ε 값은 어떻게 결정? (사용자가 "탐험 원함" 명시 가능하게?)
3. **CF의 의미**: 사용자 1명인 개인 도구에서 collaborative filtering은? (미래 다중 사용자 or 협업 모드에만 활성)
4. **Meta-Evolution 주기**: monthly가 맞는가? (너무 느리면 fitness 변화 못 따라감, 너무 빠르면 noise)
5. **Algorithm 이식성**: `algorithm.yaml` export → 다른 Hedwig 인스턴스 import 가능? (주권 원칙상 yes, 기술 구현 필요)

---

## 15. References

- [seed.yaml](../seed.yaml) — 초기 spec (v2.0)
- [docs/evolve-findings.md](./evolve-findings.md) — 진화 기록
- [docs/absorption_backlog.md](./absorption_backlog.md) — OSS + 논문 체화 대기열
- [algorithm.yaml](../algorithm.yaml) — 알고리즘 config (사용자 자산)
- [criteria.yaml](../criteria.yaml) — 관심사 config (사용자 자산)

---

**문서 책임자**: 사용자 (알고리즘 소유권 원칙)
**갱신 주기**: 아키텍처 변경 시마다. 이 문서는 **기획 single source of truth**.
