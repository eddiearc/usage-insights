#!/usr/bin/env python3
"""Generate a cross-client usage insights HTML report for Claude Code and Codex CLI.

重构说明 (v2.0):
- 移除了对外部 API key 的依赖
- Agentic 分析改为生成结构化 evidence 数据
- 由执行 skill 的 agent 基于 evidence 自行完成分析
- 输出包含 evidence.json，供 agent 分析使用
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


ZH_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
EN_CHAR_RE = re.compile(r"[A-Za-z]")
VERIFICATION_PATTERNS = [
    re.compile(r"测试|验证|回归|复测|单测|集成测试|冒烟|验收"),
    re.compile(r"\btest(s|ing)?\b|\bverify\b|\bvalidation\b|\bregression\b|\bassert\b|\blint\b|\btype-?check\b|\bsmoke\b", re.I),
]
PLANNING_PATTERNS = [
    re.compile(r"计划|步骤|拆解|分解|里程碑|待办|清单|验收标准"),
    re.compile(r"\bplan\b|\bsteps?\b|\btodo\b|\bmilestone\b|\bacceptance criteria\b", re.I),
]
FOLLOWUP_PATTERNS = [
    re.compile(r"还是|仍然|依旧|又|再次|返工|重试|不行|没好|继续报错"),
    re.compile(r"\bstill\b|\bagain\b|\bretry\b|\brework\b|\bnot work(?:ing)?\b|\bdoesn'?t work\b|\bfails? again\b", re.I),
]
ACCEPTANCE_PATTERNS = [
    re.compile(r"验收|完成标准|done"),
    re.compile(r"\bacceptance\b|\bdefinition of done\b|\bdone when\b", re.I),
]

CODEX_INTENT_PATTERNS: list[tuple[str, list[re.Pattern[str]]]] = [
    ("content_creation", [re.compile(r"小红书|文章|文案|标题|润色|改写"), re.compile(r"\bcontent\b|\bpost\b|\bcopy\b|\bheadline\b", re.I)]),
    ("release_build", [re.compile(r"发布|发版|构建|签名|公证|notar"), re.compile(r"\brelease\b|\bbuild\b|\bsign\b|\bdeploy\b", re.I)]),
    ("debugging", [re.compile(r"报错|修复|排查|无法|失败|bug"), re.compile(r"\bdebug\b|\bfix\b|\berror\b|\bfail", re.I)]),
    ("code_implementation", [re.compile(r"实现|开发|重构|改造|加功能|新增"), re.compile(r"\bimplement\b|\brefactor\b|\bfeature\b|\bcoding\b", re.I)]),
    ("tooling_config", [re.compile(r"安装|配置|技能|skill|mcp|tmux"), re.compile(r"\binstall\b|\bconfig\b|\bsetup\b", re.I)]),
    ("quick_question", [re.compile(r"为什么|怎么|是什么|能否"), re.compile(r"^\s*how\b|^\s*why\b|^\s*what\b|\?", re.I)]),
]

INTENT_LABELS = {
    "zh": {"content_creation": "内容创作", "release_build": "构建发布", "debugging": "调试修复", "code_implementation": "代码实现", "tooling_config": "工具配置", "quick_question": "快速问答", "other": "其他"},
    "en": {"content_creation": "Content Creation", "release_build": "Build & Release", "debugging": "Debugging", "code_implementation": "Implementation", "tooling_config": "Tooling Config", "quick_question": "Quick Questions", "other": "Other"},
}

# Karpathy Agentic Engineering 评分标准
KARPATHY_AGENTIC_CRITERIA = {
    "zh": [
        {
            "id": "orchestration",
            "name": "编排能力 (Orchestration)",
            "description": "从'写代码'转变为'编排 AI Agent'，设计工作流程、分解任务",
            "source": "Karpathy: 'The future of engineering management: orchestrating AI agents, not writing code'",
            "indicators": ["规划信号", "任务分解", "多步骤执行"],
        },
        {
            "id": "explore_before_code",
            "name": "先探索后编码 (Explore First)",
            "description": "编码前进行搜索和探索，了解上下文和现有方案",
            "source": "Karpathy workflow: prioritizes web search and exploration before coding",
            "indicators": ["搜索/查阅", "调研", "对比方案"],
        },
        {
            "id": "quality_oversight",
            "name": "质量监督 (Oversight)",
            "description": "'Oversight and scrutiny are no longer optional'，建立验证机制",
            "source": "Karpathy: 'Agents are now part of the default workflow. Oversight and scrutiny are no longer optional'",
            "indicators": ["验证信号", "测试", "代码审查"],
        },
        {
            "id": "first_pass",
            "name": "一次达成 (First-Pass)",
            "description": "避免返工，第一次就做对，体现清晰的任务理解",
            "source": "Agentic Engineering vs Vibe Coding: leverage without sacrificing software quality",
            "indicators": ["无返工信号", "一次完成", "明确验收标准"],
        },
        {
            "id": "parallel_agents",
            "name": "并行 Agent (Parallel)",
            "description": "同时运行多个 coding agent 处理不同任务，使用 git worktree",
            "source": "Karpathy workflow: parallel coding agents with git worktrees",
            "indicators": ["多项目切换", "并发会话", "工具多样性"],
        },
    ],
    "en": [
        {
            "id": "orchestration",
            "name": "Orchestration",
            "description": "Shift from 'writing code' to 'orchestrating AI agents', designing workflows and task decomposition",
            "source": "Karpathy: 'The future of engineering management: orchestrating AI agents, not writing code'",
            "indicators": ["planning signals", "task decomposition", "multi-step execution"],
        },
        {
            "id": "explore_before_code",
            "name": "Explore Before Code",
            "description": "Search and explore before coding, understand context and existing solutions",
            "source": "Karpathy workflow: prioritizes web search and exploration before coding",
            "indicators": ["search/research", "investigation", "solution comparison"],
        },
        {
            "id": "quality_oversight",
            "name": "Quality Oversight",
            "description": "'Oversight and scrutiny are no longer optional', establish verification mechanisms",
            "source": "Karpathy: 'Agents are now part of the default workflow. Oversight and scrutiny are no longer optional'",
            "indicators": ["verification signals", "testing", "code review"],
        },
        {
            "id": "first_pass",
            "name": "First-Pass Completion",
            "description": "Avoid rework, get it right the first time, demonstrate clear task understanding",
            "source": "Agentic Engineering vs Vibe Coding: leverage without sacrificing software quality",
            "indicators": ["no rework signals", "one-shot completion", "clear acceptance criteria"],
        },
        {
            "id": "parallel_agents",
            "name": "Parallel Agents",
            "description": "Run multiple coding agents simultaneously for different tasks using git worktrees",
            "source": "Karpathy workflow: parallel coding agents with git worktrees",
            "indicators": ["multi-project switching", "concurrent sessions", "tool diversity"],
        },
    ],
}

OUTCOME_LABELS = {
    "zh": {"fully_achieved": "完全达成", "mostly_achieved": "基本达成", "partially_achieved": "部分达成", "not_achieved": "未达成", "unclear": "不明确"},
    "en": {"fully_achieved": "Fully Achieved", "mostly_achieved": "Mostly Achieved", "partially_achieved": "Partially Achieved", "not_achieved": "Not Achieved", "unclear": "Unclear"},
}

DAYPART_LABELS = {
    "zh": {"morning": "早晨 (6-12)", "afternoon": "下午 (12-18)", "evening": "晚上 (18-24)", "night": "深夜 (0-6)"},
    "en": {"morning": "Morning (6-12)", "afternoon": "Afternoon (12-18)", "evening": "Evening (18-24)", "night": "Night (0-6)"},
}

I18N = {
    "zh": {
        "title": "跨客户端使用洞察报告",
        "subtitle": "覆盖 {start} 至 {end} · 数据源：{sources}",
        "report_time": "报告生成时间：{time}",
        "no_date": "无时间数据",
        "kpi_sessions": "会话数", "kpi_user_msgs": "用户消息", "kpi_active_days": "活跃天数", "kpi_lang": "主要语言",
        "dominant_lang_zh": "中文", "dominant_lang_en": "英文",
        "section_source": "数据源覆盖", "section_lang": "语言分布", "section_activity": "活跃时段",
        "section_intent": "主要需求类型", "section_tools": "高频工具 (Claude Code)",
        "section_outcome": "任务结果 (Claude Facets)", "section_friction": "主要摩擦点",
        "section_projects": "项目路径分布 (Claude Code)", "section_diagnostics": "深度诊断指标",
        "section_trend": "近 14 天趋势对比", "section_agentic": "Agentic 深度解读",
        "section_better_usage": "什么是更好的使用方式", "section_insights": "关键洞察",
        "section_score": "AI 使用姿势评分", "section_strengths": "你的优势",
        "section_weaknesses": "主要短板", "section_next_steps": "后续努力方向",
        "score_total": "综合得分", "score_grade": "评级",
        "score_basis": "评分维度（一次达成、返工控制、切换成本、验证覆盖、执行趋势；每项 20 分）",
        "grade_a": "A（高效策略型）", "grade_b": "B（稳健进步型）", "grade_c": "C（可优化提升型）", "grade_d": "D（需要重构使用方式）",
        "dim_completion": "一次达成率", "dim_rework": "返工控制", "dim_switch": "工具切换成本",
        "dim_verification": "验证覆盖率", "dim_consistency": "执行趋势",
        "metric_first_pass": "一次达成率", "metric_rework": "返工率", "metric_switch": "切换成本指数",
        "metric_verification": "验证覆盖率", "metric_planning": "规划覆盖率", "metric_long_session": "长会话占比",
        "diag_good": "健康", "diag_warn": "关注", "diag_risk": "风险",
        "trend_recent": "最近 14 天", "trend_previous": "前 14 天", "trend_no_data": "时间窗口数据不足，无法做趋势对比。",
        "agentic_summary": "以下结论基于证据数据生成，供 Agent 进一步分析解读。",
        "agentic_evidence_title": "证据锚点",
        "better_usage_intro": "更好的使用方式 = 一次达成更高、返工更低、验证更早、切换更少、趋势持续改善。",
        "missing": "暂无可展示数据",
        "source_claude": "Claude Code", "source_codex": "Codex CLI",
        "source_sessions": "会话", "source_messages": "消息", "source_tokens": "Token",
        "source_scope": "可分析维度",
        "scope_claude": "工具调用、结果分类、摩擦分析、项目路径",
        "scope_codex": "用户指令、会话节奏、语言与意图分布",
        "insight_default_1": "当前数据主要反映你的真实操作轨迹，而非仅统计消息量。",
        "insight_default_2": "建议定期复盘“高摩擦类型”，并将其固化到 SKILL 或 CLAUDE.md。",
        "insight_default_3": "如果你经常并行任务，可进一步引入子代理分工模板。",
        "lang_mix": "中文 {zh_pct}% · 英文 {en_pct}%",
        "agentic_placeholder": "Agentic 分析由执行 Agent 基于下方证据数据完成",
    },
    "en": {
        "title": "Cross-Client Usage Insights",
        "subtitle": "Coverage: {start} to {end} · Sources: {sources}",
        "report_time": "Generated at: {time}",
        "no_date": "No time range available",
        "kpi_sessions": "Sessions", "kpi_user_msgs": "User Messages", "kpi_active_days": "Active Days", "kpi_lang": "Dominant Language",
        "dominant_lang_zh": "Chinese", "dominant_lang_en": "English",
        "section_source": "Source Coverage", "section_lang": "Language Mix", "section_activity": "Active Time Bands",
        "section_intent": "Top Intent Types", "section_tools": "Top Tools (Claude Code)",
        "section_outcome": "Outcomes (Claude Facets)", "section_friction": "Primary Friction",
        "section_projects": "Project Path Distribution (Claude Code)", "section_diagnostics": "Deep Diagnostics",
        "section_trend": "Last 14-Day Trend Comparison", "section_agentic": "Agentic Deep Interpretation",
        "section_better_usage": "What Better Usage Looks Like", "section_insights": "Key Insights",
        "section_score": "AI Usage Posture Score", "section_strengths": "Strengths",
        "section_weaknesses": "Weaknesses", "section_next_steps": "Next Focus Areas",
        "score_total": "Total Score", "score_grade": "Grade",
        "score_basis": "Scoring dimensions (first-pass, rework control, switch cost, verification coverage, momentum; 20 points each)",
        "grade_a": "A (Strategic and Efficient)", "grade_b": "B (Stable and Improving)", "grade_c": "C (Needs Optimization)", "grade_d": "D (Workflow Needs Reset)",
        "dim_completion": "First-Pass Achievement", "dim_rework": "Rework Control", "dim_switch": "Tool Switch Cost",
        "dim_verification": "Verification Coverage", "dim_consistency": "Execution Momentum",
        "metric_first_pass": "First-Pass Rate", "metric_rework": "Rework Rate", "metric_switch": "Switch Cost Index",
        "metric_verification": "Verification Coverage", "metric_planning": "Planning Coverage", "metric_long_session": "Long Session Ratio",
        "diag_good": "Healthy", "diag_warn": "Watch", "diag_risk": "Risk",
        "trend_recent": "Last 14 days", "trend_previous": "Prior 14 days", "trend_no_data": "Not enough timeline data for trend comparison.",
        "agentic_summary": "Conclusions below are generated from evidence data for Agent analysis.",
        "agentic_evidence_title": "Evidence Anchors",
        "better_usage_intro": "Better usage means higher first-pass completion, lower rework, earlier verification, fewer switches, and improving trend momentum.",
        "missing": "No data available for this section",
        "source_claude": "Claude Code", "source_codex": "Codex CLI",
        "source_sessions": "sessions", "source_messages": "messages", "source_tokens": "tokens",
        "source_scope": "Available dimensions",
        "scope_claude": "tool calls, outcomes, friction analysis, project paths",
        "scope_codex": "user prompts, session rhythm, language and intent mix",
        "insight_default_1": "This report is behavior-first: it reflects workflow patterns, not just raw counts.",
        "insight_default_2": "Convert recurring friction into reusable rules in SKILL files or CLAUDE.md.",
        "insight_default_3": "If you often run parallel tasks, consider structured sub-agent orchestration.",
        "lang_mix": "Chinese {zh_pct}% · English {en_pct}%",
        "agentic_placeholder": "Agentic analysis performed by executing Agent based on evidence below",
    },
}


@dataclass
class SourceStats:
    name: str
    sessions: int = 0
    user_messages: int = 0
    assistant_messages: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    available: bool = False


@dataclass
class AggregatedData:
    sources: dict[str, SourceStats] = field(default_factory=dict)
    language_chars: Counter = field(default_factory=Counter)
    language_messages: Counter = field(default_factory=Counter)
    session_starts: list[datetime] = field(default_factory=list)
    user_timestamps: list[datetime] = field(default_factory=list)
    intent_counts: Counter = field(default_factory=Counter)
    tool_counts: Counter = field(default_factory=Counter)
    outcome_counts: Counter = field(default_factory=Counter)
    friction_counts: Counter = field(default_factory=Counter)
    project_counts: Counter = field(default_factory=Counter)
    session_message_counts: list[int] = field(default_factory=list)
    session_duration_minutes: list[float] = field(default_factory=list)
    session_tool_diversities: list[int] = field(default_factory=list)
    session_tool_calls: list[int] = field(default_factory=list)
    verification_signals: int = 0
    planning_signals: int = 0
    followup_signals: int = 0
    acceptance_signals: int = 0
    daily_sessions: Counter = field(default_factory=Counter)
    daily_user_messages: Counter = field(default_factory=Counter)
    daily_followups: Counter = field(default_factory=Counter)
    daily_verification: Counter = field(default_factory=Counter)

    @property
    def total_sessions(self) -> int:
        return sum(item.sessions for item in self.sources.values())

    @property
    def total_user_messages(self) -> int:
        return sum(item.user_messages for item in self.sources.values())

    @property
    def total_active_days(self) -> int:
        all_dates = {dt.date().isoformat() for dt in self.session_starts + self.user_timestamps}
        return len(all_dates)

    @property
    def total_span_days(self) -> int:
        timeline = sorted(self.session_starts + self.user_timestamps)
        if not timeline:
            return 0
        return max(1, (timeline[-1].date() - timeline[0].date()).days + 1)


@dataclass
class ScoreDimension:
    label: str
    score: int
    reason: str


@dataclass
class UsageAssessment:
    total_score: int
    grade: str
    dimensions: list[ScoreDimension]
    strengths: list[str]
    weaknesses: list[str]
    next_steps: list[str]
    diagnostics: list["DiagnosticMetric"]
    trend_lines: list[str]


@dataclass
class DiagnosticMetric:
    label: str
    value: str
    status: str
    detail: str
    tone: str


@dataclass
class EvidenceData:
    """结构化证据数据，供 Agent 分析使用"""
    metrics: dict[str, Any] = field(default_factory=dict)
    trends: dict[str, Any] = field(default_factory=dict)
    patterns: dict[str, Any] = field(default_factory=dict)
    insights: list[str] = field(default_factory=list)
    raw_counts: dict[str, Any] = field(default_factory=dict)
    session_samples: list[dict[str, Any]] = field(default_factory=list)
    karpathy_score: dict[str, Any] = field(default_factory=dict)  # Karpathy Agentic 评分


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).astimezone()
    except ValueError:
        return None


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    return 0


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def classify_codex_intent(text: str) -> str:
    for intent, patterns in CODEX_INTENT_PATTERNS:
        if any(pattern.search(text) for pattern in patterns):
            return intent
    return "other"


def update_language_counter(counter: Counter, text: str) -> None:
    if not text:
        return
    counter["zh"] += len(ZH_CHAR_RE.findall(text))
    counter["en"] += len(EN_CHAR_RE.findall(text))


def detect_text_language(text: str) -> str | None:
    if not text:
        return None
    zh_count = len(ZH_CHAR_RE.findall(text))
    en_count = len(EN_CHAR_RE.findall(text))
    if zh_count == 0 and en_count == 0:
        return None
    if zh_count >= 8 and zh_count >= int(en_count * 0.5):
        return "zh"
    if en_count >= 12 and en_count > zh_count * 1.2:
        return "en"
    return "zh" if zh_count >= en_count else "en"


def has_any_pattern(text: str, patterns: list[re.Pattern[str]]) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in patterns)


def signal_flags(text: str) -> tuple[bool, bool, bool, bool]:
    return (
        has_any_pattern(text, VERIFICATION_PATTERNS),
        has_any_pattern(text, PLANNING_PATTERNS),
        has_any_pattern(text, FOLLOWUP_PATTERNS),
        has_any_pattern(text, ACCEPTANCE_PATTERNS),
    )


def date_key(dt: datetime) -> str:
    return dt.date().isoformat()


def load_claude_data(claude_dir: Path) -> tuple[SourceStats, AggregatedData]:
    stats = SourceStats(name="claude")
    agg = AggregatedData()
    session_dir = claude_dir / "session-meta"
    facets_dir = claude_dir / "facets"

    if not session_dir.exists():
        return stats, agg

    stats.available = True
    session_files = sorted(session_dir.glob("*.json"))
    stats.sessions = len(session_files)

    for path in session_files:
        payload = load_json(path)
        if not payload:
            continue

        user_msg_count = safe_int(payload.get("user_message_count"))
        stats.user_messages += user_msg_count
        stats.assistant_messages += safe_int(payload.get("assistant_message_count"))
        stats.input_tokens += safe_int(payload.get("input_tokens"))
        stats.output_tokens += safe_int(payload.get("output_tokens"))
        agg.session_message_counts.append(max(1, user_msg_count))

        start_dt = parse_iso(payload.get("start_time"))
        if start_dt:
            agg.session_starts.append(start_dt)
            agg.daily_sessions[date_key(start_dt)] += 1

        first_prompt = str(payload.get("first_prompt") or "")
        update_language_counter(agg.language_chars, first_prompt)
        prompt_lang = detect_text_language(first_prompt)
        if prompt_lang:
            agg.language_messages[prompt_lang] += 1
        ver, plan, followup, acceptance = signal_flags(first_prompt)
        agg.verification_signals += int(ver)
        agg.planning_signals += int(plan)
        agg.followup_signals += int(followup)
        agg.acceptance_signals += int(acceptance)

        parsed_ts: list[datetime] = []
        for ts in payload.get("user_message_timestamps") or []:
            dt = parse_iso(str(ts))
            if dt:
                agg.user_timestamps.append(dt)
                parsed_ts.append(dt)
                day = date_key(dt)
                agg.daily_user_messages[day] += 1
                if followup:
                    agg.daily_followups[day] += 1
                if ver:
                    agg.daily_verification[day] += 1

        if not parsed_ts and start_dt:
            agg.daily_user_messages[date_key(start_dt)] += max(1, user_msg_count)

        if len(parsed_ts) >= 2:
            duration = (max(parsed_ts) - min(parsed_ts)).total_seconds() / 60.0
            agg.session_duration_minutes.append(max(0.0, duration))
        else:
            end_dt = parse_iso(payload.get("end_time"))
            if start_dt and end_dt:
                duration = (end_dt - start_dt).total_seconds() / 60.0
                agg.session_duration_minutes.append(max(0.0, duration))

        session_tool_diversity = 0
        session_tool_calls = 0
        for tool, count in (payload.get("tool_counts") or {}).items():
            count_int = safe_int(count)
            agg.tool_counts[str(tool)] += count_int
            session_tool_calls += count_int
            if count_int > 0:
                session_tool_diversity += 1
        agg.session_tool_diversities.append(session_tool_diversity)
        agg.session_tool_calls.append(session_tool_calls)

        project_path = str(payload.get("project_path") or "").strip()
        if project_path:
            agg.project_counts[project_path] += 1

    if facets_dir.exists():
        for path in sorted(facets_dir.glob("*.json")):
            payload = load_json(path)
            if not payload:
                continue
            outcome = str(payload.get("outcome") or "").strip()
            if outcome:
                agg.outcome_counts[outcome] += 1
            for goal, count in (payload.get("goal_categories") or {}).items():
                agg.intent_counts[str(goal)] += safe_int(count)
            for friction, count in (payload.get("friction_counts") or {}).items():
                agg.friction_counts[str(friction)] += safe_int(count)

    return stats, agg


def load_codex_data(codex_history: Path) -> tuple[SourceStats, AggregatedData]:
    stats = SourceStats(name="codex")
    agg = AggregatedData()
    if not codex_history.exists():
        return stats, agg

    stats.available = True
    session_ids: set[str] = set()
    session_starts: dict[str, datetime] = {}
    session_last_seen: dict[str, datetime] = {}
    session_msg_counts: Counter = Counter()

    with codex_history.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = str(payload.get("session_id") or "")
            text = str(payload.get("text") or "")
            ts = payload.get("ts")
            if not session_id:
                continue

            session_ids.add(session_id)
            stats.user_messages += 1
            session_msg_counts[session_id] += 1
            update_language_counter(agg.language_chars, text)
            text_lang = detect_text_language(text)
            if text_lang:
                agg.language_messages[text_lang] += 1
            agg.intent_counts[classify_codex_intent(text)] += 1
            ver, plan, followup, acceptance = signal_flags(text)
            agg.verification_signals += int(ver)
            agg.planning_signals += int(plan)
            agg.followup_signals += int(followup)
            agg.acceptance_signals += int(acceptance)

            if isinstance(ts, (int, float)):
                dt = datetime.fromtimestamp(float(ts)).astimezone()
                agg.user_timestamps.append(dt)
                day = date_key(dt)
                agg.daily_user_messages[day] += 1
                if ver:
                    agg.daily_verification[day] += 1
                if followup:
                    agg.daily_followups[day] += 1
                previous = session_starts.get(session_id)
                if previous is None or dt < previous:
                    session_starts[session_id] = dt
                last_seen = session_last_seen.get(session_id)
                if last_seen is None or dt > last_seen:
                    session_last_seen[session_id] = dt

    stats.sessions = len(session_ids)
    for session_id, start_dt in session_starts.items():
        agg.session_starts.append(start_dt)
        agg.daily_sessions[date_key(start_dt)] += 1
        agg.session_message_counts.append(max(1, session_msg_counts.get(session_id, 1)))
        end_dt = session_last_seen.get(session_id)
        if end_dt:
            duration = (end_dt - start_dt).total_seconds() / 60.0
            agg.session_duration_minutes.append(max(0.0, duration))

    sessions_without_ts = set(session_ids) - set(session_starts)
    for session_id in sessions_without_ts:
        agg.session_message_counts.append(max(1, session_msg_counts.get(session_id, 1)))

    return stats, agg


def merge_aggregates(chunks: list[AggregatedData]) -> AggregatedData:
    merged = AggregatedData()
    for chunk in chunks:
        merged.language_chars.update(chunk.language_chars)
        merged.language_messages.update(chunk.language_messages)
        merged.session_starts.extend(chunk.session_starts)
        merged.user_timestamps.extend(chunk.user_timestamps)
        merged.intent_counts.update(chunk.intent_counts)
        merged.tool_counts.update(chunk.tool_counts)
        merged.outcome_counts.update(chunk.outcome_counts)
        merged.friction_counts.update(chunk.friction_counts)
        merged.project_counts.update(chunk.project_counts)
        merged.session_message_counts.extend(chunk.session_message_counts)
        merged.session_duration_minutes.extend(chunk.session_duration_minutes)
        merged.session_tool_diversities.extend(chunk.session_tool_diversities)
        merged.session_tool_calls.extend(chunk.session_tool_calls)
        merged.verification_signals += chunk.verification_signals
        merged.planning_signals += chunk.planning_signals
        merged.followup_signals += chunk.followup_signals
        merged.acceptance_signals += chunk.acceptance_signals
        merged.daily_sessions.update(chunk.daily_sessions)
        merged.daily_user_messages.update(chunk.daily_user_messages)
        merged.daily_followups.update(chunk.daily_followups)
        merged.daily_verification.update(chunk.daily_verification)
    return merged


def pick_dominant_language(data: AggregatedData) -> str:
    zh_msg = data.language_messages.get("zh", 0)
    en_msg = data.language_messages.get("en", 0)
    if zh_msg or en_msg:
        return "zh" if zh_msg >= en_msg else "en"
    return pick_locale("auto", data.language_chars)


def language_mix_percent(data: AggregatedData) -> tuple[int, int]:
    zh_msg = data.language_messages.get("zh", 0)
    en_msg = data.language_messages.get("en", 0)
    if zh_msg or en_msg:
        total = max(zh_msg + en_msg, 1)
        zh_pct = round(zh_msg * 100 / total)
        return zh_pct, 100 - zh_pct
    zh = data.language_chars.get("zh", 0)
    en = data.language_chars.get("en", 0)
    total = max(zh + en, 1)
    zh_pct = round(zh * 100 / total)
    return zh_pct, 100 - zh_pct


def pick_locale(locale_option: str, language_chars: Counter, language_messages: Counter | None = None) -> str:
    if locale_option in {"zh", "en"}:
        return locale_option
    if language_messages:
        zh_msg = language_messages.get("zh", 0)
        en_msg = language_messages.get("en", 0)
        if zh_msg or en_msg:
            return "zh" if zh_msg >= en_msg else "en"
    zh = language_chars.get("zh", 0)
    en = language_chars.get("en", 0)
    if zh == 0 and en == 0:
        return "en"
    return "zh" if zh >= en else "en"


def fmt_num(value: int) -> str:
    return f"{value:,}"


def fmt_date(dt: datetime, locale: str) -> str:
    if locale == "zh":
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%b %d, %Y")


def fmt_datetime(dt: datetime, locale: str) -> str:
    if locale == "zh":
        return dt.strftime("%Y-%m-%d %H:%M")
    return dt.strftime("%b %d, %Y %H:%M")


def top_items(counter: Counter, limit: int) -> list[tuple[str, int]]:
    return [(key, value) for key, value in counter.most_common(limit) if value > 0]


def build_bar_rows(items: list[tuple[str, int]], color: str, empty_text: str) -> str:
    if not items:
        return f'<div class="empty">{html.escape(empty_text)}</div>'
    peak = max(value for _, value in items) or 1
    rows: list[str] = []
    for label, value in items:
        width = (value / peak) * 100
        rows.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{html.escape(label)}</div>
              <div class="bar-track"><div class="bar-fill" style="width:{width:.2f}%;background:{color}"></div></div>
              <div class="bar-value">{fmt_num(value)}</div>
            </div>
            """
        )
    return "".join(rows)


