#!/usr/bin/env bash

REPAIR_PUBLICATION_LOCK_MODE=""
REPAIR_PUBLICATION_LOCK_DIR=""

acquire_repair_publication_lock() {
  local root="$1"
  mkdir -p "$root/.locks"
  if command -v flock >/dev/null 2>&1; then
    REPAIR_PUBLICATION_LOCK_MODE="flock"
    exec 8>"$root/.locks/eod_repair_publication.flock"
    flock -n 8
    return $?
  fi
  local lock_dir="$root/.locks/eod_repair_publication.lock"
  if mkdir "$lock_dir" 2>/dev/null; then
    REPAIR_PUBLICATION_LOCK_MODE="mkdir"
    REPAIR_PUBLICATION_LOCK_DIR="$lock_dir"
    return 0
  fi
  return 1
}

release_repair_publication_lock() {
  if [[ "$REPAIR_PUBLICATION_LOCK_MODE" == "mkdir" && -n "$REPAIR_PUBLICATION_LOCK_DIR" ]]; then
    rmdir "$REPAIR_PUBLICATION_LOCK_DIR" 2>/dev/null || true
  fi
}
