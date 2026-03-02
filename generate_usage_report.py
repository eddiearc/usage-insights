#!/usr/bin/env python3
"""Generate a cross-client usage insights HTML report for Claude Code and Codex CLI."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib import error, request


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
    (
        "content_creation",
        [
            re.compile(r"小红书|文章|文案|标题|润色|改写"),
            re.compile(r"\bcontent\b|\bpost\b|\bcopy\b|\bheadline\b", re.I),
        ],
    ),
    (
        "release_build",
        [
            re.compile(r"发布|发版|构建|签名|公证|notar"),
            re.compile(r"\brelease\b|\bbuild\b|\bsign\b|\bdeploy\b", re.I),
        ],
    ),
    (
        "debugging",
        [
            re.compile(r"报错|修复|排查|无法|失败|bug"),
            re.compile(r"\bdebug\b|\bfix\b|\berror\b|\bfail", re.I),
        ],
    ),
    (
        "code_implementation",
        [
            re.compile(r"实现|开发|重构|改造|加功能|新增"),
            re.compile(r"\bimplement\b|\brefactor\b|\bfeature\b|\bcoding\b", re.I),
        ],
    ),
    (
        "tooling_config",
        [
            re.compile(r"安装|配置|技能|skill|mcp|tmux"),
            re.compile(r"\binstall\b|\bconfig\b|\bsetup\b", re.I),
        ],
    ),
    (
        "quick_question",
        [
            re.compile(r"为什么|怎么|是什么|能否"),
            re.compile(r"^\s*how\b|^\s*why\b|^\s*what\b|\?", re.I),
        ],
    ),
]

INTENT_LABELS = {
    "zh": {
        "content_creation": "内容创作",
        "release_build": "构建发布",
        "debugging": "调试修复",
        "code_implementation": "代码实现",
        "tooling_config": "工具配置",
        "quick_question": "快速问答",
        "other": "其他",
    },
    "en": {
        "content_creation": "Content Creation",
        "release_build": "Build & Release",
        "debugging": "Debugging",
        "code_implementation": "Implementation",
        "tooling_config": "Tooling Config",
        "quick_question": "Quick Questions",
        "other": "Other",
    },
}

OUTCOME_LABELS = {
    "zh": {
        "fully_achieved": "完全达成",
        "mostly_achieved": "基本达成",
        "partially_achieved": "部分达成",
        "not_achieved": "未达成",
        "unclear": "不明确",
    },
    "en": {
        "fully_achieved": "Fully Achieved",
        "mostly_achieved": "Mostly Achieved",
        "partially_achieved": "Partially Achieved",
        "not_achieved": "Not Achieved",
        "unclear": "Unclear",
    },
}

DAYPART_LABELS = {
    "zh": {
        "morning": "早晨 (6-12)",
        "afternoon": "下午 (12-18)",
        "evening": "晚上 (18-24)",
        "night": "深夜 (0-6)",
    },
    "en": {
        "morning": "Morning (6-12)",
        "afternoon": "Afternoon (12-18)",
        "evening": "Evening (18-24)",
        "night": "Night (0-6)",
    },
}

I18N = {
    "zh": {
        "title": "跨客户端使用洞察报告",
        "subtitle": "覆盖 {start} 至 {end} · 数据源：{sources}",
        "report_time": "报告生成时间：{time}",
        "no_date": "无时间数据",
        "kpi_sessions": "会话数",
        "kpi_user_msgs": "用户消息",
        "kpi_active_days": "活跃天数",
        "kpi_lang": "主要语言",
        "dominant_lang_zh": "中文",
        "dominant_lang_en": "英文",
        "section_source": "数据源覆盖",
        "section_lang": "语言分布",
        "section_activity": "活跃时段",
        "section_intent": "主要需求类型",
        "section_tools": "高频工具 (Claude Code)",
        "section_outcome": "任务结果 (Claude Facets)",
        "section_friction": "主要摩擦点",
        "section_projects": "项目路径分布 (Claude Code)",
        "section_diagnostics": "深度诊断指标",
        "section_trend": "近 14 天趋势对比",
        "section_agentic": "Agentic 深度解读",
        "section_better_usage": "什么是更好的使用方式",
        "section_insights": "关键洞察",
        "section_score": "AI 使用姿势评分",
        "section_strengths": "你的优势",
        "section_weaknesses": "主要短板",
        "section_next_steps": "后续努力方向",
        "score_total": "综合得分",
        "score_grade": "评级",
        "score_basis": "评分维度（一次达成、返工控制、切换成本、验证覆盖、执行趋势；每项 20 分）",
        "grade_a": "A（高效策略型）",
        "grade_b": "B（稳健进步型）",
        "grade_c": "C（可优化提升型）",
        "grade_d": "D（需要重构使用方式）",
        "dim_completion": "一次达成率",
        "dim_rework": "返工控制",
        "dim_switch": "工具切换成本",
        "dim_verification": "验证覆盖率",
        "dim_consistency": "执行趋势",
        "metric_first_pass": "一次达成率",
        "metric_rework": "返工率",
        "metric_switch": "切换成本指数",
        "metric_verification": "验证覆盖率",
        "metric_planning": "规划覆盖率",
        "metric_long_session": "长会话占比",
        "diag_good": "健康",
        "diag_warn": "关注",
        "diag_risk": "风险",
        "trend_recent": "最近 14 天",
        "trend_previous": "前 14 天",
        "trend_no_data": "时间窗口数据不足，无法做趋势对比。",
        "agentic_summary_fallback": "当前未启用外部推理模型，以下结论基于规则引擎与证据聚合生成。",
        "agentic_summary_hybrid": "以下结论由“证据底座 + Agent 推理”联合生成，每条建议都应能回溯到证据。",
        "agentic_evidence_title": "证据锚点",
        "better_usage_intro": "更好的使用方式 = 一次达成更高、返工更低、验证更早、切换更少、趋势持续改善。",
        "missing": "暂无可展示数据",
        "source_claude": "Claude Code",
        "source_codex": "Codex CLI",
        "source_sessions": "会话",
        "source_messages": "消息",
        "source_tokens": "Token",
        "source_scope": "可分析维度",
        "scope_claude": "工具调用、结果分类、摩擦分析、项目路径",
        "scope_codex": "用户指令、会话节奏、语言与意图分布",
        "insight_default_1": "当前数据主要反映你的真实操作轨迹，而非仅统计消息量。",
        "insight_default_2": "建议定期复盘“高摩擦类型”，并将其固化到 SKILL 或 CLAUDE.md。",
        "insight_default_3": "如果你经常并行任务，可进一步引入子代理分工模板。",
        "lang_mix": "中文 {zh_pct}% · 英文 {en_pct}%",
    },
    "en": {
        "title": "Cross-Client Usage Insights",
        "subtitle": "Coverage: {start} to {end} · Sources: {sources}",
        "report_time": "Generated at: {time}",
        "no_date": "No time range available",
        "kpi_sessions": "Sessions",
        "kpi_user_msgs": "User Messages",
        "kpi_active_days": "Active Days",
        "kpi_lang": "Dominant Language",
        "dominant_lang_zh": "Chinese",
        "dominant_lang_en": "English",
        "section_source": "Source Coverage",
        "section_lang": "Language Mix",
        "section_activity": "Active Time Bands",
        "section_intent": "Top Intent Types",
        "section_tools": "Top Tools (Claude Code)",
        "section_outcome": "Outcomes (Claude Facets)",
        "section_friction": "Primary Friction",
        "section_projects": "Project Path Distribution (Claude Code)",
        "section_diagnostics": "Deep Diagnostics",
        "section_trend": "Last 14-Day Trend Comparison",
        "section_agentic": "Agentic Deep Interpretation",
        "section_better_usage": "What Better Usage Looks Like",
        "section_insights": "Key Insights",
        "section_score": "AI Usage Posture Score",
        "section_strengths": "Strengths",
        "section_weaknesses": "Weaknesses",
        "section_next_steps": "Next Focus Areas",
        "score_total": "Total Score",
        "score_grade": "Grade",
        "score_basis": "Scoring dimensions (first-pass, rework control, switch cost, verification coverage, momentum; 20 points each)",
        "grade_a": "A (Strategic and Efficient)",
        "grade_b": "B (Stable and Improving)",
        "grade_c": "C (Needs Optimization)",
        "grade_d": "D (Workflow Needs Reset)",
        "dim_completion": "First-Pass Achievement",
        "dim_rework": "Rework Control",
        "dim_switch": "Tool Switch Cost",
        "dim_verification": "Verification Coverage",
        "dim_consistency": "Execution Momentum",
        "metric_first_pass": "First-Pass Rate",
        "metric_rework": "Rework Rate",
        "metric_switch": "Switch Cost Index",
        "metric_verification": "Verification Coverage",
        "metric_planning": "Planning Coverage",
        "metric_long_session": "Long Session Ratio",
        "diag_good": "Healthy",
        "diag_warn": "Watch",
        "diag_risk": "Risk",
        "trend_recent": "Last 14 days",
        "trend_previous": "Prior 14 days",
        "trend_no_data": "Not enough timeline data for trend comparison.",
        "agentic_summary_fallback": "External reasoning model is not enabled; insights below are generated from deterministic evidence rules.",
        "agentic_summary_hybrid": "Insights below come from evidence grounding plus agentic reasoning, with traceable evidence anchors.",
        "agentic_evidence_title": "Evidence Anchors",
        "better_usage_intro": "Better usage means higher first-pass completion, lower rework, earlier verification, fewer switches, and improving trend momentum.",
        "missing": "No data available for this section",
        "source_claude": "Claude Code",
        "source_codex": "Codex CLI",
        "source_sessions": "sessions",
        "source_messages": "messages",
        "source_tokens": "tokens",
        "source_scope": "Available dimensions",
        "scope_claude": "tool calls, outcomes, friction analysis, project paths",
        "scope_codex": "user prompts, session rhythm, language and intent mix",
        "insight_default_1": "This report is behavior-first: it reflects workflow patterns, not just raw counts.",
        "insight_default_2": "Convert recurring friction into reusable rules in SKILL files or CLAUDE.md.",
        "insight_default_3": "If you often run parallel tasks, consider structured sub-agent orchestration.",
        "lang_mix": "Chinese {zh_pct}% · English {en_pct}%",
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
class AgenticReport:
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    next_steps: list[str]
    better_usage_patterns: list[str]
    evidence_anchors: list[str]
    confidence: float
    mode: str


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
    if zh_count >= en_count:
        return "zh"
    return "en"


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
    localized: list[tuple[str, int]] = []
    for key, value in intent_items:
        label = labels.get(key, key.replace("_", " ").title())
        localized.append((label, value))
    return localized


def localize_outcomes(outcome_items: list[tuple[str, int]], locale: str) -> list[tuple[str, int]]:
    labels = OUTCOME_LABELS[locale]
    localized: list[tuple[str, int]] = []
    for key, value in outcome_items:
        localized.append((labels.get(key, key), value))
    return localized


def normalize_intent_counter(intent_counts: Counter) -> Counter:
    normalized: Counter = Counter()
    for key, value in intent_counts.items():
        canonical = str(key).strip().lower()
        if not canonical:
            continue
        mapping = {
            "content_creation": "content_creation",
            "content_refinement": "content_creation",
            "content_editing": "content_creation",
            "build_release": "release_build",
            "release_build": "release_build",
            "debugging": "debugging",
            "bug_fix": "debugging",
            "code_generation": "code_implementation",
            "implementation": "code_implementation",
            "git_operations": "tooling_config",
            "tooling_config": "tooling_config",
            "information_seeking": "quick_question",
            "quick_question": "quick_question",
            "research": "quick_question",
            "content_strategy": "content_creation",
        }
        normalized[mapping.get(canonical, canonical)] += value
    return normalized


def normalize_friction_key(key: str, locale: str) -> str:
    key_norm = key.strip().lower().replace("_", " ")
    if locale == "zh":
        mapping = {
            "misunderstood request": "误解需求",
            "buggy code": "代码缺陷",
            "wrong approach": "方案偏差",
            "minor edit requests": "细节返工",
            "wrong style": "风格不匹配",
            "tool limitation": "工具限制",
            "environment issue": "环境问题",
            "user rejected action": "用户拒绝操作",
        }
    else:
        mapping = {}
    return mapping.get(key_norm, key_norm.title())


def build_insights(locale: str, data: AggregatedData, dominant_lang: str) -> list[str]:
    tr = I18N[locale]
    insights = [tr["insight_default_1"], tr["insight_default_2"], tr["insight_default_3"]]
    total_msgs = max(1, data.total_user_messages)
    verification_rate = safe_div(data.verification_signals, total_msgs)
    planning_rate = safe_div(data.planning_signals, total_msgs)
    followup_rate = safe_div(data.followup_signals, total_msgs)
    fully = data.outcome_counts.get("fully_achieved", 0)
    mostly = data.outcome_counts.get("mostly_achieved", 0)
    partial = data.outcome_counts.get("partially_achieved", 0)
    not_achieved = data.outcome_counts.get("not_achieved", 0)
    outcome_total = sum(data.outcome_counts.values())
    if outcome_total > 0:
        first_pass = (fully + mostly * 0.62 + partial * 0.22) / outcome_total
    else:
        first_pass = clamp(0.62 + planning_rate * 0.2 - followup_rate * 0.3, 0.25, 0.9)

    zh_pct, en_pct = language_mix_percent(data)
    if zh_pct + en_pct > 0:
        mix_line = tr["lang_mix"].format(zh_pct=zh_pct, en_pct=en_pct)
        if locale == "zh":
            insights.insert(0, f"语言分布：{mix_line}，当前以{tr['dominant_lang_zh'] if dominant_lang == 'zh' else tr['dominant_lang_en']}为主。")
        else:
            insights.insert(0, f"Language mix: {mix_line}. Dominant language is {tr['dominant_lang_zh'] if dominant_lang == 'zh' else tr['dominant_lang_en']}.")

    if data.friction_counts:
        top_name, top_value = data.friction_counts.most_common(1)[0]
        if locale == "zh":
            insights.append(f"最高频摩擦：{normalize_friction_key(top_name, 'zh')}（{fmt_num(top_value)} 次）。")
        else:
            insights.append(f"Top friction type: {normalize_friction_key(top_name, 'en')} ({fmt_num(top_value)} events).")

    if locale == "zh":
        insights.append(f"一次达成率估计 {pct(first_pass)}，返工信号率 {pct(followup_rate)}。")
        insights.append(f"验证覆盖 {pct(verification_rate)}，规划覆盖 {pct(planning_rate)}。")
    else:
        insights.append(f"Estimated first-pass rate {pct(first_pass)}, follow-up signal rate {pct(followup_rate)}.")
        insights.append(f"Verification coverage {pct(verification_rate)}, planning coverage {pct(planning_rate)}.")

    return insights[:5]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def avg(values: list[int] | list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def status_by_ratio(
    locale: str,
    ratio: float,
    *,
    higher_better: bool,
    good_at: float,
    watch_at: float,
) -> tuple[str, str]:
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


def build_trend_lines(locale: str, data: AggregatedData) -> tuple[list[str], float]:
    tr = I18N[locale]
    all_dates = collect_all_dates(data)
    if not all_dates:
        return [tr["trend_no_data"]], 0.55

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
        return [tr["trend_no_data"]], 0.55

    recent_rework = safe_div(recent_followups, recent_msgs)
    prev_rework = safe_div(prev_followups, prev_msgs)
    recent_verify = safe_div(recent_verification, recent_msgs)
    prev_verify = safe_div(prev_verification, prev_msgs)
    recent_density = safe_div(recent_sessions, 14)
    prev_density = safe_div(prev_sessions, 14)

    momentum = clamp(
        0.55
        + (prev_rework - recent_rework) * 1.45
        + (recent_verify - prev_verify) * 1.05
        + (recent_density - prev_density) * 0.16,
        0.2,
        0.95,
    )

    if locale == "zh":
        lines = [
            f"{tr['trend_recent']}：会话 {recent_sessions}，消息 {recent_msgs}，返工率 {pct(recent_rework)}，验证覆盖 {pct(recent_verify)}。",
            f"{tr['trend_previous']}：会话 {prev_sessions}，消息 {prev_msgs}，返工率 {pct(prev_rework)}，验证覆盖 {pct(prev_verify)}。",
            f"趋势解读：返工率变化 {pct(recent_rework - prev_rework)}，验证覆盖变化 {pct(recent_verify - prev_verify)}。",
        ]
    else:
        lines = [
            f"{tr['trend_recent']}: sessions {recent_sessions}, messages {recent_msgs}, rework {pct(recent_rework)}, verification {pct(recent_verify)}.",
            f"{tr['trend_previous']}: sessions {prev_sessions}, messages {prev_msgs}, rework {pct(prev_rework)}, verification {pct(prev_verify)}.",
            f"Trend readout: rework delta {pct(recent_rework - prev_rework)}, verification delta {pct(recent_verify - prev_verify)}.",
        ]
    return lines, momentum


def calc_grade(total_score: int, locale: str) -> str:
    tr = I18N[locale]
    if total_score >= 85:
        return tr["grade_a"]
    if total_score >= 70:
        return tr["grade_b"]
    if total_score >= 55:
        return tr["grade_c"]
    return tr["grade_d"]


def build_assessment(locale: str, data: AggregatedData) -> UsageAssessment:
    tr = I18N[locale]
    total_sessions = max(1, data.total_sessions)
    total_messages = max(1, data.total_user_messages)
    avg_msgs_per_session = safe_div(sum(data.session_message_counts), max(1, len(data.session_message_counts)))
    avg_tool_diversity = avg(data.session_tool_diversities)
    avg_tool_calls = avg(data.session_tool_calls)
    long_sessions = 0
    baseline_sessions = max(total_sessions, len(data.session_message_counts), len(data.session_duration_minutes))
    for count in data.session_message_counts:
        if count >= 12:
            long_sessions += 1
    for duration in data.session_duration_minutes:
        if duration >= 45:
            long_sessions += 1
    long_session_ratio = clamp(safe_div(long_sessions, max(1, baseline_sessions * 2)), 0.0, 1.0)

    fully = data.outcome_counts.get("fully_achieved", 0)
    mostly = data.outcome_counts.get("mostly_achieved", 0)
    partial = data.outcome_counts.get("partially_achieved", 0)
    not_achieved = data.outcome_counts.get("not_achieved", 0)
    outcome_total = sum(data.outcome_counts.values())

    if outcome_total > 0:
        base_outcome_ratio = (
            fully * 1.0
            + mostly * 0.62
            + partial * 0.22
            + not_achieved * 0.0
        ) / outcome_total
    else:
        base_outcome_ratio = clamp(
            0.64 + safe_div(data.planning_signals, total_messages) * 0.22 - safe_div(data.followup_signals, total_messages) * 0.34,
            0.25,
            0.9,
        )

    followup_rate = clamp(safe_div(data.followup_signals, total_messages), 0.0, 1.0)
    verification_rate = clamp(safe_div(data.verification_signals, total_messages), 0.0, 1.0)
    planning_rate = clamp(safe_div(data.planning_signals, total_messages), 0.0, 1.0)
    acceptance_rate = clamp(safe_div(data.acceptance_signals, total_messages), 0.0, 1.0)
    friction_total = sum(data.friction_counts.values())
    friction_per_session = safe_div(friction_total, total_sessions)

    first_pass_rate = clamp(
        base_outcome_ratio * (1 - followup_rate * 0.36) * (1 - long_session_ratio * 0.2),
        0.1,
        0.98,
    )
    rework_rate = clamp(
        followup_rate * 0.72 + long_session_ratio * 0.42 + (1 - first_pass_rate) * 0.33,
        0.02,
        0.95,
    )
    switch_cost_index = clamp(
        max(0.0, avg_tool_diversity - 2.0) * 0.22
        + max(0.0, avg_tool_calls - 5.0) * 0.05
        + long_session_ratio * 0.28,
        0.0,
        1.0,
    )
    verification_effective = clamp(
        verification_rate * 0.75 + planning_rate * 0.2 + acceptance_rate * 0.05,
        0.0,
        1.0,
    )

    trend_lines, momentum_ratio = build_trend_lines(locale, data)

    completion_score = round(clamp(first_pass_rate * 20, 4, 20))
    rework_score = round(clamp((1 - rework_rate) * 20, 4, 20))
    switch_score = round(clamp((1 - switch_cost_index) * 20, 4, 20))
    verification_score = round(clamp(verification_effective * 28, 4, 20))
    consistency_score = round(clamp(momentum_ratio * 20, 4, 20))

    if locale == "zh":
        completion_reason = f"结果分布 {fully}/{mostly}/{partial}/{not_achieved}，结合返工信号推算一次达成率 {pct(first_pass_rate)}。"
        rework_reason = f"返工率 {pct(rework_rate)}（随“仍然/再次”等返工表达、长会话占比变化）。"
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

    first_pass_status, first_pass_tone = status_by_ratio(locale, first_pass_rate, higher_better=True, good_at=0.66, watch_at=0.48)
    rework_status, rework_tone = status_by_ratio(locale, rework_rate, higher_better=False, good_at=0.72, watch_at=0.55)
    switch_status, switch_tone = status_by_ratio(locale, switch_cost_index, higher_better=False, good_at=0.7, watch_at=0.52)
    verification_status, verification_tone = status_by_ratio(locale, verification_rate, higher_better=True, good_at=0.2, watch_at=0.1)
    planning_status, planning_tone = status_by_ratio(locale, planning_rate, higher_better=True, good_at=0.25, watch_at=0.12)
    long_status, long_tone = status_by_ratio(locale, long_session_ratio, higher_better=False, good_at=0.75, watch_at=0.58)

    diagnostics = [
        DiagnosticMetric(
            label=tr["metric_first_pass"],
            value=pct(first_pass_rate),
            status=first_pass_status,
            detail=(
                "看一次对齐后直接完成的概率。"
                if locale == "zh"
                else "Proxy for one-shot completion after initial alignment."
            ),
            tone=first_pass_tone,
        ),
        DiagnosticMetric(
            label=tr["metric_rework"],
            value=pct(rework_rate),
            status=rework_status,
            detail=(
                "越低越好；高值通常代表需求重述或方案回滚频繁。"
                if locale == "zh"
                else "Lower is better; high values usually indicate repeated rewrites or rollbacks."
            ),
            tone=rework_tone,
        ),
        DiagnosticMetric(
            label=tr["metric_switch"],
            value=pct(switch_cost_index),
            status=switch_status,
            detail=(
                "越低越好；结合工具多样性与会话拉长程度。"
                if locale == "zh"
                else "Lower is better; combines tool diversity and session stretch."
            ),
            tone=switch_tone,
        ),
        DiagnosticMetric(
            label=tr["metric_verification"],
            value=pct(verification_rate),
            status=verification_status,
            detail=(
                "衡量你是否经常主动要求测试/验证。"
                if locale == "zh"
                else "How often you explicitly request tests/verification."
            ),
            tone=verification_tone,
        ),
        DiagnosticMetric(
            label=tr["metric_planning"],
            value=pct(planning_rate),
            status=planning_status,
            detail=(
                "衡量任务前置分解与验收定义是否充分。"
                if locale == "zh"
                else "Measures pre-execution planning and acceptance definition."
            ),
            tone=planning_tone,
        ),
        DiagnosticMetric(
            label=tr["metric_long_session"],
            value=pct(long_session_ratio),
            status=long_status,
            detail=(
                "越低越好；长会话偏多往往意味着对齐和闭环效率不足。"
                if locale == "zh"
                else "Lower is better; too many long sessions often indicate weak alignment and closure."
            ),
            tone=long_tone,
        ),
    ]

    strengths: list[str] = []
    weaknesses: list[str] = []
    next_steps: list[str] = []

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
        weaknesses.append(
            f"最高频摩擦是「{label}」({top_val} 次)，这是当前效率损耗主因。"
            if locale == "zh"
            else f"Top friction is '{label}' ({top_val} times), likely the main efficiency drain."
        )
    if completion_score < 12:
        weaknesses.append("一次达成率偏低，任务常在中后段返工。" if locale == "zh" else "First-pass completion is low, with rework pushed into later stages.")
    if rework_score < 12:
        weaknesses.append("返工控制较弱，建议把“仍然/再次”类反馈前置为验收清单。" if locale == "zh" else "Rework control is weak; convert recurring follow-ups into upfront acceptance checks.")
    if switch_score < 12:
        weaknesses.append("工具切换成本偏高，单任务链路可能过于分散。" if locale == "zh" else "Switch cost is high, suggesting fragmented tool chains per task.")
    if verification_score < 12:
        weaknesses.append("验证覆盖偏低，缺少系统化“先验证再完成”的动作。" if locale == "zh" else "Verification coverage is low; add explicit validate-before-done steps.")

    if friction_total > 0:
        top_name, _ = data.friction_counts.most_common(1)[0]
        label = normalize_friction_key(top_name, locale)
        next_steps.append(
            f"先攻克头号摩擦「{label}」：整理 3 条防错规则写入 SKILL/系统提示词。"
            if locale == "zh"
            else f"Attack top friction '{label}' first: add 3 guardrail rules into your skill/system prompt."
        )
    if completion_score < 15:
        next_steps.append(
            "把需求固定为“输入-约束-验收标准”三段模板，先做一次确认再执行。"
            if locale == "zh"
            else "Adopt a strict template: input, constraints, acceptance criteria."
        )
    if verification_score < 15:
        next_steps.append(
            "给每类任务补 1 条默认验证动作（如 lint/test/回归），并写入技能脚本。"
            if locale == "zh"
            else "Attach one default verification step (lint/test/regression) to each task type."
        )
    if switch_score < 15:
        next_steps.append(
            "把同类任务收敛到 1 条主链路（固定工具顺序），减少跨工具来回切换。"
            if locale == "zh"
            else "Converge each task type to one primary tool chain to reduce switching."
        )
    if consistency_score < 14:
        next_steps.append(
            "固定每周复盘，跟踪“返工率、验证覆盖、长会话占比”三项是否持续改善。"
            if locale == "zh"
            else "Run a weekly review tracking rework, verification coverage, and long-session ratio."
        )

    if not strengths:
        strengths.append("已有可用的 AI 工作节奏，适合继续标准化与自动化。" if locale == "zh" else "You already have a workable AI routine to standardize further.")
    if not weaknesses:
        weaknesses.append("当前未出现明显短板，重点保持稳定并继续自动化。" if locale == "zh" else "No obvious bottleneck this cycle; focus on maintaining stability.")
    if not next_steps:
        next_steps.append("继续迭代现有流程，并沉淀可复用模板。" if locale == "zh" else "Keep iterating and codifying reusable templates.")

    return UsageAssessment(
        total_score=total_score,
        grade=calc_grade(total_score, locale),
        dimensions=dimensions,
        strengths=strengths[:4],
        weaknesses=weaknesses[:4],
        next_steps=next_steps[:4],
        diagnostics=diagnostics,
        trend_lines=trend_lines,
    )


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
        blocks.append(
            f"""
            <div class="diag-card tone-{metric.tone}">
              <div class="diag-head">
                <span class="diag-label">{html.escape(metric.label)}</span>
                <span class="diag-status">{html.escape(metric.status)}</span>
              </div>
              <div class="diag-value">{html.escape(metric.value)}</div>
              <div class="diag-detail">{html.escape(metric.detail)}</div>
            </div>
            """
        )
    return "<div class=\"diag-grid\">" + "".join(blocks) + "</div>"


def sanitize_str_list(value: Any, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for entry in value:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                items.append(text)
        if len(items) >= limit:
            break
    return items


def build_evidence_bundle(
    locale: str,
    data: AggregatedData,
    assessment: UsageAssessment,
    source_stats: dict[str, SourceStats],
) -> dict[str, Any]:
    timeline = sorted(data.session_starts + data.user_timestamps)
    if timeline:
        range_start = timeline[0].isoformat()
        range_end = timeline[-1].isoformat()
    else:
        range_start = ""
        range_end = ""
    dimensions = {dim.label: dim.score for dim in assessment.dimensions}
    top_frictions = [
        {"name": normalize_friction_key(name, locale), "count": count}
        for name, count in top_items(data.friction_counts, 3)
    ]
    top_intents = [
        {"name": name, "count": count}
        for name, count in top_items(normalize_intent_counter(data.intent_counts), 5)
    ]
    top_tools = [{"name": name, "count": count} for name, count in top_items(data.tool_counts, 5)]
    return {
        "locale": locale,
        "time_range": {"start": range_start, "end": range_end},
        "source_stats": {
            key: {
                "sessions": value.sessions,
                "user_messages": value.user_messages,
                "assistant_messages": value.assistant_messages,
                "input_tokens": value.input_tokens,
                "output_tokens": value.output_tokens,
            }
            for key, value in source_stats.items()
            if value.available
        },
        "summary_metrics": {
            "total_sessions": data.total_sessions,
            "total_user_messages": data.total_user_messages,
            "total_active_days": data.total_active_days,
            "verification_signals": data.verification_signals,
            "planning_signals": data.planning_signals,
            "followup_signals": data.followup_signals,
            "acceptance_signals": data.acceptance_signals,
        },
        "score_dimensions": dimensions,
        "diagnostics": [
            {"label": item.label, "value": item.value, "status": item.status}
            for item in assessment.diagnostics
        ],
        "trend_lines": assessment.trend_lines,
        "top_frictions": top_frictions,
        "top_intents": top_intents,
        "top_tools": top_tools,
    }


def default_better_usage_patterns(locale: str) -> list[str]:
    if locale == "zh":
        return [
            "任务开始前必须写清“输入-约束-验收标准”，再进入执行。",
            "默认先跑验证动作（lint/test/回归）再宣告完成。",
            "同类任务固定一条主链路，避免频繁切换工具和上下文。",
            "每周复盘返工率与验证覆盖，针对最高摩擦只做一个改进实验。",
            "把高频返工问题沉淀到 Skill 或系统提示，减少重复踩坑。",
        ]
    return [
        "Define input, constraints, and acceptance criteria before execution.",
        "Run a default verification step (lint/test/regression) before declaring done.",
        "Use one primary tool chain per task type to reduce context switching.",
        "Review rework and verification weekly, then run one focused improvement experiment.",
        "Convert recurring failure patterns into reusable skill/system guardrails.",
    ]


def build_default_agentic_report(
    locale: str,
    assessment: UsageAssessment,
    evidence_bundle: dict[str, Any],
    mode: str,
) -> AgenticReport:
    tr = I18N[locale]
    top_dimension = max(assessment.dimensions, key=lambda item: item.score, default=None)
    low_dimension = min(assessment.dimensions, key=lambda item: item.score, default=None)
    if locale == "zh":
        summary = (
            f"{tr['agentic_summary_hybrid'] if mode == 'hybrid' else tr['agentic_summary_fallback']} "
            f"当前最强维度是「{top_dimension.label if top_dimension else '-'}」，最弱维度是「{low_dimension.label if low_dimension else '-'}」。"
        )
    else:
        summary = (
            f"{tr['agentic_summary_hybrid'] if mode == 'hybrid' else tr['agentic_summary_fallback']} "
            f"Strongest dimension: {top_dimension.label if top_dimension else '-'}, weakest: {low_dimension.label if low_dimension else '-'}."
        )

    evidence_anchors: list[str] = []
    for metric in evidence_bundle.get("diagnostics", [])[:4]:
        if isinstance(metric, dict):
            label = str(metric.get("label") or "").strip()
            value = str(metric.get("value") or "").strip()
            status = str(metric.get("status") or "").strip()
            if label and value:
                evidence_anchors.append(f"{label}: {value} ({status})")
    for line in evidence_bundle.get("trend_lines", [])[:2]:
        if isinstance(line, str) and line.strip():
            evidence_anchors.append(line.strip())

    return AgenticReport(
        summary=summary,
        strengths=assessment.strengths[:4],
        weaknesses=assessment.weaknesses[:4],
        next_steps=assessment.next_steps[:4],
        better_usage_patterns=default_better_usage_patterns(locale),
        evidence_anchors=evidence_anchors[:6],
        confidence=0.62 if mode == "hybrid" else 0.5,
        mode=mode,
    )


def call_agent_model(
    *,
    locale: str,
    evidence_bundle: dict[str, Any],
    base_url: str,
    api_key: str,
    model: str,
    timeout_sec: int,
) -> dict[str, Any] | None:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    system_prompt = (
        "You are a workflow diagnostics analyst. Return JSON only. "
        "Every recommendation must be grounded in provided evidence."
    )
    user_prompt = (
        f"Locale: {locale}\n"
        "Use the evidence JSON to produce a concise analysis.\n"
        "Return JSON with fields: summary, strengths, weaknesses, next_steps, "
        "better_usage_patterns, evidence_anchors, confidence.\n"
        "Requirements:\n"
        "- strengths/weaknesses/next_steps/better_usage_patterns/evidence_anchors are arrays of short strings\n"
        "- confidence is a number between 0 and 1\n"
        "- mention concrete numbers from evidence where useful\n"
        f"Evidence JSON:\n{json.dumps(evidence_bundle, ensure_ascii=False)}"
    )
    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = request.Request(endpoint, data=body, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=timeout_sec) as resp:
            content = resp.read().decode("utf-8", errors="replace")
    except (error.URLError, TimeoutError):
        return None

    try:
        response_json = json.loads(content)
        message = response_json["choices"][0]["message"]["content"]
        parsed = json.loads(message)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def run_agentic_analysis(
    *,
    locale: str,
    assessment: UsageAssessment,
    evidence_bundle: dict[str, Any],
    analysis_mode: str,
    agent_model: str,
    agent_base_url: str,
    agent_api_key_env: str,
    agent_timeout_sec: int,
) -> AgenticReport:
    mode = "deterministic"
    parsed: dict[str, Any] | None = None
    if analysis_mode == "hybrid":
        api_key = os.getenv(agent_api_key_env, "").strip()
        if api_key and agent_model.strip():
            parsed = call_agent_model(
                locale=locale,
                evidence_bundle=evidence_bundle,
                base_url=agent_base_url,
                api_key=api_key,
                model=agent_model.strip(),
                timeout_sec=agent_timeout_sec,
            )
            if parsed:
                mode = "hybrid"
    base_report = build_default_agentic_report(locale, assessment, evidence_bundle, mode)
    if not parsed:
        return base_report

    summary = str(parsed.get("summary") or "").strip() or base_report.summary
    strengths = sanitize_str_list(parsed.get("strengths"), 5) or base_report.strengths
    weaknesses = sanitize_str_list(parsed.get("weaknesses"), 5) or base_report.weaknesses
    next_steps = sanitize_str_list(parsed.get("next_steps"), 5) or base_report.next_steps
    better_usage = sanitize_str_list(parsed.get("better_usage_patterns"), 6) or base_report.better_usage_patterns
    anchors = sanitize_str_list(parsed.get("evidence_anchors"), 8) or base_report.evidence_anchors
    confidence_raw = parsed.get("confidence")
    confidence = 0.68
    if isinstance(confidence_raw, (int, float)):
        confidence = float(clamp(float(confidence_raw), 0.0, 1.0))

    return AgenticReport(
        summary=summary,
        strengths=strengths[:5],
        weaknesses=weaknesses[:5],
        next_steps=next_steps[:5],
        better_usage_patterns=better_usage[:6],
        evidence_anchors=anchors[:8],
        confidence=confidence,
        mode=mode,
    )


def render_html(
    locale: str,
    title_override: str | None,
    data: AggregatedData,
    source_stats: dict[str, SourceStats],
    assessment: UsageAssessment,
    agentic_report: AgenticReport,
) -> str:
    tr = I18N[locale]
    dominant_lang = pick_dominant_language(data)
    dominant_lang_label = tr["dominant_lang_zh"] if dominant_lang == "zh" else tr["dominant_lang_en"]

    timeline = sorted(data.session_starts + data.user_timestamps)
    if timeline:
        start_label = fmt_date(timeline[0], locale)
        end_label = fmt_date(timeline[-1], locale)
    else:
        start_label = tr["no_date"]
        end_label = tr["no_date"]

    sources_present = []
    if source_stats.get("claude", SourceStats("claude")).available:
        sources_present.append(tr["source_claude"])
    if source_stats.get("codex", SourceStats("codex")).available:
        sources_present.append(tr["source_codex"])
    source_label = " + ".join(sources_present) if sources_present else "-"

    title = title_override or tr["title"]

    dayparts = daypart_counts(data.user_timestamps)
    daypart_items = [
        (DAYPART_LABELS[locale]["morning"], dayparts.get("morning", 0)),
        (DAYPART_LABELS[locale]["afternoon"], dayparts.get("afternoon", 0)),
        (DAYPART_LABELS[locale]["evening"], dayparts.get("evening", 0)),
        (DAYPART_LABELS[locale]["night"], dayparts.get("night", 0)),
    ]

    intent_items = localize_intents(top_items(normalize_intent_counter(data.intent_counts), 8), locale)
    tool_items = top_items(data.tool_counts, 8)
    outcome_items = localize_outcomes(top_items(data.outcome_counts, 8), locale)
    friction_items = [(normalize_friction_key(k, locale), v) for k, v in top_items(data.friction_counts, 8)]
    project_items = top_items(data.project_counts, 6)
    source_cards = "".join(source_card(item, locale) for item in source_stats.values() if item.available)
    insights = build_insights(locale, data, dominant_lang)
    insight_html = build_plain_list(insights, tr["missing"])
    score_rows = build_score_rows(assessment.dimensions)
    strengths_html = build_plain_list(agentic_report.strengths or assessment.strengths, tr["missing"])
    weaknesses_html = build_plain_list(agentic_report.weaknesses or assessment.weaknesses, tr["missing"])
    next_steps_html = build_plain_list(agentic_report.next_steps or assessment.next_steps, tr["missing"])
    diagnostics_html = build_diagnostic_cards(assessment.diagnostics, tr["missing"])
    trend_html = build_plain_list(assessment.trend_lines, tr["missing"])
    better_usage_html = build_plain_list(agentic_report.better_usage_patterns, tr["missing"])
    evidence_html = build_plain_list(agentic_report.evidence_anchors, tr["missing"])

    zh_pct, en_pct = language_mix_percent(data)

    report_time = fmt_datetime(datetime.now().astimezone(), locale)
    subtitle = tr["subtitle"].format(start=start_label, end=end_label, sources=source_label)

    return f"""<!doctype html>
