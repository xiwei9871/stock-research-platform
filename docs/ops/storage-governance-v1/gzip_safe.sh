#!/usr/bin/env bash
# Safe gzip: hash -> compress to tmp -> verify decompressed hash -> atomic mv -> rm orig
# Usage: gzip_safe.sh <file> [<file>...] — appends manifest rows to $MANIFEST
set -euo pipefail
MANIFEST="${MANIFEST:-/Users/xiwei/stock_research/docs/ops/storage-governance-v1/compression_manifest.csv}"
[ -f "$MANIFEST" ] || echo "path,orig_sha256,gz_sha256,orig_bytes,gz_bytes,saved_bytes,recovery,status" >> "$MANIFEST"

for f in "$@"; do
  [ -f "$f" ] || { echo "SKIP missing: $f"; continue; }
  orig_sha=$(shasum -a 256 "$f" | awk '{print $1}')
  orig_size=$(stat -f %z "$f")
  tmp="$f.gz.tmp"
  gzip -9 -c "$f" > "$tmp"
  check_sha=$(gunzip -c "$tmp" | shasum -a 256 | awk '{print $1}')
  if [ "$check_sha" != "$orig_sha" ]; then
    rm -f "$tmp"
    echo "FAIL verify: $f"
    echo "$f,$orig_sha,,$orig_size,,,gunzip -k $f.gz,verify_failed" >> "$MANIFEST"
    continue
  fi
  mv "$tmp" "$f.gz"          # atomic on same fs
  rm "$f"                  # original only removed AFTER verified .gz exists
  gz_sha=$(shasum -a 256 "$f.gz" | awk '{print $1}')
  gz_size=$(stat -f %z "$f.gz")
  saved=$((orig_size - gz_size))
  printf "%s,%s,%s,%s,%s,%s,%s,%s\n" "$f" "$orig_sha" "$gz_sha" "$orig_size" "$gz_size" "$saved" "gunzip -k '$f.gz'" "ok" >> "$MANIFEST"
  echo "OK $f -> $f.gz  saved=$((saved/1048576))MB"
done
