<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/platforms-6-orange" alt="Platforms">
</p>

# Hedwig

**个人 AI 信号雷达** — 自动从6个平台收集AI信号，通过LLM过滤，将重要信息推送到Slack的个人情报系统。

> **[English](../README.md)** | **[한국어](README.ko.md)** | **[日本語](README.ja.md)**

```
采集 → 评分 → 过滤 → 推送
(6个平台)  (OpenAI)  (criteria.yaml)  (Slack)
```

## 为什么

AI领域的信息分散在X、Reddit、HN、LinkedIn、Threads、GeekNews等多个平台。
每天在各平台间切换，从噪音中筛选有意义的信号，令人疲惫不堪。

Hedwig **只筛选符合你标准的信号**，推送到Slack。

## 主要功能

- **6个数据源采集** — HN、Reddit（12个AI子版块）、GeekNews、AI博客/通讯、企业AI博客、独立AI媒体
- **LLM 双层评分** — 快速模型过滤，高性能模型解读/摘要
- **Devil's Advocate** — 每个信号附带反面观点和炒作预警
- **3级输出** — 即时警报 + 每日简报 + 每周简报（趋势 + 机会洞察）
- **反馈循环** — 通过Slack表情/回复反应，过滤标准自动进化
- **criteria.yaml** — 用YAML管理兴趣、忽略项、紧急度规则、项目上下文
- **Agent兼容** — Python API、CLI JSON输出、MCP服务器，支持AI代理集成

## 快速开始

```bash
# 1. 克隆 & 安装
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. 配置环境
cp .env.example .env
# 在 .env 中填入API密钥（参见下方配置说明）

# 3. 创建Supabase表
# 在Supabase SQL编辑器中运行 migrations/001_create_tables.sql

# 4. 运行
python -m hedwig.main --dry-run      # 仅采集（无需API密钥）
python -m hedwig.main --collect      # 采集 + LLM评分
python -m hedwig.main                # 完整流程
python -m hedwig.main --weekly       # 每周简报
```

## 配置

### API 密钥 (`.env`)

| 密钥 | 获取地址 |
|------|---------|
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com) → API Keys |
| `SUPABASE_URL` | [supabase.com](https://supabase.com) → 项目 → Settings → API |
| `SUPABASE_KEY` | 同上（使用 `service_role` 密钥） |
| `SLACK_WEBHOOK_ALERTS` | [api.slack.com](https://api.slack.com) → 创建应用 → Incoming Webhooks |
| `SLACK_WEBHOOK_DAILY` | 同一应用，为每日/每周频道创建第二个webhook |

### 过滤标准 (`criteria.yaml`)

```yaml
identity:
  role: "AI 构建者"
  focus: [AI agents, LLM tooling, infra]

signal_preferences:
  care_about:
    - 真实采用信号（非炒作）
    - 论文的实际应用可能性
  ignore:
    - 纯粹的梗和病毒内容
    - 无根据的预测

context:
  current_projects:
    - "当前项目名称"
```

## 定时任务

```bash
bash setup.sh
# 每天 09:00、19:00 自动运行
# 每周一 10:00 生成周报
```

## Slack 输出示例

### 即时警报 (`#alerts`)
```
🟢 [HACKER] LLM Architecture Gallery
relevance: 0.85 | urgency: alert

💡 为什么重要：可视化比较LLM架构的画廊，
   可快速掌握模型设计模式

😈 反面观点：可视化有用，但无法解释实际性能差异
```

### 每日简报
🔴 即时关注 &nbsp;|&nbsp; 🟡 主要趋势 &nbsp;|&nbsp; 🟢 值得注意 &nbsp;|&nbsp; 💡 洞察

### 每周简报
📊 趋势 &nbsp;|&nbsp; 🔥 Top 5 &nbsp;|&nbsp; 📈 弱信号 &nbsp;|&nbsp; 🎯 机会发现 &nbsp;|&nbsp; ⚖️ 炒作预警

## Agent 集成

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

详细信息请参阅[英文README](../README.md)的Agent Integration部分。

## 许可证

MIT
