#!/usr/bin/env bash
set -euo pipefail

release_root_override="${STOCK_RESEARCH_RELEASE_ROOT:-}"
trade_date_override="${EXPECTED_TRADE_DATE:-}"
python_override="${STOCK_RESEARCH_PYTHON:-}"
remote_user_override="${REMOTE_USER:-}"
remote_host_override="${REMOTE_HOST:-}"
remote_dir_override="${REMOTE_DIR:-}"
ssh_opts_override="${SSH_OPTS:-}"
ssh_config_override="${STOCK_RESEARCH_SSH_CONFIG:-}"
base_url_override="${BASE_URL:-}"
dashboard_auth_override="${DASHBOARD_AUTH:-}"
dashboard_login_username_override="${DASHBOARD_LOGIN_USERNAME:-}"
dashboard_login_password_override="${DASHBOARD_LOGIN_PASSWORD:-}"
container_root_override="${REMOTE_CONTAINER_RELEASE_ROOT:-}"
strategy_output_root_override="${STRATEGY_OUTPUT_ROOT:-}"
local_readiness_url_override="${LOCAL_READINESS_URL:-}"
remote_env_file_override="${DASHBOARD_REMOTE_ENV_FILE:-}"
remote_pgservice_file_override="${DASHBOARD_PGSERVICE_FILE:-}"
compose_project_override="${STOCK_RESEARCH_COMPOSE_PROJECT:-}"
api_bind_port_override="${DASHBOARD_API_BIND_PORT:-}"
frontend_bind_port_override="${DASHBOARD_FRONTEND_BIND_PORT:-}"
theme_research_report_host_root_override="${THEME_RESEARCH_REPORT_HOST_ROOT:-}"
theme_research_migration_service_override="${THEME_RESEARCH_MIGRATION_SERVICE:-}"
theme_research_runtime_service_override_set="${THEME_RESEARCH_RUNTIME_SERVICE+x}"
theme_research_runtime_service_override="${THEME_RESEARCH_RUNTIME_SERVICE-}"
theme_research_report_index_service_override_set="${THEME_RESEARCH_REPORT_INDEX_SERVICE+x}"
theme_research_report_index_service_override="${THEME_RESEARCH_REPORT_INDEX_SERVICE-}"
theme_research_report_review_service_override_set="${THEME_RESEARCH_REPORT_REVIEW_SERVICE+x}"
theme_research_report_review_service_override="${THEME_RESEARCH_REPORT_REVIEW_SERVICE-}"

env_file="${DASHBOARD_SYNC_ENV:-/Users/xiwei/.stock_research_dashboard_sync.env}"
if [[ -f "$env_file" ]]; then
  # shellcheck disable=SC1090
  source "$env_file"
fi

