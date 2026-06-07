from __future__ import annotations

import argparse
import csv
import json
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path


BASE = Path("outputs/research/stock_report_web_gap_20260603")
RUN_DIR = BASE / "sina_slow_current_remaining_20260604"
MAIN_LOG = RUN_DIR / "sina_slow_current_remaining_20260604.log"
MONITOR_LOG = RUN_DIR / "sina_slow_batch_monitor_20260604.log"
STATE_FILE = RUN_DIR / "sina_slow_batch_monitor_20260604.state.json"


def now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"reported_batches": [], "completed": False}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"reported_batches": [], "completed": False}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def append_monitor(line: str) -> None:
    MONITOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with MONITOR_LOG.open("a", encoding="utf-8") as fh:
        fh.write(line.rstrip("\n") + "\n")


def notify(title: str, message: str) -> None:
    def apple_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'

    script = f"display notification {apple_string(message)} with title {apple_string(title)}"
    try:
        subprocess.run(["osascript", "-e", script], check=False, timeout=5)
    except Exception:
        return


def parse_batch_done(line: str) -> tuple[str, int] | None:
    if not line.startswith("batch_done|"):
        return None
    parts = line.strip().split("|")
    if len(parts) < 4:
        return None
    batch = parts[2]
    rc_text = parts[3].removeprefix("rc=")
    try:
        rc = int(rc_text)
    except ValueError:
        rc = -1
    return batch, rc


def summarize_batch(batch: str, rc: int) -> dict:
    collection_path = RUN_DIR / batch / "stock_report_web_source_collection.csv"
    status_counts: Counter[str] = Counter()
    stocks: set[str] = set()
    found_stocks: set[str] = set()
    rows = 0
    found_rows = 0

    if collection_path.exists():
        with collection_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows += 1
                asset_id = (row.get("asset_id") or "").strip()
                if asset_id:
                    stocks.add(asset_id)
                status = (row.get("collection_status") or "").strip() or "unknown"
                status_counts[status] += 1
                if status == "found":
                    found_rows += 1
                    if asset_id:
                        found_stocks.add(asset_id)

    return {
        "batch": batch,
        "rc": rc,
        "collection_path": str(collection_path),
        "collection_exists": collection_path.exists(),
        "rows": rows,
        "stocks": len(stocks),
        "found_rows": found_rows,
        "found_stocks": len(found_stocks),
        "no_result": status_counts.get("no_result", 0),
        "fetch_error": status_counts.get("fetch_error", 0),
        "status_counts": dict(status_counts),
    }


def render_summary(summary: dict) -> str:
    return (
        f"monitor_batch|{now()}|batch={summary['batch']}|rc={summary['rc']}|"
        f"stocks={summary['stocks']}|rows={summary['rows']}|"
        f"found_stocks={summary['found_stocks']}|found_rows={summary['found_rows']}|"
        f"no_result={summary['no_result']}|fetch_error={summary['fetch_error']}|"
        f"collection_exists={str(summary['collection_exists']).lower()}"
    )


def read_new_lines(path: Path, offset: int) -> tuple[list[str], int]:
    if not path.exists():
        return [], offset
    size = path.stat().st_size
    if size < offset:
        offset = 0
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        fh.seek(offset)
        lines = fh.readlines()
        return lines, fh.tell()


def report_batch(batch: str, rc: int, state: dict) -> None:
    if batch in set(state.get("reported_batches", [])):
        return
    summary = summarize_batch(batch, rc)
    append_monitor(render_summary(summary))
    state.setdefault("reported_batches", []).append(batch)
    save_state(state)
    notify(
        "Sina研报慢跑批次完成",
        f"{batch}: found {summary['found_stocks']} stocks / {summary['found_rows']} rows, rc={rc}",
    )


def monitor(poll_seconds: float) -> None:
    state = load_state()
    append_monitor(
        f"monitor_start|{now()}|main_log={MAIN_LOG}|reported_batches={len(state.get('reported_batches', []))}"
    )
    offset = 0

    while True:
        lines, offset = read_new_lines(MAIN_LOG, offset)
        for line in lines:
            parsed = parse_batch_done(line)
            if parsed is not None:
                report_batch(parsed[0], parsed[1], state)
            if line.startswith("all_done|") and not state.get("completed"):
                state["completed"] = True
                save_state(state)
                append_monitor(
                    f"monitor_all_done|{now()}|reported_batches={len(state.get('reported_batches', []))}"
                )
                notify("Sina研报慢跑完成", f"reported batches: {len(state.get('reported_batches', []))}")
                return
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    args = parser.parse_args()
    monitor(args.poll_seconds)


if __name__ == "__main__":
    main()
