#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
STATE_ROOT="${FOUNDER_OS_MODEL_RECOVERY_STATE_ROOT:-/Users/xiwei/.openclaw/state/founder-os-model-recovery}"
LOCK_DIR="$STATE_ROOT/python_lockfile"
LOG_FILE="${FOUNDER_OS_MODEL_RECOVERY_LOG:-/Users/xiwei/.openclaw/logs/founder-os-model-recovery.log}"
COMMAND="${1:-run}"
if [[ $# -gt 0 ]]; then
  shift
fi

[[ "$COMMAND" == "run" || "$COMMAND" == "audit" || "$COMMAND" == "spawn" ]] || {
  echo "usage: $0 [run|audit|spawn]" >&2
  exit 2
}

if [[ "$COMMAND" == "spawn" ]]; then
  nohup "$0" run "$@" </dev/null >/dev/null 2>&1 &
  exit 0
fi

mkdir -p "$STATE_ROOT" "$(dirname "$LOG_FILE")"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "model_recovery|locked|command=$COMMAND" >>"$LOG_FILE"
  exit 0
fi

cleanup_lock() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup_lock EXIT INT TERM

cd "$ROOT"
PYTHONPATH="$ROOT/src" "$PYTHON" \
  -m stock_research.founder_os_model_recovery_cli "$COMMAND" "$@" \
  >>"$LOG_FILE" 2>&1
