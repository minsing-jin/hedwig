# Absorption Backlog — OSS + Papers

> Hedwig이 흡수해야 할 것들의 대기열. Absorption Gradient(L1 API → L2 code → L3 pattern) 순서로 처리.
> 새 후보는 이 문서에 PR로 추가. 분기별로 top-3 선정해 체화.

**Last update**: 2026-04-21

---

## Part A — OSS Repositories (L2 체화 대기)

| Priority | Repo | 빼올 것 | Target file | Status |
|---|---|---|---|---|
| 🔥 P0 | [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | platform engagement 정규화, convergence 감지, 30일 윈도우 로직 | `hedwig/engine/pre_scorer.py` | Phase 1 |
| 🔥 P0 | [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | fitness keep/discard 루프, shadow mode 패턴 | `hedwig/evolution/meta.py` (신규) | Phase 4 |
| 🔴 P1 | [twitter/the-algorithm](https://github.com/twitter/the-algorithm) | heavy ranker, SimClusters, TwHIN embedding, 2-stage 구조 | `hedwig/engine/ensemble/` 설계 참고 | Phase 3 |
| 🔴 P1 | [microsoft/recommenders](https://github.com/microsoft/recommenders) | LightGBM LTR, NCF, BPR, Wide&Deep 공식 레시피 | `hedwig/engine/ensemble/ltr.py` | Phase 3 |
| 🟡 P2 | [NVIDIA-Merlin/models](https://github.com/NVIDIA-Merlin/models) | GPU 추천 파이프라인, Transformers4Rec | 참고용 (future scale) | Phase 6+ |
| 🟡 P2 | [unclecode/crawl4ai](https://github.com/unclecode/crawl4ai) | robust 크롤링 (JS rendering, stealth) | `hedwig/sources/_crawl_adapter.py` | Phase 5 |
| 🟡 P2 | [RUCAIBox/RecBole](https://github.com/RUCAIBox/RecBole) | 60+ rec models unified framework (벤치마크 참고) | `benchmarks/` (신규) | Phase 4 |

### 체화 절차 (per repo)
1. Clone + read — architecture, entry point, key algorithms
2. 핵심 로직 추출 (license 확인, 필요 시 credit)
3. Hedwig target file에 adapt (Python 스타일/타입 힌트 맞춤)
4. Unit test 추가
5. `algorithm.yaml` 또는 관련 config에 연결
6. `docs/VISION_v3.md` 섹션 10에 체화 완료 표시

---

## Part B — Top-Tier Papers (SIGIR/RecSys/NeurIPS oral/spotlight)

### 추적 venues
- SIGIR, RecSys, KDD, WWW/WebConf, CIKM, WSDM (IR/RecSys core)
- NeurIPS (oral/spotlight), ICLR (oral/spotlight), ICML (oral), AAAI (oral)

### 추적 keywords (arXiv cs.IR + cs.LG)
```
recommender, ranking, retrieval, collaborative filtering, CTR prediction,
learning-to-rank, bandit, contextual bandit, Thompson sampling,
sequential recommendation, session-based, GNN recommendation,
LLM recommender, conversational recommendation, explainable recommendation,
debiased recommendation, causal recommendation, contrastive learning,
online learning, continual learning, AutoML recommendation, NAS
```

### 체화 관심 있는 논문 영역 (우선순위순)

#### P0 — Ensemble component 직접 고도화
- **LLM-as-judge for ranking** (RecLLM, LLM4Rec, InstructRec 계열)
- **Learning-to-Rank** (LambdaMART, listwise losses)
- **Contextual Bandits** (LinUCB, Thompson variants)

#### P0 — Meta-Evolution 직접 연결
- **AutoML for recommenders** (AutoRec, NAS-Rec)
- **Online learning / concept drift** adaptation

#### P1 — Q&A 층위
- **Conversational recommendation** (CRS systems, TG-ReDial)
- **Retrieval-augmented LLM** (RAG variants for personalization)

#### P1 — "Why this signal" 투명성
- **Explainable recommendation** (attention-based, counterfactual)

#### P2 — 장기 품질
- **Calibrated / diverse recommendation** (MMR, determinantal point processes)
- **Causal / debiased** (IPS, doubly robust)

### 체화 절차 (per paper)
1. Abstract + method section 읽기
2. 관련 OSS 구현 있는지 탐색 (Papers with Code)
3. Hedwig ensemble/meta-evolution 중 어디에 plug 가능한지 판단
4. 실험 결과 (baseline 대비 Δ) 정리
5. Prototype: algorithm.yaml candidate feature로 추가
6. Shadow mode에서 fitness 비교 → 채택 여부 결정

---

## Part C — 자기참조 수집 파이프라인

Hedwig 자체 파이프라인으로 **이 backlog를 업데이트**하는 구조:

```
sources/arxiv_recsys.py (신규)
  ↓ (daily crawl with recsys keywords)
sources/semantic_scholar_recsys.py (기존 semantic_scholar 활용)
  ↓
scorer.py (논문용 스코어링 프롬프트):
  - "Hedwig's ensemble/meta-evolution에 적용 가능한가?"
  - "Absorption Gradient L1/L2/L3 중 어디?"
  ↓
backlog.md 자동 업데이트 (신규 후보를 Part B에 append)
  ↓
사용자 주간 검토 → top-3 선정
```

이 자체가 **도구가 자기 자신을 개선**하는 재귀 구조.

---

## Part D — 상태 추적

### 완료된 체화 (2026-04-21 기준)
- last30days-skill: 부분 (pre_scorer의 5-factor scoring 영감 받음 — 주석에 기록)
- Karpathy autoresearch: 부분 (daily/weekly evolution 루프 토폴로지 — 미완성)

### 진행 중 (Phase 1)
- (없음 — Phase 1 착수 중)

### 대기 중 (P0)
- last30days-skill 완전 L2 체화
- Karpathy autoresearch → meta.py 신규

---

## 기여 방법

이 문서는 **계속 갱신**됨. 새 OSS/논문 발견 시:
1. 적절한 Part에 행 추가 (priority, source, 빼올 것, target, status)
2. 자기참조 파이프라인이 자동 발견한 것은 [auto] 태그
3. 분기 리뷰: 사용자 + LLM triage로 top-3 P0 선정