def daypart_counts(timestamps: list[datetime]) -> Counter:
    counts: Counter = Counter()
    for dt in timestamps:
        hour = dt.hour
        if 6 <= hour < 12:
            counts["morning"] += 1
        elif 12 <= hour < 18:
            counts["afternoon"] += 1
        elif 18 <= hour < 24:
            counts["evening"] += 1
        else:
            counts["night"] += 1
    return counts


def source_card(stats: SourceStats, locale: str) -> str:
    tr = I18N[locale]
    source_name = tr["source_claude"] if stats.name == "claude" else tr["source_codex"]
    scope = tr["scope_claude"] if stats.name == "claude" else tr["scope_codex"]
    total_tokens = stats.input_tokens + stats.output_tokens
    return f"""
      <div class="source-card">
        <div class="source-name">{html.escape(source_name)}</div>
        <div class="source-meta">{fmt_num(stats.sessions)} {tr["source_sessions"]} · {fmt_num(stats.user_messages + stats.assistant_messages)} {tr["source_messages"]}</div>
        <div class="source-meta">{fmt_num(total_tokens)} {tr["source_tokens"]}</div>
        <div class="source-scope"><strong>{tr["source_scope"]}:</strong> {html.escape(scope)}</div>
      </div>
    """


def localize_intents(intent_items: list[tuple[str, int]], locale: str) -> list[tuple[str, int]]:
    labels = INTENT_LABELS[locale]
    return [(labels.get(key, key.replace("_", " ").title()), value) for key, value in intent_items]


