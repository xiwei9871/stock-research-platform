#!/usr/bin/env bash
# Cross-batch PDF dedup via hardlink: re-verify sha256 per path, then replace
# duplicate inodes with hardlinks to the canonical copy. All paths stay valid.
# Usage: dedup_hardlink.sh <dup_groups.csv> [--apply]  (default dry-run)
set -euo pipefail
ROOT="/Users/xiwei/stock_research"
CSV="${1:?dup_groups.csv}"
APPLY="${2:-}"
MANIFEST="${MANIFEST:-$ROOT/docs/ops/storage-governance-v1/dedup_manifest.csv}"

python3 - "$CSV" <<'PY' > /tmp/dedup_groups.txt
import csv, sys
groups = {}
with open(sys.argv[1]) as fh:
    for row in csv.DictReader(fh):
        groups.setdefault(row["sha256"], []).append(row["path"])
for sha, paths in groups.items():
    uniq = list(dict.fromkeys(paths))
    if len(uniq) > 1:
        print(sha + "\t" + "\t".join(uniq))
PY

total_saved=0
[ -f "$MANIFEST" ] || echo "sha256,canonical,linked_path,size_bytes,status" > "$MANIFEST"
while IFS=$'\t' read -r sha canonical rest; do
  [ -f "$ROOT/$canonical" ] || { echo "SKIP missing canonical $canonical"; continue; }
  csha=$(shasum -a 256 "$ROOT/$canonical" | awk '{print $1}')
  [ "${csha:0:16}" = "$sha" ] || { echo "SKIP sha mismatch canonical $canonical"; continue; }
  for dup in $(echo "$rest" | tr '\t' ' '); do
    [ -f "$ROOT/$dup" ] || continue
    [ "$dup" = "$canonical" ] && continue
    dsha=$(shasum -a 256 "$ROOT/$dup" | awk '{print $1}')
    [ "$dsha" = "$csha" ] || { echo "SKIP content drift $dup"; continue; }
    sz=$(stat -f %z "$ROOT/$dup")
    if [ "$APPLY" = "--apply" ]; then
      ln -f "$ROOT/$canonical" "$ROOT/$dup"
      printf "%s,%s,%s,%s,hardlinked\n" "$sha" "$canonical" "$dup" "$sz" >> "$MANIFEST"
      echo "LINK $dup -> $canonical"
    else
      echo "DRY  $dup ($((sz/1048576))MB) -> $canonical"
    fi
    total_saved=$((total_saved + sz))
  done
done < /tmp/dedup_groups.txt
echo "=== ${APPLY:-dry} total potential savings: $((total_saved/1048576))MB ==="
