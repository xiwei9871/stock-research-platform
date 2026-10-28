#!/usr/bin/env bash
# STORAGE-R1 / B0-C: restore L2 dump on 185 isolated instance (no prod touch)
set -uo pipefail
IMG=postgres:16.4-alpine
NAS=/mnt/Public/stock_research_backup/L2
DUMP=full_stock_research_20261028_081226.dump
PGD=/mnt/data1/l2_restore/pgdata
LOG=/mnt/data1/stock_research_backup/l2_restore_20261028.log
log(){ echo "[$(date '+%F %T')] $*" >>"$LOG"; }
fail(){ log "FAIL: $*"; exit 1; }

cd "$NAS" || fail 'NAS unreachable'
sha256sum -c "$DUMP.sha256" >>"$LOG" 2>&1 || fail 'sha256 mismatch'
log 'sha256 verified on NAS'

[ -d "$PGD" ] && [ "$(ls -A "$PGD" 2>/dev/null | wc -l)" -gt 0 ] && fail "pgdata not empty: $PGD"
mkdir -p "$PGD"
AVAIL=$(df -m /mnt/data1 | awk 'NR==2{print $4}')
[ "$AVAIL" -ge 800000 ] || fail "data1 free ${AVAIL}MB < 800GB"
log "preflight ok; data1 free ${AVAIL}MB"

docker rm -f m2_l2_restore 2>/dev/null
docker run -d --name m2_l2_restore -e POSTGRES_PASSWORD=l2drill_pw \
  -v "$PGD":/var/lib/postgresql/data \
  -v "$NAS":/backup:ro \
  -p 127.0.0.1:55432:5432 \
  $IMG -c wal_level=minimal -c max_wal_senders=0 -c archive_mode=off \
       -c fsync=off -c synchronous_commit=off -c autovacuum=off \
       -c max_wal_size=2048 -c checkpoint_timeout=60 >>"$LOG" 2>&1 || fail 'docker run'
for i in $(seq 1 60); do
  docker exec m2_l2_restore pg_isready -U postgres >>"$LOG" 2>&1 && break; sleep 2
done
docker exec m2_l2_restore psql -U postgres -qc 'CREATE DATABASE stock_research_drill' >>"$LOG" 2>&1 || fail 'create db'
log 'db created; restore starting (pg_restore -j6)'

( while docker exec m2_l2_restore true >/dev/null 2>&1; do
    SZ=$(du -sm "$PGD" 2>/dev/null | awk '{print $1}')
    AV=$(df -m /mnt/data1 | awk 'NR==2{print $4}')
    log "monitor: pgdata=${SZ}MB data1_free=${AV}MB"
    [ "$AV" -lt 150000 ] && { log 'DISK GUARD: free<150GB — killing container'; docker kill m2_l2_restore; break; }
    sleep 300
  done ) &

docker exec m2_l2_restore pg_restore -U postgres -d stock_research_drill -j6 --no-owner --no-privileges "/backup/$DUMP" >>"$LOG" 2>&1
RC=$?
log "pg_restore exit rc=$RC"
[ $RC -eq 0 ] && log 'RESTORE_COMPLETE' || log 'RESTORE_ERRORS (inspect log; rc!=0 often = benign extension/stmt warnings)'
