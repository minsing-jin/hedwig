# SNS Platform Pivot — Gap Analysis

**Date**: 2026-04-24
**Pivot**: Hedwig의 소비 UX 프레이밍을 **"내 Reader/Radar"** → **"내 SNS 플랫폼 (personal feed)"** 으로 재정렬.
Algorithm Sovereignty 원칙은 동일하되 UX · 행동신호 · 확산 · 이식 모델이 바뀜.

## 프레임 비교

| 축 | Radar/Curator (현재) | Personal SNS Platform (목표) |
|---|---|---|
| 소비 단위 | 하루 1회 브리프 | 상시 feed (on/off 자유) |
| 상호작용 | 👍/👎 버튼 | swipe / long-press / dwell / share |
| 시간축 | Daily/Weekly 정시 push | 사용자가 열 때 최신 순 + Critical push |
| 알고리즘 접근 | YAML + Ouroboros 문서 | "내 알고리즘" 프로필 페이지 |
| 확산 | 혼자 사용 | 알고리즘 export/import/share |
| 행동신호 | vote + Q&A | + dwell, scroll_depth, skip, share, re-open |
| 모바일 | 없음 | PWA + 홈 배지 + 푸시 |
| 구조 | 단일 홈 | 복수 feed (morning / deep / weekend 등) |

## 11개 구체 Gap (S1 ~ S11)

| # | 요소 | 현재 | 필요 | 우선 |
|---|---|---|---|---|
| **S1** | **Feed 무한 스크롤 뷰** | `/` 홈 10개 + `/signals` 50개 리스트 | cursor-based `/feed?stream=default&after=…` 무한 스크롤 | 🔴 high |
| **S2** | **Swipe / 단축 인터랙션** | 👍 / 👎 버튼만 | keyboard (j/k/u/d/s), touch swipe, long-press-to-save | 🔴 high |
| **S3** | **행동신호 (dwell/skip/share)** | 수집 X | `behavior_events` 테이블 + JS beacon (view_started, dwell_ms, skipped, shared) → implicit feedback 채널 | 🔴 high |
| **S4** | **복수 Feed / Deck** | 단일 홈 | `feeds` 테이블: id/name/criteria_ref/algorithm_ref. 사용자가 morning/deep/… 여러 개 운영 | 🟠 med |
| **S5** | **"내 알고리즘" 프로필** | `/criteria` + `/meta` 분산 | `/profile` 한 페이지에 criteria + algorithm + 최근 활동 통계 + shareable badge | 🟠 med |
| **S6** | **Algorithm export/import** | sovereignty.yaml "export_contract" 선언만 | `POST /algorithm/export` → bundle zip. `POST /algorithm/import` → 타인의 번들 dry-run + 수용 | 🟠 med |
| **S7** | **모바일 PWA** | 반응형 미검증 | `manifest.json` + service worker + 홈 화면 아이콘, offline fallback | 🟡 low |
| **S8** | **In-app 푸시** | Slack webhook 의존 | browser Notification API + service worker 기반 로컬 푸시. Critical 층위가 여기로 | 🟡 low |
| **S9** | **Feed 활동 통계** | 없음 | 주간 "feed personality" 요약: 선호 시간대, 평균 dwell, skip 비율, 장르 분포 | 🟡 low |
| **S10** | **Stream control** | 브리프만 | per-feed pause / refresh / notif-threshold | 🟡 low |
| **S11** | **Social layer (미래)** | 혼자 | 다른 사람 알고리즘 subscribe + overlay (필터 교집합/합집합) | 🔵 future |

## 상세 설계 스케치

### S3 — 행동신호 테이블 (핵심)

```sql
CREATE TABLE behavior_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'view_start','view_end','dwell','skip','share','save','expand_source','click_link'
  )),
  dwell_ms INTEGER,
  position_in_feed INTEGER,          -- 몇 번째 카드였는지
  feed_id TEXT DEFAULT 'default',
  device TEXT,                        -- 'desktop' | 'mobile_web' | 'pwa'
  captured_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Triple-Input이 4-Input으로 확장:
- **Explicit** (NL 편집)
- **Semi** (Q&A 수용)
- **Implicit-Active** (vote)
- **Implicit-Passive** (dwell / skip / share) ← 신규

Ensemble의 `past_upvote_similarity` / `past_downvote_similarity` 위치에 
`past_dwelled_similarity` / `past_skipped_similarity` 추가 (LTR feature 레지스트리에 이미 확장 가능).

### S1/S2 — Feed 페이지

```
GET /feed?stream=default&after=<cursor>&limit=30
  → {items: [{id, title, url, platform, score, thumbnail?}], next_cursor}

