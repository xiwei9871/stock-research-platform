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


def factor_sig(conn, asset_id: str) -> str:
    """Upstream-revision signature for one asset's derived factors.

    Any repair/rebuild touching this asset's factor rows changes
    max(updated_at) (and usually count) — downstream work keyed on this
    signature becomes stale and must recompute.
    """
    r = fetch_all(
        conn, "SELECT count(*) c, max(updated_at) mx"
              " FROM market.adjustment_factor WHERE asset_id=%s"
              " AND source_version='derived_market_daily_bar_v1'",
        [asset_id])[0]
    return f"{r['c']}:{r['mx']}"


def decide_minute_pending(asset_groups: dict[str, list[dict]],
                          sigs: dict[str, str],
                          ledger: dict) -> dict[str, dict]:
    """Pure: which minute jobs are pending given per-asset raw groups,
    current factor signatures, and the completion ledger.
    Key = asset|freq|source; pending when ledger sig != current sig."""
    todo = {}
    for asset_id, groups in asset_groups.items():
        for g in groups:
            key = f"{asset_id}|{g['freq']}|{g['source']}"
            if ledger.get(key, {}).get("factor_sig") != sigs[asset_id]:
                todo[key] = {"asset": asset_id, "freq": g["freq"],
                             "source": g["source"], "sig": sigs[asset_id]}
    return todo


def decide_feature_pending(assets: list[str], dates: list[str],
                           sigs: dict[str, str],
                           ledger: dict) -> dict[str, dict]:
    """Pure: {date|asset: {'asset','date','sig'}} needing recompute —
    skips only exact (asset, date, unchanged-sig) completions, never
    whole dates."""
    todo = {}
    for d in dates:
        for a in assets:
            key = f"{d}|{a}"
            if ledger.get(key, {}).get("factor_sig") != sigs[a]:
                todo[key] = {"asset": a, "date": d, "sig": sigs[a]}
    return todo


def _load_ledger(path: str) -> dict:
    if os.path.exists(path):
        raw = json.load(open(path))
        return raw if isinstance(raw, dict) else {}
    return {}


def pending_minute_keys(assets: list[str], conn) -> dict[str, dict]:
    ledger = _load_ledger(PROGRESS)
    groups, sigs = {}, {}
    for asset_id in assets:
        gs = fetch_all(
            conn, "SELECT DISTINCT freq, source FROM market.stock_minute_bar"
                  " WHERE asset_id=%s AND adjust_type='raw'",
            [asset_id])
        if gs:
            groups[asset_id] = gs
            sigs[asset_id] = factor_sig(conn, asset_id)
    return decide_minute_pending(groups, sigs, ledger)


def pending_feature_keys(assets: list[str], dates: list[str],
                         conn) -> tuple[dict[str, dict], dict[str, str]]:
    ledger = _load_ledger(FEAT_PROGRESS)
    sigs = {a: factor_sig(conn, a) for a in assets}
    return decide_feature_pending(assets, dates, sigs, ledger), sigs


def phase_minute(assets: list[str], dry_run: bool) -> None:
    t0 = time.time()
    n = 0
    gaps: list[str] = []
    with connect("stock_research") as conn:
        todo = pending_minute_keys(assets, conn)
        print(f"minute pending keys: {len(todo)}")
        ledger = {}
        if os.path.exists(PROGRESS):
            raw = json.load(open(PROGRESS))
            ledger = raw if isinstance(raw, dict) else {}
        for key, job_info in todo.items():
            asset_id = job_info["asset"]
            rng = fetch_all(
                conn, "SELECT ts_code, min(trade_date) mn, max(trade_date) mx,"
                      " count(*) c FROM market.stock_minute_bar"
                      " WHERE asset_id=%s AND adjust_type='raw'"
                      " AND freq=%s AND source=%s GROUP BY ts_code",
                [asset_id, job_info["freq"], job_info["source"]])
            if not rng:
                continue
            g = rng[0]
            job = {"asset_id": asset_id, "ts_code": g["ts_code"],
                   "start_date": str(g["mn"]), "end_date": str(g["mx"]),
                   "freq": job_info["freq"], "source": job_info["source"]}
            if dry_run:
                print(f"  {asset_id} {job_info['freq']}/{job_info['source']} "
                      f"{g['mn']}..{g['mx']} raw={g['c']} sig={job_info['sig']}")
                continue
            try:
                res = derive_qfq_minute_bars_from_raw_job(conn, job)
            except RuntimeError as exc:
                # raw rows on dates lacking a non-NULL factor (e.g. raw
                # daily gap) abort this job — roll back and log
                conn.rollback()
                print(f"  FACTOR_GAP {asset_id} {key}: {exc}", flush=True)
                gaps.append(key)
                continue
            conn.commit()
            ledger[key] = {"factor_sig": job_info["sig"],
                           "rows": int(res or 0)}
            n += 1
            if n % 10 == 0:
                with open(PROGRESS, "w") as f:
                    json.dump(ledger, f)
                print(f"[{n}] {key} qfq-minute rows +{res} "
                      f"({time.time()-t0:.0f}s)", flush=True)
    if not dry_run:
        with open(PROGRESS, "w") as f:
            json.dump(ledger, f)
    print(f"minute phase done: {n} jobs processed, "
          f"{len(gaps)} factor-gap jobs skipped")


def phase_features(assets: list[str], start: str, end: str) -> None:
    with connect("stock_research") as conn:
        dates = [str(r["trade_date"]) for r in fetch_all(
            conn, "SELECT DISTINCT trade_date FROM market_daily_bar"
                  " WHERE adjust_type='raw' AND trade_date BETWEEN %s AND %s"
                  " ORDER BY 1", [start, end])]
        todo, sigs = pending_feature_keys(assets, dates, conn)
        print(f"feature pending keys: {len(todo)} "
              f"(across {len({v['date'] for v in todo.values()})} dates)")
        ledger = {}
        if os.path.exists(FEAT_PROGRESS):
            raw = json.load(open(FEAT_PROGRESS))
            ledger = raw if isinstance(raw, dict) else {}
        t0 = time.time()
        for i, d in enumerate(dates):
            day_assets = [a for a in assets if f"{d}|{a}" in todo]
            if not day_assets:
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
                [day_assets, d, LOOKBACK])
            if not rows:
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
            for a in (str(x["asset_id"]) for x in built):
                ledger[f"{d}|{a}"] = {"factor_sig": sigs[a]}
            conn.commit()
            if i % 20 == 0:
                with open(FEAT_PROGRESS, "w") as f:
                    json.dump(ledger, f)
                print(f"[{i}/{len(dates)}] {d} features rows={len(df)} "
                      f"({time.time()-t0:.0f}s)", flush=True)
        with open(FEAT_PROGRESS, "w") as f:
            json.dump(ledger, f)
    print(f"features phase done: {len(dates)} dates scanned")


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
