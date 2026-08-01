#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://stock.manqiaotechnology.com}"
EXPECTED_TRADE_DATE="${EXPECTED_TRADE_DATE:?EXPECTED_TRADE_DATE is required (YYYY-MM-DD)}"
EXPECTED_RELEASE_ID="${EXPECTED_RELEASE_ID:?EXPECTED_RELEASE_ID is required}"
DASHBOARD_AUTH="${DASHBOARD_AUTH:-}"
DASHBOARD_LOGIN_USERNAME="${DASHBOARD_LOGIN_USERNAME:-}"
DASHBOARD_LOGIN_PASSWORD="${DASHBOARD_LOGIN_PASSWORD:-}"
EXPECTED_REMOTE_SOURCE_ROOT="${EXPECTED_REMOTE_SOURCE_ROOT:-}"
EXPECTED_FRONTEND_BUILD_ID="${EXPECTED_FRONTEND_BUILD_ID:-$EXPECTED_RELEASE_ID}"
EXPECTED_STRATEGY_ARTIFACT_DATE="${EXPECTED_STRATEGY_ARTIFACT_DATE:-$EXPECTED_TRADE_DATE}"
EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT="${EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT:-${EXPECTED_REMOTE_SOURCE_ROOT:+$EXPECTED_REMOTE_SOURCE_ROOT/src/stock_research}}"
EXPECTED_API_BASE_IMAGE="${EXPECTED_API_BASE_IMAGE:-python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7}"
EXPECTED_FRONTEND_BASE_IMAGE="${EXPECTED_FRONTEND_BASE_IMAGE:-nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10}"
EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION="${EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION:-5}"
THEME_RESEARCH_REPORT_HEALTH_JSON="${THEME_RESEARCH_REPORT_HEALTH_JSON:?THEME_RESEARCH_REPORT_HEALTH_JSON is required}"
EXPECTED_THEME_RESEARCH_REPORT_ROOT="${EXPECTED_THEME_RESEARCH_REPORT_ROOT:-/app/reports/theme-research}"
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

umask 077
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
curl_config="$tmp_dir/curl.conf"
cookie_jar="$tmp_dir/cookies.txt"
login_payload="$tmp_dir/login.json"
: > "$curl_config"
: > "$cookie_jar"
: > "$login_payload"
chmod 600 "$curl_config" "$cookie_jar" "$login_payload"
if [[ -n "$DASHBOARD_AUTH" ]]; then
  curl_auth_escaped="${DASHBOARD_AUTH//\\/\\\\}"
  curl_auth_escaped="${curl_auth_escaped//\"/\\\"}"
  curl_auth_escaped="${curl_auth_escaped//$'\n'/\\n}"
  curl_auth_escaped="${curl_auth_escaped//$'\r'/\\r}"
  printf 'user = "%s"\n' "$curl_auth_escaped" > "$curl_config"
fi
if [[ -n "$DASHBOARD_LOGIN_USERNAME" || -n "$DASHBOARD_LOGIN_PASSWORD" ]]; then
  if [[ -z "$DASHBOARD_LOGIN_USERNAME" || -z "$DASHBOARD_LOGIN_PASSWORD" ]]; then
    echo "DASHBOARD_LOGIN_USERNAME and DASHBOARD_LOGIN_PASSWORD must be set together" >&2
    exit 2
  fi
  "$DATE_VALIDATION_PYTHON" - "$login_payload" <<'PY'
import json
import os
import sys

with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(
        {
            "username": os.environ["DASHBOARD_LOGIN_USERNAME"],
            "password": os.environ["DASHBOARD_LOGIN_PASSWORD"],
        },
        handle,
    )
PY
fi
deadline=$((SECONDS + RELEASE_CHECK_TIMEOUT_SECONDS))

login_session() {
  local remaining
  local status

  if [[ -z "$DASHBOARD_LOGIN_USERNAME" ]]; then
    return 0
  fi
  while (( SECONDS <= deadline )); do
    remaining=$((deadline - SECONDS))
    if (( remaining < 1 )); then
      break
    fi
    if (( remaining > 15 )); then
      remaining=15
    fi
    status="$(curl --config "$curl_config" -sS --connect-timeout 5 --max-time "$remaining" \
      -X POST -H 'Content-Type: application/json' --data-binary "@$login_payload" \
      --cookie-jar "$cookie_jar" -o "$tmp_dir/login-response.json" -w '%{http_code}' \
      "${BASE_URL%/}/api/auth/login" || true)"
    if [[ "$status" == "200" ]] \
      && jq -e '.user | type == "object"' "$tmp_dir/login-response.json" >/dev/null 2>&1; then
      return 0
    fi
    if (( SECONDS + RELEASE_CHECK_RETRY_SECONDS > deadline )); then
      break
    fi
    sleep "$RELEASE_CHECK_RETRY_SECONDS"
  done
  return 1
}

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
  if [[ -n "$DASHBOARD_LOGIN_USERNAME" ]]; then
    status="$(curl --config "$curl_config" --cookie "$cookie_jar" -sS --connect-timeout 5 --max-time "$remaining" -o "$output" -w '%{http_code}' "$url" || true)"
  else
    status="$(curl --config "$curl_config" -sS --connect-timeout 5 --max-time "$remaining" -o "$output" -w '%{http_code}' "$url" || true)"
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

