#!/usr/bin/env bash
set -euo pipefail

REMOTE_USER="${REMOTE_USER:-jqz}"
REMOTE_HOST="${REMOTE_HOST:-192.168.3.185}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/code/stock-research-platform-main}"
SSH_OPTS="${SSH_OPTS:--o PreferredAuthentications=password -o PubkeyAuthentication=no}"
REBUILD="${REBUILD:-0}"
STRATEGY_OUTPUT_ROOT="${STRATEGY_OUTPUT_ROOT:-/Users/xiwei/stock_research/outputs/research}"
REPORTS_ROOT="${REPORTS_ROOT:-/Users/xiwei/stock_research/reports}"

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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
  "official_strategy_contract_rescan_20260101_20260617_fresh_all"
  "$LATEST_STRATEGY_DAILY_EOD"
  "web_lhb_shortline_v1_runs"
  "mid_trend_shadow_top10_context_fixed_20260602"
  "mid_trend_refresh_20260602"
  "tech_bottleneck_discovery_v0_1_closeout_20260608"
  "web_tech_bottleneck_v1_runs/tech_bottleneck_v1_20260616_manual"
)

echo "Building dashboard frontend"
(cd "$repo_root/dashboard" && pnpm build)

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

if [[ "$REBUILD" == "1" ]]; then
  echo "Rebuilding images because REBUILD=1"
  ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "cd '${REMOTE_DIR}' && docker compose build api dashboard && docker compose up -d api dashboard"
else
  echo "Restarting containers with mounted source/dist"
  ssh ${SSH_OPTS} "${REMOTE_USER}@${REMOTE_HOST}" "cd '${REMOTE_DIR}' && docker compose restart api dashboard"
fi

echo "Fast dashboard sync complete"
