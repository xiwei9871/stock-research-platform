#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://stock.manqiaotechnology.com}"
EXPECTED_TRADE_DATE="${EXPECTED_TRADE_DATE:?EXPECTED_TRADE_DATE is required (YYYY-MM-DD)}"
EXPECTED_RELEASE_ID="${EXPECTED_RELEASE_ID:?EXPECTED_RELEASE_ID is required}"
DASHBOARD_AUTH="${DASHBOARD_AUTH:-}"
EXPECTED_REMOTE_SOURCE_ROOT="${EXPECTED_REMOTE_SOURCE_ROOT:-}"
EXPECTED_FRONTEND_BUILD_ID="${EXPECTED_FRONTEND_BUILD_ID:-$EXPECTED_RELEASE_ID}"
EXPECTED_STRATEGY_ARTIFACT_DATE="${EXPECTED_STRATEGY_ARTIFACT_DATE:-$EXPECTED_TRADE_DATE}"
EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT="${EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT:-${EXPECTED_REMOTE_SOURCE_ROOT:+$EXPECTED_REMOTE_SOURCE_ROOT/src/stock_research}}"
EXPECTED_API_BASE_IMAGE="${EXPECTED_API_BASE_IMAGE:-python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7}"
EXPECTED_FRONTEND_BASE_IMAGE="${EXPECTED_FRONTEND_BASE_IMAGE:-nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10}"
RELEASE_CHECK_TIMEOUT_SECONDS="${RELEASE_CHECK_TIMEOUT_SECONDS:-120}"
RELEASE_CHECK_RETRY_SECONDS="${RELEASE_CHECK_RETRY_SECONDS:-3}"
DATE_VALIDATION_PYTHON="${STOCK_RESEARCH_PYTHON:-python3}"

valid_iso_date() {
  "$DATE_VALIDATION_PYTHON" -c '
from datetime import date
import sys

value = sys.argv[1]
try:
    parsed = date.fromisoformat(value)
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if parsed.isoformat() == value else 1)
' "$1" >/dev/null 2>&1
}

