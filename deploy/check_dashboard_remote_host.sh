#!/usr/bin/env bash
set -euo pipefail

project_name="${1:?compose project name is required}"
api_port="${2:?API bind port is required}"
frontend_port="${3:?frontend bind port is required}"

if [[ ! "$project_name" =~ ^[a-z0-9][a-z0-9_-]*$ ]]; then
  echo "Invalid compose project name: $project_name" >&2
  exit 2
fi

docker compose version >/dev/null
docker compose ls --format json >/dev/null

while IFS='|' read -r container_id owner_service container_name container_status; do
  [[ -n "$container_id" ]] || continue
  case "$owner_service" in
    api|dashboard) ;;
    *)
      echo "Compose project $project_name contains unsupported service=${owner_service:-unknown} container $container_name ($container_id, $container_status); manual migration required before canonical release." >&2
      echo "Inspect and remove the orphan explicitly. The release script will not let --remove-orphans delete an unreviewed service." >&2
      exit 2
      ;;
  esac
done < <(
  docker ps -a \
    --filter "label=com.docker.compose.project=$project_name" \
    --format '{{.ID}}|{{.Label "com.docker.compose.service"}}|{{.Names}}|{{.Status}}'
)

listener_exists() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -H -ltn "sport = :$port" 2>/dev/null | grep -q .
    return
  fi
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | grep -q .
    return
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -lnt 2>/dev/null | awk -v suffix=":$port" '$4 ~ suffix "$" { found=1 } END { exit !found }'
    return
  fi
  echo "Cannot inspect host listeners: ss, lsof, and netstat are unavailable" >&2
  exit 2
}

check_port() {
  local port="$1"
  local expected_service="$2"
  local allowed_count=0
  local container_id owner_project owner_service container_name

  if [[ ! "$port" =~ ^[0-9]+$ ]] || (( port < 1 || port > 65535 )); then
    echo "Invalid dashboard bind port: $port" >&2
    exit 2
  fi

  while IFS='|' read -r container_id owner_project owner_service container_name; do
    [[ -n "$container_id" ]] || continue
    if [[ "$owner_project" != "$project_name" || "$owner_service" != "$expected_service" ]]; then
      owner_label="${owner_project:-non-compose container}"
      echo "Dashboard port $port is occupied by $container_name ($container_id), owner=$owner_label service=${owner_service:-unknown}; expected service=$expected_service; migration required before canonical release." >&2
      echo "Inspect the owner and stop it explicitly, or choose approved DASHBOARD_API_BIND_PORT/DASHBOARD_FRONTEND_BIND_PORT overrides. The release script will not stop unknown containers." >&2
      exit 2
    fi
    allowed_count=$((allowed_count + 1))
  done < <(
    docker ps \
      --filter "publish=$port" \
      --format '{{.ID}}|{{.Label "com.docker.compose.project"}}|{{.Label "com.docker.compose.service"}}|{{.Names}}'
  )

  if (( allowed_count > 1 )); then
    echo "Dashboard port $port is published by multiple $project_name/$expected_service containers; migration required before canonical release." >&2
    exit 2
  fi
  if (( allowed_count == 0 )) && listener_exists "$port"; then
    echo "Dashboard port $port has a non-Docker listener and no allowed $project_name/$expected_service container; migration required before canonical release." >&2
    exit 2
  fi
}

check_port "$api_port" api
check_port "$frontend_port" dashboard

echo "Remote dashboard host preflight passed for project $project_name"
