# Phase 7 — Personal SNS Platform PRD

**Date**: 2026-04-27
**Goal**: Hedwig을 "내가 소유하고 steering하는 SNS 플랫폼"으로 만든다. 엔진은 그대로, 소비 UX와 행동신호 채널을 추가.
**Reference**: `docs/phase_reports/sns_platform_gap.md` (S1~S11), VISION_v3 §3 9원칙, §7 5-tier.

## Sprint specs

### S1 — `/feed` 무한 스크롤 (1 SP)
**API**:
```
GET /feed?stream=default&cursor=<base64>&limit=30
→ {items: [signal], next_cursor, has_more}
```
- Cursor: base64(signal.id|collected_at) for stable pagination across new inserts.
- Stream: feed name. Default "default".
- Items shape: subset of signal columns + computed `feed_position`.

**HTML**: `/feed` SSR shell + JS infinite scroll. Each card: title / source / score / 👍/👎 / "save" / "more like this" / link to source.

**Acceptance**: 200 시그널 시드해도 첫 페이지 30개 < 200ms 응답. 스크롤 끝에서 다음 30개 자동 로드.

---

### S2 — Keyboard + Swipe (0.5 SP)
- Desktop keys: `j`/`k` next/prev, `u` upvote, `d` downvote, `s` save, `?` open Q&A, `o` open source link.
- Touch swipe: left=down, right=up, up=save (long-press), tap=open.
- Card focus indicator. ARIA roles for screen readers.

**Acceptance**: 키보드 only로 60초 동안 30개 카드 vote 가능. Mobile Safari 터치 동작 확인.

---

### S3 — `behavior_events` (1 SP, 핵심)

**Schema**:
```sql
CREATE TABLE behavior_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (event_type IN (
    'view_start','view_end','dwell','skip','share','save',
    'expand_source','click_link','open_qa'
  )),
  dwell_ms INTEGER,
  position_in_feed INTEGER,
  feed_id TEXT DEFAULT 'default',
  device TEXT,
  captured_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_behavior_signal ON behavior_events(signal_id, captured_at DESC);
CREATE INDEX idx_behavior_type ON behavior_events(event_type, captured_at DESC);
```

**Beacon**: `POST /events/beacon` accepts batch `[{signal_id, event_type, dwell_ms?, position_in_feed?}]`.
JS uses `IntersectionObserver` (50% threshold) for `view_start`/`view_end`, computes `dwell_ms = end - start`. `navigator.sendBeacon()` on `pagehide`.

**Quad-Input Steering**: behavior_events events surface as `evolution_signal(channel='implicit', kind='behavior_<type>')` lazily so the existing evolution loop sees them without new wiring.

**Acceptance**: 30 cards 스크롤하면 30 view_start + 30 view_end (혹은 dwell) 이벤트가 DB에 들어가 있어야 함.

---

### S4 — Feeds (Deck) 추상 (1 SP)
**Asset**: `feeds.yaml` peer to criteria/algorithm.

```yaml
version: 1
feeds:
  - id: default
    name: 메인 피드
  - id: morning_deep
    name: 아침 딥다이브
    criteria_overrides: {signal_preferences.care_about: [...]}
    algorithm_overrides: {ranking.components.llm_judge.weight: 0.6}
```

UI: `/feed` 상단에 탭. 각 탭이 다른 stream id.
Backend: `/feed?stream=<id>` 시 feeds.yaml에서 override 적용 후 cached criteria + algorithm 으로 재랭킹.

---

### S5 — `/profile` (0.5 SP)
한 페이지에 모인 "내 알고리즘":
- 활성 criteria (요약)
- 활성 algorithm.yaml (요약)
- 활성 InterpretationStyle (tone/depth/jargon)
- 최근 7일 활동 통계 (votes, dwell, Q&A)
- 알고리즘 share 버튼 → S6으로 연결

---

### S6 — Algorithm export/import bundle (1 SP)
**Export**: `POST /algorithm/export` → zip with criteria + algorithm + interpretation_style + manifest + auto-generated README.
**Import**: `POST /algorithm/import` (multipart) → unzip → sovereignty 검사 → dry-run rank on last 100 signals → preview diff → user confirms or rejects.

**Manifest**:
```json
{
  "schema": "hedwig-algo-bundle/1",
  "exported_at": "...",
  "source_user_id": "anonymous",
  "signature": "sha256-..."
}
```

---

### S7 — PWA (0.5 SP)
- `/static/manifest.json` (icons, theme color)
- Service worker for offline shell + Critical layer push notification handling
- "Add to home screen" prompt

---

### S8 — In-app push (0.5 SP)
- Browser `Notification.requestPermission()`
- Critical alerts route through SW notification API
- /settings에 notification permission toggle

---

### S9 — Feed personality weekly report (0.5 SP)
Weekly aggregate: 선호 시간대, 평균 dwell, top platforms, skip ratio, 장르 분포.
`/profile`과 weekly briefing 둘 다에 노출.

---

### S10 — Stream control (0.3 SP)
Per-feed pause / refresh rate / notification threshold.
sovereignty.yaml에 feeds.user_editable 패턴 추가.

---

### S11 — Social subscribe (future, 1 SP)
타인 알고리즘 bundle을 import하면 "subscription" 으로 등록되고, 자신의 algorithm.yaml에 `overlay: [user_x_algo]` 형태로 합쳐짐. 다음 단계에서 결정.

---

## 실행 순서 (이번 턴)
1. S1+S2+S3 동시 — 가장 핵심. 무한 스크롤 + 키보드 + 행동신호 beacon.
2. S4~S11은 계획만, 구현은 후속 턴.

## Test plan (S1~S3)
- behavior_events CRUD round-trip
- /feed cursor pagination correctness (30 + 30 + has_more)
- /events/beacon batch insert + bad event_type rejection
- /feed page renders + has expected JS hooks

## 비-Phase-7 인터뷰 잔여 (이번 턴 동시 처리)
G5 (attribution), G6 (delivery), G7 (cycle structured), G8 (exit conditions), G9 (principled fitness), G10 (structured briefing).
G1 (judgment refactor)만 후속 턴으로 미룸 — 안전한 마이그레이션 별도 설계 필요.
