---
name: usage-insights
description: 生成兼容 Claude Code 与 Codex CLI 的会话使用分析报告，包含 Karpathy Agentic Engineering 评分。用于"分析我的使用习惯/usage report/会话洞察/工作流复盘/生成美观报告"等场景。
---

# Usage Insights

使用本技能生成「跨客户端（Claude Code + Codex CLI）」的统一历史复盘报告，并输出更美观的 HTML。

## 核心特性

### 1. Karpathy Agentic Engineering 评分 (新增)

基于 **Andrej Karpathy** 的 Agentic Coding 理念，从 5 个维度评估你的 AI 使用水平：

| 维度 | 权重 | 原文出处 |
|------|------|----------|
| **编排能力 (Orchestration)** | 20% | "The future of engineering management: orchestrating AI agents, not writing code" |
| **先探索后编码 (Explore First)** | 20% | "prioritizes web search and exploration before coding" |
| **质量监督 (Quality Oversight)** | 20% | "Oversight and scrutiny are no longer optional" |
| **一次达成 (First-Pass)** | 20% | "leverage without sacrificing software quality" |
| **并行 Agent (Parallel)** | 20% | "parallel coding agents with git worktrees" |

**评分标准**:
- A (≥85): 优秀的 Agentic Engineering 实践
- B (70-84): 良好的 Agentic 意识，有提升空间
- C (55-69): 基础水平，需要系统性改进
- D (<55): 主要还是 Vibe Coding，需要转变思维

### 2. 抽样复盘

自动抽取最近 **20 个 session** 的详细内容，包括：
- Session ID 和时间
- 首条 Prompt（前200字符）
- 用户消息数
- 使用的工具序列
- 任务结果（outcome）
- 摩擦类型
- 项目路径
- 意图分类
- 返工/验证信号

### 3. 证据驱动分析

生成 `*.evidence.json` 文件，包含：
- 统计数据（metrics）
- 趋势数据（trends）
- 行为模式（patterns）
- 抽样复盘数据（session_samples）
- **Karpathy Agentic Score**（karpathy_agentic_score）

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
  "karpathy_agentic_score": {
    "total_score": 82,
    "grade": "B",
    "dimensions": [
      {
        "id": "orchestration",
        "name": "编排能力 (Orchestration)",
        "score": 85,
        "source": "The future of engineering management: orchestrating AI agents..."
      }
    ],
    "interpretation": {
      "orchestration": "High planning signals indicate good task decomposition",
      "explore_first": "Good balance of exploration vs implementation",
      "oversight": "Strong verification habits",
      "first_pass": "Excellent first-pass completion",
      "parallel": "Good use of parallel workflows"
    }
  }
}
```

## Agentic 分析流程

执行此 skill 的 agent 应该：

1. 运行 Python 脚本生成报告和证据文件
2. 读取 `*.evidence.json` 中的结构化数据
3. 重点分析 `session_samples` 中的具体案例
4. 基于 **Karpathy Agentic Score** 给出评估
5. **模拟 Andrej Karpathy 的口吻**给出建议

### 模拟 Karpathy 打分模板

```markdown
## 🧠 Karpathy Agentic Engineering Assessment

### 维度评分

1. **编排能力 (Orchestration)** - 85/100
   - 原文: "The future of engineering management: orchestrating AI agents, not writing code"
   - 评价: 你的规划信号很强，说明你善于分解任务。但还可以更系统化，考虑使用更明确的任务模板。

2. **先探索后编码 (Explore Before Code)** - 72/100
   - 原文: "prioritizes web search and exploration before coding"
   - 评价:  exploration vs implementation 的比例不错，但在复杂任务前可以更充分地调研现有方案。

[...其他维度...]

### 总分: 82/100 (Grade: B)

### Karpathy 式建议

1. **建立验证清单**: 每个任务开始前明确"完成标准"，避免返工。
2. **多用并行 Agent**: 对于独立任务，尝试同时启动多个 agent，用 git worktree 管理。
3. **先搜索再动手**: 复杂任务前先让 agent 调研 3-5 个现有方案。
4. **定期复盘**: 每周 review 一次高频摩擦类型，固化到 SKILL。
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
- **Karpathy Agentic Score**: 5 维度评分 + 解读
- 数据源覆盖：Claude Code + Codex CLI 分别统计
- 使用姿势评分：总分 + 5 维度分（每项 20 分）
- 深度诊断：6 个健康指标卡（健康/关注/风险）
- 趋势对比：最近 14 天 vs 前 14 天
- 关键洞察、优势、短板、后续方向
- 语言分布、活跃时段、意图分布
- 高频工具、任务结果、摩擦点、项目路径
- Agentic 解读区块