def localize_outcomes(outcome_items: list[tuple[str, int]], locale: str) -> list[tuple[str, int]]:
    labels = OUTCOME_LABELS[locale]
    return [(labels.get(key, key), value) for key, value in outcome_items]


def normalize_friction_key(key: str, locale: str) -> str:
    key_norm = key.strip().lower().replace("_", " ")
    if locale == "zh":
        mapping = {
            "misunderstood request": "误解需求", "buggy code": "代码缺陷", "wrong approach": "方案偏差",
            "minor edit requests": "细节返工", "wrong style": "风格不匹配", "tool limitation": "工具限制",
            "environment issue": "环境问题", "user rejected action": "用户拒绝操作",
        }
        return mapping.get(key_norm, key_norm.title())
    return key_norm.title()


def normalize_intent_counter(intent_counts: Counter) -> Counter:
    """标准化意图分类"""
    normalized: Counter = Counter()
    for key, value in intent_counts.items():
        canonical = str(key).strip().lower()
        if not canonical:
            continue
        mapping = {
            "content_creation": "content_creation",
            "content_refinement": "content_creation",
            "build_release": "release_build",
            "release_build": "release_build",
            "bug_fix": "debugging",
            "code_generation": "code_implementation",
            "implementation": "code_implementation",
            "git_operations": "tooling_config",
            "information_seeking": "quick_question",
            "research": "quick_question",
        }
        normalized[mapping.get(canonical, canonical)] += value
    return normalized


def build_insights(locale: str, data: AggregatedData, dominant_lang: str) -> list[str]:
    """构建关键洞察列表"""
    tr = I18N[locale]
    insights = []
    
    # 语言分布
    zh_pct, en_pct = language_mix_percent(data)
    if zh_pct + en_pct > 0:
        mix_line = tr["lang_mix"].format(zh_pct=zh_pct, en_pct=en_pct)
        if locale == "zh":
            insights.append(f"语言分布：{mix_line}，当前以{'中文' if dominant_lang == 'zh' else '英文'}为主。")
        else:
            insights.append(f"Language mix: {mix_line}. Dominant language is {'Chinese' if dominant_lang == 'zh' else 'English'}.")
    
    # 数据概览
    # 优先使用 source 汇总消息数；若 source 未注入，回退到日维度计数，避免分母退化为 1 导致畸高百分比
    total_msgs = data.total_user_messages or sum(data.daily_user_messages.values())
    total_msgs = max(1, total_msgs)
    verification_rate = safe_div(data.verification_signals, total_msgs)
    planning_rate = safe_div(data.planning_signals, total_msgs)
    followup_rate = safe_div(data.followup_signals, total_msgs)
    
    if locale == "zh":
        insights.append(f"验证覆盖 {pct(verification_rate)}，规划覆盖 {pct(planning_rate)}，返工信号率 {pct(followup_rate)}。")
        insights.append(f"共分析了 {data.total_sessions} 个会话，{data.total_active_days} 天活跃使用。")
    else:
        insights.append(f"Verification coverage {pct(verification_rate)}, planning coverage {pct(planning_rate)}, rework signal rate {pct(followup_rate)}.")
        insights.append(f"Analyzed {data.total_sessions} sessions across {data.total_active_days} active days.")
    
    # 摩擦分析
    if data.friction_counts:
        top_name, top_value = data.friction_counts.most_common(1)[0]
        label = normalize_friction_key(top_name, locale)
        if locale == "zh":
            insights.append(f"最高频摩擦：{label}（{fmt_num(top_value)} 次），建议关注并制定防错规则。")
        else:
            insights.append(f"Top friction: {label} ({fmt_num(top_value)} times). Consider adding guardrails.")
    
    return insights[:5]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def avg(values: list[int] | list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pct(value: float) -> str:
    """Format a ratio (0-1) as percentage string.

    Args:
        value: A ratio between 0 and 1 (e.g., 0.87 for 87%)

    Returns:
        Formatted percentage string (e.g., "87.0%")

    Note:
        If value > 1, assumes it's already a percentage and converts accordingly.
        For example, pct(87) returns "87.0%" instead of "8700.0%".
    """
    if value > 1:
        # Value is already a percentage (e.g., 87), not a ratio (e.g., 0.87)
        return f"{value:.1f}%"
    return f"{value * 100:.1f}%"


def status_by_ratio(locale: str, ratio: float, *, higher_better: bool, good_at: float, watch_at: float) -> tuple[str, str]:
    tr = I18N[locale]
    normalized = ratio if higher_better else (1 - ratio)
    if normalized >= good_at:
        return tr["diag_good"], "good"
    if normalized >= watch_at:
        return tr["diag_warn"], "warn"
    return tr["diag_risk"], "risk"


def collect_all_dates(data: AggregatedData) -> list[date]:
    dates: set[date] = {dt.date() for dt in data.session_starts + data.user_timestamps}
    for key in list(data.daily_sessions.keys()) + list(data.daily_user_messages.keys()):
        try:
            dates.add(datetime.fromisoformat(str(key)).date())
        except ValueError:
            continue
    return sorted(dates)


def sum_counter_window(counter: Counter, start: date, end: date) -> int:
    total = 0
    cursor = start
    while cursor <= end:
        total += safe_int(counter.get(cursor.isoformat(), 0))
        cursor += timedelta(days=1)
    return total


def build_trend_data(data: AggregatedData) -> tuple[list[str], dict[str, Any]]:
    """构建趋势数据，返回显示文本和结构化数据"""
    all_dates = collect_all_dates(data)
    if not all_dates:
        return ["时间窗口数据不足，无法做趋势对比。"], {}

    end_day = all_dates[-1]
    recent_start = end_day - timedelta(days=13)
    prev_end = recent_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=13)

    recent_sessions = sum_counter_window(data.daily_sessions, recent_start, end_day)
    prev_sessions = sum_counter_window(data.daily_sessions, prev_start, prev_end)
    recent_msgs = sum_counter_window(data.daily_user_messages, recent_start, end_day)
    prev_msgs = sum_counter_window(data.daily_user_messages, prev_start, prev_end)
    recent_followups = sum_counter_window(data.daily_followups, recent_start, end_day)
    prev_followups = sum_counter_window(data.daily_followups, prev_start, prev_end)
    recent_verification = sum_counter_window(data.daily_verification, recent_start, end_day)
    prev_verification = sum_counter_window(data.daily_verification, prev_start, prev_end)

    if recent_msgs + prev_msgs == 0:
        return ["时间窗口数据不足，无法做趋势对比。"], {}

    recent_rework = safe_div(recent_followups, recent_msgs)
    prev_rework = safe_div(prev_followups, prev_msgs)
    recent_verify = safe_div(recent_verification, recent_msgs)
    prev_verify = safe_div(prev_verification, prev_msgs)

    trend_data = {
        "recent_period": {"start": recent_start.isoformat(), "end": end_day.isoformat(),
                         "sessions": recent_sessions, "messages": recent_msgs,
                         "rework_rate": recent_rework, "verification_rate": recent_verify},
        "previous_period": {"start": prev_start.isoformat(), "end": prev_end.isoformat(),
                           "sessions": prev_sessions, "messages": prev_msgs,
                           "rework_rate": prev_rework, "verification_rate": prev_verify},
        "deltas": {"rework": recent_rework - prev_rework, "verification": recent_verify - prev_verify}
    }

    lines = [
        f"最近 14 天：会话 {recent_sessions}，消息 {recent_msgs}，返工率 {pct(recent_rework)}，验证覆盖 {pct(recent_verify)}。",
        f"前 14 天：会话 {prev_sessions}，消息 {prev_msgs}，返工率 {pct(prev_rework)}，验证覆盖 {pct(prev_verify)}。",
        f"趋势解读：返工率变化 {pct(recent_rework - prev_rework)}，验证覆盖变化 {pct(recent_verify - prev_verify)}。",
    ]

    momentum = clamp(0.55 + (prev_rework - recent_rework) * 1.45 + (recent_verify - prev_verify) * 1.05, 0.2, 0.95)
    trend_data["momentum"] = momentum

    return lines, trend_data


