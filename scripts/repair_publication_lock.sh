#!/usr/bin/env bash

REPAIR_PUBLICATION_LOCK_MODE=""
REPAIR_PUBLICATION_LOCK_DIR=""

repair_publication_process_start() {
  ps -o lstart= -p "$1" 2>/dev/null | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

write_repair_publication_owner() {
  local lock_dir="$1"
  local owner_tmp="$lock_dir/owner.tmp.$$.$RANDOM"
  local host
  host="$(hostname 2>/dev/null || printf unknown)"
  printf '%s|%s|%s\n' "$$" "$host" "$(repair_publication_process_start "$$")" >"$owner_tmp"
  mv "$owner_tmp" "$lock_dir/owner"
}

acquire_repair_publication_lock() {
  local root="$1"
  mkdir -p "$root/.locks"
  if [[ "${REPAIR_PUBLICATION_DISABLE_FLOCK:-0}" != "1" ]] && command -v flock >/dev/null 2>&1; then
    REPAIR_PUBLICATION_LOCK_MODE="flock"
    exec 8>"$root/.locks/eod_repair_publication.flock"
    flock -n 8
    return $?
  fi
  local lock_dir="$root/.locks/eod_repair_publication.lock"
  local attempts=0
  while (( attempts < 3 )); do
    attempts=$((attempts + 1))
    if mkdir "$lock_dir" 2>/dev/null; then
      write_repair_publication_owner "$lock_dir"
      REPAIR_PUBLICATION_LOCK_MODE="mkdir"
      REPAIR_PUBLICATION_LOCK_DIR="$lock_dir"
      return 0
    fi

    local owner_pid=""
    local owner_host=""
    local owner_start=""
    if [[ ! -s "$lock_dir/owner" ]]; then
      sleep 0.1
    fi
    if [[ -r "$lock_dir/owner" ]]; then
      IFS='|' read -r owner_pid owner_host owner_start <"$lock_dir/owner" || true
    fi
    local current_host
    current_host="$(hostname 2>/dev/null || printf unknown)"
    if [[ "$owner_pid" =~ ^[0-9]+$ ]] \
      && [[ "$owner_host" == "$current_host" ]] \
      && kill -0 "$owner_pid" 2>/dev/null \
      && [[ "$(repair_publication_process_start "$owner_pid")" == "$owner_start" ]]; then
      return 1
    fi

    local stale_dir="${lock_dir}.stale.${owner_pid:-unknown}.$$.$RANDOM"
    if mv "$lock_dir" "$stale_dir" 2>/dev/null; then
      rm -rf "$stale_dir"
      continue
    fi
  done
  return 1
}

release_repair_publication_lock() {
  if [[ "$REPAIR_PUBLICATION_LOCK_MODE" == "mkdir" && -n "$REPAIR_PUBLICATION_LOCK_DIR" ]]; then
    rm -rf "$REPAIR_PUBLICATION_LOCK_DIR" 2>/dev/null || true
  fi
}