theme_research_matches_release() {
  jq -e '
    (.total | type == "number" and . >= 25)
    and (.items | type == "array")
    and ((.items | length) == .total)
    and ([.items[].theme_id] | length == (unique | length))
    and any(.items[]; .theme_id == "ai_compute_infrastructure_value_chain_v1")
  ' "$1" >/dev/null
}

report_health_matches_release() {
  jq -e \
    --arg root "$EXPECTED_THEME_RESEARCH_REPORT_ROOT" \
    --arg schema_version "$EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION" \
    '
      .status == "ok"
      and .root.path == $root
      and .root.exists == true
      and .root.readable == true
      and .root.readonly == true
      and .schema.status == "current"
      and .schema.schema_version == $schema_version
      and .service_permissions.runtime.status == "ok"
      and .service_permissions.indexer.status == "ok"
      and .service_permissions.reviewer.status == "ok"
      and .service_identity.status == "ok"
      and (.service_identity.server_version_nums as $versions
        | ($versions | type == "object")
        and (($versions | keys | sort) == ["indexer", "reviewer", "runtime"])
        and ([$versions.runtime, $versions.indexer, $versions.reviewer]
          | all(type == "number" and . > 0))
      )
      and (.service_identity.login_attributes as $attributes
        | ($attributes | type == "object")
        and (($attributes | keys | sort) == ["indexer", "reviewer", "runtime"])
        and ([$attributes.runtime, $attributes.indexer, $attributes.reviewer]
          | all(
            type == "object"
            and .rolcanlogin == true
            and .rolsuper == false
            and .rolcreatedb == false
            and .rolcreaterole == false
            and .rolreplication == false
            and .rolbypassrls == false
          ))
      )
      and .scheduler_index_diagnostics.status == "ok"
      and .scheduler_index_diagnostics.invalid == 0
      and .scheduler_index_diagnostics.errors == []
    ' "$1" >/dev/null
}

if ! login_session; then
  echo "Dashboard session login failed at ${BASE_URL%/}/api/auth/login" >&2
  exit 1
fi

echo "Waiting for dashboard release ${EXPECTED_RELEASE_ID} at ${BASE_URL%/}"
while (( SECONDS <= deadline )); do
  if fetch_json "${BASE_URL%/}/api/platform/readiness" "$tmp_dir/readiness.json" \
    && readiness_matches_release "$tmp_dir/readiness.json" \
    && fetch_json "${BASE_URL%/}/api/research/theme-decomposition/themes" "$tmp_dir/theme-research.json" \
    && theme_research_matches_release "$tmp_dir/theme-research.json" \
    && fetch_json "${BASE_URL%/}/release.json" "$tmp_dir/frontend-release.json" \
    && frontend_matches_release "$tmp_dir/frontend-release.json" \
    && fetch_json "${BASE_URL%/}/api/review-queue?trade_date=${EXPECTED_TRADE_DATE}&limit=10&lookback_days=90" "$tmp_dir/review-queue.json" \
    && queue_matches_release "$tmp_dir/review-queue.json" \
    && report_health_matches_release "$THEME_RESEARCH_REPORT_HEALTH_JSON"; then
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
if [[ -s "$tmp_dir/theme-research.json" ]]; then
  jq '{total, required_theme_present: any(.items[]?; .theme_id == "ai_compute_infrastructure_value_chain_v1")}' "$tmp_dir/theme-research.json" >&2 || true
fi
if [[ -s "$tmp_dir/review-queue.json" ]]; then
  jq '{requested_trade_date, trade_date, groups: [.groups[]? | {strategy_id, count, data_trade_date, freshness_status}]}' "$tmp_dir/review-queue.json" >&2 || true
fi
if [[ -s "$THEME_RESEARCH_REPORT_HEALTH_JSON" ]]; then
  jq '{status, root, schema, service_permissions, service_identity, scheduler_index_diagnostics}' "$THEME_RESEARCH_REPORT_HEALTH_JSON" >&2 || true
fi
exit 1
