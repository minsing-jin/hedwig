<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/sources-17+-orange" alt="Sources">
  <img src="https://img.shields.io/badge/version-3.0-purple" alt="Version">
  <img src="https://img.shields.io/badge/tests-321%20passing-brightgreen" alt="Tests">
</p>

# 🦉 Hedwig

**Self-Evolving Personal AI Signal Radar** — Algorithm sovereignty for individuals.

> **[한국어](docs/README.ko.md)** · **English** · **[中文](docs/README.zh.md)**

---

## ⚡ Get Started in 3 Minutes

```bash
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

python -m hedwig --quickstart
```

You only need an **OpenAI API key**. No Supabase, no Slack, no Discord, no migrations.

```
🦉 Hedwig Quickstart

Step 1: OpenAI API key
  OPENAI_API_KEY: sk-...

Step 2: What AI signals are you interested in?
  Interest (one sentence): AI agent frameworks and LLM tooling

✓ .env saved
✓ criteria.yaml generated
✓ SQLite DB initialized at ~/.hedwig/hedwig.db
✓ 17 source plugins ready
🚀 Dashboard at http://127.0.0.1:8765
```

Browser opens automatically. That's it.

---

## 🎯 Why Hedwig

Most information tools are **hands** — they fetch what you point at.
Hedwig is a **brain + hands** — it learns what you care about and improves itself over time.

| | YouTube / X | Other tools | **Hedwig** |
|---|---|---|---|
| **Who owns the algorithm?** | Corporate | Fixed / open source | **You** |
| **Optimizes for?** | Ad engagement | N/A | **Your upvote ratio** |
| **Learns your taste?** | Yes (for ads) | No | **Yes (for you)** |
| **Self-improves?** | For engagement | No | **For your relevance** |
| **Devil's Advocate?** | No | No | **Every signal** |

### Five Moats

1. **Socratic Onboarding** — LLM asks questions until criteria are clear
2. **Self-Evolving Algorithm** — Daily micro + weekly macro mutations (Karpathy autoresearch pattern)
3. **Boolean Feedback** — Just 👍/👎, the system handles the rest
4. **Long-Horizon Memory** — Weekly snapshots track taste drift over months
5. **Algorithm Sovereignty** — You own and audit the fitness function

---

## 📋 Three Ways to Run

### 1. Quickstart (Recommended for personal use)

```bash
python -m hedwig --quickstart
```
SQLite local, OpenAI key only, 3 minutes.

### 2. Full Self-Hosted (For power users)

Use Supabase + Slack/Discord for persistence and delivery:

```bash
cp .env.example .env
# Fill OpenAI, Supabase, Slack/Discord keys
python -m hedwig --dashboard
```
Open http://localhost:8765 → `/setup` handles everything in browser.

### 3. SaaS Deployment (For teams, hosted)

```bash
bash scripts/deploy_railway.sh
```
One command → Railway + Supabase + Stripe. See [docs/HOSTING.md](docs/HOSTING.md).

---

## 🔁 Daily Usage

```
1. python -m hedwig --quickstart    (one time)
2. Dashboard opens automatically
3. Click "▶ Run Daily Pipeline"
4. Signals arrive in browser
5. 👍 / 👎 on each signal
6. System evolves overnight
```

### Automate with cron

```bash
# Daily 9am + 7pm
0 9,19 * * * cd /path/to/hedwig && .venv/bin/python -m hedwig

# Weekly Monday 10am (deep evolution)
0 10 * * 1 cd /path/to/hedwig && .venv/bin/python -m hedwig --weekly
```

---

## 🧩 17 Built-in Sources

| Category | Sources |
|---|---|
| **Social** | X, Reddit, LinkedIn, Threads, Bluesky, TikTok, Instagram |
| **Tech** | Hacker News, GeekNews, YouTube, Polymarket, **GitHub Trending** |
| **Academic** | arXiv, Semantic Scholar, Papers With Code |
| **Web** | Exa semantic search |
| **Newsletters** | Ben's Bites, Latent Space, The Decoder, etc. |