ROOT="${release_root_override:-${STOCK_RESEARCH_RELEASE_ROOT:-/Users/xiwei/stock_research}}"
EXPECTED_TRADE_DATE="${trade_date_override:-${EXPECTED_TRADE_DATE:-}}"
REMOTE_USER="${remote_user_override:-${REMOTE_USER:-jqz}}"
REMOTE_HOST="${remote_host_override:-${REMOTE_HOST:-192.168.3.185}}"
REMOTE_DIR="${remote_dir_override:-${REMOTE_DIR:-/home/${REMOTE_USER}/code/stock-research-platform-main}}"
SSH_OPTS="${ssh_opts_override:-${SSH_OPTS:-}}"
STOCK_RESEARCH_SSH_CONFIG="${ssh_config_override:-${STOCK_RESEARCH_SSH_CONFIG:-}}"
BASE_URL="${base_url_override:-${BASE_URL:-https://stock.manqiaotechnology.com}}"
DASHBOARD_AUTH="${dashboard_auth_override:-${DASHBOARD_AUTH:-}}"
DASHBOARD_LOGIN_USERNAME="${dashboard_login_username_override:-${DASHBOARD_LOGIN_USERNAME:-}}"
DASHBOARD_LOGIN_PASSWORD="${dashboard_login_password_override:-${DASHBOARD_LOGIN_PASSWORD:-}}"
REMOTE_CONTAINER_RELEASE_ROOT="${container_root_override:-${REMOTE_CONTAINER_RELEASE_ROOT:-/app}}"
STRATEGY_OUTPUT_ROOT="${strategy_output_root_override:-${STRATEGY_OUTPUT_ROOT:-$ROOT/outputs/research}}"
LOCAL_READINESS_URL="${local_readiness_url_override:-${LOCAL_READINESS_URL:-http://127.0.0.1:8765/api/platform/readiness}}"
DASHBOARD_REMOTE_ENV_FILE="${remote_env_file_override:-${DASHBOARD_REMOTE_ENV_FILE:-.env.dashboard}}"
DASHBOARD_PGSERVICE_FILE="${remote_pgservice_file_override:-${DASHBOARD_PGSERVICE_FILE:-.pg_service.conf}}"
STOCK_RESEARCH_COMPOSE_PROJECT="${compose_project_override:-${STOCK_RESEARCH_COMPOSE_PROJECT:-stock_research_dashboard}}"
DASHBOARD_API_BIND_PORT="${api_bind_port_override:-${DASHBOARD_API_BIND_PORT:-8765}}"
DASHBOARD_FRONTEND_BIND_PORT="${frontend_bind_port_override:-${DASHBOARD_FRONTEND_BIND_PORT:-5174}}"
THEME_RESEARCH_REPORT_HOST_ROOT="${theme_research_report_host_root_override:-${THEME_RESEARCH_REPORT_HOST_ROOT:-}}"
THEME_RESEARCH_MIGRATION_SERVICE="${theme_research_migration_service_override:-${THEME_RESEARCH_MIGRATION_SERVICE:-stock_research}}"
if [[ -n "$theme_research_runtime_service_override_set" ]]; then
  THEME_RESEARCH_RUNTIME_SERVICE="$theme_research_runtime_service_override"
else
  THEME_RESEARCH_RUNTIME_SERVICE="${THEME_RESEARCH_RUNTIME_SERVICE-theme_research_runtime}"
fi
if [[ -n "$theme_research_report_index_service_override_set" ]]; then
  THEME_RESEARCH_REPORT_INDEX_SERVICE="$theme_research_report_index_service_override"
else
  THEME_RESEARCH_REPORT_INDEX_SERVICE="${THEME_RESEARCH_REPORT_INDEX_SERVICE-theme_research_report_indexer}"
fi
if [[ -n "$theme_research_report_review_service_override_set" ]]; then
  THEME_RESEARCH_REPORT_REVIEW_SERVICE="$theme_research_report_review_service_override"
else
  THEME_RESEARCH_REPORT_REVIEW_SERVICE="${THEME_RESEARCH_REPORT_REVIEW_SERVICE-theme_research_report_reviewer}"
fi
EXPECTED_API_BASE_IMAGE="python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"
EXPECTED_FRONTEND_BASE_IMAGE="nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION="5"

case "$ROOT" in
  */.worktrees/*|*/.worktrees)
    echo "Refusing disposable worktree release root: $ROOT" >&2
    exit 2
    ;;
esac

if [[ ! -d "$ROOT" ]]; then
  echo "Release root does not exist: $ROOT" >&2
  exit 2
fi
ROOT="$(cd "$ROOT" && pwd -P)"
case "$ROOT" in
  */.worktrees/*|*/.worktrees)
    echo "Refusing disposable worktree release root: $ROOT" >&2
    exit 2
    ;;
esac

