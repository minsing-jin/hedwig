# Hedwig SaaS — Hosting Guide

How to deploy Hedwig as a real SaaS that users can access at hedwig.app
without any local setup.

## Deployment Files Already In Repo

The repository already includes the deployment files used by hosted setups:

- `Procfile` starts the web process with `python -m hedwig --dashboard --saas --port $PORT`
- `railway.toml` configures Railway start-up and the `/landing` healthcheck
- `nixpacks.toml` configures Railway's Nixpacks build/install/start phases
- `Dockerfile` builds a container image for self-hosting or non-Railway platforms

## Required Environment Variables

Set these in Railway, Docker, or your process manager before going live:

- `OPERATOR_OPENAI_KEY` for the shared SaaS LLM key
- `SUPABASE_URL` and `SUPABASE_KEY` for database and auth access
- `STRIPE_SECRET_KEY` for Stripe API access
- `STRIPE_WEBHOOK_SECRET` for webhook verification
- `STRIPE_PRICE_PRO` for the Pro subscription price
- `STRIPE_PRICE_TEAM` for the Team subscription price

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   User       │───→│  hedwig.app      │───→│  Supabase       │
│  (browser)   │    │  (your server)   │    │  (DB + Auth)    │
└──────────────┘    └────────┬─────────┘    └─────────────────┘
                             │
                             ↓
                    ┌──────────────────┐
                    │  OpenAI / Stripe │
                    │  (operator keys) │
                    └──────────────────┘
```

The user experience:
1. Visit `hedwig.app`
2. Click "Continue with X" (or Google, GitHub, etc.)
3. Drop SNS handles into auto-onboarding form
4. LLM analyzes their profiles → criteria auto-generated
5. Free tier: receive signals, vote, evolve
6. Optional: upgrade to Pro for unlimited

The user **never** sees:
- API keys
- .env files
- Supabase setup
- Database migrations
- CLI commands

## Hosting Options

### Recommended: Railway + Supabase + Cloudflare

| Service | Role | Cost |
|---------|------|------|
| **Railway** | Run FastAPI dashboard server | $5-20/mo |
| **Supabase** | Postgres + Auth + RLS | $0 (free tier) → $25/mo (Pro) |
| **Cloudflare** | DNS + CDN + SSL | Free |
| **Stripe** | Subscription billing | 2.9% + 30¢ per transaction |
| **OpenAI** | Operator LLM key | Pay-per-use (~$50-200/mo for 100 users) |

**Total operator cost (100 free users + 10 paid):**
- Railway: $20
- Supabase: $25
- OpenAI (estimated): $100
- Stripe fees: $5
- **= ~$150/month**

**Revenue at 10 Pro users:**
- 10 × $19 = $190/month
- **Break-even reached**

### Alternative: Fly.io + Supabase

Similar setup, Fly.io has better global edge regions.

### Self-hosted alternative: Docker + Hetzner

```bash
docker run -d \
  -e OPERATOR_OPENAI_KEY=sk-... \
  -e SUPABASE_URL=... \
  -e SUPABASE_KEY=... \
  -e STRIPE_SECRET_KEY=... \
  -p 8765:8765 \
  hedwig:latest \
  python -m hedwig --dashboard --saas --port 8765
```

Hetzner CX21 (€5/mo) handles ~500 users.

## Step-by-Step Deployment

### 1. Supabase Setup

```bash
# Create new Supabase project at supabase.com
# Get the URL and service_role key

# Run base schema (in Supabase SQL Editor)
# Copy from hedwig/storage/supabase.py SCHEMA_SQL

# Run multi-tenant migration
# Copy from migrations/001_multi_tenant_schema.sql

# Enable OAuth providers
# Supabase Dashboard → Authentication → Providers
# Enable: Google, GitHub, Twitter (X), Discord, etc.
# Set redirect URL to: https://hedwig.app/auth/callback
```

### 2. Stripe Setup

```bash
# Create Stripe account at stripe.com
# Create products:
#   - Hedwig Pro ($19/mo recurring)
#   - Hedwig Team ($49/mo recurring)
# Copy Price IDs