if [[ ! "$EXPECTED_TRADE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Invalid EXPECTED_TRADE_DATE: expected YYYY-MM-DD" >&2
  exit 2
fi
if ! valid_iso_date "$EXPECTED_TRADE_DATE"; then
  echo "Invalid EXPECTED_TRADE_DATE: expected a real YYYY-MM-DD calendar date" >&2
  exit 2
fi
if [[ ! "$EXPECTED_STRATEGY_ARTIFACT_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Invalid EXPECTED_STRATEGY_ARTIFACT_DATE: expected YYYY-MM-DD" >&2
  exit 2
fi
if ! valid_iso_date "$EXPECTED_STRATEGY_ARTIFACT_DATE"; then
  echo "Invalid EXPECTED_STRATEGY_ARTIFACT_DATE: expected a real YYYY-MM-DD calendar date" >&2
  exit 2
fi
if [[ "$EXPECTED_STRATEGY_ARTIFACT_DATE" != "$EXPECTED_TRADE_DATE" ]]; then
  echo "EXPECTED_STRATEGY_ARTIFACT_DATE must equal EXPECTED_TRADE_DATE" >&2
  exit 2
fi
if [[ ! "$RELEASE_CHECK_TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] || (( RELEASE_CHECK_TIMEOUT_SECONDS < 1 || RELEASE_CHECK_TIMEOUT_SECONDS > 120 )); then
  echo "Invalid RELEASE_CHECK_TIMEOUT_SECONDS: expected 1..120" >&2
  exit 2
fi
if [[ ! "$RELEASE_CHECK_RETRY_SECONDS" =~ ^[0-9]+$ ]] || (( RELEASE_CHECK_RETRY_SECONDS < 1 )); then
  echo "Invalid RELEASE_CHECK_RETRY_SECONDS: expected a positive integer" >&2
  exit 2
fi

curl_auth=()
if [[ -n "$DASHBOARD_AUTH" ]]; then
  curl_auth=(-u "$DASHBOARD_AUTH")
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
deadline=$((SECONDS + RELEASE_CHECK_TIMEOUT_SECONDS))

fetch_json() {
  local url="$1"
  local output="$2"
  local remaining
  local status

  remaining=$((deadline - SECONDS))
  if (( remaining < 1 )); then
    return 1
  fi
  if (( remaining > 15 )); then
    remaining=15
  fi
  if (( ${#curl_auth[@]} )); then
    status="$(curl -sS --connect-timeout 5 --max-time "$remaining" "${curl_auth[@]}" -o "$output" -w '%{http_code}' "$url" || true)"
  else
    status="$(curl -sS --connect-timeout 5 --max-time "$remaining" -o "$output" -w '%{http_code}' "$url" || true)"
  fi
  [[ "$status" == "200" ]] && jq -e . "$output" >/dev/null 2>&1
}

readiness_dates_are_calendar_valid() {
  "$DATE_VALIDATION_PYTHON" -c '
from datetime import date
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
values = [
    payload.get("latest_market_date"),
    (payload.get("runtime_provenance") or {}).get("strategy_artifact_date"),
]
display = payload.get("display_trade_date")
if display not in (None, ""):
    values.append(display)
for value in values:
    if not isinstance(value, str):
        raise SystemExit(1)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise SystemExit(1)
    if parsed.isoformat() != value:
        raise SystemExit(1)
' "$1" >/dev/null 2>&1
}

readiness_matches_release() {
  readiness_dates_are_calendar_valid "$1" || return 1
  jq -e \
    --arg release "$EXPECTED_RELEASE_ID" \
    --arg source "$EXPECTED_REMOTE_SOURCE_ROOT" \
    --arg frontend_build "$EXPECTED_FRONTEND_BUILD_ID" \
    --arg strategy_date "$EXPECTED_STRATEGY_ARTIFACT_DATE" \
    --arg package_root "$EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT" \
    '
      (.latest_market_date | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
      and (.runtime_provenance.strategy_artifact_date | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
      and (.latest_market_date >= $strategy_date)
      and .runtime_provenance.strategy_artifact_date == $strategy_date
      and (
        ((.display_trade_date // "") == "")
        or (
          (.display_trade_date | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
          and .display_trade_date >= $strategy_date
        )
      )
      and .runtime_provenance.release_id == $release
      and .runtime_provenance.frontend_build_id == $frontend_build
      and .runtime_provenance.source_root != ""
      and ($source == "" or .runtime_provenance.source_root == $source)
      and (
        ($package_root == "" and .runtime_provenance.python_package_root == (.runtime_provenance.source_root + "/src/stock_research"))
        or .runtime_provenance.python_package_root == $package_root
      )
    ' "$1" >/dev/null
}

frontend_matches_release() {
  jq -e \
    --arg release "$EXPECTED_RELEASE_ID" \
    --arg api_base_image "$EXPECTED_API_BASE_IMAGE" \
    --arg frontend_base_image "$EXPECTED_FRONTEND_BASE_IMAGE" '
    .release_id == $release
    and .api_base_image == $api_base_image
    and .frontend_base_image == $frontend_base_image
  ' "$1" >/dev/null
}

queue_matches_release() {
  jq -e \
    --arg expected "$EXPECTED_TRADE_DATE" \
    '
      .requested_trade_date == $expected
      and .trade_date == $expected
      and (.groups | length) == 3
      and ([.groups[].strategy_id] | sort) == (["lhb_shortline", "mid_trend", "tech_bottleneck"] | sort)
      and all(.groups[];
        .count == 5
        and .data_trade_date == $expected
        and .freshness_status == "current"
      )
    ' "$1" >/dev/null
}

echo "Waiting for dashboard release ${EXPECTED_RELEASE_ID} at ${BASE_URL%/}"
while (( SECONDS <= deadline )); do
  if fetch_json "${BASE_URL%/}/api/platform/readiness" "$tmp_dir/readiness.json" \
    && readiness_matches_release "$tmp_dir/readiness.json" \
    && fetch_json "${BASE_URL%/}/release.json" "$tmp_dir/frontend-release.json" \
    && frontend_matches_release "$tmp_dir/frontend-release.json" \
    && fetch_json "${BASE_URL%/}/api/review-queue?trade_date=${EXPECTED_TRADE_DATE}&limit=10&lookback_days=90" "$tmp_dir/review-queue.json" \
    && queue_matches_release "$tmp_dir/review-queue.json"; then
    echo "Dashboard release check passed for ${EXPECTED_TRADE_DATE} (${EXPECTED_RELEASE_ID})."
    exit 0
  fi

  if (( SECONDS + RELEASE_CHECK_RETRY_SECONDS > deadline )); then
    break
  fi
  sleep "$RELEASE_CHECK_RETRY_SECONDS"
done

echo "Dashboard release check failed after ${RELEASE_CHECK_TIMEOUT_SECONDS}s." >&2
echo "Expected date ${EXPECTED_TRADE_DATE} and release ${EXPECTED_RELEASE_ID}." >&2
if [[ -s "$tmp_dir/readiness.json" ]]; then
  jq '{latest_market_date, display_trade_date, runtime_provenance}' "$tmp_dir/readiness.json" >&2 || true
fi
if [[ -s "$tmp_dir/frontend-release.json" ]]; then
  jq '{release_id}' "$tmp_dir/frontend-release.json" >&2 || true
fi
if [[ -s "$tmp_dir/review-queue.json" ]]; then
  jq '{requested_trade_date, trade_date, groups: [.groups[]? | {strategy_id, count, data_trade_date, freshness_status}]}' "$tmp_dir/review-queue.json" >&2 || true
fi
exit 1
