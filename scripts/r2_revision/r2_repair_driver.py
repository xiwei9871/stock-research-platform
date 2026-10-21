"""R2 overnight repair driver (hardened v2).

- fcntl.flock single-instance: a second driver refuses to start, so no two
  baostock sessions can ever be spawned by this driver.
- Repair pool comes from the disjoint-set file (post-fix classification);
  NEEDS_REVIEW / ERROR / ALREADY_CORRECT / REPAIRED are excluded.
- An asset counts as done ONLY when a batch report marks it COMPLETE
  (writes committed AND in-loop post-diff == 0). Assets with revision
  writes but no COMPLETE stay in the queue — re-processing is idempotent
  (live fetch → 0 updates → COMPLETE, ~seconds).
- Pause flag file `r2_driver_pause.flag` is honored between batches.
- Batches are 100 assets, one baostock subprocess at a time, 60-min hard
  cap per batch; per-asset commits mean a killed batch loses nothing.

Usage: r2_repair_driver.py
"""
from __future__ import annotations

import fcntl
import glob
import json
import os
import re
import subprocess
import sys
import time

BASE = "outputs/research/data01r1_finance_q2_20261020"
SETS_FILE = f"{BASE}/r2_disjoint_sets.json"
LOCK_FILE = f"{BASE}/r2_repair_driver.lock"
PAUSE_FLAG = f"{BASE}/r2_driver_pause.flag"
REPAIR_SCRIPT = "scripts/r2_revision/r2_repair_batch.py"
CHUNK = 100
BATCH_TIMEOUT_S = 60 * 60


def completed_assets() -> set[str]:
    """Report-COMPLETE assets, plus legacy repairs identified by revision
    source rows (b1/b2/samples predate per-asset status reports and were
    verified by separate post-diff runs)."""
    done: set[str] = set()
    for p in glob.glob(f"{BASE}/r2_repair_*.json"):
        try:
            d = json.load(open(p))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict):
            done.update(
                k for k, v in d.items()
                if k.startswith("CN:") and isinstance(v, dict)
                and v.get("status") == "COMPLETE"
            )
    sys.path.insert(0, "src")
    from stock_research.db import connect, fetch_all
    with connect("stock_research") as conn:
        done.update(
            r["asset_id"] for r in fetch_all(
                conn, "SELECT DISTINCT asset_id FROM market_daily_bar "
                      "WHERE source='baostock_revision_r2'"))
    return done


def next_batch_no() -> int:
    n = 1
    for p in glob.glob(f"{BASE}/r2_batch_b*_assets.txt"):
        m = re.search(r"_b(\d+)_assets", p)
        if m:
            n = max(n, int(m.group(1)) + 1)
    return n


def main() -> None:
    lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("another r2_repair_driver holds the lock — refusing to start")
        raise SystemExit(2)

    dirty = set(json.load(open(SETS_FILE))["CONFIRMED_DIRTY"])
    batch_no = next_batch_no()

    for pass_no in range(3):
        done = completed_assets()
        remaining = sorted(dirty - done)
        if not remaining:
            break
        print(f"confirmed dirty: {len(dirty)} | pass {pass_no+1} "
              f"remaining: {len(remaining)}", flush=True)
        for i in range(0, len(remaining), CHUNK):
            if os.path.exists(PAUSE_FLAG):
                print("pause flag present — stopping after current batch", flush=True)
                return
            chunk = remaining[i:i + CHUNK]
            batch_id = f"b{batch_no}"
            batch_no += 1
            list_path = f"{BASE}/r2_batch_{batch_id}_assets.txt"
            with open(list_path, "w") as f:
                f.write("\n".join(chunk))
            print(f"=== batch {batch_id} ({len(chunk)} assets) "
                  f"start {time.strftime('%H:%M:%S')}", flush=True)
            t0 = time.time()
            try:
                proc = subprocess.run(
                    [sys.executable, REPAIR_SCRIPT, batch_id, f"file:{list_path}"],
                    timeout=BATCH_TIMEOUT_S,
                    capture_output=True, text=True,
                )
                tail = proc.stdout.strip().splitlines()[-6:] if proc.stdout else []
                for line in tail:
                    print("  " + line, flush=True)
                if proc.returncode != 0:
                    print(f"!! batch {batch_id} exit={proc.returncode} "
                          f"stderr={proc.stderr[-300:] if proc.stderr else ''}", flush=True)
            except subprocess.TimeoutExpired:
                print(f"!! batch {batch_id} TIMEOUT after {BATCH_TIMEOUT_S}s — "
                      "committed assets still safe (per-asset commits)", flush=True)
            print(f"=== batch {batch_id} done in {time.time()-t0:.0f}s "
                  f"total_complete={len(completed_assets())}", flush=True)
    print("driver finished")


if __name__ == "__main__":
    main()
