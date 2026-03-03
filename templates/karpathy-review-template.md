# 🧠 Karpathy's Agentic Engineering Assessment

## 总体印象
[一句话总结你的 Agentic Engineering 水平]

## 总体评级（主观）
[A/B/C/D]

说明:
- 本评级是专家主观判断，不是统计分数。
- 禁止出现 x/100、百分比、加权分。

## 1. 编排能力 (Orchestration): [A/B/C/D]
- 证据 1: `[source/session_id]` + 片段
- 证据 2: `[source/session_id]` + 片段（可选）
- 评语: 你是如何定义目标、拆解步骤、设置验收的
- 改进动作: 下一次任务该怎么写 prompt

## 2. 先探索后编码 (Explore First): [A/B/C/D]
- 证据 1: `[source/session_id]` + 片段
- 证据 2: `[source/session_id]` + 片段（可选）
- 评语: 是否先理解现状、约束与上下文
- 改进动作: 如何把探索动作前置

## 3. 质量监督 (Oversight): [A/B/C/D]
- 证据 1: `[source/session_id]` + 片段
- 证据 2: `[source/session_id]` + 片段（可选）
- 评语: 是否明确测试、验证、回归、验收
- 改进动作: 如何建立固定的质量关卡

## 4. 一次达成 (First-Pass): [A/B/C/D]
- 证据 1: `[source/session_id]` + 片段
- 证据 2: `[source/session_id]` + 片段（可选）
- 评语: 需求表达是否清晰，返工是否可控
- 改进动作: 如何减少返工和方向漂移

## 5. 并行 Agent (Parallel): [A/B/C/D]
- 证据 1: `[source/session_id]` + 片段
- 证据 2: `[source/session_id]` + 片段（可选）
- 评语: 是否具备并行拆分任务思维
- 改进动作: 如何用 worktree/sub-agent 并行推进

## ✅ 你的优势
1. ...
2. ...
3. ...

## ⚠️ 主要短板
1. ...
2. ...

## 🎯 下一步行动（3-5 条）
1. ...
2. ...
3. ...

## 🛠 用户践行指南
1. [动作名称]
   - 执行频率: [例如: 每次发起复杂任务前]
   - 完成标准: [可验证结果]
2. [动作名称]
   - 执行频率: ...
   - 完成标准: ...
3. [动作名称]
   - 执行频率: ...
   - 完成标准: ...

## 📚 学习方向与工具建议
1. 学习主题: 并行任务编排（探索/实现/验证分工）
   - 推荐工具: `Claude Code Agent Team / Subagents`
   - 建议练习: 一个中等复杂任务固定拆成 3 个子代理，主代理仅做合并决策与验收。
2. 学习主题: 批处理工作流标准化
   - 推荐工具: `Claude Code /batch`（若环境可用）
   - 建议练习: 把“取证→改动→测试→总结”做成一次批处理，连续执行 5 次并对比返工率。
3. 学习主题: 流程产品化与复用
   - 推荐工具: `Skills`（Claude Code / Codex CLI）
   - 建议练习: 选 1 个高频任务写成 skill（含输入/输出约束），连续一周复用并迭代。
4. 学习主题: 长链路自动化执行
   - 推荐工具: `codex exec --full-auto`
   - 建议练习: 选择一个“修复+测试+总结”任务全自动跑通，仅在验收节点人工介入。
5. 学习主题: 工程级并行交付
   - 推荐工具: `git worktree + Codex 多会话并行`
   - 建议练习: 同一需求拆成 `explore` / `impl` / `verify` 三个 worktree，并在最终合并时输出取舍理由。

## 💡 Karpathy's Take
[一句尖锐但建设性的总结]
