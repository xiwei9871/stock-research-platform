#!/usr/bin/env bash
# M2.0.1 B0 — production backup plan (DRY-RUN by default).
#
# Prints the exact commands for the recommended layered backup without
# executing them. To actually run, a SEPARATE approval (B0-B) is
# required and EXECUTE=1 must be set by the operator.
#
# Layers:
#   L1 critical-table logical backup (pg_dump -Fc per table)
#   L2 full-database logical backup (pg_dump -Fc, off-peak)
#   L3 physical base backup (pg_basebackup) — needs archive/WAL plan
#
# Targets: prod PG 192.168.3.187:5432 db=stock_research (~686GB)
# Landing: NAS //192.168.3.253 mounted on stock-prod (185).
set -euo pipefail

PGHOST="${PGHOST:-192.168.3.187}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-postgres}"
PGDB="${PGDB:-stock_research}"
DEST="${BACKUP_DEST:-/mnt/data1/stock_research_backup}"
STAMP="$(date +%Y%m%d_%H%M%S)"

echo "== M2.0.1 backup plan (EXECUTE=${EXECUTE:-0}) =="
echo "target : $PGUSER@$PGHOST:$PGPORT/$PGDB"
echo "dest   : $DEST (run on stock-prod or a host that can write NAS)"
echo

run() {
  echo "+ $*"
  if [ "${EXECUTE:-0}" = "1" ]; then eval "$@"; fi
}

echo "-- L1: critical business table (asset_status_daily ~3GB) --"
run "mkdir -p '$DEST/L1'"
run "pg_dump -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDB -Fc -v \\
  -t core.asset_status_daily \\
  -f '$DEST/L1/asset_status_daily_${STAMP}.dump'"
run "pg_restore -l '$DEST/L1/asset_status_daily_${STAMP}.dump' \\
  > '$DEST/L1/asset_status_daily_${STAMP}.list'"
run "sha256sum '$DEST/L1/asset_status_daily_${STAMP}.dump' \\
  | tee '$DEST/L1/asset_status_daily_${STAMP}.sha256'"

echo
echo "-- L2: finance raw payloads + finver (future) --"
run "pg_dump -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDB -Fc -v \\
  -t raw_akshare.finance_payload -t finver.* \\
  -f '$DEST/L1/finance_version_${STAMP}.dump' || true"

echo
echo "-- L3: FULL database logical dump (~686GB, off-peak, long) --"
echo "# NOT in default plan — requires B0-B approval + resource window."
run "echo 'pg_dump -Fc (full db) -> $DEST/L3/full_${STAMP}.dump'"

echo
echo "-- L4: physical base backup (after WAL archiving approved) --"
run "echo 'pg_basebackup -h $PGHOST -D $DEST/L4/base_${STAMP} -Ft -z -P'"

echo
echo "Post-backup verification (ALWAYS):"
echo "  1) pg_restore -l on every .dump (header parse)"
echo "  2) sha256 recorded next to file"
echo "  3) restore drill into INDEPENDENT instance, checksum compare"
echo "  4) BACKUP_FOUND != RESTORE_VERIFIED — a file is not a recovery"
