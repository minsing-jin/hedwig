#!/usr/bin/env bash
# Railway deployment for Hedwig SaaS (one command).
#
# Prerequisites:
#   - Railway account (https://railway.app)
#   - Supabase project with URL + service_role key
#   - Stripe account with Pro + Team products created
#   - OpenAI API key (operator-owned, used for all SaaS users)
#
# Usage:
#   bash scripts/deploy_railway.sh

set -euo pipefail

BOLD="\033[1m"; GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[0;33m"; NC="\033[0m"

echo -e "${BOLD}🚂 Hedwig → Railway SaaS Deployment${NC}"
echo ""

# 1. Railway CLI
if ! command -v railway >/dev/null 2>&1; then
  echo -e "${YELLOW}Installing Railway CLI...${NC}"
  npm install -g @railway/cli
fi

# 2. Login
echo -e "${BOLD}Step 1/5: Railway login${NC}"
railway whoami >/dev/null 2>&1 || railway login

# 3. Project init
echo -e "${BOLD}Step 2/5: Railway project${NC}"
if [ ! -f ".railway/config.json" ] && ! railway status >/dev/null 2>&1; then
  railway init
fi

# 4. Env vars
echo ""
echo -e "${BOLD}Step 3/5: Environment variables${NC}"
echo "Paste each value when prompted (Enter to skip)."
echo ""

prompt_env() {
  local var="$1"; local help="$2"
  read -r -p "  $var ($help): " value
  if [ -n "$value" ]; then
    railway variables set "$var=$value" >/dev/null
    echo -e "  ${GREEN}✓${NC} saved"
  else
    echo -e "  ${YELLOW}⚠${NC}  skipped"
  fi
}

prompt_env OPERATOR_OPENAI_KEY "shared OpenAI key, sk-..."
prompt_env SUPABASE_URL "https://xxx.supabase.co"
prompt_env SUPABASE_KEY "service_role key"
prompt_env STRIPE_SECRET_KEY "sk_live_... or sk_test_..."
prompt_env STRIPE_WEBHOOK_SECRET "whsec_..."
prompt_env STRIPE_PRICE_PRO "price_... (\$19/mo)"
prompt_env STRIPE_PRICE_TEAM "price_... (\$49/mo)"

# 5. Supabase schema reminder
echo ""
echo -e "${BOLD}Step 4/5: Supabase schema${NC}"
echo "Run these in Supabase SQL Editor if not done:"
echo "  1. SCHEMA_SQL from hedwig/storage/supabase.py"
echo "  2. migrations/001_multi_tenant_schema.sql"
read -r -p "  Done? [y/N]: " ok
if [ "$ok" != "y" ] && [ "$ok" != "Y" ]; then
  echo -e "${RED}Aborted.${NC}"; exit 1
fi

# 6. Deploy
echo ""
echo -e "${BOLD}Step 5/5: Deploy${NC}"
railway up --detach

echo ""
echo -e "${GREEN}${BOLD}✓ Deployment started${NC}"
echo ""
echo "Next:"
echo "  • railway logs                  (tail logs)"
echo "  • railway domain                (get URL)"
echo "  • Point Stripe webhook at       https://<domain>/billing/webhook"
echo "  • Supabase OAuth redirect URL:  https://<domain>/auth/callback"
