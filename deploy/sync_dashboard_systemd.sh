#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-jqz}"
REMOTE_HOST="${REMOTE_HOST:-stock-prod}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/code/stock-research-platform-main}"
SSH_OPTS="${SSH_OPTS:-}"
STRATEGY_OUTPUT_ROOT="${STRATEGY_OUTPUT_ROOT:-/Users/xiwei/stock_research/outputs/research}"
REPORTS_ROOT="${REPORTS_ROOT:-/Users/xiwei/stock_research/reports}"
SERVICE_NAME="${SERVICE_NAME:-stock-research-dashboard-api.service}"
REMOTE_WEB_ROOT="${REMOTE_WEB_ROOT:-/var/www/stock-dashboard/current}"
REMOTE_ROOT_HELPER="${REMOTE_ROOT_HELPER:-/usr/local/bin/stock-dashboard-publish-root}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

shell_quote() {
  printf "%q" "$1"
}

ensure_remote_sudo_password() {
  if [[ -n "${REMOTE_SUDO_PASSWORD:-}" ]]; then
    return
  fi
  if [[ -t 0 ]]; then
    read -r -s -p "Remote sudo password for ${REMOTE_USER}@${REMOTE_HOST}: " REMOTE_SUDO_PASSWORD
    echo
    export REMOTE_SUDO_PASSWORD
    return
  fi
  echo "REMOTE_SUDO_PASSWORD is required for non-interactive remote sudo operations." >&2
  exit 1
}

remote_sudo() {
  ensure_remote_sudo_password
  local password_quoted
  password_quoted="$(shell_quote "$REMOTE_SUDO_PASSWORD")"
  ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" \
    "printf '%s\n' ${password_quoted} | sudo -S -p '' bash -lc $(shell_quote "$1")"
}

run_remote_root_helper() {
  local helper_cmd
  helper_cmd="sudo -n $(shell_quote "$REMOTE_ROOT_HELPER") $(shell_quote "$1") $(shell_quote "$2") $(shell_quote "$3")"
  if ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "$helper_cmd" 2>/dev/null; then
    return
  fi
  remote_sudo "$(shell_quote "$REMOTE_ROOT_HELPER") $(shell_quote "$1") $(shell_quote "$2") $(shell_quote "$3")"
}

find_latest_strategy_daily_eod() {
  find "${STRATEGY_OUTPUT_ROOT}/strategy_daily_eod" -mindepth 1 -maxdepth 1 -type d -name '????-??-??' 2>/dev/null \
    | sed "s#^${STRATEGY_OUTPUT_ROOT}/##" \
    | sort \
    | tail -1
}

LATEST_STRATEGY_DAILY_EOD="${LATEST_STRATEGY_DAILY_EOD:-$(find_latest_strategy_daily_eod)}"
if [[ -z "$LATEST_STRATEGY_DAILY_EOD" ]]; then
  echo "No strategy_daily_eod artifact directory found under ${STRATEGY_OUTPUT_ROOT}" >&2
  exit 1
fi

strategy_output_dirs=(
  "$LATEST_STRATEGY_DAILY_EOD"
  "official_strategy_contract_rescan_20260101_20260617_fresh_all"
  "web_lhb_shortline_v1_runs"
  "mid_trend_shadow_top10_context_fixed_20260602"
  "mid_trend_refresh_20260602"
  "tech_bottleneck_discovery_v0_1_closeout_20260608"
  "web_tech_bottleneck_v1_runs/tech_bottleneck_v1_20260616_manual"
)

echo "Building dashboard frontend"
(cd "$repo_root/dashboard" && CI=true pnpm build)

echo "Syncing backend source"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$repo_root/src/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/src/"

echo "Syncing frontend source and static build"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$repo_root/dashboard/src/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dashboard/src/"
rsync -az --delete -e "ssh ${SSH_OPTS}" "$repo_root/dashboard/dist/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dashboard/dist/"
rsync -az -e "ssh ${SSH_OPTS}" \
  "$repo_root/dashboard/index.html" \
  "$repo_root/dashboard/package.json" \
  "$repo_root/dashboard/pnpm-lock.yaml" \
  "$repo_root/dashboard/tsconfig.json" \
  "$repo_root/dashboard/vite.config.ts" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/dashboard/"

rsync -az -e "ssh ${SSH_OPTS}" \
  "$repo_root/pyproject.toml" \
  "$repo_root/README.md" \
  "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo "Publishing frontend dist to nginx web root"
run_remote_root_helper "${REMOTE_DIR}/dashboard/dist" "${REMOTE_WEB_ROOT}" "${SERVICE_NAME}"

echo "Syncing strategy review artifacts"
ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}/outputs/research'"
for output_dir in "${strategy_output_dirs[@]}"; do
  if [[ -d "${STRATEGY_OUTPUT_ROOT}/${output_dir}" ]]; then
    ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}/outputs/research/${output_dir}'"
    rsync -az -e "ssh ${SSH_OPTS}" \
      "${STRATEGY_OUTPUT_ROOT}/${output_dir}/" \
      "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/outputs/research/${output_dir}/"
  else
    echo "Skipping missing strategy output directory: ${STRATEGY_OUTPUT_ROOT}/${output_dir}"
  fi
done

echo "Syncing report artifacts"
if [[ -d "${REPORTS_ROOT}" ]]; then
  ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_DIR}/reports'"
  rsync -az -e "ssh ${SSH_OPTS}" \
    "${REPORTS_ROOT}/" \
    "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/reports/"
else
  echo "Skipping missing reports directory: ${REPORTS_ROOT}"
fi

echo "Writing remote PostgreSQL service file from .env"
ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "cd '${REMOTE_DIR}' && python3 -" <<'PY'
from pathlib import Path

root = Path(".")
env_path = root / ".env"
values: dict[str, str] = {}
for raw_line in env_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

host = values.get("POSTGRES_HOST", "127.0.0.1")
port = values.get("POSTGRES_PORT", "5432")
user = values.get("POSTGRES_USER", "postgres")
password = values.get("POSTGRES_PASSWORD", "")
db = values.get("POSTGRES_DB", "stock_research")
hfq_db = values.get("POSTGRES_HFQ_DB", "cn_a_stock_daily_hfq")
qfq_db = values.get("POSTGRES_QFQ_DB", "cn_a_stock_daily_qfq")

content = f"""[stock_research]
host={host}
port={port}
dbname={db}
user={user}
password={password}

[stock_hfq]
host={host}
port={port}
dbname={hfq_db}
user={user}
password={password}

[stock_qfq]
host={host}
port={port}
dbname={qfq_db}
user={user}
password={password}
"""

target = root / ".pg_service.conf"
target.write_text(content, encoding="utf-8")
target.chmod(0o600)
PY

echo "Systemd dashboard sync complete"