def calc_grade(total_score: int, locale: str) -> str:
    tr = I18N[locale]
    if total_score >= 85:
        return tr["grade_a"]
    if total_score >= 70:
        return tr["grade_b"]
    if total_score >= 55:
        return tr["grade_c"]
    return tr["grade_d"]


def analyze_session_for_examples(session_samples: list[dict], locale: str) -> dict[str, list[dict]]:
    """
    分析 session samples，提取每个维度的正反案例
    返回格式：{"orchestration": [{"session_id": ..., "date": ..., "prompt": ..., "type": "good|bad"}, ...], ...}
    """
    examples = {
        "orchestration": [],
        "explore_first": [],
        "oversight": [],
        "first_pass": [],
        "parallel": [],
    }

    for sample in session_samples:
        session_id = sample.get("session_id", "unknown")
        start_time = sample.get("start_time", "")
        first_prompt = sample.get("first_prompt", "")
        outcome = sample.get("outcome", "unknown")
        friction_types = sample.get("friction_types", [])
        tool_sequence = sample.get("tool_sequence", [])
        intent = sample.get("intent", "")

        # Parse date from start_time
        date_str = ""
        if start_time:
            try:
                dt = parse_iso(start_time) if isinstance(start_time, str) else None
                if dt:
                    date_str = dt.strftime("%Y-%m-%d")
            except:
                pass

        # Skip empty samples
        if not first_prompt:
            continue

        # --- Orchestration: 任务分解和规划 ---
        has_planning = has_any_pattern(first_prompt, PLANNING_PATTERNS)
        has_steps = any(kw in first_prompt.lower() for kw in ["步骤", "step", "分解", "拆分", "阶段", "phase", "里程碑", "milestone"])
        has_acceptance = has_any_pattern(first_prompt, ACCEPTANCE_PATTERNS)

        if has_planning or has_steps:
            examples["orchestration"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt,
                "type": "good",
                "reason": "明确的任务分解或规划信号" if locale == "zh" else "Clear task decomposition or planning",
            })
        elif len(first_prompt) > 100 and not has_acceptance and outcome in ["partially_achieved", "not_achieved"]:
            # 长提示但没有规划，且结果不好
            examples["orchestration"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt,
                "type": "bad",
                "reason": "长任务缺乏明确分解，结果未达成" if locale == "zh" else "Long task without clear decomposition, outcome not achieved",
            })

        # --- Explore First: 先探索后编码 ---
        has_research = any(kw in first_prompt.lower() for kw in ["搜索", "search", "调研", "research", "了解", "understand", "看看", "check", "怎么", "how to"])
        is_quick_impl = intent in ["code_implementation", "release_build"] and not has_research

        if intent in ["quick_question", "debugging"] or has_research:
            examples["explore_first"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt,
                "type": "good",
                "reason": "编码前进行探索或调研" if locale == "zh" else "Exploration before implementation",
            })
        elif is_quick_impl and len(first_prompt) < 80:
            # 直接要求实现，没有前期探索
            examples["explore_first"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt,
                "type": "bad",
                "reason": "直接要求实现，缺乏前期探索" if locale == "zh" else "Direct implementation request without exploration",
            })

        # --- Oversight: 质量监督 ---
        has_verification = has_any_pattern(first_prompt, VERIFICATION_PATTERNS)
        if has_verification:
            examples["oversight"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt,
                "type": "good",
                "reason": "主动要求验证或测试" if locale == "zh" else "Explicit verification request",
            })

        # --- First Pass: 一次达成 ---
        has_rework = sample.get("has_rework_signal", False) if sample.get("source") == "codex" else any(f in str(friction_types).lower() for f in ["rework", "edit", "修改", "返工"])

        if outcome == "fully_achieved" and not has_rework and not friction_types:
            examples["first_pass"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt,
                "type": "good",
                "reason": "一次达成，无返工信号" if locale == "zh" else "First-pass completion, no rework signals",
            })
        elif has_rework or outcome in ["not_achieved", "partially_achieved"]:
            friction_info = ", ".join(friction_types[:2]) if friction_types else "返工信号"
            examples["first_pass"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": first_prompt[:150] + "..." if len(first_prompt) > 150 else first_prompt,
                "type": "bad",
                "reason": f"返工或结果未达成: {friction_info}" if locale == "zh" else f"Rework or incomplete: {friction_info}",
            })

        # --- Parallel: 并行 Agent ---
        unique_tools = len(set(tool_sequence))
        if unique_tools >= 3:
            examples["parallel"].append({
                "session_id": session_id,
                "date": date_str,
                "prompt_snippet": f"工具序列: {', '.join(tool_sequence[:5])}",
                "type": "good",
                "reason": f"单会话使用 {unique_tools} 种工具，可能并行处理多个任务" if locale == "zh" else f"Used {unique_tools} tools in single session",
            })

    return examples


