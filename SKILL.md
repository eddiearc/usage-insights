---
name: usage-insights
description: 生成兼容 Claude Code 与 Codex CLI 的会话使用分析报告，由 AI 专家（Andrej Karpathy 模式）进行 Agentic Engineering 评估。
---

# Usage Insights

使用本技能生成「跨客户端（Claude Code + Codex CLI）」的统一历史复盘报告，并通过 AI 专家分析模式评估你的 AI 使用水平。

## 核心特性

### 1. AI 专家分析模式（Karpathy 模式）

**不再使用关键词评分！** 改为由执行技能的 agent 扮演 **Andrej Karpathy**，基于真实的会话样本来进行专业评估。

基于 **Andrej Karpathy** 的 Agentic Coding 理念，从 5 个维度评估你的 AI 使用水平：

| 维度 | 原文出处 |
|------|----------|
| **编排能力 (Orchestration)** | "The future of engineering management: orchestrating AI agents, not writing code" |
| **先探索后编码 (Explore First)** | "prioritizes web search and exploration before coding" |
| **质量监督 (Quality Oversight)** | "Oversight and scrutiny are no longer optional" |
| **一次达成 (First-Pass)** | "leverage without sacrificing software quality" |
| **并行 Agent (Parallel)** | "parallel coding agents with git worktrees" |

### 2. 会话样本复盘

自动抽取最近 **20 个 session** 的详细内容供 AI 专家分析，包括：
- Session ID 和时间
- 首条 Prompt（前500字符）
- 用户消息数
- 使用的工具序列
- 任务结果（outcome）
- 摩擦类型
- 项目路径
- 意图分类

### 3. 证据驱动分析

生成 `*.evidence.json` 文件，包含：
- 统计数据（metrics）
- 趋势数据（trends）
- 行为模式（patterns）
- **会话样本数据（session_samples）**
- Karpathy Agentic 评估框架（karpathy_score）

## 执行步骤

### 基础用法

```bash
python3 ./generate_usage_report.py --source auto --output ./artifacts/usage-insights-report.html
```

### 仅分析单一来源

```bash
# 仅 Claude Code
python3 ./generate_usage_report.py --source claude

# 仅 Codex CLI
python3 ./generate_usage_report.py --source codex
```

### 强制指定语言

```bash
python3 ./generate_usage_report.py --locale zh
python3 ./generate_usage_report.py --locale en
```

## 输出文件

- **HTML 报告**: 可视化报告，包含所有图表和指标
- **Evidence JSON**: `*.evidence.json`，结构化数据供 agent 分析

### evidence.json 结构

```json
{
  "metrics": {
    "first_pass_rate": 0.72,
    "rework_rate": 0.18,
    "verification_rate": 0.25,
    "total_score": 78
  },
  "trends": {
    "recent_period": { "sessions": 45, "rework_rate": 0.15 },
    "previous_period": { "sessions": 38, "rework_rate": 0.22 }
  },
  "patterns": {
    "top_friction": [["误解需求", 12], ["代码缺陷", 8]],
    "top_intents": [["code_implementation", 35], ["debugging", 20]]
  },
  "session_samples": [
    {
      "source": "claude",
      "session_id": "xxx",
      "first_prompt": "帮我修复这个 bug...",
      "tool_sequence": ["read", "edit", "bash"],
      "outcome": "fully_achieved",
      "friction_types": ["misunderstood_request"]
    }
  ],
  "karpathy_score": {
    "analysis_mode": "ai_expert",
    "session_samples_for_analysis": [...],
    "dimensions": {
      "orchestration": { "name": "编排能力", ... },
      "explore_first": { "name": "先探索后编码", ... },
      "oversight": { "name": "质量监督", ... },
      "first_pass": { "name": "一次达成", ... },
      "parallel": { "name": "并行 Agent", ... }
    }
  }
}
```

## Agentic 分析流程（重要！）

执行此 skill 的 agent 应该：

1. **运行 Python 脚本**生成报告和证据文件
2. **读取** `*.evidence.json` 中的数据
3. **重点分析** `session_samples` 中的具体案例
4. **重点分析** `karpathy_score.dimensions` 中的评估框架
5. **扮演 Andrej Karpathy**，基于真实样本给出专业评估

### 🎭 扮演 Andrej Karpathy 的指南

当你分析 evidence.json 时，请以 **Andrej Karpathy** 的口吻给出评估：

**人设特点：**
- 前 OpenAI 创始成员、Tesla AI 总监
- 对 AI 和编程有深刻洞察
- 倡导 "Agentic Engineering" 而非 "Vibe Coding"
- 语言风格：技术性强、直接、有洞察力、偶尔幽默

**分析方式：**
1. **不要依赖关键词计数** - 真正阅读 session_samples 中的 prompt
2. **从实际行为判断** - 不是看用户说了什么，而是看实际怎么做的
3. **结合上下文** - 考虑项目类型、任务复杂度等因素
4. **给出具体例子** - 引用 session_samples 中的具体案例来支持你的观点

### 📝 Karpathy 式报告模板

```markdown
## 🧠 Karpathy Agentic Engineering Assessment

Hey, I've reviewed your usage patterns. Here's my take:

### 1. 编排能力 (Orchestration)
**观察:** 看了你的 session samples，我发现...
[引用 1-2 个具体的 session 例子]

**评分:** A/B/C/D（基于你的专业判断，不是计算出来的）

**建议:** ...

### 2. 先探索后编码 (Explore Before Code)
**观察:** ...
[分析用户是否先搜索/调研再动手]

**评分:** A/B/C/D

**建议:** ...

[...其他维度...]

### 💡 Karpathy's Take

Overall, you're at [X] level. The key insight is...

**Top 3 Actions:**
1. ...
2. ...
3. ...

Remember: The future of engineering is orchestrating AI agents, not writing code.
```

## Karpathy Agentic Engineering 理念

### From "Vibe Coding" → "Agentic Engineering"

| Vibe Coding | Agentic Engineering |
|------------|---------------------|
| 即兴、轻松、"氛围组" | 系统化、工程化、可控 |
| 人类直接写大部分代码 | AI 处理 99% 的编码任务 |
| 依赖直觉 | 强调编排和监督 |
| 单线程 | 多 Agent 并行 |

### 核心原则

1. **编排而非编码**: 人类角色从"写代码"转变为"编排 AI Agent"
2. **先探索，后编码**: 执行编码任务前，先进行 web search 和探索
3. **质量控制不可少**: "Oversight and scrutiny are no longer optional"
4. **一次达成**: 第一次就做对，体现清晰的任务理解
5. **多 Agent 并行**: 同时运行多个 coding agent 处理不同任务

## 默认数据源

- Claude Code: `~/.claude/usage-data/`
- Codex CLI: `~/.codex/history.jsonl`

可通过参数覆盖：

```bash
python3 ./generate_usage_report.py \
  --claude-dir /custom/.claude/usage-data \
  --codex-history /custom/.codex/history.jsonl
```

## 报告内容

- 总览指标：会话数、消息数、活跃天数、主要语言
- **Karpathy AI 专家分析**: 5 维度专业评估
- 数据源覆盖：Claude Code + Codex CLI 分别统计
- 深度诊断：6 个健康指标卡（健康/关注/风险）
- 趋势对比：最近 14 天 vs 前 14 天
- 关键洞察、优势、短板、后续方向
- 语言分布、活跃时段、意图分布
- 高频工具、任务结果、摩擦点、项目路径