<html lang="{locale}">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      --bg-1: #ecfeff;
      --bg-2: #fff7ed;
      --card: rgba(255, 255, 255, 0.88);
      --text: #0f172a;
      --subtext: #475569;
      --line: #e2e8f0;
      --teal: #0f766e;
      --orange: #ea580c;
      --rose: #e11d48;
      --blue: #0369a1;
      --indigo: #4338ca;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "SF Pro Display", "PingFang SC", "Noto Sans SC", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(1200px 600px at -10% -10%, #cffafe 0%, transparent 60%),
        radial-gradient(900px 500px at 110% 0%, #ffedd5 0%, transparent 60%),
        linear-gradient(180deg, var(--bg-1) 0%, var(--bg-2) 100%);
      min-height: 100vh;
      padding: 28px 16px 40px;
    }}
    .container {{ max-width: 1120px; margin: 0 auto; }}
    .hero {{
      background: linear-gradient(120deg, #0f766e 0%, #0369a1 55%, #4338ca 100%);
      color: white;
      border-radius: 18px;
      padding: 28px 24px;
      box-shadow: 0 24px 48px rgba(15, 118, 110, 0.24);
    }}
    .hero h1 {{
      margin: 0 0 10px;
      letter-spacing: 0.2px;
      font-size: clamp(26px, 4.2vw, 40px);
      line-height: 1.15;
    }}
    .hero .sub {{ opacity: 0.96; font-size: 14px; line-height: 1.6; }}
    .hero .time {{ opacity: 0.9; font-size: 12px; margin-top: 8px; }}
    .kpis {{
      margin-top: 18px;
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    }}
    .kpi {{
      background: rgba(255, 255, 255, 0.92);
      color: #0b1324;
      border-radius: 14px;
      padding: 14px;
    }}
    .kpi .label {{ font-size: 12px; color: #334155; text-transform: uppercase; letter-spacing: 0.7px; }}
    .kpi .value {{ font-size: 28px; margin-top: 6px; font-weight: 700; line-height: 1.1; }}
    .grid {{
      margin-top: 16px;
      display: grid;
      gap: 16px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }}
    .card {{
      background: var(--card);
      border: 1px solid rgba(255, 255, 255, 0.7);
      border-radius: 16px;
      padding: 16px;
      backdrop-filter: blur(8px);
      box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
    }}
    .card h2 {{
      margin: 0 0 12px;
      font-size: 17px;
      letter-spacing: 0.2px;
    }}
    .source-card {{
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fff;
      padding: 12px;
      margin-bottom: 10px;
    }}
    .source-name {{ font-weight: 700; margin-bottom: 4px; }}
    .source-meta {{ color: var(--subtext); font-size: 13px; margin-bottom: 2px; }}
    .source-scope {{ color: var(--subtext); font-size: 12px; margin-top: 6px; line-height: 1.5; }}
    .lang-track {{
      height: 18px;
      border-radius: 999px;
      overflow: hidden;
      display: flex;
      border: 1px solid var(--line);
      background: #fff;
      margin-top: 8px;
    }}
    .lang-zh {{ background: linear-gradient(90deg, #0f766e, #14b8a6); }}
    .lang-en {{ background: linear-gradient(90deg, #ea580c, #fb923c); }}
    .lang-caption {{ margin-top: 10px; color: var(--subtext); font-size: 13px; }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(112px, 1.3fr) 4fr minmax(48px, auto);
      gap: 8px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .bar-label {{
      font-size: 12px;
      color: #334155;
      word-break: break-word;
      line-height: 1.35;
    }}
    .bar-track {{
      height: 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #f8fafc;
      overflow: hidden;
    }}
    .bar-fill {{ height: 100%; border-radius: 999px; }}
    .bar-value {{
      text-align: right;
      font-size: 12px;
      color: #0f172a;
      font-variant-numeric: tabular-nums;
    }}
    .insight-list {{
      margin: 8px 0 0;
      padding-left: 18px;
      color: var(--subtext);
      line-height: 1.6;
      font-size: 14px;
    }}
    .score-layout {{
      display: grid;
      gap: 12px;
      grid-template-columns: minmax(170px, 220px) 1fr;
      align-items: start;
    }}
    .score-total {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
      padding: 14px;
      text-align: center;
    }}
    .score-total .value {{
      font-size: 44px;
      font-weight: 800;
      line-height: 1.05;
      color: #0f766e;
      margin-top: 6px;
    }}
    .score-total .grade {{
      margin-top: 8px;
      font-size: 13px;
      color: #334155;
    }}
    .score-rows {{
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #fff;
      padding: 12px;
    }}
    .score-row {{
      padding: 8px 0 10px;
      border-bottom: 1px dashed #e2e8f0;
    }}
    .score-row:last-child {{ border-bottom: 0; padding-bottom: 2px; }}
    .score-head {{
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      color: #0f172a;
      margin-bottom: 6px;
    }}
    .score-track {{
      height: 9px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: #f8fafc;
      overflow: hidden;
    }}
    .score-fill {{
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, #0f766e, #4338ca);
    }}
    .score-reason {{
      margin-top: 6px;
      font-size: 12px;
      color: #64748b;
      line-height: 1.45;
    }}
    .diag-grid {{
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    }}
    .diag-card {{
      border-radius: 12px;
      border: 1px solid var(--line);
      background: #fff;
      padding: 12px;
    }}
    .diag-head {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }}
    .diag-label {{
      font-size: 12px;
      color: #334155;
      font-weight: 600;
    }}
    .diag-status {{
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid currentColor;
      line-height: 1.4;
      font-weight: 600;
    }}
    .diag-value {{
      margin-top: 8px;
      font-size: 28px;
      font-weight: 800;
      line-height: 1.1;
      letter-spacing: 0.2px;
    }}
    .diag-detail {{
      margin-top: 6px;
      color: #64748b;
      font-size: 12px;
      line-height: 1.45;
    }}
    .tone-good {{ border-color: #bbf7d0; background: linear-gradient(180deg, #f0fdf4, #ffffff); }}
    .tone-good .diag-status {{ color: #166534; }}
    .tone-good .diag-value {{ color: #166534; }}
    .tone-warn {{ border-color: #fde68a; background: linear-gradient(180deg, #fffbeb, #ffffff); }}
    .tone-warn .diag-status {{ color: #92400e; }}
    .tone-warn .diag-value {{ color: #92400e; }}
    .tone-risk {{ border-color: #fecaca; background: linear-gradient(180deg, #fef2f2, #ffffff); }}
    .tone-risk .diag-status {{ color: #991b1b; }}
    .tone-risk .diag-value {{ color: #991b1b; }}
    .empty {{
      border: 1px dashed var(--line);
      border-radius: 12px;
      padding: 14px;
      color: #64748b;
      font-size: 13px;
      background: #fff;
    }}
    @media (max-width: 760px) {{
      .bar-row {{ grid-template-columns: minmax(88px, 1.1fr) 3fr minmax(38px, auto); }}
      .score-layout {{ grid-template-columns: 1fr; }}
      .diag-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <section class="hero">
      <h1>{html.escape(title)}</h1>
      <div class="sub">{html.escape(subtitle)}</div>
      <div class="time">{html.escape(tr["report_time"].format(time=report_time))}</div>
      <div class="kpis">
        <div class="kpi"><div class="label">{tr["kpi_sessions"]}</div><div class="value">{fmt_num(data.total_sessions)}</div></div>
        <div class="kpi"><div class="label">{tr["kpi_user_msgs"]}</div><div class="value">{fmt_num(data.total_user_messages)}</div></div>
        <div class="kpi"><div class="label">{tr["kpi_active_days"]}</div><div class="value">{fmt_num(data.total_active_days)}</div></div>
        <div class="kpi"><div class="label">{tr["kpi_lang"]}</div><div class="value">{html.escape(dominant_lang_label)}</div></div>
      </div>
    </section>

    <div class="grid">
      <section class="card" style="grid-column: 1 / -1;">
        <h2>{tr["section_score"]}</h2>
        <div class="score-layout">
          <div class="score-total">
            <div class="label">{tr["score_total"]}</div>
            <div class="value">{assessment.total_score}</div>
            <div class="grade">{tr["score_grade"]}: {html.escape(assessment.grade)}</div>
          </div>
          <div class="score-rows">
            <div style="font-size:12px;color:#64748b;margin-bottom:8px;">{tr["score_basis"]}</div>
            {score_rows}
          </div>
        </div>
      </section>
      <section class="card">
        <h2>{tr["section_strengths"]}</h2>
        {strengths_html}
      </section>
      <section class="card">
        <h2>{tr["section_weaknesses"]}</h2>
        {weaknesses_html}
      </section>
      <section class="card" style="grid-column: 1 / -1;">
        <h2>{tr["section_next_steps"]}</h2>
        {next_steps_html}
      </section>
      <section class="card" style="grid-column: 1 / -1;">
        <h2>{tr["section_agentic"]}</h2>
        <div style="font-size:14px;line-height:1.65;color:#334155;">{html.escape(agentic_report.summary)}</div>
        <div style="margin-top:8px;font-size:12px;color:#64748b;">mode={html.escape(agentic_report.mode)} · confidence={agentic_report.confidence:.2f}</div>
      </section>
      <section class="card">
        <h2>{tr["section_better_usage"]}</h2>
        <div style="font-size:13px;color:#64748b;margin-bottom:6px;">{html.escape(tr["better_usage_intro"])}</div>
        {better_usage_html}
      </section>
      <section class="card">
        <h2>{tr["agentic_evidence_title"]}</h2>
        {evidence_html}
      </section>
      <section class="card" style="grid-column: 1 / -1;">
        <h2>{tr["section_diagnostics"]}</h2>
        {diagnostics_html}
      </section>
      <section class="card" style="grid-column: 1 / -1;">
        <h2>{tr["section_trend"]}</h2>
        {trend_html}
      </section>
      <section class="card">
        <h2>{tr["section_source"]}</h2>
        {source_cards or f'<div class="empty">{tr["missing"]}</div>'}
      </section>
      <section class="card">
        <h2>{tr["section_lang"]}</h2>
        <div class="lang-track">
          <div class="lang-zh" style="width:{zh_pct}%"></div>
          <div class="lang-en" style="width:{en_pct}%"></div>
        </div>
        <div class="lang-caption">{html.escape(tr["lang_mix"].format(zh_pct=zh_pct, en_pct=en_pct))}</div>
      </section>
      <section class="card">
        <h2>{tr["section_activity"]}</h2>
        {build_bar_rows(daypart_items, "#0369a1", tr["missing"])}
      </section>
      <section class="card">
        <h2>{tr["section_intent"]}</h2>
        {build_bar_rows(intent_items, "#0f766e", tr["missing"])}
      </section>
      <section class="card">
        <h2>{tr["section_tools"]}</h2>
        {build_bar_rows(tool_items, "#4338ca", tr["missing"])}
      </section>
      <section class="card">
        <h2>{tr["section_outcome"]}</h2>
        {build_bar_rows(outcome_items, "#ea580c", tr["missing"])}
      </section>
      <section class="card">
        <h2>{tr["section_friction"]}</h2>
        {build_bar_rows(friction_items, "#e11d48", tr["missing"])}
      </section>
      <section class="card">
        <h2>{tr["section_projects"]}</h2>
        {build_bar_rows(project_items, "#0f766e", tr["missing"])}
      </section>
      <section class="card" style="grid-column: 1 / -1;">
        <h2>{tr["section_insights"]}</h2>
        {insight_html}
      </section>
    </div>
  </div>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a polished usage insights report for Claude Code and Codex CLI."
    )
    parser.add_argument(
        "--source",
        choices=["auto", "claude", "codex", "both"],
        default="auto",
        help="Data source mode (default: auto).",
    )
    parser.add_argument(
        "--claude-dir",
        default=str(Path.home() / ".claude" / "usage-data"),
        help="Claude usage-data directory path.",
    )
    parser.add_argument(
        "--codex-history",
        default=str(Path.home() / ".codex" / "history.jsonl"),
        help="Codex history.jsonl path.",
    )
    parser.add_argument(
        "--locale",
        choices=["auto", "zh", "en"],
        default="auto",
        help="Report language. Auto selects based on dominant language usage.",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Optional report title override.",
    )
    parser.add_argument(
        "--output",
        default="./usage-insights-report.html",
        help="Output HTML path.",
    )
    parser.add_argument(
        "--analysis-mode",
        choices=["hybrid", "deterministic"],
        default="hybrid",
        help="Analysis mode. hybrid uses evidence + optional LLM reasoning; deterministic uses rules only.",
    )
    parser.add_argument(
        "--agent-model",
        default="",
        help="Model name for OpenAI-compatible chat completions. Leave empty to disable remote agent reasoning.",
    )
    parser.add_argument(
        "--agent-base-url",
        default="https://api.openai.com/v1",
        help="Base URL for OpenAI-compatible API.",
    )
    parser.add_argument(
        "--agent-api-key-env",
        default="OPENAI_API_KEY",
        help="Environment variable name that stores the API key.",
    )
    parser.add_argument(
        "--agent-timeout-sec",
        type=int,
        default=45,
        help="Timeout in seconds for agent reasoning API calls.",
    )
    parser.add_argument(
        "--evidence-output",
        default="",
        help="Optional path to write grounded evidence JSON. Defaults to <output>.evidence.json.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_mode: str = args.source
    claude_dir = Path(args.claude_dir).expanduser()
    codex_history = Path(args.codex_history).expanduser()

    source_stats: dict[str, SourceStats] = {
        "claude": SourceStats(name="claude"),
        "codex": SourceStats(name="codex"),
    }
    aggregates: list[AggregatedData] = []

    use_claude = source_mode in {"auto", "claude", "both"}
    use_codex = source_mode in {"auto", "codex", "both"}

    if use_claude:
        claude_stats, claude_agg = load_claude_data(claude_dir)
        source_stats["claude"] = claude_stats
        if claude_stats.available:
            aggregates.append(claude_agg)

    if use_codex:
        codex_stats, codex_agg = load_codex_data(codex_history)
        source_stats["codex"] = codex_stats
        if codex_stats.available:
            aggregates.append(codex_agg)

    if not aggregates:
        print("No usable data found. Check --claude-dir / --codex-history.")
        return 1

    merged = merge_aggregates(aggregates)
    merged.sources = source_stats
    locale = pick_locale(args.locale, merged.language_chars, merged.language_messages)
    output_path = Path(args.output).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    assessment = build_assessment(locale, merged)
    evidence_bundle = build_evidence_bundle(locale, merged, assessment, source_stats)
    agentic_report = run_agentic_analysis(
        locale=locale,
        assessment=assessment,
        evidence_bundle=evidence_bundle,
        analysis_mode=args.analysis_mode,
        agent_model=str(args.agent_model or ""),
        agent_base_url=str(args.agent_base_url or "https://api.openai.com/v1"),
        agent_api_key_env=str(args.agent_api_key_env or "OPENAI_API_KEY"),
        agent_timeout_sec=max(5, safe_int(args.agent_timeout_sec)),
    )
    html_content = render_html(
        locale,
        args.title.strip() or None,
        merged,
        source_stats,
        assessment,
        agentic_report,
    )
    output_path.write_text(html_content, encoding="utf-8")

    evidence_output = str(args.evidence_output or "").strip()
    evidence_path = Path(evidence_output).expanduser() if evidence_output else output_path.with_suffix(".evidence.json")
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_doc = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "locale": locale,
        "analysis_mode": args.analysis_mode,
        "agentic_mode_used": agentic_report.mode,
        "agent_confidence": agentic_report.confidence,
        "assessment": {
            "total_score": assessment.total_score,
            "grade": assessment.grade,
            "dimensions": [{"label": dim.label, "score": dim.score, "reason": dim.reason} for dim in assessment.dimensions],
        },
        "agentic_report": {
            "summary": agentic_report.summary,
            "strengths": agentic_report.strengths,
            "weaknesses": agentic_report.weaknesses,
            "next_steps": agentic_report.next_steps,
            "better_usage_patterns": agentic_report.better_usage_patterns,
            "evidence_anchors": agentic_report.evidence_anchors,
        },
        "evidence_bundle": evidence_bundle,
    }
    evidence_path.write_text(json.dumps(evidence_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Report written to: {output_path}")
    print(f"Evidence written to: {evidence_path}")
    print(f"Locale: {locale}")
    print(f"Analysis mode: requested={args.analysis_mode}, actual={agentic_report.mode}")
    print(
        "Sources used: "
        + ", ".join(
            key for key, value in source_stats.items() if value.available
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