JS:
- IntersectionObserver로 view_start/view_end 기록
- dwell_ms = (view_end - view_start)
- Keyboard: j=next, k=prev, u=upvote, d=downvote, s=save, /=q&a
- Swipe (touch): left=down, right=up, up=save, down=skip
```

### S4 — Feed 추상 (Deck)

```yaml
# feeds.yaml (사용자 소유, peer to criteria.yaml / algorithm.yaml)
version: 1
feeds:
  - id: default
    name: 메인 피드
    criteria_ref: criteria.yaml
    algorithm_ref: algorithm.yaml
  - id: morning_deep
    name: 아침 딥다이브
    criteria_overrides:
      signal_preferences.care_about: [large model architecture]
    algorithm_overrides:
      ranking.components.llm_judge.weight: 0.6
```

Feed 하나 = criteria + algorithm 조합. 같은 시그널 풀에서 다른 알고리즘으로 재랭킹.

### S6 — Algorithm export/import

Export bundle:
```
hedwig-algo-<hash>.zip
├── criteria.yaml
├── algorithm.yaml
├── interpretation_style.json
├── manifest.json           # author, created_at, signature
└── README.md               # auto-generated "내 알고리즘 프로필"
```

Import flow: bundle 업로드 → sovereignty boundary 검사 → dry-run rank on last 100 signals → 비교 preview (이 알고리즘으로 보면 top10이 이렇게 바뀜) → 수용/기각.

## 보강될 원칙 (VISION_v3 §3 → 9원칙)

**#9 — Personal SNS Platform (new)**
> 소비 UX 자체가 알고리즘의 표면이다. Feed는 단지 출력이 아니라
> 행동신호(dwell/skip/share)를 실시간 피드백으로 돌리는 입력 채널이다.
> 브리프는 pull-to-digest, Feed는 push-to-stream — 같은 엔진의 두 상태.

## 기획서 업데이트 범위

- `docs/VISION_v3.md` → §3 원칙 8→9, §4 차별축 5→6, §7 4-tier에 "feed stream" 층위 명시, §12 Roadmap에 Phase 7 추가
- `docs/absorption_backlog.md` → feed/timeline 관련 OSS + 논문 (Instagram Explore, TikTok recs, Twitter rankflow)

## Roadmap 추가 — Phase 7 "SNS Platform"

| 스프린트 | 내용 | 예상 기간 |
|---|---|---|
| 7.1 | `behavior_events` 테이블 + JS beacon + `/feed` 무한 스크롤 + keyboard/swipe | 1주 |
| 7.2 | LTR feature registry에 dwell/skip/share similarity 추가 + fit_from_history 확장 | 3일 |
| 7.3 | Feeds 테이블 + deck UI (top-bar 탭) + per-feed criteria/algorithm override | 1주 |
| 7.4 | `/profile` 페이지 + export/import bundle | 4일 |
| 7.5 | PWA (manifest + SW) + in-app Notification API + Critical 연결 | 3일 |
| 7.6 | Feed personality weekly report + /evolution timeline에 feed-event 노출 | 3일 |
| 7.7 (옵션) | Social subscribe (다른 사람 알고리즘 overlay) | 추후 |

## 이 Gap 분석이 의미하는 것

현재 기획의 **엔진** 쪽은 거의 완성 상태. 부족한 건 **엔진의 얼굴(Feed UX)** — 
Algorithm Sovereignty는 있지만 "당신이 매일 열어 시간을 쓰는 내 SNS"라는 사용자 내면화가 없음.
Phase 7이 이 gap을 닫음. 엔진은 이미 준비됐기 때문에 대부분 UI + 행동신호 + 피드 추상화 작업이라 1-2개월 스코프.

---

**다음 액션 선택**: 
- (A) VISION_v3 + 원칙/차별축 업데이트 지금 진행
- (B) S1/S2/S3 (feed + behavior events) 부터 즉시 구현
- (C) 전체 Phase 7 PRD 스펙부터 세세하게
