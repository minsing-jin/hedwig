<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/sources-16+-orange" alt="Sources">
  <img src="https://img.shields.io/badge/version-3.0-purple" alt="Version">
</p>

# Hedwig

**Self-Evolving Personal AI Signal Radar** — Algorithm sovereignty for individuals.

## What's New in v3.0 — SaaS + Native

Hedwig v3.0 transforms from a single-user CLI tool into a full **SaaS platform** with multi-tenant support, while retaining the original self-hosted experience.

### SaaS Features

- **Multi-tenant Architecture** — Each user gets isolated data with Supabase Row-Level Security (RLS). Signals, feedback, criteria, and evolution logs are all user-scoped.
- **Supabase Auth Integration** — Signup, signin, session management, and JWT verification via Supabase Auth. Cookie-based sessions for the web dashboard.
- **Stripe Billing** — Three subscription tiers (Free / Pro $19/mo / Team $49/mo) with Stripe Checkout, Customer Portal, and webhook handling for subscription lifecycle events.
- **Quota Enforcement** — Free tier limits (5 sources, 50 signals/day, daily evolution only, 2-week memory). Pro and Team tiers unlock unlimited sources, signals, weekly evolution, and extended memory.
- **Web Dashboard** — FastAPI-powered UI with setup wizard, Socratic onboarding, signal viewer, criteria editor, source browser, and pipeline controls. Runs in both single-user and SaaS modes.
- **Landing Page & Auth Pages** — SaaS mode adds a landing page, signup form, and login page for new user registration.
- **Database Migration** — Multi-tenant schema migration (`migrations/001_multi_tenant_schema.sql`) adds user_id columns, subscription/usage tables, RLS policies, and auto-provisioning triggers.

### Native Desktop App

- **pywebview Integration** — Run Hedwig as a native desktop window (`python -m hedwig --native`) wrapping the FastAPI dashboard.
- **macOS Menu Bar Tray** — System tray icon with quick actions: open dashboard, run daily/dry/weekly pipelines, Socratic onboarding, and signal viewer (via `rumps`).
- **Cross-platform** — Native app works on macOS, Windows, and Linux via pywebview.

### Subscription Tiers

| Feature | Free | Pro ($19/mo) | Team ($49/mo) |
|---------|------|-------------|---------------|
| Sources | 5 | Unlimited | Unlimited |
| Signals/day | 50 | Unlimited | Unlimited |
| Evolution | Daily only | Daily + Weekly | Daily + Weekly |
| Memory horizon | 2 weeks | Unlimited | Unlimited |
| Custom sources | No | Yes | Yes |
| Shared criteria | No | No | Yes |
| Team channels | — | — | 5 |
| Users per team | — | — | 10 |

> **[한국어](docs/README.ko.md)** | **[English](README.md)** | **[中文](docs/README.zh.md)**

```
Socratic Onboarding → Agent Collection → Normalize → Pre-score → LLM Score → Deliver → Self-Evolve
```

---

## The Moat: Why Hedwig Is Different

Most information tools are **hands** — they fetch what you point at. Hedwig is a **brain + hands** — it learns what you care about and improves itself over time.

| Capability | Others (Agent-Reach, last30days, bb-browser, r.jina.ai) | **Hedwig** |
|---|---|---|
| **Who decides what to collect?** | You, every single time | AI agent, using evolving criteria |
| **How does it learn your taste?** | It doesn't | Socratic onboarding + boolean feedback + natural language + weekly memory |
| **Does it improve over time?** | No — static tools | Yes — daily micro-evolution + weekly macro-evolution |
| **Algorithm ownership** | Corporate (YouTube, X) or fixed (open-source tools) | **You own it. Fully controllable.** |
| **Devil's Advocate** | No | Every signal includes a counter-perspective |

### Hedwig's Five Unique Moats

1. **Socratic Onboarding** — LLM asks you questions until your criteria are clear (ambiguity ≤ 0.2), inspired by Ouroboros philosophy. No manual config files.