# Set up webhook
# Stripe Dashboard → Developers → Webhooks
# URL: https://hedwig.app/billing/webhook
# Events: checkout.session.completed, customer.subscription.*
```

### 3. Railway Deployment

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login & init
railway login
railway init

# Set environment variables
railway variables set OPERATOR_OPENAI_KEY=sk-...
railway variables set SUPABASE_URL=https://xxx.supabase.co
railway variables set SUPABASE_KEY=eyJ...
railway variables set STRIPE_SECRET_KEY=sk_live_...
railway variables set STRIPE_WEBHOOK_SECRET=whsec_...
railway variables set STRIPE_PRICE_PRO=price_...
railway variables set STRIPE_PRICE_TEAM=price_...

# Deployment config already checked in
# Procfile: web: python -m hedwig --dashboard --saas --port $PORT
# railway.toml: startCommand + healthcheckPath=/landing
# nixpacks.toml: install/start phases for Railway's Nixpacks builder

# Deploy
railway up
```

### 4. Custom Domain (Cloudflare)

```bash
# Buy domain at registrar (or use existing)
# Add to Cloudflare
# Set DNS:
#   CNAME @ -> railway.app provided URL
#   CNAME www -> railway.app provided URL
# Enable SSL/TLS → Full (strict)
```

### 5. Test Full Flow

1. Visit https://hedwig.app
2. Click "Continue with X"
3. Authorize → redirected to /onboarding/auto
4. Drop SNS handles + bio
5. Wait for inference
6. Receive criteria
7. Visit /signals → see first signals
8. Vote → trigger evolution
9. Click "Upgrade to Pro" → Stripe checkout
10. Test successful payment → Pro tier activated

## Operational Concerns

### Cost Control

- Set OpenAI usage alerts at $200/month
- Monitor `usage_tracking` table for outliers
- Auto-suspend free tier users at 50K tokens/day
- Cache LLM responses for repeated criteria/queries

### Scaling

- Single Railway instance handles ~1000 active users
- Beyond that: Railway Pro ($20/mo) → multiple replicas
- Supabase Pro ($25/mo) → 8GB DB, 100 concurrent connections
- Add Redis for session caching ($5/mo)

### Monitoring

- Railway provides logs + metrics
- Add Sentry for error tracking (free tier: 5K events/mo)
- Stripe Dashboard for billing health
- Supabase Dashboard for DB health

### Privacy & Compliance

- GDPR: users can export/delete their data via /settings
- All user data isolated via RLS
- Passwords managed by Supabase Auth (bcrypt)
- API keys never logged

## Branding Checklist

Before going live:

- [ ] Domain (hedwig.app, hedwig.ai, gethedwig.com, etc.)
- [ ] Logo (🦉 emoji works for v1)
- [ ] Favicon
- [ ] Terms of Service page
- [ ] Privacy Policy page
- [ ] Pricing page (already in landing.html)
- [ ] About page
- [ ] Contact email (hello@hedwig.app)
- [ ] Social media (@hedwigapp on X)
- [ ] Product Hunt launch page

## Launch Sequence

1. **Soft launch (week 1)**: Deploy to hedwig.app, test with friends
2. **Beta (week 2-4)**: Share in AI builder communities (X, Reddit r/MachineLearning, HN)
3. **Product Hunt (week 5)**: Launch on PH for visibility
4. **Iterate (ongoing)**: Use feedback to improve criteria inference, add sources

## Estimated Timeline

| Phase | Duration |
|-------|----------|
| Supabase + Stripe setup | 1 day |
| Railway deployment | 1 day |
| Domain + DNS | 1 hour |
| OAuth provider activation | 1 hour each |
| Testing full flow | 1 day |
| **Ready for soft launch** | **3-4 days** |
