#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${DASHBOARD_DAILY_SYNC_ENV:-/Users/xiwei/.stock_research_dashboard_sync.env}"
trade_date="${1:-}"

if [[ -f "$env_file" ]]; then
  # shellcheck disable=SC1090
  source "$env_file"
fi

if [[ $# -ne 1 ]] || [[ ! "$trade_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Usage: ./deploy/publish_prod.sh YYYY-MM-DD" >&2
  exit 1
fi

BASE_URL="${BASE_URL:-https://stock.manqiaotechnology.com}"
START_DATE="${START_DATE:-2026-01-01}"
END_DATE="${END_DATE:-$trade_date}"
LATEST_STRATEGY_DAILY_EOD="strategy_daily_eod/${trade_date}"

if [[ -z "${DASHBOARD_AUTH:-}" && "${SKIP_RELEASE_CHECK:-0}" != "1" ]]; then
  echo "DASHBOARD_AUTH is required for release verification unless SKIP_RELEASE_CHECK=1" >&2
  exit 1
fi

LATEST_STRATEGY_DAILY_EOD="$LATEST_STRATEGY_DAILY_EOD" \
  "${repo_root}/deploy/sync_dashboard_systemd.sh"

if [[ "${SKIP_RELEASE_CHECK:-0}" == "1" ]]; then
  echo "Skipping release check because SKIP_RELEASE_CHECK=1"
  exit 0
fi

BASE_URL="$BASE_URL" \
DASHBOARD_AUTH="$DASHBOARD_AUTH" \
TRADE_DATE="$trade_date" \
START_DATE="$START_DATE" \
END_DATE="$END_DATE" \
  "${repo_root}/deploy/check_dashboard_release.sh"
