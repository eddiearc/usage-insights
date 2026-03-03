#!/usr/bin/env python3
"""Render usage-insights markdown review to a polished HTML page.

This renderer emphasizes:
- Green for strengths
- Red for weaknesses
- Amber/teal for transitional sections
- Bold labels for evidence/judgment/action
"""

from __future__ import annotations

import argparse
import re
from html import escape
from pathlib import Path


def inline_fmt(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(
        r"\b(目标|约束|验收|风险|回归|并行|短板|优势|改进动作|评语|证据)\b",
        r"<strong>\1</strong>",
        text,
    )
    return text


def render_markdown(md_text: str) -> str:
    lines = md_text.splitlines()
    html_parts: list[str] = []
    para_buf: list[str] = []
    in_ul = False
    in_ol = False
    in_blockquote = False
    current_h2 = ""

    def flush_para() -> None:
        nonlocal para_buf
        if para_buf:
            html_parts.append(f"<p>{inline_fmt(' '.join(para_buf).strip())}</p>")
            para_buf = []

    def close_all() -> None:
        nonlocal in_ul, in_ol, in_blockquote
        if in_ul:
            html_parts.append("</ul>")
            in_ul = False
        if in_ol:
            html_parts.append("</ol>")
            in_ol = False
        if in_blockquote:
            html_parts.append("</blockquote>")
            in_blockquote = False

    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            flush_para()
            close_all()
            continue

        h1 = re.match(r"^#\s+(.+)$", stripped)
        h2 = re.match(r"^##\s+(.+)$", stripped)
        ul = re.match(r"^-\s+(.+)$", stripped)
        ol = re.match(r"^\d+\.\s+(.+)$", stripped)
        bq = re.match(r"^>\s+(.+)$", stripped)

        if h1:
            flush_para()
            close_all()
            html_parts.append(f"<h1>{inline_fmt(h1.group(1))}</h1>")
            continue

        if h2:
            flush_para()
            close_all()
            current_h2 = h2.group(1)
            classes = ["section-title"]

            if "优势" in current_h2:
                classes.append("positive-title")
            elif "短板" in current_h2:
                classes.append("negative-title")
            elif "下一步行动" in current_h2:
                classes.append("action-title")

            m = re.search(r":\s*([ABCD])\s*$", current_h2)
            if m:
                classes.append("dim-title")
                classes.append(f"grade-{m.group(1)}")

            html_parts.append(f"<h2 class=\"{' '.join(classes)}\">{inline_fmt(current_h2)}</h2>")
            continue

        if bq:
            flush_para()
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False
            if not in_blockquote:
                html_parts.append("<blockquote>")
                in_blockquote = True
            html_parts.append(f"<p>{inline_fmt(bq.group(1))}</p>")
            continue

        if ul:
            flush_para()
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False
            if in_blockquote:
                html_parts.append("</blockquote>")
                in_blockquote = False
            if not in_ul:
                list_class = "list"
                if "优势" in current_h2:
                    list_class += " positive-list"
                elif "短板" in current_h2:
                    list_class += " negative-list"
                elif "下一步行动" in current_h2:
                    list_class += " action-list"
                html_parts.append(f"<ul class=\"{list_class}\">")
                in_ul = True

            item = inline_fmt(ul.group(1))
            item = re.sub(
                r"^(证据\s*\d*[:：]|片段[:：]|评语[:：]|改进动作[:：]|说明[:：])",
                r"<strong>\1</strong>",
                item,
            )
            html_parts.append(f"<li>{item}</li>")
            continue

        if ol:
            flush_para()
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if in_blockquote:
                html_parts.append("</blockquote>")
                in_blockquote = False
            if not in_ol:
                list_class = "list"
                if "优势" in current_h2:
                    list_class += " positive-list"
                elif "短板" in current_h2:
                    list_class += " negative-list"
                elif "下一步行动" in current_h2:
                    list_class += " action-list"
                html_parts.append(f"<ol class=\"{list_class}\">")
                in_ol = True
            html_parts.append(f"<li>{inline_fmt(ol.group(1))}</li>")
            continue

        if in_ul:
            html_parts.append("</ul>")
            in_ul = False
        if in_ol:
            html_parts.append("</ol>")
            in_ol = False
        if in_blockquote:
            html_parts.append("</blockquote>")
            in_blockquote = False
        para_buf.append(stripped)

    flush_para()
    close_all()
    return "\n".join(html_parts)


def render_html_doc(body_html: str, source_name: str, title: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f6f7fb;
      --card: #ffffff;
      --text: #142033;
      --muted: #5a6678;
      --line: #e5e9f1;
      --green: #168a5f;
      --green-bg: #eaf8f1;
      --amber: #b26a00;
      --amber-bg: #fff6e8;
      --red: #c0392b;
      --red-bg: #fdeeee;
      --teal: #157f8f;
      --teal-bg: #e9f7fa;
      --code-bg: #f3f5fa;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--text);
      background:
        radial-gradient(1000px 520px at -8% -20%, #eaf6ff 0%, transparent 56%),
        radial-gradient(900px 420px at 110% -10%, #f0f9ef 0%, transparent 52%),
        var(--bg);
      font-family: "Avenir Next", "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
      line-height: 1.75;
      padding: 30px 14px;
    }}
    .wrap {{
      max-width: 960px;
      margin: 0 auto;
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: 0 12px 32px rgba(22, 38, 62, 0.08);
      padding: 30px;
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 1.9rem;
      line-height: 1.3;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--line);
    }}
    .section-title {{
      margin: 28px 0 10px;
      padding: 9px 12px;
      border-radius: 10px;
      font-size: 1.12rem;
      font-weight: 800;
      border: 1px solid var(--line);
      background: #f8fafc;
    }}
    .dim-title.grade-A {{ color: var(--green); background: var(--green-bg); border-color: #caebdd; }}
    .dim-title.grade-B {{ color: var(--teal); background: var(--teal-bg); border-color: #cdeaf0; }}
    .dim-title.grade-C {{ color: var(--amber); background: var(--amber-bg); border-color: #f2dfb8; }}
    .dim-title.grade-D {{ color: var(--red); background: var(--red-bg); border-color: #f4c8c5; }}
    .positive-title {{ color: var(--green); background: var(--green-bg); border-color: #caebdd; }}
    .negative-title {{ color: var(--red); background: var(--red-bg); border-color: #f4c8c5; }}
    .action-title {{ color: var(--amber); background: var(--amber-bg); border-color: #f2dfb8; }}
    p {{ margin: 10px 0; }}
    .list {{ margin: 10px 0 10px 22px; padding: 0; }}
    .list li {{ margin: 7px 0; }}
    .positive-list li::marker {{ color: var(--green); font-weight: 700; }}
    .negative-list li::marker {{ color: var(--red); font-weight: 700; }}
    .action-list li::marker {{ color: var(--amber); font-weight: 700; }}
    blockquote {{
      margin: 12px 0;
      padding: 8px 12px;
      border-left: 4px solid #9bb8d5;
      background: #f5f9ff;
      border-radius: 8px;
    }}
    code {{
      font-family: "SF Mono", "Menlo", "Consolas", monospace;
      font-size: 0.92em;
      background: var(--code-bg);
      border: 1px solid #e6eaf2;
      border-radius: 6px;
      padding: 0.15em 0.4em;
      color: #223a5e;
    }}
    strong {{ font-weight: 800; }}
    .meta {{
      margin-top: 28px;
      padding-top: 14px;
      border-top: 1px dashed var(--line);
      color: var(--muted);
      font-size: 0.9rem;
    }}
    @media (max-width: 720px) {{
      .wrap {{ padding: 20px 14px; border-radius: 12px; }}
      h1 {{ font-size: 1.42rem; }}
      .section-title {{ font-size: 1rem; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    {body_html}
    <div class="meta">Rendered from <code>{escape(source_name)}</code></div>
  </main>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Render usage-insights markdown review to HTML.")
    parser.add_argument("--input", default="./artifacts/usage-insights-review.md", help="Input markdown path")
    parser.add_argument("--output", default="./artifacts/usage-insights-review.html", help="Output html path")
    parser.add_argument("--title", default="Usage Insights Review", help="HTML title")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        raise SystemExit(f"Input not found: {in_path}")

    md_text = in_path.read_text(encoding="utf-8")
    body_html = render_markdown(md_text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_html_doc(body_html, in_path.name, args.title), encoding="utf-8")
    print(f"Rendered HTML: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

