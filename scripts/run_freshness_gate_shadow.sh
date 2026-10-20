#!/bin/bash
# Freshness Gate — daily SHADOW sweep (read-only; no enforcement, no DB writes).
# Emits a CSV + JSON health report per run. Safe to add to cron AFTER approval.
set -euo pipefail

cd /Users/xiwei/stock_research
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
AS_OF="${1:-$(date +%F)}"
OUT_DIR="${FRESHNESS_GATE_OUTPUT_DIR:-outputs/research/freshness_gate_shadow}"
mkdir -p "$OUT_DIR"

"$PYTHON_BIN" - "$AS_OF" "$OUT_DIR" <<'PY'
import json, sys
from stock_research.data_freshness_gate import run_freshness_sweep

as_of, out_dir = sys.argv[1], sys.argv[2]
csv_path = f"{out_dir}/data_freshness_health_{as_of.replace('-', '')}.csv"
rows = run_freshness_sweep(as_of_date=as_of, output_path=csv_path)
counts = {}
for r in rows:
    counts[r["freshness_status"]] = counts.get(r["freshness_status"], 0) + 1
summary = {"as_of_date": as_of, "inputs": len(rows), "status_counts": counts, "report": csv_path}
with open(f"{out_dir}/data_freshness_health_{as_of.replace('-', '')}.json", "w") as fh:
    json.dump({"summary": summary, "rows": rows}, fh, indent=2, default=str)
print("freshness_gate_shadow|" + json.dumps(summary, ensure_ascii=False))
PY
