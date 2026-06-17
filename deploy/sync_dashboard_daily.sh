#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
env_file="${DASHBOARD_DAILY_SYNC_ENV:-/Users/xiwei/.stock_research_dashboard_sync.env}"
log_file="${DASHBOARD_DAILY_SYNC_LOG:-${repo_root}/logs/dashboard_daily_sync.log}"
lock_dir="${DASHBOARD_DAILY_SYNC_LOCK_DIR:-/tmp/stock-research-dashboard-daily-sync.lockdir}"

mkdir -p "$(dirname "$log_file")"

if [[ -f "$env_file" ]]; then
  # shellcheck disable=SC1090
  source "$env_file"
fi

REMOTE_HOST="${REMOTE_HOST:-192.168.3.185}"
BASE_URL="${BASE_URL:-https://stock.manqiaotechnology.com}"
REMOTE_USER="${REMOTE_USER:-jqz}"
REMOTE_DIR="${REMOTE_DIR:-/home/${REMOTE_USER}/code/stock-research-platform-main}"
SSH_OPTS="${SSH_OPTS:--o PreferredAuthentications=password -o PubkeyAuthentication=no}"
REBUILD="${REBUILD:-0}"
STRATEGY_OUTPUT_ROOT="${STRATEGY_OUTPUT_ROOT:-/Users/xiwei/stock_research/outputs/research}"

timestamp() {
  date '+%Y-%m-%dT%H:%M:%S%z'
}

if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "$(timestamp) dashboard daily sync already running" | tee -a "$log_file"
  exit 0
fi
trap 'rmdir "$lock_dir"' EXIT

exec > >(tee -a "$log_file") 2>&1

echo "$(timestamp) dashboard daily sync starting"
echo "repo_root=${repo_root}"
echo "remote_host=${REMOTE_HOST}"
echo "base_url=${BASE_URL}"

cd "$repo_root"

git diff-index --quiet HEAD --
dirty_untracked="$(git status --porcelain --untracked-files=all | grep -v '^?? tmp/' || true)"
if [[ -n "$dirty_untracked" ]]; then
  echo "Refusing to sync dirty dashboard worktree. Commit or remove these files first:"
  echo "$dirty_untracked"
  exit 1
fi

if [[ -z "${DASHBOARD_AUTH:-}" && "${SKIP_RELEASE_CHECK:-0}" != "1" ]]; then
  echo "DASHBOARD_AUTH is required for release verification unless SKIP_RELEASE_CHECK=1"
  echo "Set it in ${env_file} as DASHBOARD_AUTH='user:password'."
  exit 1
fi

export REMOTE_USER REMOTE_HOST REMOTE_DIR SSH_OPTS REBUILD STRATEGY_OUTPUT_ROOT
"${repo_root}/deploy/sync_dashboard_fast.sh"

if [[ "${SKIP_RELEASE_CHECK:-0}" == "1" ]]; then
  echo "Skipping release check because SKIP_RELEASE_CHECK=1"
else
  BASE_URL="$BASE_URL" DASHBOARD_AUTH="$DASHBOARD_AUTH" "${repo_root}/deploy/check_dashboard_release.sh"
fi

echo "$(timestamp) dashboard daily sync complete"
