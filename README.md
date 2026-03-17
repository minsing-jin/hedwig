<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/platforms-6-orange" alt="Platforms">
</p>

# Hedwig

**Personal AI Signal Radar** — Automatically collects AI signals from 6 platforms, filters them with LLM judgment, and delivers what matters to Slack.

> **[한국어](docs/README.ko.md)** | **[中文](docs/README.zh.md)** | **[日本語](docs/README.ja.md)**

```
Collect → Score → Filter → Deliver
  (6 platforms)  (OpenAI)  (criteria.yaml)  (Slack)
```

## Why

AI information is scattered across X, Reddit, HN, LinkedIn, Threads, GeekNews, and more. Manually scanning each platform for meaningful signals among noise is exhausting.

Hedwig **filters only the signals that match your criteria** and sends them to Slack.

## Features

- **6 Source Collectors** — HN, Reddit (12 AI subreddits), GeekNews, AI blogs/newsletters, corporate AI blogs, indie AI press
- **2-Tier LLM Scoring** — Fast model for filtering, high-performance model for interpretation/summary
- **Devil's Advocate** — Every signal includes a counter-perspective and hype warning
- **3-Level Output** — Individual Alerts + Daily Briefing + Weekly Briefing (trends + opportunity notes)
- **Feedback Loop** — React with Slack emoji/threads and your filtering criteria evolve automatically
- **criteria.yaml** — Manage interests, ignore patterns, urgency rules, and project context in YAML
- **Agent-Ready** — Python API, CLI JSON output, and MCP server for AI agent integration

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env with your API keys (see Configuration below)

# 3. Create Supabase tables
# Run migrations/001_create_tables.sql in Supabase SQL Editor

# 4. Run
python -m hedwig.main --dry-run      # Collect only (no API keys needed)
python -m hedwig.main --collect      # Collect + LLM scoring
python -m hedwig.main                # Full pipeline
python -m hedwig.main --weekly       # Weekly briefing
```

## Configuration

### API Keys (`.env`)

| Key | Where to get |
|-----|-------------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) → API Keys |
| `SUPABASE_URL` | [supabase.com](https://supabase.com) → Project → Settings → API |
| `SUPABASE_KEY` | Same (use `service_role` key) |
| `SLACK_WEBHOOK_ALERTS` | [api.slack.com](https://api.slack.com) → Create App → Incoming Webhooks |
| `SLACK_WEBHOOK_DAILY` | Same app, second webhook for daily/weekly channel |

### Filtering Criteria (`criteria.yaml`)

```yaml
identity:
  role: "AI builder"
  focus: [AI agents, LLM tooling, infra]

signal_preferences:
  care_about:
    - Real adoption signals (not hype)
    - Practical applicability of papers
  ignore:
    - Memes and viral content
    - Unsubstantiated predictions

context:
  current_projects:
    - "My current project"
```

## Cron Setup

```bash
bash setup.sh
# Daily  at 09:00, 19:00
# Weekly at Monday 10:00
```

## Architecture

```
hedwig/
├── sources/           # 6 platform collectors
│   ├── hackernews.py  # HN API (top + best)
│   ├── reddit.py      # Reddit JSON API (12 subreddits)
│   ├── geeknews.py    # GeekNews RSS
│   ├── twitter.py     # AI blogs/newsletters (RSS)
│   ├── linkedin.py    # Corporate AI blogs (RSS)
│   └── threads.py     # Indie AI press (RSS)
├── engine/
│   ├── scorer.py      # OpenAI 2-tier (gpt-4o-mini → gpt-4o)
│   └── briefing.py    # Daily/weekly briefing generation
├── delivery/
│   └── slack.py       # Slack Block Kit messages
├── storage/
│   └── supabase.py    # Persistence + dedup
├── feedback/
│   └── slack_events.py # Emoji/thread → criteria evolution
├── agent.py           # Agent API (Python/CLI/JSON)
├── mcp_server.py      # MCP server for AI agents
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

## Slack Output Examples

### Individual Alert (`#alerts`)
```
🟢 [HACKER] LLM Architecture Gallery
relevance: 0.85 | urgency: alert

💡 Why it matters: Visual gallery comparing LLM architectures,
   useful for quickly grasping model design patterns

😈 Counter-view: Visualization is helpful but doesn't explain
   actual performance differences
```

### Daily Briefing
🔴 Immediate attention &nbsp;|&nbsp; 🟡 Key trends &nbsp;|&nbsp; 🟢 Worth noting &nbsp;|&nbsp; 💡 Insights

### Weekly Briefing
📊 Trends &nbsp;|&nbsp; 🔥 Top 5 &nbsp;|&nbsp; 📈 Weak signals &nbsp;|&nbsp; 🎯 Opportunities &nbsp;|&nbsp; ⚖️ Hype warnings

## Agent Integration

Hedwig can be used as a tool by AI agents:

### Python API
```python
from hedwig.agent import pipeline, collect, score, briefing

signals = await pipeline(top=10)
posts = await collect(sources=["hackernews", "reddit"])
text = await briefing("weekly")
```

### CLI (JSON output)
```bash
python -m hedwig.agent --top 10
python -m hedwig.agent --source reddit
python -m hedwig.agent --briefing daily
```

### MCP Server
```json
{
  "mcpServers": {
    "hedwig": {
      "command": "python",
      "args": ["-m", "hedwig.mcp_server"],
      "cwd": "/path/to/hedwig"
    }
  }
}
```

Tools: `hedwig_collect`, `hedwig_score`, `hedwig_briefing`, `hedwig_pipeline`

## License

MIT
