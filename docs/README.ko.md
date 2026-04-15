<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/sources-17+-orange" alt="Sources">
  <img src="https://img.shields.io/badge/version-3.0-purple" alt="Version">
  <img src="https://img.shields.io/badge/tests-321%20passing-brightgreen" alt="Tests">
</p>

# 🦉 Hedwig

**자기진화하는 개인 AI 시그널 레이더** — 개인을 위한 알고리즘 주권.

> **한국어** · **[English](../README.md)** · **[中文](README.zh.md)**

---

## ⚡ 3분 안에 시작

```bash
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

python -m hedwig --quickstart
```

**OpenAI API 키** 하나만 있으면 됩니다. Supabase, Slack, Discord, 마이그레이션 전부 불필요.

```
🦉 Hedwig Quickstart

Step 1: OpenAI API key
  OPENAI_API_KEY: sk-...

Step 2: What AI signals are you interested in?
  Interest (one sentence): AI 에이전트, LLM 툴링

✓ .env saved
✓ criteria.yaml generated
✓ SQLite DB initialized at ~/.hedwig/hedwig.db
✓ 17 source plugins ready
🚀 Dashboard at http://127.0.0.1:8765
```

브라우저 자동으로 열림. 끝.

---

## 🎯 왜 Hedwig

대부분의 정보 도구는 **손**입니다 — 가리킨 것을 가져다줄 뿐.
Hedwig는 **두뇌 + 손** — 당신이 무엇을 원하는지 학습하고 스스로 개선합니다.

| | YouTube / X | 다른 도구 | **Hedwig** |
|---|---|---|---|
| **알고리즘 소유** | 기업 | 고정 / 오픈소스 | **당신** |
| **최적화 대상** | 광고 노출 | N/A | **당신의 upvote 비율** |
| **취향 학습** | 네 (광고용) | 안 함 | **네 (당신용)** |
| **자기 진화** | 광고 수익용 | 안 함 | **당신 관련성용** |
| **Devil's Advocate** | 없음 | 없음 | **모든 시그널에 포함** |

### 5가지 해자

1. **소크라틱 온보딩** — LLM이 기준 명확해질 때까지 질문
2. **자기진화 알고리즘** — 일간 미세조정 + 주간 대폭 진화 (Karpathy autoresearch 패턴)
3. **Boolean 피드백** — 👍/👎만, 나머지는 시스템이 처리
4. **장기 메모리** — 주간 스냅샷으로 수개월 취향 변화 추적
5. **알고리즘 주권** — fitness function을 당신이 소유하고 감사 가능

---

## 📋 3가지 실행 방식

### 1. Quickstart (개인 사용 추천)

```bash
python -m hedwig --quickstart
```
SQLite 로컬, OpenAI 키만, 3분.

### 2. 완전 셀프호스팅 (파워 유저)

Supabase + Slack/Discord 연동:

```bash
cp .env.example .env
# OpenAI, Supabase, Slack/Discord 키 입력
python -m hedwig --dashboard
```
http://localhost:8765 → `/setup`에서 브라우저로 모든 설정.

### 3. SaaS 배포 (팀, 호스팅)

```bash
bash scripts/deploy_railway.sh
```
Railway + Supabase + Stripe 원커맨드. [docs/HOSTING.md](HOSTING.md) 참조.

---

## 🔁 일상 사용

```
1. python -m hedwig --quickstart    (최초 1회)
2. 대시보드 자동 열림
3. "▶ Run Daily Pipeline" 클릭
4. 브라우저에 시그널 도착
5. 각 시그널에 👍 / 👎
6. 밤새 시스템이 진화
```

### cron 자동화

```bash
# 매일 오전 9시, 오후 7시
0 9,19 * * * cd /path/to/hedwig && .venv/bin/python -m hedwig

# 매주 월요일 오전 10시 (대폭 진화)
0 10 * * 1 cd /path/to/hedwig && .venv/bin/python -m hedwig --weekly
```

---

## 🧩 17개 내장 소스

| 카테고리 | 소스 |
|---|---|
| **소셜** | X, Reddit, LinkedIn, Threads, Bluesky, TikTok, Instagram |
| **테크** | Hacker News, GeekNews, YouTube, Polymarket, **GitHub Trending** |
| **학술** | arXiv, Semantic Scholar, Papers With Code |
| **웹** | Exa 시맨틱 검색 |
| **뉴스레터** | Ben's Bites, Latent Space, The Decoder 등 |

YouTube는 **yt-dlp 자막 자동 enrichment** 포함.
모든 소스는 `/settings`에서 on/off 토글 가능.

---

## ⚙️ CLI 레퍼런스

```bash
python -m hedwig --quickstart           # 제로 설정 로컬 모드
python -m hedwig                        # 일간 풀 파이프라인
python -m hedwig --weekly               # 주간 브리핑 + 대폭 진화
python -m hedwig --dry-run              # 수집만 (API 키 불필요)
python -m hedwig --sources              # 소스 플러그인 목록
python -m hedwig --dashboard            # 웹 대시보드 수동 시작
python -m hedwig --dashboard --saas     # SaaS 모드 (멀티유저)
python -m hedwig --native               # 네이티브 데스크톱 앱
python -m hedwig --tray                 # macOS 메뉴바
python -m hedwig --onboard              # 소크라틱 인터뷰 (CLI)
```

---

## 💰 SaaS 티어 (공개 배포 시)

| 기능 | Free | Pro $19/월 | Team $49/월 |
|---|---|---|---|
| 소스 | 5개 | 무제한 | 무제한 |
| 시그널/일 | 50 | 무제한 | 무제한 |
| 진화 | 일간 | 일간+주간 | 일간+주간 |
| 메모리 | 2주 | 무제한 | 무제한 |
| 커스텀 소스 | ❌ | ✅ | ✅ |
| 팀원 | — | — | 10명 |

---

## 📜 라이선스

MIT

---

<p align="center">
  <em>당신에게 도달하는 정보를 결정하는 알고리즘은 당신의 것이어야 합니다.</em>
</p>
