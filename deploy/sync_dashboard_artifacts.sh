#!/usr/bin/env bash
# Lightweight artifact mirror: pushes dashboard-consumed artifact trees to the
# external host without rebuilding or redeploying images. Intended to run right
# after strategy EOD publish / repair so the public site reflects new data
# within minutes instead of waiting for the nightly release sync.
set -euo pipefail

ROOT="${STOCK_RESEARCH_RELEASE_ROOT:-/Users/xiwei/stock_research}"
cd "$ROOT"

env_file="${DASHBOARD_SYNC_ENV:-/Users/xiwei/.stock_research_dashboard_sync.env}"
if [[ -f "$env_file" ]]; then
  # shellcheck disable=SC1090
  source "$env_file"
fi

REMOTE_USER="${REMOTE_USER:-jqz}"
REMOTE_HOST="${REMOTE_HOST:-192.168.3.185}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/code/stock-research-platform-main}"
SSH_OPTS="${SSH_OPTS:-}"
BASE_URL="${BASE_URL:-https://stock.manqiaotechnology.com}"
DASHBOARD_AUTH="${DASHBOARD_AUTH:-}"
LOG_DIR="${ARTIFACT_SYNC_LOG_DIR:-$ROOT/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/dashboard_artifact_sync.log"

log() { printf '%s %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" | tee -a "$LOG_FILE"; }

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10)
if [[ -n "$SSH_OPTS" ]]; then
  read -r -a extra_opts <<<"$SSH_OPTS"
  ssh_opts+=("${extra_opts[@]}")
fi
remote="${REMOTE_USER}@${REMOTE_HOST}"
printf -v remote_dir_q '%q' "$REMOTE_DIR"
printf -v rsync_rsh ' %q' "${ssh_opts[@]}"
rsync_rsh="ssh${rsync_rsh}"

if ! ssh "${ssh_opts[@]}" -- "$remote" "mkdir -p ${remote_dir_q}/outputs/research ${remote_dir_q}/reports ${remote_dir_q}/artifacts/theme_decomposition"; then
  log "artifact-sync FAIL: cannot reach ${remote}"
  exit 1
fi

status=0

log "artifact-sync start root=${ROOT} -> ${remote}:${REMOTE_DIR}"
rsync -az -e "$rsync_rsh" -- \
  "$ROOT/outputs/research/strategy_daily_eod/" \
  "$remote:$REMOTE_DIR/outputs/research/strategy_daily_eod/" || status=1
rsync -az -e "$rsync_rsh" -- \
  "$ROOT/reports/" "$remote:$REMOTE_DIR/reports/" || status=1
if [[ -d "$ROOT/artifacts/theme_decomposition" ]]; then
  rsync -az -e "$rsync_rsh" -- \
    "$ROOT/artifacts/theme_decomposition/" \
    "$remote:$REMOTE_DIR/artifacts/theme_decomposition/" || status=1
fi

latest_td="$(ls -1 "$ROOT/outputs/research/strategy_daily_eod" 2>/dev/null | grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort | tail -n 1 || true)"
if [[ -n "$latest_td" ]]; then
  auth_args=()
  if [[ -n "$DASHBOARD_AUTH" ]]; then
    auth_args=(-u "$DASHBOARD_AUTH")
  fi
  counts="$(
    curl -fsS --connect-timeout 5 --max-time 30 "${auth_args[@]}" \
      "$BASE_URL/api/review-queue?trade_date=${latest_td}&limit=20&lookback_days=90" 2>/dev/null \
      | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("parse_error"); raise SystemExit(0)
counts = {g.get("bucket", "").split(":")[-1]: g.get("count", 0) for g in d.get("groups", [])}
print(json.dumps(counts, ensure_ascii=False))' || true
  )"
  log "artifact-sync verify ${latest_td}: review-queue counts=${counts:-unavailable}"
  if [[ -z "$counts" || "$counts" == "parse_error" ]]; then
    status=1
  fi
fi

if [[ "$status" -eq 0 ]]; then
  log "artifact-sync done"
else
  log "artifact-sync FAIL: see errors above"
fi
exit "$status"
