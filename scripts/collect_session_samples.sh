#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash ./scripts/collect_session_samples.sh [options]

Options:
  --source auto|claude|codex      Data source (default: auto)
  --limit N                       Number of sessions (default: 20)
  --output-dir DIR                Output directory (default: ./artifacts)
  --claude-dir DIR                Claude usage dir (default: ~/.claude/usage-data)
  --codex-history FILE            Codex history file (default: ~/.codex/history.jsonl)
  -h, --help                      Show help
EOF
}

SOURCE="auto"
LIMIT=20
OUTPUT_DIR="./artifacts"
CLAUDE_DIR="${HOME}/.claude/usage-data"
CODEX_HISTORY="${HOME}/.codex/history.jsonl"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source)
      SOURCE="$2"
      shift 2
      ;;
    --limit)
      LIMIT="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --claude-dir)
      CLAUDE_DIR="$2"
      shift 2
      ;;
    --codex-history)
      CODEX_HISTORY="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required." >&2
  exit 1
fi

if ! [[ "$LIMIT" =~ ^[0-9]+$ ]] || [[ "$LIMIT" -le 0 ]]; then
  echo "--limit must be a positive integer." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
PARTS=()

load_claude() {
  local session_meta_dir="${CLAUDE_DIR}/session-meta"
  local out="${TMP_DIR}/claude.json"
  if [[ ! -d "$session_meta_dir" ]]; then
    return
  fi

  if ! find "$session_meta_dir" -type f -name '*.json' -print -quit | grep -q .; then
    return
  fi

  find "$session_meta_dir" -type f -name '*.json' -print0 \
    | xargs -0 cat \
    | jq -s '
      map({
        source: "claude",
        session_id: (.session_id // ""),
        start_ts: (
          .start_time
          | tostring
          | sub("\\.[0-9]+Z$"; "Z")
          | fromdateiso8601?
          // 0
        ),
        start_time: (.start_time // ""),
        project_path: (.project_path // ""),
        message_count: ((.user_message_count // 0) + (.assistant_message_count // 0)),
        first_prompt: (.first_prompt // "")
      })
      | map(select(.session_id != "" and .start_ts > 0))
    ' > "$out"

  PARTS+=("$out")
}

load_codex() {
  local out="${TMP_DIR}/codex.json"
  if [[ ! -f "$CODEX_HISTORY" ]]; then
    return
  fi

  jq -s '
    map(select(.session_id != null and .session_id != "" and .ts != null))
    | sort_by(.session_id, .ts)
    | group_by(.session_id)
    | map(
        sort_by(.ts)
        | {
            source: "codex",
            session_id: (.[0].session_id // ""),
            start_ts: (.[0].ts // 0),
            start_time: ((.[0].ts // 0) | todateiso8601),
            project_path: "",
            message_count: length,
            first_prompt: (.[0].text // "")
          }
      )
    | map(select(.session_id != "" and .start_ts > 0))
  ' "$CODEX_HISTORY" > "$out"

  PARTS+=("$out")
}

case "$SOURCE" in
  auto)
    load_claude
    load_codex
    ;;
  claude)
    load_claude
    ;;
  codex)
    load_codex
    ;;
  *)
    echo "--source must be one of: auto, claude, codex" >&2
    exit 1
    ;;
esac

if [[ "${#PARTS[@]}" -eq 0 ]]; then
  echo "No session data found." >&2
  exit 1
fi

JSON_OUT="${OUTPUT_DIR}/session-samples.json"
MD_OUT="${OUTPUT_DIR}/session-samples.md"

if [[ "$SOURCE" == "auto" ]]; then
  jq -s --argjson limit "$LIMIT" '
    add as $all
    | (($limit / 2) | floor) as $claude_quota
    | ($limit - $claude_quota) as $codex_quota
    | ($all | map(select(.source == "claude")) | sort_by(.start_ts) | reverse | .[:$claude_quota]) as $claude
    | ($all | map(select(.source == "codex")) | sort_by(.start_ts) | reverse | .[:$codex_quota]) as $codex
    | ($claude + $codex) as $selected
    | if ($selected | length) < $limit then
        ($all
         | map(select((.session_id as $sid | $selected | map(.session_id) | index($sid)) | not))
         | sort_by(.start_ts)
         | reverse
         | .[:($limit - ($selected | length))]) as $extra
        | ($selected + $extra)
      else
        $selected
      end
    | sort_by(.start_ts)
    | reverse
    | .[:$limit]
  ' "${PARTS[@]}" > "$JSON_OUT"
else
  jq -s --argjson limit "$LIMIT" '
    add
    | sort_by(.start_ts)
    | reverse
    | .[:$limit]
  ' "${PARTS[@]}" > "$JSON_OUT"
fi

{
  jq -r '
    "# Session Samples\n\n"
    + "Total: \(. | length)\n\n"
    + (
      to_entries
      | map(
          "## \(.key + 1). [\(.value.source)] \(.value.session_id)\n"
          + "- 时间: \(.value.start_time)\n"
          + "- 项目: \(.value.project_path)\n"
          + "- 消息数: \(.value.message_count)\n"
          + "- 首条请求:\n\n"
          + "> \(.value.first_prompt | gsub("\n"; " ") | .[0:320])\n"
        )
      | join("\n")
    )
  ' "$JSON_OUT"
} > "$MD_OUT"

echo "Session samples JSON: $JSON_OUT"
echo "Session samples Markdown: $MD_OUT"
