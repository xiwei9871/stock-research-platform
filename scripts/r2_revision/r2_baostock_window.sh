#!/bin/bash
# Baostock idle-window jobs: run ONLY when repair driver is paused
# (single baostock session host-wide). Sequence:
#   0) wait until NO r2_repair_batch child process remains (real check,
#      not PID guessing)
#   1) 40-asset stratified REVIEW verification
#   2) 29 ERROR reclass (drop ERROR rows from classification CSV, rerun)
#   3) recompute classification sets
#   4) merge results into canonical r2_disjoint_sets.json (atomic,
#      disjoint + cardinality verified)
# Caller (orchestrator) restarts the repair driver afterwards.
set -euo pipefail
cd "$(dirname "$0")/../.."
BASE=outputs/research/data01r1_finance_q2_20261020
PY=.venv/bin/python

echo "=== waiting for repair batch processes to exit ==="
while pgrep -f 'r2_repair_batch.py' >/dev/null 2>&1; do
    echo "  repair batch still running, wait 15s"
    sleep 15
done
echo "  no repair batch process — baostock is free"

echo "=== review verify (40-asset sample) ==="
$PY scripts/r2_revision/r2_review_verify.py

echo "=== reclassify ERROR assets ==="
$PY - <<'EOF'
import csv
p = "outputs/research/data01r1_finance_q2_20261020/r2_classification.csv"
rows = list(csv.reader(open(p)))
hdr, keep = rows[0], [r for r in rows[1:] if len(r) > 2 and r[2] != "ERROR"]
dropped = len(rows) - 1 - len(keep)
with open(p, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(hdr)
    w.writerows(keep)
print(f"dropped {dropped} ERROR rows for reclassification")
EOF
$PY scripts/r2_revision/r2_classify_batch.py

echo "=== recompute classification sets ==="
$PY - <<'EOF'
import csv, json
from collections import defaultdict
p = "outputs/research/data01r1_finance_q2_20261020/r2_classification.csv"
sets = defaultdict(set)
for r in csv.DictReader(open(p)):
    sets[r["status"]].add(r["asset_id"])
out = {k: sorted(v) for k, v in sets.items()}
json.dump(out, open(
    "outputs/research/data01r1_finance_q2_20261020/r2_classification_sets.json",
    "w"), indent=1)
for k, v in out.items():
    print(k, len(v))
EOF

echo "=== merge into canonical disjoint sets (atomic) ==="
$PY scripts/r2_revision/r2_merge_sets.py
echo "=== window done ==="
