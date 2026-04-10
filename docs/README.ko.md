<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/sources-16+-orange" alt="Sources">
  <img src="https://img.shields.io/badge/version-2.1-purple" alt="Version">
</p>

# Hedwig

**자기진화하는 개인 AI 시그널 레이더** — 개인을 위한 알고리즘 주권.

> **[한국어](README.ko.md)** | **[English](../README.md)** | **[中文](README.zh.md)**

```
소크라틱 온보딩 → 에이전트 수집 → 정제 → 사전 스코어링 → LLM 스코어링 → 배달 → 자기 진화
```

---

## 해자(Moat): Hedwig가 다른 이유

대부분의 정보 도구는 **손**입니다 — 당신이 가리키는 걸 가져다 줄 뿐. Hedwig는 **두뇌 + 손**입니다 — 당신이 무엇을 원하는지 학습하고, 스스로 개선합니다.

| 기능 | 다른 도구 (Agent-Reach, last30days, bb-browser, r.jina.ai) | **Hedwig** |
|---|---|---|
| **무엇을 수집할지 누가 결정?** | 당신이 매번 직접 | AI 에이전트가 진화하는 기준으로 결정 |
| **취향을 어떻게 학습?** | 학습 안 함 | 소크라틱 온보딩 + boolean 피드백 + 자연어 + 주간 메모리 |
| **시간이 지나면?** | 변화 없음 (정적 도구) | 일간 미세조정 + 주간 대폭 진화 |
| **알고리즘 소유권** | 기업 (YouTube, X) 또는 고정 (오픈소스) | **당신이 완전히 통제** |
| **Devil's Advocate** | 없음 | 모든 시그널에 반론 포함 |

### Hedwig만의 5가지 해자

1. **소크라틱 온보딩** — LLM이 질문을 통해 기준을 명확히 합니다 (ambiguity ≤ 0.2). Ouroboros 철학 기반. 수동 설정 파일 없음.