def calculate_karpathy_agentic_score(data: AggregatedData, session_samples: list, locale: str) -> dict[str, Any]:
    """
    生成 Karpathy Agentic Engineering 分析所需的数据
    基于真实 session samples 提供具体案例分析
    原文出处：Karpathy 关于 Agentic Coding 的推文和演讲
    """
    total_messages = max(1, data.total_user_messages)
    total_sessions = max(1, data.total_sessions)
    avg_tool_diversity = avg(data.session_tool_diversities)
    project_count = len(data.project_counts)

    # 计算基础统计
    planning_rate = safe_div(data.planning_signals, total_messages)
    verification_rate = safe_div(data.verification_signals, total_messages)
    followup_rate = safe_div(data.followup_signals, total_messages)

    # 从 session samples 中提取具体案例
    concrete_examples = analyze_session_for_examples(session_samples, locale)

    # 5 个维度的评估框架，包含具体案例
    criteria = KARPATHY_AGENTIC_CRITERIA[locale]

    # 计算 explore_ratio
    explore_intents = data.intent_counts.get("quick_question", 0) + data.intent_counts.get("debugging", 0)
    implementation_intents = data.intent_counts.get("code_implementation", 0) + data.intent_counts.get("release_build", 0)
    total_categorized = explore_intents + implementation_intents
    explore_ratio = safe_div(explore_intents, total_categorized) if total_categorized > 0 else 0

    # 为每个维度生成基于真实案例的评价
    def generate_dimension_evaluation(
        dim_id: str,
        metric_value: float,
        good_threshold: float,
        bad_threshold: float,
        good_examples: list,
        bad_examples: list,
    ) -> dict:
        """基于指标和真实案例生成维度评价"""
        examples_good = good_examples[:2]  # 最多2个正面案例
        examples_bad = bad_examples[:2]   # 最多2个负面案例

        # 生成评分
        if metric_value >= good_threshold:
            score = min(100, int(75 + (metric_value - good_threshold) / (1 - good_threshold) * 25))
            grade = "A"
        elif metric_value >= bad_threshold:
            score = int(50 + (metric_value - bad_threshold) / (good_threshold - bad_threshold) * 25)
            grade = "B" if metric_value > (good_threshold + bad_threshold) / 2 else "C"
        else:
            score = max(0, int(metric_value / bad_threshold * 50))
            grade = "D"

        # 生成评价文本
        if locale == "zh":
            if examples_good and examples_bad:
                evaluation = f"表现混合：有{len(examples_good)}个做得好的案例，也有{len(examples_bad)}个需要改进的案例。"
            elif examples_good:
                evaluation = f"表现较好：在{len(examples_good)}个案例中都展现了良好的实践。"
            elif examples_bad:
                evaluation = f"需要改进：在{len(examples_bad)}个案例中暴露出明显问题。"
            else:
                evaluation = "样本不足，无法给出基于具体案例的评价。"
        else:
            if examples_good and examples_bad:
                evaluation = f"Mixed performance: {len(examples_good)} good examples but {len(examples_bad)} areas needing improvement."
            elif examples_good:
                evaluation = f"Good performance: demonstrated best practices in {len(examples_good)} cases."
            elif examples_bad:
                evaluation = f"Needs improvement: issues identified in {len(examples_bad)} cases."
            else:
                evaluation = "Insufficient samples for case-based evaluation."

        return {
            "score": score,
            "grade": grade,
            "metric_value": round(metric_value, 3),
            "evaluation": evaluation,
            "examples_good": examples_good,
            "examples_bad": examples_bad,
        }

    # 为每个维度生成详细评估
    orchestration_eval = generate_dimension_evaluation(
        "orchestration", planning_rate, 0.25, 0.1,
        concrete_examples["orchestration"],
        [e for e in concrete_examples["orchestration"] if e["type"] == "bad"]
    )

    explore_eval = generate_dimension_evaluation(
        "explore_first", explore_ratio, 0.3, 0.15,
        concrete_examples["explore_first"],
        [e for e in concrete_examples["explore_first"] if e["type"] == "bad"]
    )

    oversight_eval = generate_dimension_evaluation(
        "oversight", verification_rate, 0.25, 0.1,
        concrete_examples["oversight"],
        []  # Oversight 只有正面案例（主动要求验证）
    )

    first_pass_eval = generate_dimension_evaluation(
        "first_pass", 1 - followup_rate, 0.75, 0.5,  # 返工率越低越好
        concrete_examples["first_pass"],
        [e for e in concrete_examples["first_pass"] if e["type"] == "bad"]
    )

    parallel_eval = generate_dimension_evaluation(
        "parallel", min(1.0, avg_tool_diversity / 5), 0.6, 0.3,
        concrete_examples["parallel"],
        []
    )

    analysis_framework = {
        "orchestration": {
            "id": "orchestration",
            "name": criteria[0]["name"],
            "description": criteria[0]["description"],
            "source": criteria[0]["source"],
            "indicators": criteria[0]["indicators"],
            "evaluation": orchestration_eval,
            "raw_data": {
                "planning_signals_count": data.planning_signals,
                "planning_rate": round(planning_rate, 3),
                "avg_messages_per_session": round(total_messages / total_sessions, 1),
            }
        },
        "explore_first": {
            "id": "explore_first",
            "name": criteria[1]["name"],
            "description": criteria[1]["description"],
            "source": criteria[1]["source"],
            "indicators": criteria[1]["indicators"],
            "evaluation": explore_eval,
            "raw_data": {
                "intent_distribution": dict(data.intent_counts.most_common(10)),
                "explore_ratio": round(explore_ratio, 3),
            }
        },
        "oversight": {
            "id": "oversight",
            "name": criteria[2]["name"],
            "description": criteria[2]["description"],
            "source": criteria[2]["source"],
            "indicators": criteria[2]["indicators"],
            "evaluation": oversight_eval,
            "raw_data": {
                "verification_signals_count": data.verification_signals,
                "verification_rate": round(verification_rate, 3),
                "tool_diversity_avg": round(avg_tool_diversity, 2),
            }
        },
        "first_pass": {
            "id": "first_pass",
            "name": criteria[3]["name"],
            "description": criteria[3]["description"],
            "source": criteria[3]["source"],
            "indicators": criteria[3]["indicators"],
            "evaluation": first_pass_eval,
            "raw_data": {
                "followup_signals_count": data.followup_signals,
                "followup_rate": round(followup_rate, 3),
                "outcome_distribution": dict(data.outcome_counts),
                "friction_types": dict(data.friction_counts.most_common(5)),
            }
        },
        "parallel": {
            "id": "parallel",
            "name": criteria[4]["name"],
            "description": criteria[4]["description"],
            "source": criteria[4]["source"],
            "indicators": criteria[4]["indicators"],
            "evaluation": parallel_eval,
            "raw_data": {
                "avg_tool_diversity_per_session": round(avg_tool_diversity, 2),
                "unique_projects": project_count,
                "project_paths": list(data.project_counts.keys())[:10],
            }
        }
    }

    # 计算总分
    total_score = sum([
        orchestration_eval["score"],
        explore_eval["score"],
        oversight_eval["score"],
        first_pass_eval["score"],
        parallel_eval["score"],
    ]) / 5

    # 生成总评等级
    if total_score >= 85:
        overall_grade = "A"
    elif total_score >= 70:
        overall_grade = "B"
    elif total_score >= 55:
        overall_grade = "C"
    else:
        overall_grade = "D"

    # 生成基于真实案例的具体建议
    concrete_recommendations = []
    if locale == "zh":
        # 基于负面案例生成具体建议
        for dim_id, dim_data in analysis_framework.items():
            bad_examples = dim_data["evaluation"].get("examples_bad", [])
            if bad_examples:
                for ex in bad_examples[:1]:  # 每个维度取一个案例
                    date_info = f"{ex['date']} / " if ex.get('date') else ""
                    rec = f"【{dim_data['name']}】{date_info}{ex['session_id'][:20]}...: {ex['reason']}。建议: "
                    if dim_id == "orchestration":
                        rec += "在任务开始时明确列出步骤和验收标准。"
                    elif dim_id == "explore_first":
                        rec += "复杂任务前先搜索调研，了解现有方案。"
                    elif dim_id == "oversight":
                        rec += "主动要求验证步骤，如测试或代码审查。"
                    elif dim_id == "first_pass":
                        rec += " upfront 明确需求，减少后期返工。"
                    elif dim_id == "parallel":
                        rec += "尝试用 git worktree 并行处理独立任务。"
                    concrete_recommendations.append(rec)
    else:
        for dim_id, dim_data in analysis_framework.items():
            bad_examples = dim_data["evaluation"].get("examples_bad", [])
            if bad_examples:
                for ex in bad_examples[:1]:
                    date_info = f"{ex['date']} / " if ex.get('date') else ""
                    rec = f"[{dim_data['name']}] {date_info}{ex['session_id'][:20]}...: {ex['reason']}. Suggestion: "
                    if dim_id == "orchestration":
                        rec += "List steps and acceptance criteria at the start."
                    elif dim_id == "explore_first":
                        rec += "Research existing solutions before implementing."
                    elif dim_id == "oversight":
                        rec += "Explicitly request verification steps."
                    elif dim_id == "first_pass":
                        rec += "Clarify requirements upfront to reduce rework."
                    elif dim_id == "parallel":
                        rec += "Use git worktrees for parallel tasks."
                    concrete_recommendations.append(rec)

    return {
        "analysis_mode": "evidence_based",  # 基于证据的分析模式
        "note": "基于真实 session samples 的 Agentic Engineering 评估",
        "total_score": round(total_score, 1),
        "overall_grade": overall_grade,
        "concrete_examples_summary": {
            "total_samples_analyzed": len(session_samples),
            "orchestration_examples": len(concrete_examples["orchestration"]),
            "explore_first_examples": len(concrete_examples["explore_first"]),
            "oversight_examples": len(concrete_examples["oversight"]),
            "first_pass_examples": len(concrete_examples["first_pass"]),
            "parallel_examples": len(concrete_examples["parallel"]),
        },
        "dimensions": analysis_framework,
        "concrete_recommendations": concrete_recommendations[:5],  # 最多5条具体建议
        "raw_metrics": {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "active_days": data.total_active_days,
            "planning_rate": planning_rate,
            "verification_rate": verification_rate,
            "followup_rate": followup_rate,
            "avg_tool_diversity": avg_tool_diversity,
            "project_count": project_count,
        },
    }


