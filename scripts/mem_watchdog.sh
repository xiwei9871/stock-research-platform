#!/usr/bin/env bash
# mem_watchdog.sh — RSS watchdog for heavy research Python jobs.
#
# Context: 2026-10-26 the machine panicked (WindowServer watchdog timeout)
# after three concurrent Python jobs grew to ~28/20/14 GB on a 16 GB box,
# driving 42 swapfiles and the compressor to 100% of its segment limit.
#
# Behavior: every INTERVAL seconds scan user processes whose comm is a Python
# interpreter. Any process exceeding KILL_RSS_MB gets SIGTERM, then SIGKILL
# after GRACE_SECONDS if still alive. Processes on the exclude regex are
# never touched. All actions append to logs/mem_watchdog.log.
#
# Run modes:
#   mem_watchdog.sh          -> foreground loop (this is what launchd runs)
#   mem_watchdog.sh --once   -> single scan, print what it would do (dry-run)

set -u

ROOT="${MEM_WATCHDOG_ROOT:-/Users/xiwei/stock_research}"
LOG_DIR="$ROOT/logs"
LOG="$LOG_DIR/mem_watchdog.log"
INTERVAL="${MEM_WATCHDOG_INTERVAL_SECONDS:-15}"
WARN_RSS_MB="${MEM_WATCHDOG_WARN_MB:-6144}"
KILL_RSS_MB="${MEM_WATCHDOG_KILL_MB:-10240}"
GRACE_SECONDS="${MEM_WATCHDOG_GRACE_SECONDS:-20}"
# processes matching this regex in their args are never killed
EXCLUDE_RE="${MEM_WATCHDOG_EXCLUDE_RE:-Devin|pyright|language_server|jupyter|ipkernel|mem_watchdog|pgAdmin|postgres -D}"
# only watch processes whose args match this regex (heavy batch jobs); empty
# means every Python process
WATCH_RE="${MEM_WATCHDOG_WATCH_RE:-}"

mkdir -p "$LOG_DIR"

log() { printf '%s mem_watchdog|%s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }

scan_once() {
  # pid rss(KB) args — one pass over user processes; match the interpreter
  # path (first token of args), since macOS truncates comm to ~15 chars
  ps -axo pid=,rss=,args= -U "$(id -un)" | while read -r pid rss args; do
    exe="${args%% *}"
    case "$exe" in
      *ython*|*Python*) : ;;  # interpreters only
      *) continue ;;
    esac
    [[ "$args" =~ $EXCLUDE_RE ]] && continue
    if [[ -n "$WATCH_RE" && ! "$args" =~ $WATCH_RE ]]; then continue; fi
    mb=$((rss / 1024))
    if (( mb > KILL_RSS_MB )); then
      log "KILL|pid=$pid|rss=${mb}MB|args=${args:0:200}"
      kill -TERM "$pid" 2>/dev/null || continue
      # SIGKILL on the next scan pass if still alive (~INTERVAL grace)
      echo "$pid" >>"$LOG_DIR/.mem_watchdog_pending_kill"
    elif (( mb > WARN_RSS_MB )); then
      log "WARN|pid=$pid|rss=${mb}MB|args=${args:0:160}"
    fi
  done

  # grace-kill pass: pids still alive after TERM get KILL
  if [[ -s "$LOG_DIR/.mem_watchdog_pending_kill" ]]; then
    while read -r pid; do
      if kill -0 "$pid" 2>/dev/null; then
        log "SIGKILL|pid=$pid|still alive after ${GRACE_SECONDS}s grace"
        kill -KILL "$pid" 2>/dev/null || true
      fi
    done <"$LOG_DIR/.mem_watchdog_pending_kill"
    : >"$LOG_DIR/.mem_watchdog_pending_kill"
  fi
}

if [[ "${1:-}" == "--once" ]]; then
  MEM_WATCHDOG_DRYRUN=1 scan_once
  exit 0
fi

log "START|interval=${INTERVAL}s|warn=${WARN_RSS_MB}MB|kill=${KILL_RSS_MB}MB"
while true; do
  scan_once
  sleep "$INTERVAL"
done
