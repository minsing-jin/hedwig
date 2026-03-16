#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Hedwig Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$(dirname "$0")"

# 1. Python venv
if [ ! -d ".venv" ]; then
    echo "[1/5] Creating virtual environment..."
    uv venv .venv
else
    echo "[1/5] Virtual environment exists ✓"
fi

echo "[2/5] Installing dependencies..."
.venv/bin/pip install -e . -q

# 2. .env check
if [ ! -f ".env" ]; then
    echo ""
    echo "[3/5] ⚠️  .env 파일이 없습니다!"
    echo "  cp .env.example .env 후 API 키를 입력하세요:"
    echo ""
    echo "  필수:"
    echo "    OPENAI_API_KEY=sk-..."
    echo "    SUPABASE_URL=https://xxx.supabase.co"
    echo "    SUPABASE_KEY=eyJ..."
    echo "    SLACK_WEBHOOK_ALERTS=https://hooks.slack.com/services/..."
    echo "    SLACK_WEBHOOK_DAILY=https://hooks.slack.com/services/..."
    echo ""
    cp .env.example .env
    echo "  .env.example → .env 복사 완료. 키를 입력하세요."
else
    echo "[3/5] .env exists ✓"
fi

# 3. Supabase tables
echo "[4/5] Supabase 테이블 생성 SQL:"
echo "  Supabase Dashboard > SQL Editor 에서 아래 파일 실행:"
echo "  → migrations/001_create_tables.sql"

# 4. Cron
echo "[5/5] Cron 등록 확인..."
CRON_DAILY="0 9,19 * * * cd $(pwd) && .venv/bin/python -m hedwig.main >> logs/hedwig.log 2>&1"
CRON_WEEKLY="0 10 * * 1 cd $(pwd) && .venv/bin/python -m hedwig.main --weekly >> logs/hedwig.log 2>&1"

mkdir -p logs

if crontab -l 2>/dev/null | grep -q "hedwig.main"; then
    echo "  Cron already registered ✓"
else
    echo ""
    echo "  아래 cron을 등록하시겠습니까?"
    echo "  Daily  (매일 09:00, 19:00): $CRON_DAILY"
    echo "  Weekly (매주 월 10:00):     $CRON_WEEKLY"
    echo ""
    read -p "  cron 등록? (y/n): " answer
    if [ "$answer" = "y" ]; then
        (crontab -l 2>/dev/null; echo "$CRON_DAILY"; echo "$CRON_WEEKLY") | crontab -
        echo "  Cron registered ✓"
    else
        echo "  Skipped. 나중에 수동 등록하세요."
    fi
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  테스트:  .venv/bin/python -m hedwig.main --dry-run"
echo "  실행:    .venv/bin/python -m hedwig.main"
echo "  주간:    .venv/bin/python -m hedwig.main --weekly"
echo ""
