<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <img src="https://img.shields.io/badge/sources-16+-orange" alt="Sources">
  <img src="https://img.shields.io/badge/version-2.1-purple" alt="Version">
</p>

# Hedwig

**自进化的个人AI信号雷达** — 个人算法主权。

> **[한국어](README.ko.md)** | **[English](../README.md)** | **[中文](README.zh.md)**

```
苏格拉底式引导 → 智能体收集 → 内容净化 → 预评分 → LLM评分 → 分发 → 自我进化
```

---

## 护城河:Hedwig 的独特之处

大多数信息工具是**手** — 只取回你指向的东西。Hedwig 是**大脑 + 手** — 它学习你关心什么,并随时间改进自己。

| 能力 | 其他工具 (Agent-Reach, last30days, bb-browser, r.jina.ai) | **Hedwig** |
|---|---|---|
| **谁决定收集什么?** | 你每次都要亲自决定 | AI 智能体,基于不断进化的标准 |
| **如何学习你的偏好?** | 不学习 | 苏格拉底式引导 + 布尔反馈 + 自然语言 + 周度记忆 |
| **随时间如何变化?** | 不变化(静态工具) | 每日微进化 + 每周宏进化 |
| **算法所有权** | 企业(YouTube、X)或固定(开源工具) | **你完全掌控** |
| **魔鬼代言人** | 无 | 每个信号都包含反对观点 |

### Hedwig 的五大独特护城河

1. **苏格拉底式引导** — LLM 通过提问使你的标准清晰化(ambiguity ≤ 0.2)。灵感来自 Ouroboros 哲学。无需手动配置文件。

2. **自进化算法** — 基于 [Karpathy autoresearch](https://github.com/karpathy/autoresearch) 模式的每日微变异 + 每周宏变异。系统实验标准,测量你的 upvote 比率,保留改进,丢弃退步。

3. **仅布尔反馈** — 只需 upvote/downvote。系统承担解读模式的重担。需要指引时可选自然语言输入。

4. **长期记忆** — 每周用户偏好快照追踪你的品味轨迹。系统理解你的兴趣如何在数月间演变,不只是本周。

5. **算法主权** — 与优化用户停留时间(=广告收入)的 YouTube/X 不同,Hedwig 优化*你定义的相关性*。你控制适应度函数。

---

## 它做什么

AI 信号散布在 15+ 个平台上。手动扫描噪音中的有意义信号令人疲惫。Hedwig:

1. **苏格拉底式访谈**具体化你所关心的内容
2. **AI 智能体**根据你的标准从 16+ 个源智能收集
3. **内容净化** — 通过 r.jina.ai 获得干净的 markdown(去广告/导航)
4. **数字预评分** — 在昂贵的 LLM 调用之前进行 5-factor 过滤
5. **LLM 评分** — 每个信号都包含魔鬼代言人反对观点
6. **分发到 Slack + Discord** — Alert / Daily / Weekly 三个频道
7. **自我进化** — 每日(微)+ 每周(宏),基于布尔反馈

---

## 快速开始

```bash
# 1. 克隆 & 安装
git clone https://github.com/minsing-jin/hedwig.git
cd hedwig
uv venv .venv && source .venv/bin/activate
uv pip install -e .

# 2. 配置 API 密钥
cp .env.example .env

# 3. 创建 Supabase 表
# 在 Supabase SQL Editor 中运行 hedwig/storage/supabase.py 的 SCHEMA_SQL

# 4. 苏格拉底式引导(首次设置)
python -m hedwig --onboard

# 5. 测试收集(无需 API 密钥)
python -m hedwig --dry-run

# 6. 运行完整流程
python -m hedwig
```

---

## CLI 命令

| 命令 | 功能 |
|---|---|
| `python -m hedwig --onboard` | 运行苏格拉底式访谈定义你的标准 |
| `python -m hedwig --sources` | 列出所有 16 个已注册源插件 |
| `python -m hedwig --dry-run` | 仅收集(无需 API 密钥) |
| `python -m hedwig --collect` | 收集 + LLM 评分,打印到控制台 |
| `python -m hedwig` | **每日完整流程**(收集 → 评分 → 分发 → 进化) |
| `python -m hedwig --weekly` | **周简报** + 宏进化 + 记忆更新 |
| `python -m hedwig --evolve` | 手动进化周期 |

---

## 如何使用(分步)

### 第 1 天 — 引导
```bash
python -m hedwig --onboard
```
系统提出一系列苏格拉底式问题:哪些主题重要、想要多深入、忽略什么、应用什么紧急规则。结果写入 `criteria.yaml`。

### 第 2 天 — 首次运行
```bash
python -m hedwig
```
智能体根据你的标准从 16 个源收集,通过 LLM 过滤,分发到 Slack/Discord。

### 第 3 天及以后 — 反应
对收到的信号 upvote/downvote。无需任何配置 — 系统读取你的反应。

### 每日(自动)
每次日运行都包含微进化步骤:LLM 分析反馈,对标准进行微调。

### 每周
```bash
python -m hedwig --weekly
```
深度分析:品味轨迹、源演进、新探索方向。更新你的长期记忆。

### 随时 — 重新校准
```bash
python -m hedwig --onboard
```

### Cron 设置
```bash
# 每日运行
0 9,19 * * * cd /path/to/hedwig && .venv/bin/python -m hedwig

# 每周运行(周一 10:00)
0 10 * * 1 cd /path/to/hedwig && .venv/bin/python -m hedwig --weekly
```

---

## 16 个内置源插件

| 类别 | 源 |
|---|---|
| **社交媒体** | X/Twitter, Reddit, LinkedIn, Threads, Bluesky, TikTok, Instagram |
| **技术社区** | Hacker News, GeekNews, YouTube, Polymarket |
| **学术** | arXiv, Semantic Scholar, Papers With Code |
| **网络** | Exa 语义搜索 |
| **新闻通讯** | Ben's Bites, Latent Space, The Decoder 等 |

**+ 用户可扩展:** 添加自定义 RSS、Discord/Telegram 频道、API 端点。

---

## 灵感 & 集成

| 项目 | Stars | Hedwig 借用的 |
|---|---|---|
| [karpathy/autoresearch](https://github.com/karpathy/autoresearch) | — | 自我改进循环模式 |
| [jina-ai/reader](https://github.com/jina-ai/reader) | 10.5K | **已集成** — URL 到 Markdown 净化 |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 1K | **已集成** — 5-factor 多信号评分算法 |
| [Panniantong/Agent-Reach](https://github.com/Panniantong/Agent-Reach) | 16.4K | 基于 cookie 的平台收集模式(计划中) |
| [epiral/bb-browser](https://github.com/epiral/bb-browser) | 4.3K | 登录所需平台的浏览器即 API(计划中) |

**但它们都没做 Hedwig 做的事:** 苏格拉底式引导、自进化标准、布尔反馈学习、魔鬼代言人、长期记忆。这些是 Hedwig 的独特护城河。

---

## 许可证

MIT

---

<p align="center">
  <i>决定哪些信息到达你的算法应该属于你。</i>
</p>
