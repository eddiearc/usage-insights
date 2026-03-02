# usage-insights-skill

架构说明：
- 该技能用于生成 Claude Code 与 Codex CLI 的统一历史复盘报告。
- 核心逻辑由 `generate_usage_report.py` 完成：先构建可审计证据层，再执行 Hybrid Agentic 推理，最后输出 5 维评分与改进建议。
- 输出为单文件美化 HTML + 证据 JSON，包含深度诊断指标卡、最近 14 天趋势对比、证据锚点与更好使用方式判定。

文件清单：
| 名字 | 地位 | 功能 |
| --- | --- | --- |
| SKILL.md | 核心说明 | 定义触发语义、执行步骤与参数示例 |
| generate_usage_report.py | 脚本 | 生成跨客户端历史分析，输出 HTML 报告、evidence.json、Agentic 诊断与判定标准 |
| README.md | 文档 | 说明 usage-insights 目录结构与职责 |

<!-- 📁 一旦我所属的文件夹有所变化，请更新我 -->
