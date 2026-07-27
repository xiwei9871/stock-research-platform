#!/usr/bin/env bash
set -euo pipefail

release_root_override="${STOCK_RESEARCH_RELEASE_ROOT:-}"
trade_date_override="${EXPECTED_TRADE_DATE:-}"
python_override="${STOCK_RESEARCH_PYTHON:-}"
remote_user_override="${REMOTE_USER:-}"
remote_host_override="${REMOTE_HOST:-}"
remote_dir_override="${REMOTE_DIR:-}"
ssh_opts_override="${SSH_OPTS:-}"
base_url_override="${BASE_URL:-}"
dashboard_auth_override="${DASHBOARD_AUTH:-}"
container_root_override="${REMOTE_CONTAINER_RELEASE_ROOT:-}"
strategy_output_root_override="${STRATEGY_OUTPUT_ROOT:-}"
local_readiness_url_override="${LOCAL_READINESS_URL:-}"

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
SSH_OPTS="${ssh_opts_override:-${SSH_OPTS:--o PreferredAuthentications=password -o PubkeyAuthentication=no}}"
BASE_URL="${base_url_override:-${BASE_URL:-https://stock.manqiaotechnology.com}}"
DASHBOARD_AUTH="${dashboard_auth_override:-${DASHBOARD_AUTH:-}}"
REMOTE_CONTAINER_RELEASE_ROOT="${container_root_override:-${REMOTE_CONTAINER_RELEASE_ROOT:-/app}}"
STRATEGY_OUTPUT_ROOT="${strategy_output_root_override:-${STRATEGY_OUTPUT_ROOT:-$ROOT/outputs/research}}"
LOCAL_READINESS_URL="${local_readiness_url_override:-${LOCAL_READINESS_URL:-http://127.0.0.1:8765/api/platform/readiness}}"

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

if [[ ! "$REMOTE_USER" =~ ^[A-Za-z0-9._-]+$ ]] || [[ ! "$REMOTE_HOST" =~ ^[A-Za-z0-9.:-]+$ ]]; then
  echo "REMOTE_USER or REMOTE_HOST contains unsupported characters" >&2
  exit 2
fi
if [[ ! "$REMOTE_DIR" =~ ^/[A-Za-z0-9._/-]+$ ]] || [[ ! "$REMOTE_CONTAINER_RELEASE_ROOT" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "REMOTE_DIR or REMOTE_CONTAINER_RELEASE_ROOT must be a safe absolute path" >&2
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
      | jq -er '.latest_market_date | select(type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}$"))' \
      2>/dev/null || true
  )"
fi
if [[ -z "$EXPECTED_TRADE_DATE" ]]; then
  EXPECTED_TRADE_DATE="$(
    env -u PYTHONPATH STOCK_RESEARCH_RELEASE_ROOT="$ROOT" "$STOCK_RESEARCH_PYTHON" -c \
      'from stock_research.dashboard.platform import load_platform_summary; print(load_platform_summary().get("latest_market_date") or "")' \
      2>/dev/null || true
  )"
fi
if [[ ! "$EXPECTED_TRADE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "Unable to resolve a valid EXPECTED_TRADE_DATE from override or local readiness" >&2
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
if [[ -n "$SSH_OPTS" ]]; then
  read -r -a ssh_opts <<<"$SSH_OPTS"
fi
remote="${REMOTE_USER}@${REMOTE_HOST}"
printf -v remote_dir_q '%q' "$REMOTE_DIR"
printf -v container_root_q '%q' "$REMOTE_CONTAINER_RELEASE_ROOT"
printf -v release_id_q '%q' "$release_id"

echo "Building canonical frontend for release ${release_id}"
STOCK_RESEARCH_RELEASE_ID="$release_id" VITE_RELEASE_ID="$release_id" rtk pnpm --dir "$ROOT/dashboard" build
if ! jq -e --arg release "$release_id" '.release_id == $release' "$ROOT/dashboard/dist/release.json" >/dev/null; then
  echo "Frontend release metadata does not match release ${release_id}" >&2
  exit 2
fi

echo "Preparing remote release directories"
ssh "${ssh_opts[@]}" "$remote" \
  "mkdir -p ${remote_dir_q}/src ${remote_dir_q}/dashboard/dist ${remote_dir_q}/deploy ${remote_dir_q}/outputs/research/strategy_daily_eod/${EXPECTED_TRADE_DATE}"

echo "Syncing backend source"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$ROOT/src/" "$remote:$REMOTE_DIR/src/"
rsync -az -e "ssh ${SSH_OPTS}" "$ROOT/pyproject.toml" "$remote:$REMOTE_DIR/"
rsync -az -e "ssh ${SSH_OPTS}" \
  "$ROOT/deploy/dashboard-api.Dockerfile" \
  "$ROOT/deploy/dashboard-frontend.Dockerfile" \
  "$ROOT/deploy/dashboard-nginx.conf" \
  "$ROOT/deploy/dashboard-release.compose.yml" \
  "$remote:$REMOTE_DIR/deploy/"

echo "Syncing canonical frontend build"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$ROOT/dashboard/dist/" "$remote:$REMOTE_DIR/dashboard/dist/"

echo "Syncing strategy artifacts for ${EXPECTED_TRADE_DATE}"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$strategy_output/" \
  "$remote:$REMOTE_DIR/outputs/research/strategy_daily_eod/${EXPECTED_TRADE_DATE}/"

echo "Restarting Docker Compose API and dashboard services"
ssh "${ssh_opts[@]}" "$remote" \
  "cd ${remote_dir_q} && compose_file='' && for candidate in compose.yaml compose.yml docker-compose.yaml docker-compose.yml; do if [ -f \"\$candidate\" ]; then compose_file=\"\$candidate\"; break; fi; done && test -n \"\$compose_file\" && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} docker compose -f \"\$compose_file\" -f deploy/dashboard-release.compose.yml build api dashboard && STOCK_RESEARCH_RELEASE_ROOT=${container_root_q} STOCK_RESEARCH_RELEASE_ID=${release_id_q} STOCK_RESEARCH_FRONTEND_BUILD_ID=${release_id_q} docker compose -f \"\$compose_file\" -f deploy/dashboard-release.compose.yml up -d --force-recreate api dashboard"

echo "Running bounded external release gate"
BASE_URL="$BASE_URL" \
EXPECTED_TRADE_DATE="$EXPECTED_TRADE_DATE" \
EXPECTED_RELEASE_ID="$release_id" \
DASHBOARD_AUTH="$DASHBOARD_AUTH" \
EXPECTED_REMOTE_SOURCE_ROOT="$REMOTE_CONTAINER_RELEASE_ROOT" \
  "$ROOT/deploy/check_dashboard_release.sh"
