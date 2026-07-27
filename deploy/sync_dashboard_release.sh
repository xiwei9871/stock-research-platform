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
container_root_override="${REMOTE_CONTAINER_RELEASE_ROOT:-}"
strategy_output_root_override="${STRATEGY_OUTPUT_ROOT:-}"
local_readiness_url_override="${LOCAL_READINESS_URL:-}"
remote_env_file_override="${DASHBOARD_REMOTE_ENV_FILE:-}"
remote_pgservice_file_override="${DASHBOARD_PGSERVICE_FILE:-}"
compose_project_override="${STOCK_RESEARCH_COMPOSE_PROJECT:-}"
platform_summary_file_override="${PLATFORM_SUMMARY_FILE:-}"
api_bind_port_override="${DASHBOARD_API_BIND_PORT:-}"
frontend_bind_port_override="${DASHBOARD_FRONTEND_BIND_PORT:-}"

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
REMOTE_CONTAINER_RELEASE_ROOT="${container_root_override:-${REMOTE_CONTAINER_RELEASE_ROOT:-/app}}"
STRATEGY_OUTPUT_ROOT="${strategy_output_root_override:-${STRATEGY_OUTPUT_ROOT:-$ROOT/outputs/research}}"
LOCAL_READINESS_URL="${local_readiness_url_override:-${LOCAL_READINESS_URL:-http://127.0.0.1:8765/api/platform/readiness}}"
DASHBOARD_REMOTE_ENV_FILE="${remote_env_file_override:-${DASHBOARD_REMOTE_ENV_FILE:-.env.dashboard}}"
DASHBOARD_PGSERVICE_FILE="${remote_pgservice_file_override:-${DASHBOARD_PGSERVICE_FILE:-.pg_service.conf}}"
STOCK_RESEARCH_COMPOSE_PROJECT="${compose_project_override:-${STOCK_RESEARCH_COMPOSE_PROJECT:-stock_research_dashboard}}"
PLATFORM_SUMMARY_FILE="${platform_summary_file_override:-${PLATFORM_SUMMARY_FILE:-$ROOT/outputs/research/platform_daily_summary_v1/latest.json}}"
DASHBOARD_API_BIND_PORT="${api_bind_port_override:-${DASHBOARD_API_BIND_PORT:-8765}}"
DASHBOARD_FRONTEND_BIND_PORT="${frontend_bind_port_override:-${DASHBOARD_FRONTEND_BIND_PORT:-5174}}"

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
            | .latest_market_date
            | select(type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))
          ' \
      2>/dev/null || true
  )"
fi
if [[ -z "$EXPECTED_TRADE_DATE" ]]; then
  if [[ -f "$PLATFORM_SUMMARY_FILE" ]]; then
    summary_path="$(cd "$(dirname "$PLATFORM_SUMMARY_FILE")" && pwd -P)/$(basename "$PLATFORM_SUMMARY_FILE")"
    case "$summary_path" in
      "$ROOT"/*)
        EXPECTED_TRADE_DATE="$(jq -er '.latest_market_date | select(type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))' "$summary_path" 2>/dev/null || true)"
        ;;
    esac
  fi
fi
if [[ ! "$EXPECTED_TRADE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Unable to resolve a valid EXPECTED_TRADE_DATE from override, current readiness, or the selected release platform summary" >&2
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

echo "Building canonical frontend for release ${release_id}"
rtk pnpm --dir "$ROOT/dashboard" install --frozen-lockfile
STOCK_RESEARCH_RELEASE_ID="$release_id" \
VITE_RELEASE_ID="$release_id" \
VITE_API_BASE_IMAGE="python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7" \
VITE_FRONTEND_BASE_IMAGE="nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10" \
  rtk pnpm --dir "$ROOT/dashboard" build
if ! jq -e --arg release "$release_id" '
  .release_id == $release
  and .api_base_image == "python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"
  and .frontend_base_image == "nginx:1.27.5-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10"
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
rsync -az -e "$rsync_rsh" -- \
  "$ROOT/deploy/dashboard-api.Dockerfile" \
  "$ROOT/deploy/dashboard-api-requirements.in" \
  "$ROOT/deploy/dashboard-api-requirements.lock" \
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
  "cd ${remote_dir_q} && test -f ${remote_env_file_q} && test -f ${pgservice_file_q} && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} DASHBOARD_REMOTE_ENV_FILE=${remote_env_file_q} DASHBOARD_PGSERVICE_FILE=${pgservice_file_q} DASHBOARD_API_BIND_PORT=${api_bind_port_q} DASHBOARD_FRONTEND_BIND_PORT=${frontend_bind_port_q} docker compose --project-name ${compose_project_q} -f deploy/dashboard-release.compose.yml build api dashboard && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} DASHBOARD_REMOTE_ENV_FILE=${remote_env_file_q} DASHBOARD_PGSERVICE_FILE=${pgservice_file_q} DASHBOARD_API_BIND_PORT=${api_bind_port_q} DASHBOARD_FRONTEND_BIND_PORT=${frontend_bind_port_q} docker compose --project-name ${compose_project_q} -f deploy/dashboard-release.compose.yml up -d --force-recreate api dashboard"

echo "Running bounded external release gate"
BASE_URL="$BASE_URL" \
EXPECTED_TRADE_DATE="$EXPECTED_TRADE_DATE" \
EXPECTED_RELEASE_ID="$release_id" \
DASHBOARD_AUTH="$DASHBOARD_AUTH" \
EXPECTED_REMOTE_SOURCE_ROOT="$REMOTE_CONTAINER_RELEASE_ROOT" \
  "$ROOT/deploy/check_dashboard_release.sh"
