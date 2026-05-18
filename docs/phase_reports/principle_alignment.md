# Core Principles ↔ Code Alignment Matrix

**Date**: 2026-04-28
**Source of priorities**: 사용자가 명시적으로 강조한 3가지 핵심.

## 사용자가 강조한 3가지

| # | 원칙 | 사용자 표현 |
|---|---|---|
| 1 | **정보 홍수에서 핵심만 + 크로스플랫폼** | "정보의 홍수에서 핵심만 모두 크로스플랫폼을 볼수있게" |
| 2 | **자가진화 + 자연어 steering** | "스스로 진화하는 추천알고리즘이고, 사용자가 원하는대로 자연어로 방향성을 지시" |
| 3 | **SNS 통합 플랫폼 + 인지 부하 0** | "내 sns 통합 플랫폼이 되는것. 정보들을 모두 내가 중앙화해서 볼수있고 인지 부하없이" |

## Alignment Matrix

| 핵심 | 코드 위치 | 충족도 | 약점 |
|---|---|---|---|
| **1.1** 17+ 소스 멀티플랫폼 | `hedwig/sources/*.py` (19개 등록) | ✅ 충족 | 일부 SNS는 RSS proxy 의존, 안정성 낮음 |
| **1.2** 핵심만 (noise reduction) | `engine/pre_scorer.py` (5-factor) + ensemble + LLM judge | ✅ 충족 | LightGBM 미도입으로 ranker 약함 (S8.1 대기) |
| **1.3** 한 화면 통합 entry | `/chat` (방금 추가) | ✅ 충족 | 첫 시연용 — UX 다듬기 필요 |
| **1.4** Devil's Advocate (편향 방어) | `engine/scorer.py` 프롬프트 | ✅ 충족 | — |
| **2.1** 자연어로 criteria steering | `onboarding/nl_editor.py` + `/criteria/propose` | ✅ 충족 | — |
| **2.2** 자연어로 algorithm steering | `onboarding/nl_algo_editor.py` + `/algorithm/propose` | ✅ 충족 | — |
| **2.3** Daily 자가진화 | `evolution/engine.py::run_evolution_daily` | ✅ 충족 | 피드백 5+개 필요 |
| **2.4** Weekly 자가진화 | `evolution/engine.py::run_evolution_weekly` + `evolution/interpretation.py` | ✅ 충족 | — |
| **2.5** Monthly Meta-evolution | `evolution/meta.py::run_meta_cycle` (4 strategies) | ✅ 충족 | 기본 OFF — `algorithm.yaml.meta_evolution.enabled: true` 켜야 |
| **2.6** Quad-Input Steering (NL + Q&A + vote + dwell) | NL editor / `/qa/feedback` / `/feedback/{id}/{vote}` / `behavior_events` beacon | ✅ 충족 | 모두 단일 `evolution_signal` 스트림으로 수렴 |
| **2.7** Algorithm Sovereignty (감사/이식) | `criteria_versions` / `algorithm_versions` / `sovereignty.yaml` / `/sovereignty` | ✅ 충족 | export bundle 미구현 (S5/S6 of Phase 7) |
| **3.1** 통합 SNS 플랫폼 (피드 형태) | `/feed` 무한스크롤 + 키보드/swipe + behavior beacon | ✅ 충족 | 다중 deck (S4) 대기 |
| **3.2** 한 곳에서 모든 정보 (Chat) | `/chat` + 11 tools | ✅ 방금 추가 | LLM tool-use 정확도는 사용해보며 튜닝 |
| **3.3** 인지 부하 ↓ (헤드라인+토글) | GeekNews-style headline+toggle (`/brief`, `/signals`) | ✅ 방금 추가 | — |
| **3.4** 가독성 (다크/라이트 일관성) | `static/v3.css` 오버레이 | ✅ 방금 추가 | 일부 페이지(/sandbox, /meta) 추가 점검 필요 |

## 결론
**핵심 3가지 모두 코드에 1:1 대응 매핑 존재**. 약점은 소스 안정성 (SNS scraping), LightGBM 미도입, export bundle, 일부 페이지 UX 다듬기 — 모두 known/tracked.

## 약점 → 후속 액션
1. LightGBM 도입 (S8.1) — 1 SP, ROI 최대
2. Export bundle (Phase 7 S6) — algorithm 이식성 완성
3. 가독성 잔여 페이지 점검 (sandbox/meta/sovereignty)
4. 다중 deck (Phase 7 S4) — 사용자가 morning/deep/weekend 분리 운영
