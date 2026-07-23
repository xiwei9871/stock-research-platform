#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://stock.manqiaotechnology.com}"
API_BASE="${API_BASE:-${BASE_URL%/}/api}"
TRADE_DATE="${TRADE_DATE:-2026-06-08}"
START_DATE="${START_DATE:-2026-01-01}"
END_DATE="${END_DATE:-2026-06-08}"
DASHBOARD_AUTH="${DASHBOARD_AUTH:-}"
FETCH_RETRIES="${FETCH_RETRIES:-10}"
FETCH_RETRY_SLEEP_SECONDS="${FETCH_RETRY_SLEEP_SECONDS:-3}"

curl_auth=()
if [[ -n "$DASHBOARD_AUTH" ]]; then
  curl_auth=(-u "$DASHBOARD_AUTH")
fi

fetch() {
  local attempt
  for attempt in $(seq 1 "$FETCH_RETRIES"); do
    if curl -fsS "${curl_auth[@]}" "$@"; then
      return 0
    fi
    if [[ "$attempt" == "$FETCH_RETRIES" ]]; then
      return 1
    fi
    sleep "$FETCH_RETRY_SLEEP_SECONDS"
  done
}

require_body_contains() {
  local body="$1"
  local expected="$2"
  local label="$3"

  if ! grep -Fq "$expected" <<<"$body"; then
    echo "FAIL: $label did not contain expected text: $expected" >&2
    exit 1
  fi
}

require_body_not_old_dashboard() {
  local body="$1"

  if grep -Fq "TOPN" <<<"$body" && ! grep -Fq "Backtest Lab" <<<"$body"; then
    echo "FAIL: old TOPN dashboard detected; deploy the dashboard branch frontend build." >&2
    exit 1
  fi
}

echo "Checking frontend at $BASE_URL"
home_body="$(fetch "${BASE_URL%/}/")"
js_asset="$(awk 'match($0, /\/assets\/[^"]+\.js/) { print substr($0, RSTART, RLENGTH); exit }' <<<"$home_body")"
if [[ -z "$js_asset" ]]; then
  echo "FAIL: frontend HTML does not reference a Vite JS asset." >&2
  exit 1
fi
bundle_body="$(fetch "${BASE_URL%/}${js_asset}")"
require_body_contains "$bundle_body" "Backtest Lab" "frontend bundle"
require_body_contains "$bundle_body" "Market Monitor" "frontend bundle"
require_body_contains "$bundle_body" "Stock Workspace" "frontend bundle"
require_body_not_old_dashboard "$bundle_body"

echo "Checking /api/platform/summary endpoint"
fetch "${API_BASE%/}/platform/summary" >/dev/null

echo "Checking /api/platform/readiness endpoint"
readiness_body="$(fetch "${API_BASE%/}/platform/readiness")"
require_body_contains "$readiness_body" "\"latest_trade_date\"" "platform readiness"

echo "Checking /api/backtests/strategies endpoint"
strategies_body="$(fetch "${API_BASE%/}/backtests/strategies")"
require_body_contains "$strategies_body" "lhb_shortline" "strategy catalog"
require_body_contains "$strategies_body" "mid_trend" "strategy catalog"
require_body_contains "$strategies_body" "tech_bottleneck" "strategy catalog"

echo "Checking /api/review-queue endpoint"
review_queue_body="$(fetch "${API_BASE%/}/review-queue?trade_date=${TRADE_DATE}&limit=20")"
require_body_contains "$review_queue_body" "\"trade_date\"" "review queue"
require_body_contains "$review_queue_body" "\"groups\"" "review queue"

echo "Checking /api/daily-review-lite endpoint"
daily_review_body="$(fetch "${API_BASE%/}/daily-review-lite?trade_date=${TRADE_DATE}")"
require_body_contains "$daily_review_body" "\"trade_date\"" "daily review lite"
require_body_contains "$daily_review_body" "\"sections\"" "daily review lite"

echo "Checking /api/strategy-score-audit endpoint"
strategy_score_audit_body="$(fetch "${API_BASE%/}/strategy-score-audit?trade_date=${TRADE_DATE}")"
require_body_contains "$strategy_score_audit_body" "\"trade_date\"" "strategy score audit"
require_body_contains "$strategy_score_audit_body" "\"status\"" "strategy score audit"
require_body_contains "$strategy_score_audit_body" "\"summary_path\"" "strategy score audit"

echo "Checking /api/assets/000001.SZ/profile endpoint"
fetch "${API_BASE%/}/assets/000001.SZ/profile?trade_date=${TRADE_DATE}&start_date=${START_DATE}&end_date=${END_DATE}&score_version=manual_v1&adjust_type=qfq" >/dev/null

echo "Checking /api/backtests/jobs endpoint wiring"
job_body="$(fetch \
  -H "Content-Type: application/json" \
  -X POST \
  --data "{\"strategy_id\":\"lhb_shortline\",\"start_date\":\"${START_DATE}\",\"end_date\":\"${END_DATE}\",\"top_n\":5,\"transaction_cost_bps\":10,\"max_positions\":null,\"max_position_weight\":0.2}" \
  "${API_BASE%/}/backtests/jobs")"
require_body_contains "$job_body" "job_id" "backtest job submission"
require_body_contains "$job_body" "status" "backtest job submission"

echo "Dashboard release check passed."
