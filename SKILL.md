---
name: usage-insights
description: 生成兼容 Claude Code 与 Codex CLI 的会话使用分析报告。用于“分析我的使用习惯/usage report/会话洞察/工作流复盘/生成美观报告”等场景；支持自动识别主要语言（中文/英文）并切换报告文案。
---

# Usage Insights

使用本技能生成「跨客户端（Claude Code + Codex CLI）」的统一历史复盘报告，并输出更美观的 HTML。
分析流程采用 Hybrid Agentic：
- 第 1 层（证据）：代码提取可复现事实，并输出 `evidence.json`
- 第 2 层（推理）：可选调用 OpenAI 兼容模型做深度诊断
- 第 3 层（约束）：要求建议绑定证据锚点与置信度

报告核心目标：
- 分析你在 AI 工具使用上的优势与短板
- 给出可执行的后续努力方向
- 给出可解释的“使用姿势评分”（总分 + 5 个维度分）
- 输出深度诊断：一次达成率、返工率、工具切换成本、验证覆盖率、近 14 天趋势对比

## 执行步骤

1. 运行：

```bash
python3 ./generate_usage_report.py --source auto --output ./artifacts/usage-insights-report.html
```

2. 启用 Hybrid Agentic（需要配置 API Key + 模型）：

```bash
export OPENAI_API_KEY=...
python3 ./generate_usage_report.py \
  --source auto \
  --analysis-mode hybrid \
  --agent-model gpt-4o-mini \
  --output ./artifacts/usage-insights-report.html
```

3. 若只分析单一来源：

```bash
# 仅 Claude Code
python3 ./generate_usage_report.py --source claude

# 仅 Codex CLI
python3 ./generate_usage_report.py --source codex
```

4. 若需要强制语言（否则默认自动识别主要语言）：

```bash
python3 ./generate_usage_report.py --locale zh
python3 ./generate_usage_report.py --locale en
```

## 默认数据源

- Claude Code: `~/.claude/usage-data/`
- Codex CLI: `~/.codex/history.jsonl`

可通过参数覆盖：

```bash
python3 ./generate_usage_report.py \
  --claude-dir /custom/.claude/usage-data \
  --codex-history /custom/.codex/history.jsonl
```

## 输出说明

- 输出为单文件 HTML，适合本地直接打开查看。
- 同时输出证据文件：默认 `<output>.evidence.json`，用于审计结论依据。
- 报告包含：总览指标、使用姿势评分、优势、短板、后续努力方向，以及语言占比、时段活跃、意图分布、工具与摩擦（若数据源可提供）等分析维度。
- 报告新增深度诊断区：6 个健康指标卡（健康/关注/风险），并附最近 14 天 vs 前 14 天趋势对比。
- 报告新增 Agentic 区块：总结、证据锚点、以及“什么是更好的使用方式”清单。
- 当 Codex 数据缺失某类指标时，报告会自动降级展示可用维度。

## “更好的使用方式”判定标准

- 一次达成率更高：同等任务下，最终通过次数更多、返工更少
- 返工率更低：`still/again/返工` 等信号下降
- 验证更早：在完成前明确触发 `test/lint/verify/回归`
- 切换更少：同类任务固定主链路，工具跳转减少
- 趋势更稳：最近 14 天相对前 14 天，返工下降且验证覆盖提升
