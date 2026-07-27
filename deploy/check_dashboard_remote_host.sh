#!/usr/bin/env bash
set -euo pipefail

project_name="${1:?compose project name is required}"
shift

if [[ ! "$project_name" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  echo "Invalid compose project name: $project_name" >&2
  exit 2
fi
if (( $# == 0 )); then
  echo "At least one dashboard bind port is required" >&2
  exit 2
fi

docker compose version >/dev/null
docker compose ls --format json >/dev/null

for port in "$@"; do
  if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    echo "Invalid dashboard bind port: $port" >&2
    exit 2
  fi
  while IFS='|' read -r container_id owner_project container_name; do
    [[ -n "$container_id" ]] || continue
    if [[ "$owner_project" != "$project_name" ]]; then
      owner_label="${owner_project:-non-compose container}"
      echo "Dashboard port $port is occupied by $container_name ($container_id), owner=$owner_label; migration required before canonical release." >&2
      echo "Inspect the owner and stop it explicitly, or choose approved DASHBOARD_API_BIND_PORT/DASHBOARD_FRONTEND_BIND_PORT overrides. The release script will not stop unknown containers." >&2
      exit 2
    fi
  done < <(
    docker ps \
      --filter "publish=$port" \
      --format '{{.ID}}|{{.Label "com.docker.compose.project"}}|{{.Names}}'
  )
done

echo "Remote dashboard host preflight passed for project $project_name"
