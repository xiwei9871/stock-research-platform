#!/usr/bin/env bash
# L2 weekly NAS backup runner — DESIGN ARTIFACT, pending approval. NOT scheduled.
# Fail-closed hardening over scripts/m2_l2_backup.sh (incident-proven gates).
# Requirements covered: NAS mount verify (no local fallback), capacity fail-closed,
# alert hooks, retention keep-4, credential file, globals sidecar, old-backup mutex,
# never writes to 187 disk.
set -uo pipefail
IMG=postgres:16.4-alpine
NAS_ROOT=/mnt/Public
NAS=$NAS_ROOT/stock_research_backup/L2
LOGDIR=/mnt/data1/stock_research_backup
LOG=$LOGDIR/l2_weekly_$(date +%Y%m%d).log
PGPASS_FILE=${PGPASS_FILE:-/home/jqz/.pgpass_l2}          # chmod 600, host:5432:stock_research:postgres:<pw>
KEEP_GENERATIONS=${KEEP_GENERATIONS:-4}
MIN_NAS_FREE_MB=${MIN_NAS_FREE_MB:-300000}                # ~2x expected artifact
mkdir -p "$LOGDIR"
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
alert(){ # OpenClaw heartbeat / webhook hook — log line is the contract
  log "ALERT[$1]: $2"
  # optional: curl -fsS -m 5 -X POST "$ALERT_WEBHOOK_URL" -d "{\"level\":\"$1\",\"msg\":\"$2\"}" || true
}
fail(){ alert FAIL "$*"; rm -f "$NAS/.tmp_${OUT:-x}"; exit 1; }

log 'weekly L2 runner started (design-validated, scheduled run pending approval)'

# --- Gate 0: NAS mount must be a REAL mount, not a plain dir (no local fallback) ---
mountpoint -q "$NAS_ROOT" || fail "NAS_ROOT $NAS_ROOT not a mountpoint — refusing local fallback"
grep -qE " $NAS_ROOT (cifs|nfs|smb3|fuse\.)" /proc/mounts || fail "NAS_ROOT not a network filesystem"
[ -d "$NAS" ] || fail "NAS L2 dir missing"

# --- Gate 1: mutual exclusion — the legacy same-disk backup must stay stopped ---
LEGACY=$(curl -fsS -m 8 http://192.168.3.187:2375/containers/postgres-backup/json 2>/dev/null \
        | python3 -c 'import json,sys;print(json.load(sys.stdin)["State"]["Status"])' 2>/dev/null || echo unknown)
[ "$LEGACY" = 'exited' ] || fail "legacy postgres-backup container status=$LEGACY (must stay stopped)"

# --- Gate 2: production preflight (read-only) ---
[ -r "$PGPASS_FILE" ] || fail "pgpass file unreadable: $PGPASS_FILE"
export PGPASSFILE=$PGPASS_FILE
docker run --rm $IMG pg_isready -h 192.168.3.187 -p 5432 -U postgres >>"$LOG" 2>&1 || fail 'pg unreachable'
LT=$(docker run --rm -e PGPASSFILE -v $PGPASS_FILE:/root/.pgpass:ro $IMG psql 'host=192.168.3.187 dbname=stock_research user=postgres' -Atc "SELECT count(*) FROM pg_stat_activity WHERE xact_start < now()-interval '10 minutes'") || fail 'precheck query failed'
[ "$LT" = '0' ] || fail "long transactions present: $LT"

# --- Gate 3: capacity fail-closed ---
FREE=$(df -m "$NAS" | awk 'NR==2{print $4}')
[ "$FREE" -ge "$MIN_NAS_FREE_MB" ] || fail "NAS free ${FREE}MB < ${MIN_NAS_FREE_MB}MB"
touch "$NAS/.probe_$$" && rm "$NAS/.probe_$$" || fail 'NAS not writable'

