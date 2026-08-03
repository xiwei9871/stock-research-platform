#!/usr/bin/env bash
set -euo pipefail

mode="${1:-}"
host_root="${2:-}"

if [[ "$mode" != "--validate-path" && "$mode" != "--host-only" && "$mode" != "--require-mount" ]]; then
  echo "usage: $0 --validate-path HOST_ROOT | --host-only HOST_ROOT | --require-mount HOST_ROOT CONTAINER TARGET" >&2
  exit 2
fi

validate_host_root_path() {
  local candidate="$1"
  local relative
  local basename
  local -a components

  if [[ ! "$candidate" =~ ^/[A-Za-z0-9._/-]+$ ]] \
    || [[ "$candidate" == *"//"* ]] \
    || [[ "$candidate" == *"/./"* || "$candidate" == */. ]] \
    || [[ "$candidate" == *"/../"* || "$candidate" == */.. ]] \
    || [[ "$candidate" == */ ]]; then
    echo "Theme Research report host root must be a safe absolute path" >&2
    return 2
  fi
  case "$candidate" in
    /|/bin|/boot|/dev|/etc|/home|/lib|/lib64|/media|/mnt|/opt|/proc|/root|/run|/sbin|/srv|/sys|/tmp|/usr|/var)
      echo "Theme Research report host root must not be a system root" >&2
      return 2
      ;;
  esac

  relative="${candidate#/}"
  IFS='/' read -r -a components <<< "$relative"
  basename="${candidate##*/}"
  if (( ${#components[@]} < 3 )) || [[ "$basename" != *theme-research* ]]; then
    echo "Theme Research report host root must be a dedicated theme-research directory at depth 3 or greater" >&2
    return 2
  fi
}

validate_host_root_path "$host_root"
if [[ "$mode" == "--validate-path" ]]; then
  printf '%s\n' "$host_root"
  exit 0
fi
if [[ ! -d "$host_root" || ! -r "$host_root" || ! -x "$host_root" ]]; then
  echo "Theme Research report host root must already exist as a readable directory: $host_root" >&2
  exit 2
fi

host_root_real="$(cd "$host_root" && pwd -P)"
if ! validate_host_root_path "$host_root_real"; then
  echo "Resolved Theme Research report host root is not a safe dedicated path" >&2
  exit 2
fi
if [[ "$mode" == "--host-only" ]]; then
  printf '%s\n' "$host_root_real"
  exit 0
fi

container_name="${3:-}"
target="${4:-}"
if [[ ! "$container_name" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] \
  || [[ ! "$target" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "Theme Research report container or mount target is invalid" >&2
  exit 2
fi

mount_rows="$(docker inspect --format '{{range .Mounts}}{{printf "%s|%s|%t\n" .Destination .Source .RW}}{{end}}' "$container_name")"
match_count=0
mount_source=""
mount_rw=""
while IFS='|' read -r destination source rw; do
  [[ "$destination" == "$target" ]] || continue
  match_count=$((match_count + 1))
  mount_source="$source"
  mount_rw="$rw"
done <<< "$mount_rows"

if (( match_count != 1 )) || [[ ! -d "$mount_source" ]]; then
  echo "Theme Research report mount is missing or ambiguous at $target" >&2
  exit 1
fi
mount_source_real="$(cd "$mount_source" && pwd -P)"
if [[ "$mount_source_real" != "$host_root_real" ]]; then
  echo "Theme Research report mount source mismatch: expected $host_root_real, got $mount_source_real" >&2
  exit 1
fi
if [[ "$mount_rw" != "false" ]]; then
  echo "Theme Research report mount must be read-only" >&2
  exit 1
fi

printf '%s|%s|%s\n' "$target" "$mount_source_real" "$mount_rw"