def build_assessment(locale: str, data: AggregatedData, session_samples: list = None) -> tuple[UsageAssessment, EvidenceData]:
    """构建评估和证据数据"""
    tr = I18N[locale]
    total_sessions = max(1, data.total_sessions)
    total_messages = max(1, data.total_user_messages)
    avg_tool_diversity = avg(data.session_tool_diversities)
    avg_tool_calls = avg(data.session_tool_calls)

    long_sessions = sum(1 for c in data.session_message_counts if c >= 12)
    long_sessions += sum(1 for d in data.session_duration_minutes if d >= 45)
    baseline_sessions = max(total_sessions, len(data.session_message_counts))
    long_session_ratio = clamp(safe_div(long_sessions, max(1, baseline_sessions * 2)), 0.0, 1.0)

    fully = data.outcome_counts.get("fully_achieved", 0)
    mostly = data.outcome_counts.get("mostly_achieved", 0)
    partial = data.outcome_counts.get("partially_achieved", 0)
    not_achieved = data.outcome_counts.get("not_achieved", 0)
    outcome_total = sum(data.outcome_counts.values())

    if outcome_total > 0:
        base_outcome_ratio = (fully * 1.0 + mostly * 0.62 + partial * 0.22) / outcome_total
    else:
        base_outcome_ratio = clamp(0.64 + safe_div(data.planning_signals, total_messages) * 0.22 - safe_div(data.followup_signals, total_messages) * 0.34, 0.25, 0.9)

    followup_rate = clamp(safe_div(data.followup_signals, total_messages), 0.0, 1.0)
    verification_rate = clamp(safe_div(data.verification_signals, total_messages), 0.0, 1.0)
    planning_rate = clamp(safe_div(data.planning_signals, total_messages), 0.0, 1.0)
    acceptance_rate = clamp(safe_div(data.acceptance_signals, total_messages), 0.0, 1.0)
    friction_total = sum(data.friction_counts.values())

    first_pass_rate = clamp(base_outcome_ratio * (1 - followup_rate * 0.36) * (1 - long_session_ratio * 0.2), 0.1, 0.98)
    rework_rate = clamp(followup_rate * 0.72 + long_session_ratio * 0.42 + (1 - first_pass_rate) * 0.33, 0.02, 0.95)
    switch_cost_index = clamp(max(0.0, avg_tool_diversity - 2.0) * 0.22 + max(0.0, avg_tool_calls - 5.0) * 0.05 + long_session_ratio * 0.28, 0.0, 1.0)
    verification_effective = clamp(verification_rate * 0.75 + planning_rate * 0.2 + acceptance_rate * 0.05, 0.0, 1.0)

    trend_lines, trend_data = build_trend_data(data)
    momentum_ratio = trend_data.get("momentum", 0.55)

    completion_score = round(clamp(first_pass_rate * 20, 4, 20))
    rework_score = round(clamp((1 - rework_rate) * 20, 4, 20))
    switch_score = round(clamp((1 - switch_cost_index) * 20, 4, 20))
    verification_score = round(clamp(verification_effective * 28, 4, 20))
    consistency_score = round(clamp(momentum_ratio * 20, 4, 20))

    if locale == "zh":
        completion_reason = f"结果分布 {fully}/{mostly}/{partial}/{not_achieved}，结合返工信号推算一次达成率 {pct(first_pass_rate)}。"
        rework_reason = f'返工率 {pct(rework_rate)}（随"仍然/再次"等返工表达、长会话占比变化）。'
        switch_reason = f"工具切换成本指数 {pct(switch_cost_index)}，会话平均工具种类 {avg_tool_diversity:.1f}。"
        verification_reason = f"验证覆盖 {pct(verification_rate)}、规划覆盖 {pct(planning_rate)}、验收覆盖 {pct(acceptance_rate)}。"
        consistency_reason = "基于最近 14 天 vs 前 14 天的返工与验证变化计算执行趋势。"
    else:
        completion_reason = f"Outcome mix {fully}/{mostly}/{partial}/{not_achieved}; first-pass estimate is {pct(first_pass_rate)} after rework adjustments."
        rework_reason = f"Rework rate {pct(rework_rate)} inferred from follow-up language and long-session pressure."
        switch_reason = f"Switch cost index {pct(switch_cost_index)} with avg tool diversity {avg_tool_diversity:.1f}."
        verification_reason = f"Verification {pct(verification_rate)}, planning {pct(planning_rate)}, acceptance {pct(acceptance_rate)}."
        consistency_reason = "Momentum compares the latest 14 days vs the prior 14 days on rework and verification."

    dimensions = [
        ScoreDimension(tr["dim_completion"], completion_score, completion_reason),
        ScoreDimension(tr["dim_rework"], rework_score, rework_reason),
        ScoreDimension(tr["dim_switch"], switch_score, switch_reason),
        ScoreDimension(tr["dim_verification"], verification_score, verification_reason),
        ScoreDimension(tr["dim_consistency"], consistency_score, consistency_reason),
    ]
    total_score = sum(item.score for item in dimensions)

    first_pass_status, _ = status_by_ratio(locale, first_pass_rate, higher_better=True, good_at=0.66, watch_at=0.48)
    rework_status, _ = status_by_ratio(locale, rework_rate, higher_better=False, good_at=0.72, watch_at=0.55)
    switch_status, _ = status_by_ratio(locale, switch_cost_index, higher_better=False, good_at=0.7, watch_at=0.52)
    verification_status, _ = status_by_ratio(locale, verification_rate, higher_better=True, good_at=0.2, watch_at=0.1)
    planning_status, _ = status_by_ratio(locale, planning_rate, higher_better=True, good_at=0.25, watch_at=0.12)
    long_status, _ = status_by_ratio(locale, long_session_ratio, higher_better=False, good_at=0.75, watch_at=0.58)

    diagnostics = [
        DiagnosticMetric(tr["metric_first_pass"], pct(first_pass_rate), first_pass_status,
                        "看一次对齐后直接完成的概率。" if locale == "zh" else "Proxy for one-shot completion after initial alignment.",
                        "good" if first_pass_rate > 0.66 else "warn" if first_pass_rate > 0.48 else "risk"),
        DiagnosticMetric(tr["metric_rework"], pct(rework_rate), rework_status,
                        "越低越好；高值通常代表需求重述或方案回滚频繁。" if locale == "zh" else "Lower is better; high values usually indicate repeated rewrites or rollbacks.",
                        "good" if rework_rate < 0.28 else "warn" if rework_rate < 0.45 else "risk"),
        DiagnosticMetric(tr["metric_switch"], pct(switch_cost_index), switch_status,
                        "越低越好；结合工具多样性与会话拉长程度。" if locale == "zh" else "Lower is better; combines tool diversity and session stretch.",
                        "good" if switch_cost_index < 0.3 else "warn" if switch_cost_index < 0.48 else "risk"),
        DiagnosticMetric(tr["metric_verification"], pct(verification_rate), verification_status,
                        "衡量你是否经常主动要求测试/验证。" if locale == "zh" else "How often you explicitly request tests/verification.",
                        "good" if verification_rate > 0.2 else "warn" if verification_rate > 0.1 else "risk"),
        DiagnosticMetric(tr["metric_planning"], pct(planning_rate), planning_status,
                        "衡量任务前置分解与验收定义是否充分。" if locale == "zh" else "Measures pre-execution planning and acceptance definition.",
                        "good" if planning_rate > 0.25 else "warn" if planning_rate > 0.12 else "risk"),
        DiagnosticMetric(tr["metric_long_session"], pct(long_session_ratio), long_status,
                        "越低越好；长会话偏多往往意味着对齐和闭环效率不足。" if locale == "zh" else "Lower is better; too many long sessions often indicate weak alignment and closure.",
                        "good" if long_session_ratio < 0.25 else "warn" if long_session_ratio < 0.42 else "risk"),
    ]

    # 构建 evidence 数据
    evidence = EvidenceData(
        metrics={
            "first_pass_rate": first_pass_rate, "rework_rate": rework_rate,
            "switch_cost_index": switch_cost_index, "verification_rate": verification_rate,
            "planning_rate": planning_rate, "long_session_ratio": long_session_ratio,
            "completion_score": completion_score, "rework_score": rework_score,
            "switch_score": switch_score, "verification_score": verification_score,
            "consistency_score": consistency_score, "total_score": total_score,
            "avg_tool_diversity": avg_tool_diversity,  # 添加工具多样性指标
        },
        trends=trend_data,
        patterns={
            "top_friction": data.friction_counts.most_common(3) if data.friction_counts else [],
            "top_intents": data.intent_counts.most_common(5) if data.intent_counts else [],
            "top_tools": data.tool_counts.most_common(5) if data.tool_counts else [],
            "language_mix": {"zh": data.language_messages.get("zh", 0), "en": data.language_messages.get("en", 0)},
        },
        raw_counts={
            "sessions": data.total_sessions, "user_messages": data.total_user_messages,
            "active_days": data.total_active_days, "verification_signals": data.verification_signals,
            "planning_signals": data.planning_signals, "followup_signals": data.followup_signals,
            "outcomes": dict(data.outcome_counts), "friction": dict(data.friction_counts),
        },
        karpathy_score=calculate_karpathy_agentic_score(data, session_samples or [], locale)
    )

    strengths, weaknesses, next_steps = [], [], []

    if completion_score >= 15:
        strengths.append("一次达成率较高，说明你在目标对齐上做得不错。" if locale == "zh" else "Your first-pass completion is strong, indicating solid alignment discipline.")
    if verification_score >= 14:
        strengths.append("你有较好的验证意识，能够主动推动结果可证伪。" if locale == "zh" else "You actively request verification, which keeps outcomes falsifiable.")
    if consistency_score >= 14:
        strengths.append("近 14 天执行趋势向上，说明你的方法在收敛。" if locale == "zh" else "Momentum is positive over the last 14 days, signaling convergence.")
    if rework_rate <= 0.25:
        strengths.append("返工率处于低位，说明过程控制有效。" if locale == "zh" else "Rework is under control, a sign of healthy execution.")

    if friction_total > 0:
        top_name, top_val = data.friction_counts.most_common(1)[0]
        label = normalize_friction_key(top_name, locale)
        weaknesses.append(f"最高频摩擦是「{label}」({top_val} 次)，这是当前效率损耗主因。" if locale == "zh" else f"Top friction is '{label}' ({top_val} times), likely the main efficiency drain.")
    if completion_score < 12:
        weaknesses.append("一次达成率偏低，任务常在中后段返工。" if locale == "zh" else "First-pass completion is low, with rework pushed into later stages.")
    if rework_score < 12:
        weaknesses.append('返工控制较弱，建议把"仍然/再次"类反馈前置为验收清单。' if locale == "zh" else "Rework control is weak; convert recurring follow-ups into upfront acceptance checks.")
    if switch_score < 12:
        weaknesses.append("工具切换成本偏高，单任务链路可能过于分散。" if locale == "zh" else "Switch cost is high, suggesting fragmented tool chains per task.")
    if verification_score < 12:
        weaknesses.append('验证覆盖偏低，缺少系统化"先验证再完成"的动作。' if locale == "zh" else "Verification coverage is low; add explicit validate-before-done steps.")

    if friction_total > 0:
        top_name, _ = data.friction_counts.most_common(1)[0]
        label = normalize_friction_key(top_name, locale)
        next_steps.append(f"先攻克头号摩擦「{label}」：整理 3 条防错规则写入 SKILL/系统提示词。" if locale == "zh" else f"Attack top friction '{label}' first: add 3 guardrail rules into your skill/system prompt.")
    if completion_score < 15:
        next_steps.append('把需求固定为"输入-约束-验收标准"三段模板，先做一次确认再执行。' if locale == "zh" else "Adopt a strict template: input, constraints, acceptance criteria.")
    if verification_score < 15:
        next_steps.append("给每类任务补 1 条默认验证动作（如 lint/test/回归），并写入技能脚本。" if locale == "zh" else "Attach one default verification step (lint/test/regression) to each task type.")
    if switch_score < 15:
        next_steps.append("把同类任务收敛到 1 条主链路（固定工具顺序），减少跨工具来回切换。" if locale == "zh" else "Converge each task type to one primary tool chain to reduce switching.")
    if consistency_score < 14:
        next_steps.append('固定每周复盘，跟踪"返工率、验证覆盖、长会话占比"三项是否持续改善。' if locale == "zh" else "Run a weekly review tracking rework, verification coverage, and long-session ratio.")

    if not strengths:
        strengths.append("已有可用的 AI 工作节奏，适合继续标准化与自动化。" if locale == "zh" else "You already have a workable AI routine to standardize further.")
    if not weaknesses:
        weaknesses.append("当前未出现明显短板，重点保持稳定并继续自动化。" if locale == "zh" else "No obvious bottleneck this cycle; focus on maintaining stability.")
    if not next_steps:
        next_steps.append("继续迭代现有流程，并沉淀可复用模板。" if locale == "zh" else "Keep iterating and codifying reusable templates.")

    assessment = UsageAssessment(
        total_score=total_score, grade=calc_grade(total_score, locale),
        dimensions=dimensions, strengths=strengths[:4], weaknesses=weaknesses[:4],
        next_steps=next_steps[:4], diagnostics=diagnostics, trend_lines=trend_lines,
    )

    return assessment, evidence


def build_plain_list(items: list[str], empty_text: str) -> str:
    if not items:
        return f'<div class="empty">{html.escape(empty_text)}</div>'
    return "<ul class=\"insight-list\">" + "".join(f"<li>{html.escape(item)}</li>" for item in items) + "</ul>"


def build_score_rows(dimensions: list[ScoreDimension]) -> str:
    rows: list[str] = []
    for item in dimensions:
        width = clamp(item.score / 20 * 100, 0, 100)
        rows.append(
            f"""
            <div class="score-row">
              <div class="score-head">
                <span>{html.escape(item.label)}</span>
                <span>{item.score}/20</span>
              </div>
              <div class="score-track"><div class="score-fill" style="width:{width:.2f}%"></div></div>
              <div class="score-reason">{html.escape(item.reason)}</div>
            </div>
            """
        )
    return "".join(rows)


def build_diagnostic_cards(metrics: list[DiagnosticMetric], empty_text: str) -> str:
    if not metrics:
        return f'<div class="empty">{html.escape(empty_text)}</div>'
    blocks: list[str] = []
    for metric in metrics:
        tone_class = f"tone-{metric.tone}"
        blocks.append(
            f"""
            <div class="diagnostic-card {tone_class}">
              <div class="diagnostic-header">
                <span class="diagnostic-label">{html.escape(metric.label)}</span>
                <span class="diagnostic-value">{html.escape(metric.value)}</span>
              </div>
              <div class="diagnostic-status">{html.escape(metric.status)}</div>
              <div class="diagnostic-detail">{html.escape(metric.detail)}</div>
            </div>
            """
        )
    return "".join(blocks)


