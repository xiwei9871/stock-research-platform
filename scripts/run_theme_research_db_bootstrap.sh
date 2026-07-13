#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
ADMIN_USERNAME="${THEME_RESEARCH_ADMIN_USERNAME:?set THEME_RESEARCH_ADMIN_USERNAME}"
EXPECTED_GENERATION="${THEME_RESEARCH_EXPECTED_GENERATION:-0}"
IDEMPOTENCY_KEY="${THEME_RESEARCH_IDEMPOTENCY_KEY:-theme-research-bootstrap-v1}"
MIGRATION_SERVICE="${THEME_RESEARCH_MIGRATION_SERVICE:-stock_research}"
RUNTIME_SERVICE="${THEME_RESEARCH_RUNTIME_SERVICE:-theme_research_runtime}"
AUTH_SERVICE="${THEME_RESEARCH_AUTH_SERVICE:-stock_research}"

COMMON_ARGS=(
  --migration-service "$MIGRATION_SERVICE"
  --runtime-service "$RUNTIME_SERVICE"
  --auth-service "$AUTH_SERVICE"
)

"$PYTHON_BIN" -m stock_research.theme_research_db_schema \
  "${COMMON_ARGS[@]}" \
  apply-schema \
  --admin-username "$ADMIN_USERNAME"

"$PYTHON_BIN" -m stock_research.theme_research_db_schema \
  "${COMMON_ARGS[@]}" \
  schema-status

"$PYTHON_BIN" -m stock_research.theme_research_db_schema \
  "${COMMON_ARGS[@]}" \
  import --dry-run

if [[ "${THEME_RESEARCH_DB_EXECUTE:-0}" != "1" ]]; then
  printf '%s\n' 'theme_research_db_execute_disabled'
  exit 0
fi

"$PYTHON_BIN" -m stock_research.theme_research_db_schema \
  "${COMMON_ARGS[@]}" \
  import --execute \
  --admin-username "$ADMIN_USERNAME" \
  --expected-generation "$EXPECTED_GENERATION" \
  --idempotency-key "$IDEMPOTENCY_KEY"

"$PYTHON_BIN" -m stock_research.theme_research_db_schema \
  "${COMMON_ARGS[@]}" \
  compare