TS=$(date +%Y%m%d_%H%M%S)
OUT=.tmp_full_stock_research_${TS}.dump
GOUT=.tmp_globals_${TS}.sql.gz
log "preflight ok; NAS free ${FREE}MB; starting dump"

( while true; do
    SZ=$(stat -c%s "$NAS/$OUT" 2>/dev/null || echo 0)
    PROD=$(docker run --rm -e PGPASSFILE -v $PGPASS_FILE:/root/.pgpass:ro $IMG psql 'host=192.168.3.187 dbname=stock_research user=postgres' -Atc "SELECT count(*) FILTER (WHERE state='active'), count(*) FROM pg_stat_activity" 2>/dev/null | head -1)
    log "monitor: out=${SZ}B prod_active/total=$PROD"
    sleep 120
  done ) & MONPID=$!

docker run --rm --name m2_l2_dump -e PGPASSFILE -v $PGPASS_FILE:/root/.pgpass:ro \
  -v $NAS:/backup/L2 $IMG \
  pg_dump -h 192.168.3.187 -U postgres -d stock_research -Fc \
  -f /backup/L2/$OUT >>"$LOG" 2>&1
RC=$?
kill $MONPID 2>/dev/null
log "dump exit rc=$RC size=$(stat -c%s "$NAS/$OUT" 2>/dev/null || echo 0)"
[ $RC -eq 0 ] || fail "pg_dump rc=$RC"

# --- globals sidecar (roles/tablespaces — pg_dump does not cover them) ---
docker run --rm -e PGPASSFILE -v $PGPASS_FILE:/root/.pgpass:ro -v $NAS:/backup/L2 $IMG \
  sh -c "pg_dumpall -h 192.168.3.187 -U postgres --globals-only | gzip > /backup/L2/$GOUT" >>"$LOG" 2>&1 \
  || fail 'globals dump failed'
mv "$NAS/$GOUT" "$NAS/globals_${TS}.sql.gz"

# --- verify + promote ---
SHA=$(sha256sum "$NAS/$OUT" | awk '{print $1}')
docker run --rm -v $NAS:/backup $IMG pg_restore -l /backup/$OUT > "$NAS/$OUT.list" || fail 'pg_restore -l failed'
SCHEMAS=$(grep -c 'SCHEMA' "$NAS/$OUT.list")
[ "$SCHEMAS" -ge 20 ] || fail "schema count $SCHEMAS < 20"
mv "$NAS/$OUT" "$NAS/full_stock_research_${TS}.dump"
echo "$SHA  full_stock_research_${TS}.dump" > "$NAS/full_stock_research_${TS}.dump.sha256"
mv "$NAS/$OUT.list" "$NAS/full_stock_research_${TS}.dump.list"
cat > "$NAS/MANIFEST_L2_${TS}.json" <<EOF2
{"file":"full_stock_research_${TS}.dump","sha256":"$SHA","globals":"globals_${TS}.sql.gz",
 "bytes":$(stat -c%s "$NAS/full_stock_research_${TS}.dump"),
 "source":"192.168.3.187 stock_research pg16.13","scope":"full-database+globals",
 "tool":"pg_dump -Fc (pg16 docker)","created":"$(date -Iseconds)","verdict":"L2_BACKUP_VERIFIED"}
EOF2

# --- retention: keep last KEEP_GENERATIONS, delete oldest only inside L2 naming space ---
ls -1t "$NAS"/full_stock_research_*.dump 2>/dev/null | tail -n +$((KEEP_GENERATIONS+1)) | while read -r old; do
  base=$(basename "$old" .dump)
  log "retention: removing $base"
  rm -f "$old" "$old.sha256" "$old.list" "$NAS/MANIFEST_L2_${base#full_stock_research_}.json"
done
ls -1t "$NAS"/globals_*.sql.gz 2>/dev/null | tail -n +$((KEEP_GENERATIONS+1)) | xargs -r rm -f

alert SUCCESS "L2 weekly backup verified: full_stock_research_${TS}.dump ($SHA)"
log 'done'