def sample_recent_sessions(
    claude_dir: Path,
    codex_history: Path,
    limit: int = 20
) -> list[dict[str, Any]]:
    """抽样最近 N 个 session 的详细内容用于复盘分析"""
    samples: list[dict[str, Any]] = []

    # 从 Claude Code 收集 sessions
    session_dir = claude_dir / "session-meta"
    facets_dir = claude_dir / "facets"

    if session_dir.exists():
        session_files = sorted(session_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in session_files[:limit]:
            payload = load_json(path)
            if not payload:
                continue

            session_id = path.stem
            start_time = payload.get("start_time", "")
            first_prompt = str(payload.get("first_prompt", ""))[:200]  # 截断避免过长

            # 加载 facets 数据（如果有）
            facets_path = facets_dir / f"{session_id}.json"
            facets = load_json(facets_path) or {}

            # 提取 tool 使用序列
            tool_sequence = list(payload.get("tool_counts", {}).keys())

            samples.append({
                "source": "claude",
                "session_id": session_id,
                "start_time": start_time,
                "first_prompt": first_prompt,
                "user_message_count": payload.get("user_message_count", 0),
                "tool_count": len(tool_sequence),
                "tool_sequence": tool_sequence[:10],  # 前10个工具
                "outcome": facets.get("outcome", "unknown"),
                "friction_types": list(facets.get("friction_counts", {}).keys())[:3],
                "project_path": payload.get("project_path", ""),
            })

    # 从 Codex CLI 收集 sessions
    if codex_history.exists():
        # 先收集所有消息，按 session 分组
        session_msgs: dict[str, list[dict]] = {}
        with codex_history.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    sid = str(payload.get("session_id", ""))
                    if sid:
                        if sid not in session_msgs:
                            session_msgs[sid] = []
                        session_msgs[sid].append({
                            "text": str(payload.get("text", ""))[:150],
                            "ts": payload.get("ts", 0),
                        })
                except json.JSONDecodeError:
                    continue

        # 取最近的 session
        recent_sessions = sorted(
            session_msgs.items(),
            key=lambda x: max(m.get("ts", 0) for m in x[1]) if x[1] else 0,
            reverse=True
        )[:limit]

        for session_id, msgs in recent_sessions:
            if not msgs:
                continue
            # 按时间排序
            msgs_sorted = sorted(msgs, key=lambda m: m.get("ts", 0))
            first_msg = msgs_sorted[0]
            last_msg = msgs_sorted[-1]

            # 检测意图
            texts = [m["text"] for m in msgs_sorted[:5]]  # 前5条消息
            intent = classify_codex_intent(texts[0]) if texts else "other"

            # 检测是否有返工信号
            has_rework = any(has_any_pattern(t, FOLLOWUP_PATTERNS) for t in texts)
            has_verification = any(has_any_pattern(t, VERIFICATION_PATTERNS) for t in texts)

            samples.append({
                "source": "codex",
                "session_id": session_id,
                "message_count": len(msgs),
                "first_prompt": texts[0][:200] if texts else "",
                "intent": intent,
                "has_rework_signal": has_rework,
                "has_verification_signal": has_verification,
            })

    # 按时间排序，取最近的 N 个
    samples.sort(key=lambda x: x.get("start_time", ""), reverse=True)
    return samples[:limit]


def generate_evidence_json(evidence: EvidenceData, output_path: Path) -> None:
    """生成证据 JSON 文件，供 Agent 分析使用"""

    # 构建基于真实案例的分析摘要
    karpathy = evidence.karpathy_score
    case_summary = ""

    if karpathy and karpathy.get("dimensions"):
        case_summary = "\n\n## 基于真实案例的评估结果\n\n"
        for dim_id, dim_data in karpathy.get("dimensions", {}).items():
            eval_data = dim_data.get("evaluation", {})
            case_summary += f"\n### {dim_data.get('name', dim_id)} (评分: {eval_data.get('score', 0)}/100, 等级: {eval_data.get('grade', 'N/A')})\n"
            case_summary += f"评价: {eval_data.get('evaluation', '')}\n"

            good_examples = eval_data.get("examples_good", [])
            bad_examples = eval_data.get("examples_bad", [])

            if good_examples:
                case_summary += "\n做得好的案例:\n"
                for ex in good_examples[:2]:
                    date_info = f"{ex['date']} / " if ex.get('date') else ""
                    case_summary += f"- {date_info}{ex['session_id']}: {ex['reason']}\n"
                    case_summary += f"  内容片段: \"{ex['prompt_snippet'][:100]}...\"\n"

            if bad_examples:
                case_summary += "\n需要改进的案例:\n"
                for ex in bad_examples[:2]:
                    date_info = f"{date_info} / " if ex.get('date') else ""
                    case_summary += f"- {date_info}{ex['session_id']}: {ex['reason']}\n"
                    case_summary += f"  内容片段: \"{ex['prompt_snippet'][:100]}...\"\n"

        if karpathy.get("concrete_recommendations"):
            case_summary += "\n\n基于案例的具体建议:\n"
            for rec in karpathy["concrete_recommendations"]:
                case_summary += f"- {rec}\n"

    evidence_dict = {
        "metrics": evidence.metrics,
        "trends": evidence.trends,
        "patterns": {
            **evidence.patterns,
            "top_friction": evidence.patterns.get("top_friction", []),
            "top_intents": evidence.patterns.get("top_intents", []),
            "top_tools": evidence.patterns.get("top_tools", []),
        },
        "raw_counts": evidence.raw_counts,
        "session_samples": evidence.session_samples,
        "karpathy_agentic_score": evidence.karpathy_score,
        "analysis_summary": case_summary,
        "analysis_prompt": f"""
基于以上证据数据，请进行 Agentic 深度分析：

## 1. 基于真实案例的评估（已自动生成）
{case_summary}

## 2. 补充分析建议
请基于上述案例和数据，进一步分析：

- **模式识别**: 从案例中发现重复出现的行为模式
- **根本原因**: 负面案例背后的根本原因是什么
- **可操作建议**: 给出3-5条具体、可执行的下月改进计划

## 3. Karpathy 式总结
用 Andrej Karpathy 的口吻给出一段简洁有力的总结，风格要技术、直接、有洞察力。
"""
    }
    output_path.write_text(json.dumps(evidence_dict, ensure_ascii=False, indent=2), encoding="utf-8")


def build_html_report(
    locale: str,
    sources: dict[str, SourceStats],
    data: AggregatedData,
    assessment: UsageAssessment,
    evidence: EvidenceData,
    session_samples: list[dict[str, Any]],
) -> str:
    tr = I18N[locale]
    dominant_lang = pick_dominant_language(data)
    zh_pct, en_pct = language_mix_percent(data)

    timeline = sorted(data.session_starts + data.user_timestamps)
    if timeline:
        start_date = fmt_date(timeline[0], locale)
        end_date = fmt_date(timeline[-1], locale)
    else:
        start_date = end_date = tr["no_date"]

    source_names = [tr["source_claude"], tr["source_codex"]]
    available_sources = ", ".join(name for name, stats in zip(source_names, [sources.get("claude"), sources.get("codex")]) if stats and stats.available)

    insights = build_insights(locale, data, dominant_lang)
    dayparts = daypart_counts(data.user_timestamps or data.session_starts)

    intent_items = localize_intents(top_items(normalize_intent_counter(data.intent_counts), 6), locale)
    tool_items = top_items(data.tool_counts, 6)
    outcome_items = localize_outcomes(top_items(data.outcome_counts, 5), locale)
    friction_items = [(normalize_friction_key(k, locale), v) for k, v in top_items(data.friction_counts, 5)]
    project_items = top_items(data.project_counts, 6)

    # Calculate actual percentages for display
    total_msgs_for_pct = max(1, data.total_user_messages)
    verification_pct = safe_div(data.verification_signals, total_msgs_for_pct) * 100
    planning_pct = safe_div(data.planning_signals, total_msgs_for_pct) * 100
    followup_pct = safe_div(data.followup_signals, total_msgs_for_pct) * 100

    # Agentic 区块 - 显示 placeholder，实际分析由执行 agent 完成
    sample_summary = f"已抽取最近 {len(session_samples)} 个 session 样本进行复盘分析"
    agentic_section = f"""
    <section class="agentic">
      <h2>{tr["section_agentic"]}</h2>
      <div class="agentic-placeholder">
        <p><em>{tr["agentic_placeholder"]}</em></p>
        <p>{tr["agentic_summary"]}</p>
        <p class="sample-info"><strong>{sample_summary}</strong></p>
      </div>
      <h3>{tr["agentic_evidence_title"]}</h3>
      <div class="evidence-anchors">
        <ul>
          <li>综合得分: {assessment.total_score}/100 - {assessment.grade}</li>
          <li>一次达成率: {evidence.metrics.get("first_pass_rate", 0):.1%}</li>
          <li>返工率: {evidence.metrics.get("rework_rate", 0):.1%}</li>
          <li>验证覆盖率: {verification_pct:.1f}% ({data.verification_signals}/{total_msgs_for_pct})</li>
          <li>规划覆盖率: {planning_pct:.1f}% ({data.planning_signals}/{total_msgs_for_pct})</li>
          <li>高频摩擦: {", ".join([f"{k}({v})" for k, v in evidence.patterns.get("top_friction", [])[:3]]) or "无"}</li>
          <li>抽样样本数: {len(session_samples)} 个 session</li>
        </ul>
        <p class="evidence-file">详细证据数据已保存至: <code>*.evidence.json</code></p>
      </div>
    </section>
    """

    # Karpathy Agentic Score 区块 - 基于真实案例的展示
    karpathy = evidence.karpathy_score
    karpathy_dimensions_html = ""

    if karpathy and karpathy.get("dimensions"):
        dimensions_data = karpathy.get("dimensions", {})
        overall_grade = karpathy.get("overall_grade", "N/A")
        total_score = karpathy.get("total_score", 0)
        concrete_recommendations = karpathy.get("concrete_recommendations", [])

        # 生成每个维度的详细展示
        for dim_id, dim_data in dimensions_data.items():
            eval_data = dim_data.get("evaluation", {})
            grade = eval_data.get("grade", "N/A")
            score = eval_data.get("score", 0)
            evaluation_text = eval_data.get("evaluation", "")
            good_examples = eval_data.get("examples_good", [])
            bad_examples = eval_data.get("examples_bad", [])

            grade_color = {"A": "#22c55e", "B": "#06b6d4", "C": "#f59e0b", "D": "#ef4444"}.get(grade, "#888")

            # 构建案例展示HTML
            examples_html = ""
            if good_examples or bad_examples:
                examples_html += '<div style="margin-top: 0.75rem; padding: 0.75rem; background: var(--bg); border-radius: 6px; font-size: 0.8rem;">'

                # 正面案例
                if good_examples:
                    examples_html += '<div style="margin-bottom: 0.5rem;"><strong style="color: #22c55e;">✓ 做得好的案例:</strong></div>'
                    for ex in good_examples[:1]:  # 只显示一个案例避免过长
                        date_info = f"{ex['date']} / " if ex.get('date') else ""
                        examples_html += f'<div style="margin-left: 0.5rem; margin-bottom: 0.5rem; color: var(--text-secondary);">'
                        examples_html += f'<div style="font-size: 0.75rem; margin-bottom: 0.2rem;">{date_info}{ex["session_id"][:25]}...</div>'
                        examples_html += f'<div style="font-style: italic; color: var(--text);">"{html.escape(ex["prompt_snippet"][:80])}..."</div>'
                        examples_html += f'<div style="color: #22c55e; margin-top: 0.2rem;">{html.escape(ex["reason"])}</div>'
                        examples_html += '</div>'

                # 负面案例
                if bad_examples:
                    examples_html += '<div style="margin-top: 0.5rem;"><strong style="color: #ef4444;">✗ 需要改进的案例:</strong></div>'
                    for ex in bad_examples[:1]:  # 只显示一个案例避免过长
                        date_info = f"{ex['date']} / " if ex.get('date') else ""
                        examples_html += f'<div style="margin-left: 0.5rem; margin-bottom: 0.5rem; color: var(--text-secondary);">'
                        examples_html += f'<div style="font-size: 0.75rem; margin-bottom: 0.2rem;">{date_info}{ex["session_id"][:25]}...</div>'
                        examples_html += f'<div style="font-style: italic; color: var(--text);">"{html.escape(ex["prompt_snippet"][:80])}..."</div>'
                        examples_html += f'<div style="color: #ef4444; margin-top: 0.2rem;">{html.escape(ex["reason"])}</div>'
                        examples_html += '</div>'

                examples_html += '</div>'

            karpathy_dimensions_html += f"""
            <div class="karpathy-dim" style="margin-bottom: 1.25rem; padding: 1rem; background: var(--surface-2); border-radius: 8px; border-left: 4px solid {grade_color};">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span style="font-weight: 600; color: var(--text);">{html.escape(dim_data.get("name", dim_id))}</span>
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <span style="color: var(--text-secondary); font-size: 0.85rem;">{score}/100</span>
                  <span style="background: {grade_color}; color: white; padding: 0.2rem 0.6rem; border-radius: 4px; font-weight: bold; font-size: 0.9rem;">{grade}</span>
                </div>
              </div>
              <div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.4rem;">
                {html.escape(evaluation_text)}
              </div>
              {examples_html}
            </div>
            """

        # 生成具体建议HTML
        recommendations_html = ""
        if concrete_recommendations:
            recommendations_html = '<div style="margin-top: 1.5rem; padding: 1rem; background: var(--surface-2); border-radius: 8px;">'
            recommendations_html += f'<h4 style="margin: 0 0 0.75rem 0; color: var(--accent-2);">{"基于案例的具体建议" if locale == "zh" else "Case-Based Recommendations"}</h4>'
            recommendations_html += '<ul style="margin: 0; padding-left: 1.2rem; font-size: 0.85rem;">'
            for rec in concrete_recommendations[:3]:  # 最多显示3条建议
                recommendations_html += f'<li style="margin: 0.5rem 0;">{html.escape(rec)}</li>'
            recommendations_html += '</ul></div>'

        overall_color = {"A": "#22c55e", "B": "#06b6d4", "C": "#f59e0b", "D": "#ef4444"}.get(overall_grade, "#888")

        karpathy_section = f"""
        <section class="karpathy-score">
          <h2>🧠 AI 专家评估 (Karpathy 分析)</h2>
          <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; padding: 1rem; background: var(--surface-2); border-radius: 8px;">
            <span style="font-size: 1.1rem; color: var(--text-secondary);">综合评级</span>
            <span style="background: {overall_color}; color: white; padding: 0.4rem 1rem; border-radius: 6px; font-size: 1.5rem; font-weight: bold;">{overall_grade}</span>
            <span style="color: var(--text-secondary);">{total_score:.1f}/100</span>
          </div>
          {karpathy_dimensions_html}
          {recommendations_html}
        </section>
        """
    else:
        karpathy_section = ""

    html_template = f"""<!DOCTYPE html>
<html lang="{locale}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{tr["title"]}</title>
  <style>
    :root {{ --bg: #0f0f0f; --surface: #1a1a1a; --surface-2: #242424; --text: #e0e0e0; --text-secondary: #888; --accent: #4f46e5; --accent-2: #06b6d4; --good: #22c55e; --warn: #f59e0b; --risk: #ef4444; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--bg); color: var(--text); line-height: 1.6; margin: 0; padding: 2rem 1rem; }}
    .container {{ max-width: 960px; margin: 0 auto; }}
    header {{ text-align: center; margin-bottom: 2rem; padding-bottom: 1.5rem; border-bottom: 1px solid var(--surface-2); }}
    h1 {{ font-size: 1.75rem; margin: 0 0 0.5rem; background: linear-gradient(135deg, var(--accent), var(--accent-2)); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
    .subtitle {{ color: var(--text-secondary); font-size: 0.9rem; }}
    .report-time {{ color: var(--text-secondary); font-size: 0.8rem; margin-top: 0.5rem; }}
    section {{ background: var(--surface); border-radius: 12px; padding: 1.5rem; margin-bottom: 1.5rem; }}
    h2 {{ font-size: 1.1rem; margin: 0 0 1rem; color: var(--accent-2); }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 1rem; }}
    .kpi {{ background: var(--surface-2); padding: 1rem; border-radius: 8px; text-align: center; }}
    .kpi-value {{ font-size: 1.5rem; font-weight: bold; color: var(--accent); }}
    .kpi-label {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.25rem; }}
    .source-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }}
    .source-card {{ background: var(--surface-2); padding: 1rem; border-radius: 8px; }}
    .source-name {{ font-weight: bold; color: var(--accent); }}
    .source-meta {{ font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem; }}
    .source-scope {{ font-size: 0.8rem; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--surface); }}
    .bar-row {{ display: flex; align-items: center; gap: 0.75rem; margin: 0.5rem 0; }}
    .bar-label {{ width: 120px; font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .bar-track {{ flex: 1; height: 8px; background: var(--surface-2); border-radius: 4px; overflow: hidden; }}
    .bar-fill {{ height: 100%; border-radius: 4px; }}
    .bar-value {{ width: 50px; text-align: right; font-size: 0.85rem; color: var(--text-secondary); }}
    .score-row {{ margin: 1rem 0; }}
    .score-head {{ display: flex; justify-content: space-between; font-size: 0.9rem; margin-bottom: 0.25rem; }}
    .score-track {{ height: 6px; background: var(--surface-2); border-radius: 3px; overflow: hidden; }}
    .score-fill {{ height: 100%; background: linear-gradient(90deg, var(--accent), var(--accent-2)); border-radius: 3px; }}
    .score-reason {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.25rem; }}
    .diagnostic-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; }}
    .diagnostic-card {{ background: var(--surface-2); padding: 1rem; border-radius: 8px; border-left: 3px solid var(--text-secondary); }}
    .diagnostic-card.tone-good {{ border-left-color: var(--good); }}
    .diagnostic-card.tone-warn {{ border-left-color: var(--warn); }}
    .diagnostic-card.tone-risk {{ border-left-color: var(--risk); }}
    .diagnostic-header {{ display: flex; justify-content: space-between; align-items: center; }}
    .diagnostic-label {{ font-weight: 500; }}
    .diagnostic-value {{ font-weight: bold; color: var(--accent); }}
    .diagnostic-status {{ display: inline-block; font-size: 0.75rem; padding: 0.15rem 0.5rem; border-radius: 4px; background: var(--surface); margin-top: 0.5rem; }}
    .diagnostic-detail {{ font-size: 0.8rem; color: var(--text-secondary); margin-top: 0.5rem; }}
    .insight-list {{ margin: 0; padding-left: 1.2rem; }}
    .insight-list li {{ margin: 0.5rem 0; }}
    .trend-box {{ background: var(--surface-2); padding: 1rem; border-radius: 8px; }}
    .trend-line {{ padding: 0.5rem 0; border-bottom: 1px solid var(--surface); }}
    .trend-line:last-child {{ border-bottom: none; }}
    .agentic-placeholder {{ background: var(--surface-2); padding: 1rem; border-radius: 8px; border-left: 3px solid var(--accent); margin-bottom: 1rem; }}
    .evidence-anchors {{ background: var(--surface-2); padding: 1rem; border-radius: 8px; }}
    .evidence-anchors ul {{ margin: 0; padding-left: 1.2rem; }}
    .evidence-anchors li {{ margin: 0.3rem 0; font-family: monospace; font-size: 0.9rem; }}
    .evidence-file {{ margin-top: 1rem; font-size: 0.85rem; color: var(--text-secondary); }}
    .grade {{ display: inline-block; font-size: 1.25rem; font-weight: bold; color: var(--accent); margin-left: 0.5rem; }}
    .empty {{ color: var(--text-secondary); font-style: italic; padding: 1rem; text-align: center; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>{tr["title"]}</h1>
      <div class="subtitle">{tr["subtitle"].format(start=start_date, end=end_date, sources=available_sources)}</div>
      <div class="report-time">{tr["report_time"].format(time=fmt_datetime(datetime.now().astimezone(), locale))}</div>
    </header>

    <!-- 1. AI 专家评估（Karpathy 分析） -->
    {karpathy_section}

    <!-- 2. 优势 -->
    <section class="strengths">
      <h2>{tr["section_strengths"]}</h2>
      {build_plain_list(assessment.strengths, tr["missing"])}
    </section>

    <!-- 3. 劣势 -->
    <section class="weaknesses">
      <h2>{tr["section_weaknesses"]}</h2>
      {build_plain_list(assessment.weaknesses, tr["missing"])}
    </section>

    <!-- 4. 改进建议 -->
    <section class="next-steps">
      <h2>{tr["section_next_steps"]}</h2>
      {build_plain_list(assessment.next_steps, tr["missing"])}
    </section>

    <!-- 5. 关键洞察 -->
    <section class="insights">
      <h2>{tr["section_insights"]}</h2>
      {build_plain_list(insights, tr["missing"])}
    </section>

    <!-- 附加分析 -->
    {agentic_section}

    <section class="score">
      <h2>{tr["section_score"]} <span class="grade">{assessment.total_score} / {assessment.grade}</span></h2>
      <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 1rem;">{tr["score_basis"]}</p>
      {build_score_rows(assessment.dimensions)}
    </section>

    <section class="diagnostics">
      <h2>{tr["section_diagnostics"]}</h2>
      {build_diagnostic_cards(assessment.diagnostics, tr["missing"])}
    </section>

    <section class="trend">
      <h2>{tr["section_trend"]}</h2>
      <div class="trend-box">
        {''.join(f'<div class="trend-line">{html.escape(line)}</div>' for line in assessment.trend_lines)}
      </div>
    </section>

    <!-- 6. 统计指标（放最后） -->
    <section class="kpi">
      <h2>📊 {tr["kpi_sessions"]} · {tr["kpi_user_msgs"]} · {tr["kpi_active_days"]} · {tr["kpi_lang"]}</h2>
      <div class="kpi-grid">
        <div class="kpi">
          <div class="kpi-value">{fmt_num(data.total_sessions)}</div>
          <div class="kpi-label">{tr["kpi_sessions"]}</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">{fmt_num(data.total_user_messages)}</div>
          <div class="kpi-label">{tr["kpi_user_msgs"]}</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">{fmt_num(data.total_active_days)}</div>
          <div class="kpi-label">{tr["kpi_active_days"]}</div>
        </div>
        <div class="kpi">
          <div class="kpi-value">{tr["dominant_lang_zh"] if dominant_lang == "zh" else tr["dominant_lang_en"]}</div>
          <div class="kpi-label">{tr["lang_mix"].format(zh_pct=zh_pct, en_pct=en_pct)}</div>
        </div>
      </div>
    </section>

    <section class="sources">
      <h2>{tr["section_source"]}</h2>
      <div class="source-grid">
        {source_card(sources.get("claude", SourceStats("claude")), locale)}
        {source_card(sources.get("codex", SourceStats("codex")), locale)}
      </div>
    </section>

    <section class="language">
      <h2>{tr["section_lang"]}</h2>
      {build_bar_rows([(DAYPART_LABELS[locale][k], v) for k, v in dayparts.items()], "var(--accent-2)", tr["missing"])}
    </section>

    <section class="intent">
      <h2>{tr["section_intent"]}</h2>
      {build_bar_rows(intent_items, "var(--accent)", tr["missing"])}
    </section>

    <section class="tools">
      <h2>{tr["section_tools"]}</h2>
      {build_bar_rows(tool_items, "var(--accent-2)", tr["missing"])}
    </section>

    <section class="outcome">
      <h2>{tr["section_outcome"]}</h2>
      {build_bar_rows(outcome_items, "var(--good)", tr["missing"])}
    </section>

    <section class="friction">
      <h2>{tr["section_friction"]}</h2>
      {build_bar_rows(friction_items, "var(--risk)", tr["missing"])}
    </section>

    <section class="projects">
      <h2>{tr["section_projects"]}</h2>
      {build_bar_rows(project_items, "var(--accent)", tr["missing"])}
    </section>

    <section class="better-usage">
      <h2>{tr["section_better_usage"]}</h2>
      <p>{tr["better_usage_intro"]}</p>
    </section>
  </div>
</body>
</html>"""

    return html_template


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate cross-client usage insights report")
    parser.add_argument("--source", choices=["auto", "claude", "codex"], default="auto")
    parser.add_argument("--claude-dir", type=Path, default=Path.home() / ".claude" / "usage-data")
    parser.add_argument("--codex-history", type=Path, default=Path.home() / ".codex" / "history.jsonl")
    parser.add_argument("--output", type=Path, default=Path("usage-insights-report.html"))
    parser.add_argument("--locale", choices=["auto", "zh", "en"], default="auto")
    args = parser.parse_args()

    # 加载数据
    sources: dict[str, SourceStats] = {}
    aggregates: list[AggregatedData] = []

    if args.source in ("auto", "claude"):
        claude_stats, claude_agg = load_claude_data(args.claude_dir)
        if claude_stats.available:
            sources["claude"] = claude_stats
            aggregates.append(claude_agg)

    if args.source in ("auto", "codex"):
        codex_stats, codex_agg = load_codex_data(args.codex_history)
        if codex_stats.available:
            sources["codex"] = codex_stats
            aggregates.append(codex_agg)

    if not aggregates:
        print("No data sources found. Please check your Claude Code or Codex CLI data paths.")
        return

    data = merge_aggregates(aggregates)
    data.sources = sources
    locale = pick_locale(args.locale, data.language_chars, data.language_messages)
    
    # 抽样复盘：收集最近 20 个 session 的详细内容
    session_samples = sample_recent_sessions(args.claude_dir, args.codex_history, limit=20)
    
    assessment, evidence = build_assessment(locale, data, session_samples)
    evidence.session_samples = session_samples

    # 生成报告
    html_content = build_html_report(locale, sources, data, assessment, evidence, session_samples)
    args.output.write_text(html_content, encoding="utf-8")

    # 生成证据 JSON
    evidence_path = args.output.with_suffix(".evidence.json")
    generate_evidence_json(evidence, evidence_path)

    print(f"Report generated: {args.output}")
    print(f"Evidence data: {evidence_path}")
    print(f"Total score: {assessment.total_score}/100 ({assessment.grade})")


if __name__ == "__main__":
    main()
