# usage-insights-skill

生成 Claude Code 与 Codex CLI 的统一历史复盘报告，采用 **Karpathy 视角的定性评审**。

## 核心特性

- 📊 **跨客户端分析**: 同时分析 Claude Code 和 Codex CLI 的使用数据
- 🎭 **Karpathy 专家评审**: 基于真实会话样本进行 5 维定性评价
- 🔍 **抽样复盘**: 自动抽取最近 20 个 session，输出证据文件
- 🧱 **证据先行**: 先取样，再由 agent 写主观评级与改进建议
- 🚫 **禁程序化评分**: 不输出 x/100、百分比或加权总分

## 快速开始

```bash
# 1) 抽取跨客户端会话样本（默认 20 条）
bash ./scripts/collect_session_samples.sh \
  --source auto \
  --limit 20 \
  --output-dir ./artifacts

# 2) 按模板写专家复盘（由 agent 完成）
# 使用 ./templates/karpathy-review-template.md

# 3) 渲染简洁高对比 HTML（优缺点颜色化 + 重点加粗）
python3 ./scripts/render_review_html.py \
  --input ./artifacts/usage-insights-review.md \
  --output ./artifacts/usage-insights-review.html
```

## 输出文件

- `artifacts/session-samples.json` - 结构化会话样本
- `artifacts/session-samples.md` - 人类可读样本摘要
- `artifacts/usage-insights-review.md` - 最终专家评审报告（由 agent 生成）
- `artifacts/usage-insights-review.html` - 可视化复盘页面（优缺点高亮）

## 评审方式（非评分器）

基于 Andrej Karpathy 的 Agentic Coding 理念，从 5 个维度给出主观评级:

| 维度 | 评审重点 |
|------|----------|
| 编排能力 (Orchestration) | 有没有先拆解任务、定义验收 |
| 先探索后编码 (Explore First) | 有没有先理解现状再改动 |
| 质量监督 (Oversight) | 有没有主动要求验证/测试 |
| 一次达成 (First-Pass) | 指令是否清晰、返工是否可控 |
| 并行 Agent (Parallel) | 是否具备并行拆任务思维 |

最终仅允许:
- 维度等级: `A/B/C/D`（主观）
- 总体评级: `A/B/C/D`（主观）

禁止:
- `92/100`、`53%`、`权重加权`、`关键词命中分`

### 参考链接

- **Andrej Karpathy 推文**: https://twitter.com/karpathy/status/1886193731057684941
- **从 Vibe Coding 到 Agentic Engineering**: https://medium.com/generative-ai-revolution-ai-native-transformation/openai-cofounder-andrej-karpathy-signals-the-shift-from-vibe-coding-to-agentic-engineering-ea4bc364c4a1
- **Vibe Coding 一周年回顾**: https://twitter.com/karpathy/status/2019137879310836075
- **The 80% Problem in Agentic Coding**: https://addyo.substack.com/p/the-80-problem-in-agentic-coding

## 文件清单

| 文件 | 说明 |
|------|------|
| `SKILL.md` | 核心使用说明、触发语义、参数示例 |
| `scripts/collect_session_samples.sh` | 会话样本抽取脚本（不做评分） |
| `scripts/render_review_html.py` | Markdown 评审报告渲染为 HTML（优缺点颜色化） |
| `templates/karpathy-review-template.md` | 专家评审模板 |
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

### v3.0.0 (2026-03-03)
- 🔥 删除程序化 Python 评分器
- ✨ 改为证据抽样 + Karpathy 主观评审
- ✨ 新增样本抽取脚本与评审模板
- ✨ 新增评审报告 HTML 渲染脚本（优缺点颜色强化）
- 🚫 默认禁止数字化评分表达

### v1.0.0
- 🎉 初始版本
- 📊 跨客户端使用分析
- 📈 5 维使用姿势评分

---

*Built with 🦞 by OpenClaw Agent*
