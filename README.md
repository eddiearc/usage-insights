# usage-insights-skill

生成 Claude Code 与 Codex CLI 的统一历史复盘报告，包含 **Karpathy Agentic Engineering 评分系统**。

## 核心特性

- 📊 **跨客户端分析**: 同时分析 Claude Code 和 Codex CLI 的使用数据
- 🧠 **Karpathy Agentic Score**: 基于 Andrej Karpathy 的 Agentic Coding 理念进行 5 维度评分
- 🔍 **抽样复盘**: 自动抽取最近 20 个 session 的详细内容进行深度分析
- 📈 **趋势对比**: 最近 14 天 vs 前 14 天的使用趋势
- 🎨 **美观报告**: 单文件 HTML 输出，支持中文/英文自动切换

## 快速开始

```bash
# 生成报告
python3 ./generate_usage_report.py --source auto --output ./report.html

# 指定语言
python3 ./generate_usage_report.py --locale zh

# 仅分析 Claude Code
python3 ./generate_usage_report.py --source claude

# 仅分析 Codex CLI  
python3 ./generate_usage_report.py --source codex
```

## 输出文件

- `report.html` - 可视化报告
- `report.evidence.json` - 结构化证据数据（包含 Karpathy Score）

## Karpathy Agentic Engineering 评分

基于 Andrej Karpathy 的 Agentic Coding 理念：

| 维度 | 权重 | 指标 | 原文出处 |
|------|------|------|----------|
| **编排能力** | 20% | 规划信号、任务分解 | "The future of engineering management: orchestrating AI agents, not writing code" |
| **先探索后编码** | 20% | 探索:实现比例 | "prioritizes web search and exploration before coding" |
| **质量监督** | 20% | 验证信号、测试 | "Oversight and scrutiny are no longer optional" |
| **一次达成** | 20% | 返工率 | "leverage without sacrificing software quality" |
| **并行 Agent** | 20% | 工具多样性、项目数 | "parallel coding agents with git worktrees" |

### 参考链接

- **Andrej Karpathy 推文**: https://twitter.com/karpathy/status/1886193731057684941
- **从 Vibe Coding 到 Agentic Engineering**: https://medium.com/generative-ai-revolution-ai-native-transformation/openai-cofounder-andrej-karpathy-signals-the-shift-from-vibe-coding-to-agentic-engineering-ea4bc364c4a1
- **Vibe Coding 一周年回顾**: https://twitter.com/karpathy/status/2019137879310836075
- **The 80% Problem in Agentic Coding**: https://addyo.substack.com/p/the-80-problem-in-agentic-coding

## 文件清单

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 核心使用说明、触发语义、参数示例 |
| `generate_usage_report.py` | 主脚本，生成 HTML 报告和 evidence.json |
| `README.md` | 本文件 |

## 默认数据源

- **Claude Code**: `~/.claude/usage-data/`
- **Codex CLI**: `~/.codex/history.jsonl`

可通过 `--claude-dir` 和 `--codex-history` 参数覆盖。

## Agentic Engineering vs Vibe Coding

| | Vibe Coding | Agentic Engineering |
|--|-------------|---------------------|
| **角色** | 人类写代码 | 人类编排 AI |
| **流程** | 即兴、直觉 | 系统化、可控 |
| **质量** | 依赖运气 | 强制验证 |
| **并行** | 单线程 | 多 Agent |

## 版本历史

### v2.0.0 (2026-03-03)
- ✨ 新增 Karpathy Agentic Engineering 评分系统
- ✨ 新增抽样复盘功能（最近 20 个 session）
- 🔥 移除外部 API Key 依赖
- 📊 Evidence JSON 包含完整分析 prompt

### v1.0.0
- 🎉 初始版本
- 📊 跨客户端使用分析
- 📈 5 维使用姿势评分

---

*Built with 🦞 by OpenClaw Agent*
