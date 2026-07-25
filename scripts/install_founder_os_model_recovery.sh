#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
BIN_DIR="/Users/xiwei/.openclaw/bin"
SHIM="$BIN_DIR/founder-os-model-recovery"

case "${1:-}" in
  --dry-run)
    exec env PYTHONPATH="$ROOT/src" "$PYTHON" \
      -m stock_research.founder_os_model_recovery_config dry-run
    ;;
  --apply)
    mkdir -p "$BIN_DIR"
    ln -sfn "$ROOT/scripts/run_founder_os_model_recovery_cron.sh" "$SHIM"
    exec env PYTHONPATH="$ROOT/src" "$PYTHON" \
      -m stock_research.founder_os_model_recovery_config apply
    ;;
  --rollback)
    [[ $# -eq 2 ]] || {
      echo "usage: $0 --rollback BACKUP_JSON" >&2
      exit 2
    }
    exec env PYTHONPATH="$ROOT/src" "$PYTHON" \
      -m stock_research.founder_os_model_recovery_config rollback --backup "$2"
    ;;
  *)
    echo "usage: $0 --dry-run|--apply|--rollback BACKUP_JSON" >&2
    exit 2
    ;;
esac
