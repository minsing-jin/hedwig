<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/platforms-6-orange" alt="Platforms">
</p>

# Hedwig

**개인용 AI 시그널 레이더** — 6개 플랫폼의 AI 신호를 자동 수집하고, LLM으로 필터링해서, Slack으로 전달하는 개인 인텔리전스 시스템.

> **[English](../README.md)** | **[中文](README.zh.md)** | **[日本語](README.ja.md)**

```
수집 → 스코어링 → 필터링 → 전달
(6개 플랫폼)  (OpenAI)   (criteria.yaml)  (Slack)
```

## 왜 만들었나

AI 분야 정보가 X, Reddit, HN, LinkedIn, Threads, GeekNews 등에 흩어져 있다.
매일 여러 플랫폼을 돌아다니며 노이즈 속에서 의미 있는 신호를 찾는 건 피로하다.

Hedwig는 **내 기준에 맞는 신호만 골라서** Slack으로 보내준다.

## 주요 기능

- **6개 소스 수집** — HN, Reddit (12개 AI subreddit), GeekNews, AI 블로그/뉴스레터, 기업 AI 블로그, 인디 AI 프레스
- **LLM 2-tier 스코어링** — 빠른 모델로 필터링, 고성능 모델로 해석/요약
- **Devil's Advocate** — 각 신호에 반대 관점/과열 경고 포함
- **3단계 출력** — 개별 Alert + 일일 브리핑 + 주간 브리핑 (트렌드 + 기회 포착)
- **피드백 루프** — Slack 이모지/쓰레드로 반응하면 필터링 기준이 자동 진화
- **criteria.yaml** — 관심사, 무시할 것, 긴급도 규칙, 현재 프로젝트 컨텍스트를 YAML로 관리
- **에이전트 호환** — Python API, CLI JSON 출력, MCP 서버로 AI 에이전트 연동 지원

## 빠른 시작

```bash
# 1. 클론 & 설치
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. 환경 설정
cp .env.example .env
# .env 파일에 API 키 입력 (아래 설정 참조)

# 3. Supabase 테이블 생성
# Supabase SQL Editor에서 migrations/001_create_tables.sql 실행

# 4. 실행
python -m hedwig.main --dry-run      # 수집만 (API 키 불필요)
python -m hedwig.main --collect      # 수집 + LLM 스코어링
python -m hedwig.main                # 풀 파이프라인
python -m hedwig.main --weekly       # 주간 브리핑
```

## 설정

### API 키 (`.env`)

| 키 | 발급처 |
|----|--------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) → API Keys |
| `SUPABASE_URL` | [supabase.com](https://supabase.com) → 프로젝트 → Settings → API |
| `SUPABASE_KEY` | 위와 같음 (`service_role` 키 사용) |
| `SLACK_WEBHOOK_ALERTS` | [api.slack.com](https://api.slack.com) → 앱 생성 → Incoming Webhooks |
| `SLACK_WEBHOOK_DAILY` | 같은 앱, 일일/주간 채널용 두 번째 webhook |

### 필터링 기준 (`criteria.yaml`)

```yaml
identity:
  role: "AI 빌더"
  focus: [AI agents, LLM tooling, infra]

signal_preferences:
  care_about:
    - 실제 adoption 신호 (hype 아님)
    - 논문의 실무 적용 가능성
  ignore:
    - 단순 밈/바이럴
    - 근거 없는 예측

context:
  current_projects:
    - "현재 프로젝트 이름"
```

## Cron 설정

```bash
bash setup.sh
# 매일 09:00, 19:00 자동 실행
# 매주 월요일 10:00 주간 브리핑
```

## Slack 출력 예시

### 개별 Alert (`#alerts`)
```
🟢 [HACKER] LLM Architecture Gallery
relevance: 0.85 | urgency: alert

💡 왜 중요한가: LLM 아키텍처를 시각적으로 비교한 갤러리로,
   모델 설계 패턴을 빠르게 파악할 수 있음

😈 반대 관점: 시각화는 유용하지만 실제 성능 차이를 설명하진 않음
```

### 일일 브리핑
🔴 즉시 주목 &nbsp;|&nbsp; 🟡 주요 흐름 &nbsp;|&nbsp; 🟢 참고 &nbsp;|&nbsp; 💡 인사이트

### 주간 브리핑
📊 트렌드 &nbsp;|&nbsp; 🔥 Top 5 &nbsp;|&nbsp; 📈 약신호 &nbsp;|&nbsp; 🎯 기회 포착 &nbsp;|&nbsp; ⚖️ 과열 경고

## 에이전트 연동

```python
from hedwig.agent import pipeline, collect, score, briefing

signals = await pipeline(top=10)
posts = await collect(sources=["hackernews", "reddit"])
text = await briefing("weekly")
```

```bash
python -m hedwig.agent --top 10
python -m hedwig.agent --briefing daily
```

자세한 내용은 [영어 README](../README.md)의 Agent Integration 섹션 참조.

## 라이선스

MIT
