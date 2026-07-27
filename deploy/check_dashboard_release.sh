#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://stock.manqiaotechnology.com}"
EXPECTED_TRADE_DATE="${EXPECTED_TRADE_DATE:?EXPECTED_TRADE_DATE is required (YYYY-MM-DD)}"
EXPECTED_RELEASE_ID="${EXPECTED_RELEASE_ID:?EXPECTED_RELEASE_ID is required}"
DASHBOARD_AUTH="${DASHBOARD_AUTH:-}"
EXPECTED_REMOTE_SOURCE_ROOT="${EXPECTED_REMOTE_SOURCE_ROOT:-}"
RELEASE_CHECK_TIMEOUT_SECONDS="${RELEASE_CHECK_TIMEOUT_SECONDS:-120}"
RELEASE_CHECK_RETRY_SECONDS="${RELEASE_CHECK_RETRY_SECONDS:-3}"

if [[ ! "$EXPECTED_TRADE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Invalid EXPECTED_TRADE_DATE: expected YYYY-MM-DD" >&2
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

readiness_matches_release() {
  jq -e \
    --arg expected "$EXPECTED_TRADE_DATE" \
    --arg release "$EXPECTED_RELEASE_ID" \
    --arg source "$EXPECTED_REMOTE_SOURCE_ROOT" \
    '
      .latest_market_date == $expected
      and .runtime_provenance.release_id == $release
      and .runtime_provenance.frontend_build_id == $release
      and .runtime_provenance.strategy_artifact_date == $expected
      and .runtime_provenance.source_root != ""
      and ($source == "" or .runtime_provenance.source_root == $source)
      and .runtime_provenance.python_package_root == (.runtime_provenance.source_root + "/src/stock_research")
    ' "$1" >/dev/null
}

frontend_matches_release() {
  jq -e --arg release "$EXPECTED_RELEASE_ID" '.release_id == $release' "$1" >/dev/null
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
  jq '{latest_market_date, runtime_provenance}' "$tmp_dir/readiness.json" >&2 || true
fi
if [[ -s "$tmp_dir/frontend-release.json" ]]; then
  jq '{release_id}' "$tmp_dir/frontend-release.json" >&2 || true
fi
if [[ -s "$tmp_dir/review-queue.json" ]]; then
  jq '{requested_trade_date, trade_date, groups: [.groups[]? | {strategy_id, count, data_trade_date, freshness_status}]}' "$tmp_dir/review-queue.json" >&2 || true
fi
exit 1
