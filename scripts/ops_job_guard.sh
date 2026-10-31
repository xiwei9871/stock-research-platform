#!/usr/bin/env bash
# Minimal runtime protection for launchd jobs (EOD recovery 2026-11-02).
# Source this file, then:
#   ops_preflight <job_name> [python_bin]   -> exit 1 on env failure (alert written)
#   ops_record <job_name> <rc> [artifact]   -> update status/alerts; call via trap
#
# State lives under logs/ops/ (JSON per job). First failure -> WARN alert file;
# two consecutive failed runs -> CRITICAL alert file. Success records
# last_success_date + artifact and clears failure counters.

OPS_GUARD_ROOT="${OPS_GUARD_ROOT:-/Users/xiwei/stock_research}"
OPS_GUARD_STATE_DIR="${OPS_GUARD_STATE_DIR:-$OPS_GUARD_ROOT/logs/ops}"

ops_guard_now() { date '+%Y-%m-%dT%H:%M:%S%z'; }

ops_preflight() {
  local job="$1" py="${2:-$OPS_GUARD_ROOT/.venv/bin/python}"
  mkdir -p "$OPS_GUARD_STATE_DIR"
  local sha; sha="$(git -C "$OPS_GUARD_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  if [[ ! -x "$py" ]]; then
    ops_record_fail "$job" "preflight: missing interpreter $py (sha=$sha)"
    echo "OPS_PREFLIGHT_FAIL job=$job missing_python=$py sha=$sha" >&2
    return 1
  fi
  if ! "$py" -c "import pandas,psycopg,tabulate,requests" 2>>"$OPS_GUARD_STATE_DIR/${job}.preflight.err"; then
    ops_record_fail "$job" "preflight: import check failed sha=$sha: $(tail -1 "$OPS_GUARD_STATE_DIR/${job}.preflight.err" 2>/dev/null)"
    echo "OPS_PREFLIGHT_FAIL job=$job import_check sha=$sha" >&2
    return 1
  fi
  echo "OPS_PREFLIGHT_OK job=$job sha=$sha ts=$(ops_guard_now)"
  return 0
}

ops_record_fail() {
  local job="$1" msg="$2"
  mkdir -p "$OPS_GUARD_STATE_DIR"
  local f="$OPS_GUARD_STATE_DIR/${job}.json"
  local fails=1
  if [[ -f "$f" ]]; then
    fails=$(( $(grep -o '"consecutive_failures":[0-9]*' "$f" | cut -d: -f2 || echo 0) + 1 ))
  fi
  cat > "$f" <<EOF
{"job":"$job","state":"FAILED","consecutive_failures":$fails,"last_failure_ts":"$(ops_guard_now)","last_failure_reason":$(ops_json_str "$msg"),"git_sha":"$(git -C "$OPS_GUARD_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"}
EOF
  local level=WARN sev=first_failure
  if (( fails >= 2 )); then level=CRITICAL; sev=consecutive_failures; fi
  cat > "$OPS_GUARD_STATE_DIR/ALERT_${job}_${level}" <<EOF
level=$level
job=$job
severity=$sev
consecutive_failures=$fails
ts=$(ops_guard_now)
detail=$msg
EOF
}

ops_json_str() { printf '"%s"' "${1//\"/\\\"}"; }

ops_record() {
  local job="$1" rc="$2" artifact="${3:-}"
  mkdir -p "$OPS_GUARD_STATE_DIR"
  local f="$OPS_GUARD_STATE_DIR/${job}.json"
  if [[ "$rc" == "0" ]]; then
    cat > "$f" <<EOF
{"job":"$job","state":"OK","consecutive_failures":0,"last_success_date":"$(date '+%Y-%m-%d')","last_success_ts":"$(ops_guard_now)","artifact":$(ops_json_str "$artifact"),"git_sha":"$(git -C "$OPS_GUARD_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"}
EOF
    rm -f "$OPS_GUARD_STATE_DIR/ALERT_${job}_WARN" "$OPS_GUARD_STATE_DIR/ALERT_${job}_CRITICAL"
  else
    ops_record_fail "$job" "exit_code=$rc artifact=$artifact"
  fi
}

# Staleness check (manual/health-check use): exit 1 if last success is older
# than N calendar days or no success recorded.
ops_check_stale() {
  local job="$1" max_age_days="${2:-3}"
  local f="$OPS_GUARD_STATE_DIR/${job}.json"
  if [[ ! -f "$f" ]] || ! grep -q '"state":"OK"' "$f"; then
    echo "STALE job=$job no_success_record" >&2; return 1
  fi
  local d; d="$(grep -o '"last_success_date":"[^"]*"' "$f" | cut -d'"' -f4)"
  local age=$(( ( $(date +%s) - $(date -j -f %Y-%m-%d "$d" +%s 2>/dev/null || echo 0) ) / 86400 ))
  if (( age > max_age_days )); then
    echo "STALE job=$job last_success=$d age_days=$age" >&2; return 1
  fi
}
