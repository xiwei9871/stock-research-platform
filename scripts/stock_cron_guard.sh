#!/usr/bin/env bash
set -euo pipefail

clear_stock_proxy_env() {
  unset HTTP_PROXY HTTPS_PROXY ALL_PROXY http_proxy https_proxy all_proxy
  export NO_PROXY="*"
  export no_proxy="*"
}

stock_cron_guard_or_exit() {
  local python_bin="$1"
  local trade_date="${2:-}"
  local service="${3:-}"
  local guard_args=(-m stock_research.stock_cron_guard)

  if [[ -n "$trade_date" ]]; then
    guard_args+=(--date "$trade_date")
  fi
  if [[ -n "$service" ]]; then
    guard_args+=(--service "$service")
  fi

  set +e
  "$python_bin" "${guard_args[@]}"
  local guard_rc=$?
  set -e

  if [[ "$guard_rc" -eq 2 ]]; then
    exit 0
  fi
  if [[ "$guard_rc" -ne 0 ]]; then
    exit "$guard_rc"
  fi
}
