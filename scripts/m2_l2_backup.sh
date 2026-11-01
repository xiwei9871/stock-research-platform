#!/usr/bin/env bash
# M2 B0-B L2 full-db backup runner — scope-locked, stop-capable.
set -uo pipefail
IMG=postgres:16.4-alpine
NAS=/mnt/Public/stock_research_backup/L2
LOGDIR=/mnt/data1/stock_research_backup
LOG=$LOGDIR/l2_run_$(date +%Y%m%d).log
mkdir -p "$LOGDIR"
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

in_window(){ local n=$(date +%H%M); [ "$n" -ge 2230 ] || [ "$n" -lt 900 ]; }
past_deadline(){ local n=$(date +%H%M); [ "$n" -ge 900 ] && [ "$n" -lt 2230 ]; }

log 'runner started; waiting for 22:30-09:00 window'
while ! in_window; do sleep 60; done
log 'in window; running preflight'

TS=$(date +%Y%m%d_%H%M%S)
OUT=.tmp_full_stock_research_${TS}.dump
fail(){ log "FAIL: $*"; rm -f "$NAS/$OUT"; exit 1; }

# preflight inside window
docker run --rm $IMG pg_isready -h 192.168.3.187 -p 5432 -U postgres >>"$LOG" 2>&1 || fail 'pg unreachable'
LT=$(docker run --rm -e PGPASSWORD=mqkj1234 $IMG psql 'host=192.168.3.187 dbname=stock_research user=postgres' -Atc "SELECT count(*) FROM pg_stat_activity WHERE xact_start < now()-interval '10 minutes'") || fail 'precheck query failed'
[ "$LT" = '0' ] || fail "long transactions present: $LT"
FREE=$(df -m "$NAS" | awk 'NR==2{print $4}')
[ "$FREE" -ge 500000 ] || fail "NAS free ${FREE}MB < 500GB threshold"
touch "$NAS/.probe_$$" && rm "$NAS/.probe_$$" || fail 'NAS not writable'
log "preflight ok; NAS free ${FREE}MB; starting dump $OUT"

# monitor loop: prod activity + output size every 120s
( while true; do
    SZ=$(stat -c%s "$NAS/$OUT" 2>/dev/null || echo 0)
    ACT=$(docker exec m2_l2_dump true 2>/dev/null && echo alive || echo gone)
    PROD=$(docker run --rm -e PGPASSWORD=mqkj1234 $IMG psql 'host=192.168.3.187 dbname=stock_research user=postgres' -Atc "SELECT count(*) FILTER (WHERE state='active'), count(*) FROM pg_stat_activity" 2>/dev/null | head -1)
    log "monitor: out=${SZ}B container=$ACT prod_active/total=$PROD"
    sleep 120
  done ) & MONPID=$!

# deadline killer
( while ! past_deadline; do sleep 120; done
  log 'DEADLINE 09:00 reached — killing dump'
  docker kill m2_l2_dump 2>/dev/null ) & KILLER=$!

log 'dump started'
docker run --rm --name m2_l2_dump -e PGPASSWORD=mqkj1234   -v /mnt/Public/stock_research_backup/L2:/backup/L2 $IMG   pg_dump -h 192.168.3.187 -U postgres -d stock_research -Fc   -f /backup/L2/$OUT >>"$LOG" 2>&1
RC=$?
kill $MONPID $KILLER 2>/dev/null
log "dump exit rc=$RC size=$(stat -c%s "$NAS/$OUT" 2>/dev/null || echo 0)"
[ $RC -eq 0 ] || fail "pg_dump rc=$RC"

SHA=$(sha256sum "$NAS/$OUT" | awk '{print $1}')
log "sha256=$SHA"
docker run --rm -v $NAS:/backup $IMG pg_restore -l /backup/$OUT > "$NAS/$OUT.list" || fail 'pg_restore -l failed'
grep -c 'SCHEMA' "$NAS/$OUT.list" >>"$LOG" 2>&1
mv "$NAS/$OUT" "$NAS/full_stock_research_${TS}.dump"
echo "$SHA  full_stock_research_${TS}.dump" > "$NAS/full_stock_research_${TS}.dump.sha256"
mv "$NAS/$OUT.list" "$NAS/full_stock_research_${TS}.dump.list"
cat > "$NAS/MANIFEST_L2_${TS}.json" <<EOF2
{"file":"full_stock_research_${TS}.dump","sha256":"$SHA",
 "bytes":$(stat -c%s "$NAS/full_stock_research_${TS}.dump"),
 "source":"192.168.3.187 stock_research pg16.13",
 "scope":"full-database","tool":"pg_dump -Fc (pg16.4 docker)",
 "created":"$(date -Iseconds)","verdict":"L2_BACKUP_VERIFIED"}
EOF2
log 'L2_BACKUP_VERIFIED — manifest written'
