"""R2 downstream rebuild — re-derive qfq minute bars + recompute
technical features for R2-repaired assets. DB-only (no baostock).

phases:
  minute   — per asset, re-derive qfq minute bars from raw minute bars
             joined to the rebuilt adjustment_factor (pure SQL upsert).
  features — per affected trade_date, recompute stock_technical_features_daily
             for the target assets only (asset-scoped lookback), upsert.

Assets come from repair reports with status COMPLETE (all batches),
or an explicit file. Resumable: per-asset commits + a progress ledger
under outputs/research/data01r1_finance_q2_20261020/r2_downstream_*.json

Usage:
  r2_downstream_rebuild.py minute [--assets file] [--dry-run]
  r2_downstream_rebuild.py features <start_date> <end_date> [--assets file]
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.minute_backfill import (  # noqa: E402
    derive_qfq_minute_bars_from_raw_job)
from stock_research.technical_feature_store import (  # noqa: E402
    _build_technical_feature_rows_for_assets,
    upsert_stock_technical_features_daily,
    TECHNICAL_FEATURE_TABLE_COLUMNS)
import pandas as pd  # noqa: E402

BASE = "outputs/research/data01r1_finance_q2_20261020"
PROGRESS = f"{BASE}/r2_downstream_minute_done.json"
FEAT_PROGRESS = f"{BASE}/r2_downstream_features_done.json"
END = "2026-10-20"
LOOKBACK = 260
SOURCE_VERSION = "market_daily_bar:qfq"


def completed_assets() -> set[str]:
    done = set()
    for p in glob.glob(f"{BASE}/r2_repair_*.json"):
        try:
            rep = json.load(open(p))
        except Exception:
            continue
        for k, v in rep.items():
            if k.startswith("CN:") and v.get("status") == "COMPLETE":
                done.add(k)
    return done


def load_asset_list(path: str | None) -> list[str]:
    if path:
        return [ln.strip() for ln in open(path) if ln.strip().startswith("CN:")]
    return sorted(completed_assets())


def phase_minute(assets: list[str], dry_run: bool) -> None:
    done = set()
    if os.path.exists(PROGRESS):
        done = set(json.load(open(PROGRESS)))
    t0 = time.time()
    n = 0
    gaps: list[str] = []
    with connect("stock_research") as conn:
        for asset_id in assets:
            if asset_id in done:
                continue
            groups = fetch_all(
                conn, "SELECT ts_code, freq, source, min(trade_date) mn,"
                      " max(trade_date) mx, count(*) c"
                      " FROM market.stock_minute_bar"
                      " WHERE asset_id=%s AND adjust_type='raw'"
                      " GROUP BY ts_code, freq, source",
                [asset_id])
            total_up = 0
            failed = False
            for g in groups:
                job = {"asset_id": asset_id, "ts_code": g["ts_code"],
                       "start_date": str(g["mn"]), "end_date": str(g["mx"]),
                       "freq": g["freq"], "source": g["source"]}
                if dry_run:
                    print(f"  {asset_id} {g['freq']}/{g['source']} "
                          f"{g['mn']}..{g['mx']} raw={g['c']}")
                    continue
                try:
                    res = derive_qfq_minute_bars_from_raw_job(conn, job)
                except RuntimeError as exc:
                    # raw rows on dates lacking a non-NULL factor (e.g. raw
                    # daily gap) abort the whole asset — roll back and log
                    conn.rollback()
                    print(f"  FACTOR_GAP {asset_id}: {exc}", flush=True)
                    gaps.append(asset_id)
                    failed = True
                    break
                total_up += int(res or 0)
            if not dry_run and not failed:
                conn.commit()
                done.add(asset_id)
                n += 1
                if n % 10 == 0:
                    with open(PROGRESS, "w") as f:
                        json.dump(sorted(done), f)
                    print(f"[{n}] {asset_id} qfq-minute rows +{total_up} "
                          f"({time.time()-t0:.0f}s)", flush=True)
    if not dry_run:
        with open(PROGRESS, "w") as f:
            json.dump(sorted(done), f)
    print(f"minute phase done: {n} assets processed, "
          f"{len(gaps)} factor-gap assets skipped")


def phase_features(assets: list[str], start: str, end: str) -> None:
    done_dates = set()
    if os.path.exists(FEAT_PROGRESS):
        done_dates = set(json.load(open(FEAT_PROGRESS)))
    with connect("stock_research") as conn:
        dates = [str(r["trade_date"]) for r in fetch_all(
            conn, "SELECT DISTINCT trade_date FROM market_daily_bar"
                  " WHERE adjust_type='raw' AND trade_date BETWEEN %s AND %s"
                  " ORDER BY 1", [start, end])]
        t0 = time.time()
        for i, d in enumerate(dates):
            if d in done_dates:
                continue
            rows = fetch_all(
                conn, """SELECT trade_date, asset_id, open, high, low, close,
                         preclose, volume, amount, turnover_rate
                         FROM market_daily_bar
                         WHERE adjust_type='qfq' AND asset_id=ANY(%s)
                           AND trade_date IN (
                             SELECT DISTINCT trade_date FROM market_daily_bar
                             WHERE adjust_type='raw' AND trade_date <= %s
                             ORDER BY trade_date DESC LIMIT %s)""",
                [assets, d, LOOKBACK])
            if not rows:
                done_dates.add(d)
                continue
            frame = pd.DataFrame(rows)
            grouped = frame.groupby("asset_id", sort=False, group_keys=False)
            built = _build_technical_feature_rows_for_assets(
                ((str(a), g) for a, g in grouped),
                normalized_trade_date=d,
                adjust_type="qfq",
                source_data_version=SOURCE_VERSION)
            df = pd.DataFrame(built, columns=TECHNICAL_FEATURE_TABLE_COLUMNS)
            if not df.empty:
                upsert_stock_technical_features_daily(df)
            conn.commit()
            done_dates.add(d)
            if i % 20 == 0:
                with open(FEAT_PROGRESS, "w") as f:
                    json.dump(sorted(done_dates), f)
                print(f"[{i}/{len(dates)}] {d} features rows={len(df)} "
                      f"({time.time()-t0:.0f}s)", flush=True)
        with open(FEAT_PROGRESS, "w") as f:
            json.dump(sorted(done_dates), f)
    print(f"features phase done: {len(dates)} dates")


def main() -> None:
    phase = sys.argv[1]
    assets = None
    if "--assets" in sys.argv:
        assets = load_asset_list(sys.argv[sys.argv.index("--assets") + 1])
    else:
        assets = load_asset_list(None)
    dry = "--dry-run" in sys.argv
    if phase == "minute":
        print(f"minute rebuild for {len(assets)} assets dry={dry}")
        phase_minute(assets, dry)
    elif phase == "features":
        start, end = sys.argv[2], sys.argv[3]
        print(f"features rebuild {start}..{end} for {len(assets)} assets")
        phase_features(assets, start, end)
    else:
        raise SystemExit("phase must be minute|features")


if __name__ == "__main__":
    main()
