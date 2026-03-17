<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/platforms-6-orange" alt="Platforms">
</p>

# Hedwig

**パーソナルAIシグナルレーダー** — 6つのプラットフォームからAIシグナルを自動収集し、LLMでフィルタリングして、Slackに配信する個人インテリジェンスシステム。

> **[English](../README.md)** | **[한국어](README.ko.md)** | **[中文](README.zh.md)**

```
収集 → スコアリング → フィルタリング → 配信
(6プラットフォーム)  (OpenAI)     (criteria.yaml)   (Slack)
```

## なぜ作ったのか

AI分野の情報はX、Reddit、HN、LinkedIn、Threads、GeekNewsなど多くのプラットフォームに散らばっている。
毎日各プラットフォームを巡回して、ノイズの中から意味のあるシグナルを見つけるのは疲れる。

Hedwigは**自分の基準に合うシグナルだけを選んで**Slackに送る。

## 主な機能

- **6つのソース収集** — HN、Reddit（12のAIサブレディット）、GeekNews、AIブログ/ニュースレター、企業AIブログ、インディーAIプレス
- **LLM 2段階スコアリング** — 高速モデルでフィルタリング、高性能モデルで解釈/要約
- **Devil's Advocate** — 各シグナルに反対意見・ハイプ警告を付与
- **3段階出力** — 個別アラート + デイリーブリーフィング + ウィークリーブリーフィング（トレンド + 機会発見）
- **フィードバックループ** — Slackの絵文字/スレッドで反応するとフィルタリング基準が自動進化
- **criteria.yaml** — 関心事、無視項目、緊急度ルール、プロジェクトコンテキストをYAMLで管理
- **エージェント対応** — Python API、CLI JSON出力、MCPサーバーでAIエージェント連携

## クイックスタート

```bash
# 1. クローン & インストール
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. 環境設定
cp .env.example .env
# .envにAPIキーを入力（下記の設定を参照）

# 3. Supabaseテーブル作成
# Supabase SQLエディタで migrations/001_create_tables.sql を実行

# 4. 実行
python -m hedwig.main --dry-run      # 収集のみ（APIキー不要）
python -m hedwig.main --collect      # 収集 + LLMスコアリング
python -m hedwig.main                # フルパイプライン
python -m hedwig.main --weekly       # ウィークリーブリーフィング
```

## 設定

### APIキー (`.env`)

| キー | 取得先 |
|------|--------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) → API Keys |
| `SUPABASE_URL` | [supabase.com](https://supabase.com) → プロジェクト → Settings → API |
| `SUPABASE_KEY` | 同上（`service_role`キーを使用） |
| `SLACK_WEBHOOK_ALERTS` | [api.slack.com](https://api.slack.com) → アプリ作成 → Incoming Webhooks |
| `SLACK_WEBHOOK_DAILY` | 同じアプリ、デイリー/ウィークリーチャンネル用の2つ目のwebhook |

### フィルタリング基準 (`criteria.yaml`)

```yaml
identity:
  role: "AIビルダー"
  focus: [AI agents, LLM tooling, infra]

signal_preferences:
  care_about:
    - 実際の採用シグナル（ハイプではない）
    - 論文の実務適用可能性
  ignore:
    - 単純なミーム/バイラル
    - 根拠のない予測

context:
  current_projects:
    - "現在のプロジェクト名"
```

## Cron設定

```bash
bash setup.sh
# 毎日 09:00、19:00 に自動実行
# 毎週月曜 10:00 にウィークリーブリーフィング
```

## Slack出力例

### 個別アラート (`#alerts`)
```
🟢 [HACKER] LLM Architecture Gallery
relevance: 0.85 | urgency: alert

💡 なぜ重要か：LLMアーキテクチャを視覚的に比較するギャラリー、
   モデル設計パターンを素早く把握できる

😈 反対意見：可視化は有用だが、実際のパフォーマンス差を説明はしない
```

### デイリーブリーフィング
🔴 即座に注目 &nbsp;|&nbsp; 🟡 主要トレンド &nbsp;|&nbsp; 🟢 参考 &nbsp;|&nbsp; 💡 インサイト

### ウィークリーブリーフィング
📊 トレンド &nbsp;|&nbsp; 🔥 Top 5 &nbsp;|&nbsp; 📈 弱シグナル &nbsp;|&nbsp; 🎯 機会発見 &nbsp;|&nbsp; ⚖️ ハイプ警告

## エージェント連携

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

詳細は[英語README](../README.md)のAgent Integrationセクションを参照。

## ライセンス

MIT