YouTube includes **automatic transcript enrichment** via yt-dlp.
All sources can be toggled on/off in `/settings`.

---

## ⚙️ CLI Reference

```bash
python -m hedwig --quickstart           # Zero-config local mode
python -m hedwig                        # Daily full pipeline
python -m hedwig --weekly               # Weekly brief + macro-evolution
python -m hedwig --dry-run              # Collect only (no API keys)
python -m hedwig --sources              # List source plugins
python -m hedwig --dashboard            # Web dashboard (manual start)
python -m hedwig --dashboard --saas     # SaaS mode (multi-user)
python -m hedwig --native               # Native desktop app (pywebview)
python -m hedwig --tray                 # macOS menu bar
python -m hedwig --onboard              # Socratic interview (CLI)
```

---

## 🏗️ Pipeline

```
┌───────────────────────────────────────────────────────────┐
│   Agent Strategy   → LLM decides what/where/how deep      │
│   Collection       → 17 sources in parallel               │
│   Normalization    → r.jina.ai cleans HTML → markdown     │
│   Pre-scoring      → 5-factor numeric filter              │
│                      (engagement + authority + recency    │
│                       + convergence + relevance)          │
│   LLM Scoring      → Relevance + Devil's Advocate         │
│   Delivery         → Dashboard / Slack / Discord / Email  │
│   Evolution        → Daily micro + Weekly macro           │
└───────────────────────────────────────────────────────────┘
```

---

## 🔧 Configuration

### Minimum (.env)

```bash
OPENAI_API_KEY=sk-...          # Only this is truly required
```

### Optional Delivery

```bash
# Pick any one or combine
SLACK_WEBHOOK_ALERTS=...
SLACK_WEBHOOK_DAILY=...
DISCORD_WEBHOOK_ALERTS=...
DISCORD_WEBHOOK_DAILY=...
SMTP_HOST=smtp.gmail.com  SMTP_USER=...  SMTP_PASS=...  SMTP_FROM=...
```

### Optional Storage (instead of local SQLite)

```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
# Set HEDWIG_STORAGE=sqlite to force local; else auto-detects
```

### Optional Sources

```bash
EXA_API_KEY=...                 # Semantic web search
SCRAPECREATORS_API_KEY=...      # TikTok + Instagram
```

See [.env.example](.env.example) for the full list.

---

## 🧪 Tests

```bash
.venv/bin/python -m pytest tests/ -q
# 321 passed
```

---

## 💰 SaaS Tiers (when deploying publicly)

| Feature | Free | Pro $19/mo | Team $49/mo |
|---|---|---|---|
| Sources | 5 | Unlimited | Unlimited |
| Signals/day | 50 | Unlimited | Unlimited |
| Evolution | Daily | Daily + Weekly | Daily + Weekly |
| Memory | 2 weeks | Unlimited | Unlimited |
| Custom sources | ❌ | ✅ | ✅ |
| Team members | — | — | 10 |

---

## 📚 Documentation

- [docs/HOSTING.md](docs/HOSTING.md) — Full SaaS deployment guide (Railway + Supabase + Stripe)
- [docs/interviews/](docs/interviews/) — Ouroboros Socratic interviews that shaped the design
- [seed.yaml](seed.yaml) — Full project specification (ambiguity 0.10)

---

## 🙏 Built With & Inspired By

| Project | What we borrowed |
|---|---|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | Self-improvement loop pattern |
| [jina-ai/reader](https://github.com/jina-ai/reader) | URL-to-Markdown normalization |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | Multi-signal scoring |
| Supabase · Stripe · FastAPI · Pydantic · htmx | Infrastructure |

---

## 📜 License

MIT

---

<p align="center">
  <em>The algorithm that decides what information reaches you should belong to you.</em>
</p>
