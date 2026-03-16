# Hedwig

**Personal AI Signal Radar** — 6개 플랫폼의 AI 신호를 자동 수집하고, LLM으로 필터링해서, Slack으로 전달하는 개인 인텔리전스 시스템.

```
Collect → Score → Filter → Deliver
  (6 platforms)  (OpenAI)  (criteria.yaml)  (Slack)
```

## Why

AI 분야 정보가 X, Reddit, HN, LinkedIn, Threads, GeekNews 등에 흩어져 있다.
매일 플랫폼을 돌아다니며 노이즈 속에서 의미 있는 신호를 찾는 건 피로하다.

Hedwig는 **내 기준에 맞는 신호만 골라서** Slack으로 보내준다.

## Features

- **6개 소스 수집** — HN, Reddit (12개 AI subreddit), GeekNews, AI blogs/newsletters, corporate AI blogs, indie AI press
- **LLM 2-tier 스코어링** — 빠른 모델로 필터링, 고성능 모델로 해석/요약
- **Devil's Advocate** — 각 신호에 반대 관점/과열 경고 포함
- **3단계 출력** — 개별 Alert + Daily Briefing + Weekly Briefing (트렌드 + 기회 포착)
- **피드백 루프** — Slack 이모지/쓰레드로 반응하면 필터링 기준이 자동 진화
- **criteria.yaml** — 관심사, 무시할 것, 긴급도 규칙, 현재 프로젝트 컨텍스트를 YAML로 관리

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. Set up environment
cp .env.example .env
# Edit .env with your API keys (see Configuration below)

# 3. Create Supabase tables
# Run migrations/001_create_tables.sql in Supabase SQL Editor

# 4. Test
python -m hedwig.main --dry-run      # Collect only (no API keys needed)
python -m hedwig.main --collect      # Collect + LLM score
python -m hedwig.main                # Full pipeline
python -m hedwig.main --weekly       # Weekly briefing
```

## Configuration

### Required API Keys (`.env`)

| Key | Where to get |
|-----|-------------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) → API Keys |
| `SUPABASE_URL` | [supabase.com](https://supabase.com) → Project → Settings → API |
| `SUPABASE_KEY` | Same as above (use `service_role` key) |
| `SLACK_WEBHOOK_ALERTS` | [api.slack.com](https://api.slack.com) → Create App → Incoming Webhooks |
| `SLACK_WEBHOOK_DAILY` | Same app, second webhook for daily/weekly channel |

### Filtering Criteria (`criteria.yaml`)

```yaml
identity:
  role: "AI builder"
  focus: [AI agents, LLM tooling, infra]

signal_preferences:
  care_about:
    - 실제 adoption 신호
    - 논문의 실무 적용 가능성
  ignore:
    - 단순 밈/바이럴
    - 근거 없는 예측

context:
  current_projects:
    - "My current project"
```

Edit this file to tune what Hedwig considers relevant.

## Cron Setup

```bash
bash setup.sh
# Registers:
#   Daily  at 09:00, 19:00
#   Weekly at Monday 10:00
```

Or manually:
```bash
crontab -e
# Add:
0 9,19 * * * cd /path/to/hedwig && .venv/bin/python -m hedwig.main >> logs/hedwig.log 2>&1
0 10 * * 1 cd /path/to/hedwig && .venv/bin/python -m hedwig.main --weekly >> logs/hedwig.log 2>&1
```

## Architecture

```
hedwig/
├── sources/           # 6 platform collectors
│   ├── hackernews.py  # HN API (top + best stories)
│   ├── reddit.py      # Reddit JSON API (12 AI subreddits)
│   ├── geeknews.py    # GeekNews RSS
│   ├── twitter.py     # AI blogs/newsletters (RSS)
│   ├── linkedin.py    # Corporate AI blogs (RSS)
│   └── threads.py     # Indie AI press (RSS)
├── engine/
│   ├── scorer.py      # OpenAI 2-tier scoring (gpt-4o-mini → gpt-4o)
│   └── briefing.py    # Daily/weekly briefing generation
├── delivery/
│   └── slack.py       # Slack Block Kit messages
├── storage/
│   └── supabase.py    # Signal persistence + dedup
├── feedback/
│   └── slack_events.py # Emoji/thread feedback → criteria evolution
├── models.py          # Pydantic data models
├── config.py          # Environment & criteria loader
└── main.py            # CLI entry point
```

## Data Sources

| Platform | Method | Posts/run |
|----------|--------|-----------|
| HackerNews | Firebase API | ~50 |
| Reddit | JSON API (no auth) | ~48 |
| GeekNews | RSS | ~30 |
| AI Blogs | RSS (karpathy, simonwillison, latent.space, etc.) | ~45 |
| Corp AI Blogs | RSS (OpenAI, Google AI, HuggingFace, etc.) | ~15 |
| Indie AI Press | RSS (TechCrunch AI, The Decoder, etc.) | ~15 |
| **Total** | | **~200** |

## Slack Output

### Individual Alert (`#alerts`)
```
🟢 [HACKER] LLM Architecture Gallery
relevance: 0.85 | urgency: alert

💡 왜 중요한가: LLM 아키텍처를 시각적으로 비교한 갤러리로,
   모델 설계 패턴을 빠르게 파악할 수 있음

😈 반대 관점: 시각화는 유용하지만 실제 성능 차이를 설명하진 않음
```

### Daily Briefing (`#daily-brief`)
- 🔴 즉시 주목 (Alert 레벨)
- 🟡 오늘의 주요 흐름
- 🟢 참고할 만한 것
- 💡 오늘의 인사이트

### Weekly Briefing
- 📊 핵심 트렌드
- 🔥 Top 5 신호
- 📈 약신호 추적
- 🎯 기회 포착 (Opportunity Notes)
- ⚖️ 과열 경고

## OpenClaw / Codex Integration

Hedwig can be used as a tool by AI agents (OpenClaw, Codex, etc.):

```bash
# Collect and return JSON (for agent consumption)
python -m hedwig.agent

# Or import directly
from hedwig.sources.hackernews import HackerNewsSource
from hedwig.engine.scorer import score_posts
```

See `hedwig/agent.py` for the agent-friendly interface.

## License

MIT