if [[ ! "$REMOTE_USER" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
  || [[ ! "$REMOTE_HOST" =~ ^[A-Za-z0-9]([A-Za-z0-9.:-]*[A-Za-z0-9])?$ ]] \
  || [[ "$REMOTE_HOST" == *".."* ]] \
  || [[ "$REMOTE_HOST" == *":::"* ]]; then
  echo "REMOTE_USER or REMOTE_HOST contains unsupported characters" >&2
  exit 2
fi
if [[ ! "$STOCK_RESEARCH_COMPOSE_PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  echo "Invalid STOCK_RESEARCH_COMPOSE_PROJECT: $STOCK_RESEARCH_COMPOSE_PROJECT" >&2
  exit 2
fi
for port in "$DASHBOARD_API_BIND_PORT" "$DASHBOARD_FRONTEND_BIND_PORT"; do
  if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    echo "Invalid dashboard bind port: $port" >&2
    exit 2
  fi
done
if [[ ! "$REMOTE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || [[ ! "$REMOTE_CONTAINER_RELEASE_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "REMOTE_DIR or REMOTE_CONTAINER_RELEASE_ROOT must be a safe absolute path" >&2
  exit 2
fi
if [[ "$REMOTE_CONTAINER_RELEASE_ROOT" != "/app" ]]; then
  echo "REMOTE_CONTAINER_RELEASE_ROOT must be /app for the canonical release compose" >&2
  exit 2
fi
if [[ ! "$DASHBOARD_REMOTE_ENV_FILE" =~ ^[A-Za-z0-9._/-]+$ ]] || [[ ! "$DASHBOARD_PGSERVICE_FILE" =~ ^[A-Za-z0-9._/-]+$ ]]; then
  echo "DASHBOARD_REMOTE_ENV_FILE or DASHBOARD_PGSERVICE_FILE contains unsupported characters" >&2
  exit 2
fi
if ! bash "$ROOT/deploy/check_dashboard_report_mount.sh" --validate-path "$THEME_RESEARCH_REPORT_HOST_ROOT" >/dev/null; then
  echo "THEME_RESEARCH_REPORT_HOST_ROOT must be a safe dedicated path" >&2
  exit 2
fi
if [[ -z "$THEME_RESEARCH_RUNTIME_SERVICE" ]] \
  || [[ -z "$THEME_RESEARCH_REPORT_INDEX_SERVICE" ]] \
  || [[ -z "$THEME_RESEARCH_REPORT_REVIEW_SERVICE" ]] \
  || [[ "$THEME_RESEARCH_RUNTIME_SERVICE" == "$THEME_RESEARCH_REPORT_INDEX_SERVICE" ]] \
  || [[ "$THEME_RESEARCH_RUNTIME_SERVICE" == "$THEME_RESEARCH_REPORT_REVIEW_SERVICE" ]] \
  || [[ "$THEME_RESEARCH_REPORT_INDEX_SERVICE" == "$THEME_RESEARCH_REPORT_REVIEW_SERVICE" ]]; then
  echo "Theme Research runtime, index, and review services must be distinct non-empty values" >&2
  exit 2
fi
if [[ ! "$THEME_RESEARCH_MIGRATION_SERVICE" =~ ^[A-Za-z0-9._-]+$ ]] \
  || [[ ! "$THEME_RESEARCH_RUNTIME_SERVICE" =~ ^[A-Za-z0-9._-]+$ ]] \
  || [[ ! "$THEME_RESEARCH_REPORT_INDEX_SERVICE" =~ ^[A-Za-z0-9._-]+$ ]] \
  || [[ ! "$THEME_RESEARCH_REPORT_REVIEW_SERVICE" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "Theme Research database service names contain unsupported characters" >&2
  exit 2
fi
if [[ -n "$python_override" ]]; then
  STOCK_RESEARCH_PYTHON="$python_override"
elif [[ -n "${STOCK_RESEARCH_PYTHON:-}" ]]; then
  STOCK_RESEARCH_PYTHON="$STOCK_RESEARCH_PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  STOCK_RESEARCH_PYTHON="$ROOT/.venv/bin/python"
else
  STOCK_RESEARCH_PYTHON="/Users/xiwei/stock_research/.venv/bin/python"
fi
if [[ ! -x "$STOCK_RESEARCH_PYTHON" ]]; then
  echo "Stock research Python is missing: $STOCK_RESEARCH_PYTHON" >&2
  exit 2
fi

valid_iso_date() {
  "$STOCK_RESEARCH_PYTHON" -c '
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

release_id="$(git -C "$ROOT" rev-parse HEAD)"
dirty="$(git -C "$ROOT" status --porcelain --untracked-files=all)"
if [[ -n "$dirty" ]]; then
  echo "Refusing dirty release root: $ROOT" >&2
  printf '%s\n' "$dirty" >&2
  exit 2
fi

package_file="$(env -u PYTHONPATH STOCK_RESEARCH_RELEASE_ROOT="$ROOT" "$STOCK_RESEARCH_PYTHON" -c 'import stock_research; print(stock_research.__file__)')"
EXPECTED_PACKAGE_ROOT="$(cd "$ROOT/src/stock_research" && pwd -P)"
case "$package_file" in
  "$ROOT"/src/stock_research/*) ;;
  *)
    echo "Python import root mismatch: $package_file" >&2
    exit 2
    ;;
esac

if [[ -z "$EXPECTED_TRADE_DATE" ]]; then
  EXPECTED_TRADE_DATE="$(
    curl -fsS --connect-timeout 3 --max-time 10 "$LOCAL_READINESS_URL" 2>/dev/null \
      | jq -er \
          --arg release "$release_id" \
          --arg source "$ROOT" \
          --arg package "$EXPECTED_PACKAGE_ROOT" \
          '
            select(
              .runtime_provenance.release_id == $release
              and .runtime_provenance.source_root == $source
              and .runtime_provenance.python_package_root == $package
            )
            | .runtime_provenance.strategy_artifact_date as $artifact
            | select($artifact | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
            | select(
                (.latest_market_date | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
                and (.display_trade_date | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
                and .latest_market_date == $artifact
                and .display_trade_date == $artifact
              )
            | $artifact
          ' \
      2>/dev/null || true
  )"
fi
if [[ -z "$EXPECTED_TRADE_DATE" ]]; then
  EXPECTED_TRADE_DATE="$(
    env \
      PYTHONPATH="$ROOT/src" \
      STOCK_RESEARCH_RELEASE_ROOT="$ROOT" \
      STOCK_RESEARCH_RELEASE_ID="$release_id" \
      "$STOCK_RESEARCH_PYTHON" -c \
      'from datetime import date; from stock_research.dashboard.readiness import build_platform_readiness; payload = build_platform_readiness(); artifact = str(payload.get("runtime_provenance", {}).get("strategy_artifact_date") or ""); market = str(payload.get("latest_market_date") or ""); display = str(payload.get("display_trade_date") or ""); valid = lambda value: date.fromisoformat(value).isoformat() == value; print(artifact if all(valid(value) for value in (artifact, market, display)) and artifact == market == display else "")' \
      2>/dev/null || true
  )"
fi
if [[ ! "$EXPECTED_TRADE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
  || ! valid_iso_date "$EXPECTED_TRADE_DATE"; then
  if [[ -n "$trade_date_override" ]]; then
    echo "Invalid EXPECTED_TRADE_DATE: expected a real YYYY-MM-DD calendar date" >&2
    exit 2
  fi
  echo "Unable to resolve a valid EXPECTED_TRADE_DATE from override, current readiness, or the current release platform loader" >&2
  exit 2
fi
echo "Resolved EXPECTED_TRADE_DATE=${EXPECTED_TRADE_DATE}"

strategy_output="${STRATEGY_OUTPUT_ROOT%/}/strategy_daily_eod/${EXPECTED_TRADE_DATE}"
if [[ ! -d "$strategy_output" ]]; then
  echo "Missing strategy release artifacts: $strategy_output" >&2
  exit 2
fi
"$STOCK_RESEARCH_PYTHON" "$ROOT/deploy/validate_strategy_release.py" \
  --output-dir "$strategy_output" \
  --trade-date "$EXPECTED_TRADE_DATE"

manifest_snapshot="$(mktemp)"
theme_research_report_health_snapshot="$(mktemp)"
cleanup_manifest_snapshot() {
  rm -f "$manifest_snapshot" "$theme_research_report_health_snapshot"
}
trap cleanup_manifest_snapshot EXIT
PYTHONPATH="$ROOT/src" "$STOCK_RESEARCH_PYTHON" -m stock_research.strategy_manifest_transfer export \
  --trade-date "$EXPECTED_TRADE_DATE" \
  --source-root "$ROOT" \
  --target-root "$REMOTE_CONTAINER_RELEASE_ROOT" > "$manifest_snapshot"

check_release_state() {
  validate_theme_research_report_mount || return 1
  capture_theme_research_report_health "$1" "$2" || return 1
  BASE_URL="$BASE_URL" \
  DASHBOARD_AUTH="$DASHBOARD_AUTH" \
  DASHBOARD_LOGIN_USERNAME="$DASHBOARD_LOGIN_USERNAME" \
  DASHBOARD_LOGIN_PASSWORD="$DASHBOARD_LOGIN_PASSWORD" \
  EXPECTED_TRADE_DATE="$EXPECTED_TRADE_DATE" \
  EXPECTED_RELEASE_ID="$release_id" \
  EXPECTED_REMOTE_SOURCE_ROOT="$REMOTE_CONTAINER_RELEASE_ROOT" \
  EXPECTED_FRONTEND_BUILD_ID="$release_id" \
  EXPECTED_STRATEGY_ARTIFACT_DATE="$EXPECTED_TRADE_DATE" \
  EXPECTED_REMOTE_PYTHON_PACKAGE_ROOT="$REMOTE_CONTAINER_RELEASE_ROOT/src/stock_research" \
  EXPECTED_API_BASE_IMAGE="$EXPECTED_API_BASE_IMAGE" \
  EXPECTED_FRONTEND_BASE_IMAGE="$EXPECTED_FRONTEND_BASE_IMAGE" \
  EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION="$EXPECTED_THEME_RESEARCH_REPORT_SCHEMA_VERSION" \
  THEME_RESEARCH_REPORT_HEALTH_JSON="$theme_research_report_health_snapshot" \
  EXPECTED_THEME_RESEARCH_REPORT_ROOT="/app/reports/theme-research" \
  RELEASE_CHECK_TIMEOUT_SECONDS="$1" \
  RELEASE_CHECK_RETRY_SECONDS="$2" \
    "$ROOT/deploy/check_dashboard_release.sh"
}

ssh_opts=()
if [[ -n "$STOCK_RESEARCH_SSH_CONFIG" ]]; then
  if [[ ! -f "$STOCK_RESEARCH_SSH_CONFIG" ]]; then
    echo "STOCK_RESEARCH_SSH_CONFIG does not exist: $STOCK_RESEARCH_SSH_CONFIG" >&2
    exit 2
  fi
  ssh_opts=(-F "$STOCK_RESEARCH_SSH_CONFIG")
fi
if [[ -n "$SSH_OPTS" ]]; then
  parsed_ssh_opts=()
  read -r -a parsed_ssh_opts <<<"$SSH_OPTS"
  index=0
  while (( index < ${#parsed_ssh_opts[@]} )); do
    token="${parsed_ssh_opts[$index]}"
    case "$token" in
      -4|-6)
        index=$((index + 1))
        ;;
      -p)
        index=$((index + 1))
        value="${parsed_ssh_opts[$index]:-}"
        [[ "$value" =~ ^[0-9]+$ ]] || { echo "Unsupported SSH option token: $token $value" >&2; exit 2; }
        index=$((index + 1))
        ;;
      -i)
        index=$((index + 1))
        value="${parsed_ssh_opts[$index]:-}"
        [[ "$value" =~ ^/[A-Za-z0-9._/-]+$ ]] || { echo "Unsupported SSH option token: $token $value" >&2; exit 2; }
        index=$((index + 1))
        ;;
      -o)
        index=$((index + 1))
        value="${parsed_ssh_opts[$index]:-}"
        [[ "$value" =~ ^(BatchMode|ConnectTimeout|IdentitiesOnly|PreferredAuthentications|PubkeyAuthentication|ServerAliveInterval|ServerAliveCountMax|StrictHostKeyChecking|UserKnownHostsFile)=[A-Za-z0-9_.,:/@+-]+$ ]] || { echo "Unsupported SSH option token: $token $value" >&2; exit 2; }
        index=$((index + 1))
        ;;
      *)
        echo "Unsupported SSH option token: $token" >&2
        exit 2
        ;;
    esac
  done
  ssh_opts+=("${parsed_ssh_opts[@]}")
else
  ssh_opts+=(-o BatchMode=yes)
fi
printf -v rsync_rsh ' %q' "${ssh_opts[@]}"
rsync_rsh="ssh${rsync_rsh}"
remote="${REMOTE_USER}@${REMOTE_HOST}"
printf -v remote_dir_q '%q' "$REMOTE_DIR"
printf -v container_root_q '%q' "$REMOTE_CONTAINER_RELEASE_ROOT"
printf -v release_id_q '%q' "$release_id"
printf -v compose_project_q '%q' "$STOCK_RESEARCH_COMPOSE_PROJECT"
printf -v api_bind_port_q '%q' "$DASHBOARD_API_BIND_PORT"
printf -v frontend_bind_port_q '%q' "$DASHBOARD_FRONTEND_BIND_PORT"
printf -v theme_research_report_host_root_q '%q' "$THEME_RESEARCH_REPORT_HOST_ROOT"
theme_research_artifact_host_root="$REMOTE_DIR/artifacts/theme_decomposition"
printf -v theme_research_artifact_host_root_q '%q' "$theme_research_artifact_host_root"
printf -v theme_research_migration_service_q '%q' "$THEME_RESEARCH_MIGRATION_SERVICE"
printf -v theme_research_runtime_service_q '%q' "$THEME_RESEARCH_RUNTIME_SERVICE"
printf -v theme_research_report_index_service_q '%q' "$THEME_RESEARCH_REPORT_INDEX_SERVICE"
printf -v theme_research_report_review_service_q '%q' "$THEME_RESEARCH_REPORT_REVIEW_SERVICE"
api_container="${STOCK_RESEARCH_COMPOSE_PROJECT}-api-1"
printf -v api_container_q '%q' "$api_container"
case "$DASHBOARD_REMOTE_ENV_FILE" in
  /*) remote_env_file="$DASHBOARD_REMOTE_ENV_FILE" ;;
  *) remote_env_file="$REMOTE_DIR/$DASHBOARD_REMOTE_ENV_FILE" ;;
esac
case "$DASHBOARD_PGSERVICE_FILE" in
  /*) pgservice_file="$DASHBOARD_PGSERVICE_FILE" ;;
  *) pgservice_file="$REMOTE_DIR/$DASHBOARD_PGSERVICE_FILE" ;;
esac
printf -v remote_env_file_q '%q' "$remote_env_file"
printf -v pgservice_file_q '%q' "$pgservice_file"

validate_theme_research_report_host_root() {
  ssh "${ssh_opts[@]}" -- "$remote" \
    "bash -s -- --host-only ${theme_research_report_host_root_q}" \
    < "$ROOT/deploy/check_dashboard_report_mount.sh"
}

validate_theme_research_report_mount() {
  ssh "${ssh_opts[@]}" -- "$remote" \
    "bash -s -- --require-mount ${theme_research_report_host_root_q} ${api_container_q} /app/reports/theme-research" \
    < "$ROOT/deploy/check_dashboard_report_mount.sh"
}

capture_theme_research_report_health() {
  local timeout_seconds="$1"
  local retry_seconds="$2"
  local health_deadline=$((SECONDS + timeout_seconds))
  while (( SECONDS <= health_deadline )); do
    if ssh "${ssh_opts[@]}" -- "$remote" \
      "docker exec ${api_container_q} python /app/deploy/check_theme_research_report_runtime.py --expected-root /app/reports/theme-research --migration-service ${theme_research_migration_service_q} --runtime-service ${theme_research_runtime_service_q} --index-service ${theme_research_report_index_service_q} --review-service ${theme_research_report_review_service_q}" \
      > "$theme_research_report_health_snapshot" \
      && jq -e . "$theme_research_report_health_snapshot" >/dev/null 2>&1; then
      return 0
    fi
    if (( SECONDS + retry_seconds > health_deadline )); then
      break
    fi
    sleep "$retry_seconds"
  done
  return 1
}

if ! validate_theme_research_report_host_root >/dev/null; then
  echo "Theme Research report host root validation failed: $THEME_RESEARCH_REPORT_HOST_ROOT" >&2
  exit 2
fi
if ! ssh "${ssh_opts[@]}" -- "$remote" \
  "bash -s -- ${theme_research_artifact_host_root_q} 25 ai_compute_infrastructure_value_chain_v1" \
  < "$ROOT/deploy/check_theme_research_artifacts.sh" >/dev/null; then
  echo "Theme Research canonical artifact validation failed: $theme_research_artifact_host_root" >&2
  exit 2
fi

if check_release_state \
  "${DASHBOARD_DESIRED_STATE_TIMEOUT_SECONDS:-12}" \
  "${DASHBOARD_DESIRED_STATE_RETRY_SECONDS:-2}" >/dev/null 2>&1; then
  echo "Dashboard desired state already live for ${EXPECTED_TRADE_DATE} (${release_id}); deployment skipped."
  exit 0
fi
echo "Dashboard desired-state gate not yet satisfied; continuing idempotent deployment."

echo "Building canonical frontend for release ${release_id}"
CI=true rtk pnpm --dir "$ROOT/dashboard" install --frozen-lockfile
STOCK_RESEARCH_RELEASE_ID="$release_id" \
VITE_RELEASE_ID="$release_id" \
VITE_API_BASE_IMAGE="$EXPECTED_API_BASE_IMAGE" \
VITE_FRONTEND_BASE_IMAGE="$EXPECTED_FRONTEND_BASE_IMAGE" \
CI=true \
  rtk pnpm --dir "$ROOT/dashboard" build
if ! jq -e \
  --arg release "$release_id" \
  --arg api_base_image "$EXPECTED_API_BASE_IMAGE" \
  --arg frontend_base_image "$EXPECTED_FRONTEND_BASE_IMAGE" '
  .release_id == $release
  and .api_base_image == $api_base_image
  and .frontend_base_image == $frontend_base_image
' "$ROOT/dashboard/dist/release.json" >/dev/null; then
  echo "Frontend release metadata does not match release ${release_id}" >&2
  exit 2
fi

echo "Preparing remote release directories"
ssh "${ssh_opts[@]}" -- "$remote" \
  "bash -s -- ${compose_project_q} ${api_bind_port_q} ${frontend_bind_port_q}" < "$ROOT/deploy/check_dashboard_remote_host.sh"
ssh "${ssh_opts[@]}" -- "$remote" \
  "mkdir -p ${remote_dir_q}/src ${remote_dir_q}/dashboard/dist ${remote_dir_q}/deploy ${remote_dir_q}/outputs/research/strategy_daily_eod/${EXPECTED_TRADE_DATE}"

echo "Syncing backend source"
rsync -az --delete -e "$rsync_rsh" -- "$ROOT/src/" "$remote:$REMOTE_DIR/src/"
rsync -az -e "$rsync_rsh" -- "$ROOT/pyproject.toml" "$remote:$REMOTE_DIR/"
rsync -az -e "$rsync_rsh" -- "$ROOT/.dockerignore" "$remote:$REMOTE_DIR/"
rsync -az -e "$rsync_rsh" -- \
  "$ROOT/deploy/dashboard-api.Dockerfile" \
  "$ROOT/deploy/dashboard-api-requirements.in" \
  "$ROOT/deploy/dashboard-api-requirements.lock" \
  "$ROOT/deploy/check_dashboard_report_mount.sh" \
  "$ROOT/deploy/check_theme_research_report_runtime.py" \
  "$ROOT/deploy/dashboard-frontend.Dockerfile" \
  "$ROOT/deploy/dashboard-nginx.conf" \
  "$ROOT/deploy/check_dashboard_remote_host.sh" \
  "$ROOT/deploy/dashboard-release.compose.yml" \
  "$remote:$REMOTE_DIR/deploy/"

echo "Syncing canonical frontend build"
rsync -az --delete -e "$rsync_rsh" -- "$ROOT/dashboard/dist/" "$remote:$REMOTE_DIR/dashboard/dist/"

echo "Syncing strategy artifacts for ${EXPECTED_TRADE_DATE}"
rsync -az --delete -e "$rsync_rsh" -- "$strategy_output/" \
  "$remote:$REMOTE_DIR/outputs/research/strategy_daily_eod/${EXPECTED_TRADE_DATE}/"

echo "Restarting Docker Compose API and dashboard services"
ssh "${ssh_opts[@]}" -- "$remote" \
  "cd ${remote_dir_q} && test -f ${remote_env_file_q} && test -f ${pgservice_file_q} && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} DASHBOARD_REMOTE_ENV_FILE=${remote_env_file_q} DASHBOARD_PGSERVICE_FILE=${pgservice_file_q} DASHBOARD_API_BIND_PORT=${api_bind_port_q} DASHBOARD_FRONTEND_BIND_PORT=${frontend_bind_port_q} THEME_RESEARCH_REPORT_HOST_ROOT=${theme_research_report_host_root_q} THEME_RESEARCH_MIGRATION_SERVICE=${theme_research_migration_service_q} THEME_RESEARCH_RUNTIME_SERVICE=${theme_research_runtime_service_q} THEME_RESEARCH_REPORT_INDEX_SERVICE=${theme_research_report_index_service_q} THEME_RESEARCH_REPORT_REVIEW_SERVICE=${theme_research_report_review_service_q} docker compose --project-name ${compose_project_q} -f deploy/dashboard-release.compose.yml build api dashboard && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} DASHBOARD_REMOTE_ENV_FILE=${remote_env_file_q} DASHBOARD_PGSERVICE_FILE=${pgservice_file_q} DASHBOARD_API_BIND_PORT=${api_bind_port_q} DASHBOARD_FRONTEND_BIND_PORT=${frontend_bind_port_q} THEME_RESEARCH_REPORT_HOST_ROOT=${theme_research_report_host_root_q} THEME_RESEARCH_MIGRATION_SERVICE=${theme_research_migration_service_q} THEME_RESEARCH_RUNTIME_SERVICE=${theme_research_runtime_service_q} THEME_RESEARCH_REPORT_INDEX_SERVICE=${theme_research_report_index_service_q} THEME_RESEARCH_REPORT_REVIEW_SERVICE=${theme_research_report_review_service_q} docker compose --project-name ${compose_project_q} -f deploy/dashboard-release.compose.yml run --rm --no-deps -e PGSERVICE=${theme_research_migration_service_q} api python -m stock_research.theme_research_report_schema --apply --service ${theme_research_migration_service_q} && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} DASHBOARD_REMOTE_ENV_FILE=${remote_env_file_q} DASHBOARD_PGSERVICE_FILE=${pgservice_file_q} DASHBOARD_API_BIND_PORT=${api_bind_port_q} DASHBOARD_FRONTEND_BIND_PORT=${frontend_bind_port_q} THEME_RESEARCH_REPORT_HOST_ROOT=${theme_research_report_host_root_q} THEME_RESEARCH_MIGRATION_SERVICE=${theme_research_migration_service_q} THEME_RESEARCH_RUNTIME_SERVICE=${theme_research_runtime_service_q} THEME_RESEARCH_REPORT_INDEX_SERVICE=${theme_research_report_index_service_q} THEME_RESEARCH_REPORT_REVIEW_SERVICE=${theme_research_report_review_service_q} docker compose --project-name ${compose_project_q} -f deploy/dashboard-release.compose.yml run --rm --no-deps -e PGSERVICE=${theme_research_migration_service_q} api python /app/deploy/check_theme_research_report_runtime.py --schema-only --migration-service ${theme_research_migration_service_q} --runtime-service ${theme_research_runtime_service_q} --index-service ${theme_research_report_index_service_q} --review-service ${theme_research_report_review_service_q} && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} DASHBOARD_REMOTE_ENV_FILE=${remote_env_file_q} DASHBOARD_PGSERVICE_FILE=${pgservice_file_q} DASHBOARD_API_BIND_PORT=${api_bind_port_q} DASHBOARD_FRONTEND_BIND_PORT=${frontend_bind_port_q} THEME_RESEARCH_REPORT_HOST_ROOT=${theme_research_report_host_root_q} THEME_RESEARCH_MIGRATION_SERVICE=${theme_research_migration_service_q} THEME_RESEARCH_RUNTIME_SERVICE=${theme_research_runtime_service_q} THEME_RESEARCH_REPORT_INDEX_SERVICE=${theme_research_report_index_service_q} THEME_RESEARCH_REPORT_REVIEW_SERVICE=${theme_research_report_review_service_q} docker compose --project-name ${compose_project_q} -f deploy/dashboard-release.compose.yml up -d --force-recreate --remove-orphans api dashboard"

echo "Synchronizing trusted strategy manifest into remote database"
ssh "${ssh_opts[@]}" -- "$remote" \
  "docker exec -i ${api_container_q} python -m stock_research.strategy_manifest_transfer import && docker restart ${api_container_q} >/dev/null" \
  < "$manifest_snapshot"

echo "Running bounded external release gate"
check_release_state \
  "${RELEASE_CHECK_TIMEOUT_SECONDS:-120}" \
  "${RELEASE_CHECK_RETRY_SECONDS:-3}"