2. **자기진화 알고리즘** — [Karpathy autoresearch](https://github.com/karpathy/autoresearch) 패턴 기반의 일간 미세조정 + 주간 대폭 진화. 시스템이 기준을 실험하고, upvote 비율로 측정하고, 개선은 유지하고 퇴보는 폐기합니다.

3. **Boolean 피드백** — upvote/downvote만. 시스템이 패턴 해석을 담당. 방향을 주고 싶을 때만 자연어로 추가 입력 가능.

4. **Long-Horizon 메모리** — 주간 사용자 취향 스냅샷이 취향 궤적을 추적합니다. 시스템은 몇 달에 걸친 관심사 변화를 이해합니다.

5. **알고리즘 주권** — engagement(=광고 수익)을 최적화하는 YouTube/X와 달리, Hedwig는 *당신이 정의한 관련성*을 최적화합니다. fitness function을 당신이 통제합니다.

---

## 무엇을 하는가

AI 시그널은 15개 이상의 플랫폼에 흩어져 있습니다. noise 속에서 의미 있는 signal을 수동으로 찾는 건 피곤합니다. Hedwig는:

1. **소크라틱 인터뷰**로 당신이 원하는 것을 구체화
2. **AI 에이전트**가 16개+ 소스에서 지능적으로 수집
3. **콘텐츠 정제** — r.jina.ai로 깨끗한 마크다운 (광고/네비 제거)
4. **수치 기반 사전 스코어링** — LLM 호출 전 5-factor 필터링
5. **LLM 스코어링** — 모든 시그널에 Devil's Advocate 반론 포함
6. **Slack + Discord 배달** — Alert / Daily / Weekly 3개 채널
7. **자기 진화** — 일간(미세) + 주간(대폭) boolean 피드백 기반

---

## 빠른 시작

```bash
# 1. 클론 & 설치
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. API 키 설정
cp .env.example .env

# 3. Supabase 테이블 생성
# hedwig/storage/supabase.py의 SCHEMA_SQL을 Supabase SQL Editor에서 실행

# 4. 소크라틱 온보딩 (첫 실행)
python -m hedwig --onboard

# 5. 수집 테스트 (API 키 불필요)
python -m hedwig --dry-run

# 6. 전체 파이프라인 실행
python -m hedwig
```

---

## CLI 명령어

| 명령어 | 설명 |
|--------|------|
| `python -m hedwig --onboard` | 소크라틱 인터뷰로 기준 정의 |
| `python -m hedwig --sources` | 16개 소스 플러그인 목록 |
| `python -m hedwig --dry-run` | 수집만 (API 키 불필요) |
| `python -m hedwig --collect` | 수집 + LLM 스코어링, 콘솔 출력 |
| `python -m hedwig` | **일간 전체 파이프라인** (수집 → 스코어 → 배달 → 진화) |
| `python -m hedwig --weekly` | **주간 브리핑** + 대폭 진화 + 메모리 업데이트 |
| `python -m hedwig --evolve` | 수동 진화 사이클 |

---

## 사용 방법 (단계별)

### 1일차 — 온보딩
```bash
python -m hedwig --onboard
```
시스템이 소크라틱 질문을 던집니다: 어떤 주제, 얼마나 깊이, 무엇을 무시할지, 어떤 긴급도 규칙을 적용할지. 결과를 `criteria.yaml`에 저장합니다.

### 2일차 — 첫 실행
```bash
python -m hedwig
```
에이전트가 당신의 기준으로 16개 소스에서 수집, LLM으로 필터, Slack/Discord에 배달.

### 3일차+ — 반응
받은 시그널에 upvote/downvote. 설정 필요 없음 — 시스템이 반응을 읽습니다.

### 매일 (자동)
각 일간 실행에 미세 진화 단계 포함: LLM이 피드백 분석, criteria에 작은 조정.

### 매주
```bash
python -m hedwig --weekly
```
깊은 분석: 취향 궤적, 소스 진화, 새로운 탐색 방향. 장기 메모리 업데이트.

### 언제든 — 재조정
```bash
python -m hedwig --onboard
```

### Cron 설정
```bash
# 일간 실행 (오전 9시, 오후 7시)
0 9,19 * * * cd /path/to/hedwig && .venv/bin/python -m hedwig

# 주간 실행 (월요일 오전 10시)
0 10 * * 1 cd /path/to/hedwig && .venv/bin/python -m hedwig --weekly
```

---

## 16개 내장 소스 플러그인

| 카테고리 | 소스 |
|---|---|
| **SNS** | X/Twitter, Reddit, LinkedIn, Threads, Bluesky, TikTok, Instagram |
| **테크 커뮤니티** | Hacker News, GeekNews, YouTube, Polymarket |
| **학술** | arXiv, Semantic Scholar, Papers With Code |
| **웹** | Exa 시맨틱 검색 |
| **뉴스레터** | Ben's Bites, Latent Space, The Decoder 등 |

**+ 사용자 확장 가능:** 커스텀 RSS, Discord, Telegram, API 엔드포인트.

---

## 영감 & 통합

| 프로젝트 | 스타 | Hedwig가 차용한 것 |
|---|---|---|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | — | 자기 개선 루프 패턴 |
| [jina-ai/reader](https://github.com/jina-ai/reader) | 10.5K | **통합** — URL→Markdown 정제 |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 1K | **통합** — 5-factor 스코어링 알고리즘 |
| [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 16.4K | 쿠키 기반 수집 패턴 (예정) |
| [epiral/bb-browser](https://github.com/epiral/bb-browser) | 4.3K | 브라우저-as-API (예정) |

**하지만 이들 중 어느 것도 Hedwig가 하는 걸 하지 않습니다:** 소크라틱 온보딩, 자기진화 기준, boolean 피드백 학습, Devil's Advocate, long-horizon 메모리. 이것이 Hedwig만의 해자입니다.

---

## 라이선스

MIT

---

<p align="center">
  <i>당신에게 도달하는 정보를 결정하는 알고리즘은 당신의 것이어야 합니다.</i>
</p>