2. **Self-Evolving Algorithm** — Daily micro-mutations + weekly macro-mutations following the [Karpathy autoresearch](https://github.com/karpathy/autoresearch) pattern. The system experiments with criteria, measures your upvote ratio, keeps improvements, discards regressions.

3. **Boolean-Only Feedback** — Just upvote/downvote. The system does the heavy lifting of interpreting patterns. Optional natural language when you want to direct it.

4. **Long-Horizon Memory** — Weekly user preference snapshots track your taste trajectory. The system understands how your interests shift over months, not just this week.

5. **Algorithm Sovereignty** — Unlike YouTube/X recommendation algorithms optimized for engagement (= ad revenue), Hedwig optimizes for *your* definition of relevance. You control the fitness function.

---

## What It Does

AI signals are scattered across 15+ platforms. Manually scanning them for meaningful signals among noise is exhausting. Hedwig:

1. **Interviews you Socratically** to crystallize what you care about
2. **Sends an AI agent** to intelligently collect from 16+ sources based on your criteria
3. **Normalizes content** via r.jina.ai (clean markdown, no ads/nav noise)
4. **Pre-scores numerically** (engagement velocity, source authority, recency, convergence) before expensive LLM calls
5. **LLM-scores with Devil's Advocate** counter-perspective on every signal
6. **Delivers to Slack + Discord** in three channels: Alerts / Daily / Weekly
7. **Self-evolves** daily (micro) and weekly (macro) based on your boolean feedback

---

## Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│                  Daily Pipeline (Hedwig v3.0)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Agent Strategy      LLM decides what to collect, from   │
│     Generation          where, how deep, what to explore    │
│          ↓                                                  │
│  2. Agent Collection    Execute strategy — priority first,  │
│                         exploration for discovery           │
│          ↓                                                  │
│  3. Content             r.jina.ai → clean markdown          │
│     Normalization       (strips ads, nav, handles SPAs)     │
│          ↓                                                  │
│  4. Pre-scoring         5-factor numeric filtering BEFORE   │
│                         expensive LLM calls                 │
│          ↓                                                  │
│  5. LLM Scoring         Relevance + Devil's Advocate        │
│          ↓                                                  │
│  6. Delivery            Slack + Discord channels            │
│          ↓                                                  │
│  7. Evolution           Daily: micro-mutations              │
│                         Weekly: macro-evolution + memory    │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. Configure API keys
cp .env.example .env
# Edit .env (see Configuration below)

# 3. Create Supabase tables
# Run hedwig/storage/supabase.py SCHEMA_SQL in Supabase SQL Editor

# 4. Socratic onboarding (first-time setup)
python -m hedwig --onboard

# 5. Test collection (no API keys needed)
python -m hedwig --dry-run

# 6. Run full pipeline
python -m hedwig
```

### Web Dashboard

```bash
# Single-user mode (local setup wizard + pipeline controls)
python -m hedwig dashboard

# SaaS mode (multi-tenant with auth, billing, landing page)
python -m hedwig dashboard --saas
```

### Native Desktop App

```bash
# Install native dependencies
uv pip install -e ".[native]"

# Run as native desktop window
python -m hedwig --native
```

---

## CLI Commands

| Command | What it does |
|---------|--------------|
| `python -m hedwig --onboard` | Run Socratic interview to define your criteria |
| `python -m hedwig --sources` | List all 16 registered source plugins |
| `python -m hedwig --dry-run` | Collect only (no API keys needed) |
| `python -m hedwig --collect` | Collect + LLM scoring, print to console |
| `python -m hedwig` | **Daily full pipeline** (collect → score → deliver → evolve) |
| `python -m hedwig --weekly` | **Weekly briefing** + macro-evolution + memory update |
| `python -m hedwig --evolve` | Manual evolution cycle |
| `python -m hedwig dashboard` | **v3.0** — Web dashboard (single-user mode) |
| `python -m hedwig dashboard --saas` | **v3.0** — Web dashboard (SaaS multi-tenant mode) |
| `python -m hedwig --native` | **v3.0** — Native desktop app via pywebview |

---

## Configuration

### Required API Keys (`.env`)

| Key | Where to get |
|-----|-------------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) |
| `SUPABASE_URL` / `SUPABASE_KEY` | [supabase.com](https://supabase.com) — Project → Settings → API |

### Delivery (Slack and/or Discord)

| Key | Purpose |
|-----|---------|
| `SLACK_WEBHOOK_ALERTS` | `#alerts` channel webhook |
| `SLACK_WEBHOOK_DAILY` | `#daily-brief` channel webhook |
| `DISCORD_WEBHOOK_ALERTS` | Discord alert channel |
| `DISCORD_WEBHOOK_DAILY` | Discord daily channel |
| `DISCORD_WEBHOOK_WEEKLY` | Discord weekly channel |

### SaaS Billing (v3.0, optional)

| Key | Purpose |
|-----|---------|
| `STRIPE_SECRET_KEY` | Stripe secret key for subscription billing |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature verification |
| `STRIPE_PRICE_PRO` | Stripe Price ID for Pro tier |
| `STRIPE_PRICE_TEAM` | Stripe Price ID for Team tier |

### Optional (for expanded sources)

| Key | Enables |
|-----|---------|
| `EXA_API_KEY` | Semantic web search (1000/mo free) |
| `SCRAPECREATORS_API_KEY` | TikTok + Instagram collection |

---

## 16 Source Plugins (Built-in)

| Category | Sources |
|----------|---------|
| **SNS** | X/Twitter (RSS proxy), Reddit (12 AI subreddits), LinkedIn (corporate blogs), Threads (newsletters), Bluesky (AT Protocol), TikTok, Instagram |
| **Tech Communities** | Hacker News (Firebase API), GeekNews, YouTube (RSS), Polymarket |
| **Academic** | arXiv, Semantic Scholar, Papers With Code |
| **Web** | Exa semantic search |
| **Newsletters** | Ben's Bites, Latent Space, The Decoder, AINews, etc. |

**Plus user-extensible:** Add custom RSS feeds, Discord/Telegram channels, or API endpoints.

---

## How to Use It (Step-by-Step)

### Day 1 — Onboarding
```bash
python -m hedwig --onboard
```
The system asks you a series of Socratic questions: what topics matter, what depth you want, what to ignore, what urgency rules to apply. It writes the result to `criteria.yaml`.

### Day 2 — First Run
```bash
python -m hedwig
```
The agent collects from 16 sources based on your criteria, filters via LLM, delivers to Slack/Discord.

### Day 3+ — React
Upvote/downvote the signals you receive. No need to configure anything — the system reads your reactions.

### Daily (automatic)
Each daily run includes a micro-evolution step: LLM analyzes your feedback, makes small adjustments to criteria.

### Weekly
```bash
python -m hedwig --weekly
```
Deep analysis: taste trajectory, source evolution, new exploration directions. Updates your long-horizon memory.

### Anytime — Recalibrate
```bash
python -m hedwig --onboard
```
Re-enter Socratic mode when you want to change direction.

### Cron Setup
```bash
# Daily runs
0 9,19 * * * cd /path/to/hedwig && .venv/bin/python -m hedwig

# Weekly run (Mondays 10:00)
0 10 * * 1 cd /path/to/hedwig && .venv/bin/python -m hedwig --weekly
```

---

## Architecture

```
hedwig/
├── sources/              # 16 source plugins + user-extensible
│   ├── base.py           # Plugin registry, RSSSource, CustomRSSSource
│   ├── hackernews.py, reddit.py, arxiv.py, bluesky.py, ...
│
├── engine/
│   ├── agent_collector.py   # AI-driven collection strategy
│   ├── normalizer.py        # r.jina.ai content cleaning
│   ├── pre_scorer.py        # 5-factor numeric pre-scoring
│   ├── scorer.py            # LLM scoring with Devil's Advocate
│   └── briefing.py          # Daily/weekly briefing generation
│
├── onboarding/
│   └── interviewer.py       # Socratic interview engine
│
├── evolution/
│   └── engine.py            # Daily + weekly self-improvement loops
│
├── memory/
│   └── store.py             # Long-horizon user preference model
│
├── feedback/
│   └── collector.py         # Boolean vote + natural language
│
├── delivery/
│   ├── slack.py             # Slack Block Kit delivery
│   └── discord.py           # Discord webhook delivery
│
├── storage/
│   └── supabase.py          # DB (signals, feedback, evolution, memory)
│
├── saas/                 # v3.0 — Multi-tenant SaaS infrastructure
│   ├── auth.py           # Supabase Auth (signup, signin, JWT)
│   ├── billing.py        # Stripe subscriptions & checkout
│   ├── quota.py          # Usage tracking & tier limit enforcement
│   └── models.py         # UserProfile, Subscription, Usage models
│
├── dashboard/            # v3.0 — Web UI (FastAPI + Jinja2)
│   ├── app.py            # Dashboard server (single-user & SaaS modes)
│   ├── env_manager.py    # .env file management for setup wizard
│   ├── validator.py      # API key validation against live endpoints
│   └── db_setup.py       # Supabase table auto-creation
│
├── native/               # v3.0 — Desktop app (pywebview + rumps)
│   ├── app.py            # Native window wrapping the dashboard
│   └── tray.py           # macOS menu bar tray integration
│
├── models.py                # Pydantic data models
├── config.py                # Environment & criteria loader
└── main.py                  # CLI orchestration

migrations/
└── 001_multi_tenant_schema.sql  # v3.0 — Multi-tenant DB migration
```

---

## Inspirations & Integrations

Hedwig stands on the shoulders of giants. What we absorbed:

| Project | Stars | What Hedwig Borrows |
|---------|-------|---------------------|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | — | Self-improvement loop pattern (experiment → measure → keep/discard) |
| [jina-ai/reader](https://github.com/jina-ai/reader) | 10.5K | **Integrated** — URL-to-Markdown normalization for all 16 sources |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 1K | **Integrated** — 5-factor multi-signal scoring algorithm |
| [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 16.4K | Cookie-based platform collection patterns (planned) |
| [epiral/bb-browser](https://github.com/epiral/bb-browser) | 4.3K | Browser-as-API for login-required platforms (planned) |

**But none of them do what Hedwig does:** Socratic onboarding, self-evolving criteria, boolean feedback learning, Devil's Advocate, long-horizon memory. Those are Hedwig's unique moat.

---

## License

MIT

---

<p align="center">
  <i>The algorithm that decides what information reaches you should belong to you.</i>
</p>
