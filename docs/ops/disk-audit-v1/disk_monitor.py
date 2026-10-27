#!/usr/bin/env python3
"""disk_monitor.py — lightweight disk-capacity monitor (read-only).

Design per storage-governance task spec phase D. Emits one JSON line per
check to a log file plus a summary line to stdout, so it can be driven by
cron, launchd, or run manually. NOT installed anywhere by default.

Thresholds (Data volume free space):
    <30 GiB WARNING | <15 GiB CRITICAL | <8 GiB EMERGENCY

Also tracks a watchlist of project dirs and flags the fastest-growing ones
versus the previous run's state file.

Usage:
    python3 disk_monitor.py
    python3 disk_monitor.py --state ~/.cache/disk_monitor_state.json \
        --log ~/stock_research/logs/disk_monitor.jsonl
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_VOLUME = "/System/Volumes/Data"
WARN_GIB, CRIT_GIB, EMERG_GIB = 30.0, 15.0, 8.0

WATCH_DIRS = [
    "~/northshore_property_watchdog/data",
    "~/northshore_property_watchdog/outputs",
    "~/stock_research/outputs/research",
    "~/Library/Application Support/Claude-3p",
    "~/.local/share/devin",
    "~/.codex",
    "~/Library/Caches",
    "~/interior_design",
]


def du_gb(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["du", "-sk", str(path)], capture_output=True, text=True, timeout=120
        )
        if out.returncode == 0 and out.stdout.strip():
            return round(int(out.stdout.split()[0]) / 1048576, 3)
    except Exception:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(Path.home() / ".cache/disk_monitor_state.json"))
    ap.add_argument("--log", default=str(Path.home() / "stock_research/logs/disk_monitor.jsonl"))
    args = ap.parse_args()
    state_path, log_path = Path(args.state), Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)

    usage = shutil.disk_usage(DATA_VOLUME)
    free_gib = usage.free / 2**30
    used_gib = usage.used / 2**30
    level = (
        "EMERGENCY" if free_gib < EMERG_GIB
        else "CRITICAL" if free_gib < CRIT_GIB
        else "WARNING" if free_gib < WARN_GIB
        else "OK"
    )

    prev = {}
    if state_path.exists():
        try:
            prev = json.loads(state_path.read_text()).get("dirs", {})
        except Exception:
            prev = {}

    dirs = {}
    growers = []
    for pat in WATCH_DIRS:
        p = Path(pat).expanduser()
        gb = du_gb(p)
        if gb is None:
            continue
        old = prev.get(str(p))
        delta = round(gb - old, 3) if isinstance(old, (int, float)) else None
        dirs[str(p)] = {"gb": gb, "delta_gb": delta}
        if delta is not None and delta > 0.5:
            growers.append({"path": str(p), "delta_gb": delta, "gb": gb})
    growers.sort(key=lambda g: -g["delta_gb"])

    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "volume": DATA_VOLUME,
        "used_gib": round(used_gib, 2),
        "free_gib": round(free_gib, 2),
        "level": level,
        "top_growers": growers[:10],
        "dirs": dirs,
    }
    with log_path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    state_path.write_text(json.dumps({"ts": record["ts"], "dirs": {k: v["gb"] for k, v in dirs.items()}}))

    print(f"[{level}] {DATA_VOLUME} free={free_gib:.1f}GiB used={used_gib:.1f}GiB")
    for g in growers[:5]:
        print(f"  +{g['delta_gb']}GB {g['path']} (now {g['gb']}GB)")
    if level != "OK":
        print(f"  thresholds: WARN<{WARN_GIB} CRIT<{CRIT_GIB} EMERG<{EMERG_GIB} GiB", file=sys.stderr)
    return 0 if level in ("OK", "WARNING") else 1


if __name__ == "__main__":
    raise SystemExit(main())
