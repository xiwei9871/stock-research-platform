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


def raw_minute_sig(conn, asset_id: str, freq: str, source: str) -> str:
    """Upstream signature for a job's raw minute input — re-ingested raw
    bars change count/max(updated_at) and force re-derivation."""
    r = fetch_all(
        conn, "SELECT count(*) c, max(updated_at) mx"
              " FROM market.stock_minute_bar WHERE asset_id=%s"
              " AND adjust_type='raw' AND freq=%s AND source=%s",
        [asset_id, freq, source])[0]
    return f"{r['c']}:{r['mx']}"


def decide_minute_pending(asset_groups: dict[str, list[dict]],
                          sigs: dict[str, str],
                          raw_sigs: dict[str, str],
                          ledger: dict) -> dict[str, dict]:
    """Pure: which minute jobs are pending given per-asset raw groups,
    factor signatures AND raw-minute signatures, and the ledger.
    Key = asset|freq|source; pending when either upstream signature
    differs from what the ledger recorded."""
    todo = {}
    for asset_id, groups in asset_groups.items():
        for g in groups:
            key = f"{asset_id}|{g['freq']}|{g['source']}"
            want = {"factor_sig": sigs[asset_id],
                    "raw_sig": raw_sigs.get(key, "")}
            got = ledger.get(key, {})
            if (got.get("factor_sig") != want["factor_sig"]
                    or got.get("raw_sig") != want["raw_sig"]):
                todo[key] = {"asset": asset_id, "freq": g["freq"],
                             "source": g["source"], **want}
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
    groups, sigs, raw_sigs = {}, {}, {}
    for asset_id in assets:
        gs = fetch_all(
            conn, "SELECT DISTINCT freq, source FROM market.stock_minute_bar"
                  " WHERE asset_id=%s AND adjust_type='raw'",
            [asset_id])
        if gs:
            groups[asset_id] = gs
            sigs[asset_id] = factor_sig(conn, asset_id)
            for g in gs:
                key = f"{asset_id}|{g['freq']}|{g['source']}"
                raw_sigs[key] = raw_minute_sig(
                    conn, asset_id, g["freq"], g["source"])
    return decide_minute_pending(groups, sigs, raw_sigs, ledger)


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
                      f"{g['mn']}..{g['mx']} raw={g['c']} "
                      f"sig={job_info['factor_sig']}|{job_info['raw_sig']}")
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
            ledger[key] = {"factor_sig": job_info["factor_sig"],
                           "raw_sig": job_info["raw_sig"],
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
    """Per-asset FULL-HISTORY feature recompute, upsert only rows in
    [start,end]. Full history is required for cumulative indicators
    (OBV = cumsum; a 260-day window introduces systematic level bias)
    and is also the convention-correct baseline since EMA/MACD/KDJ are
    warmup-converged (verified identical to within 1e-4)."""
    from stock_research.technical_features import (
        compute_daily_technical_features)
    t0 = time.time()
    with connect("stock_research") as conn:
        dates = {str(r["trade_date"]) for r in fetch_all(
            conn, "SELECT DISTINCT trade_date FROM market_daily_bar"
                  " WHERE adjust_type='raw' AND trade_date BETWEEN %s AND %s",
            [start, end])}
        todo, sigs = pending_feature_keys(assets, sorted(dates), conn)
        print(f"feature pending keys: {len(todo)} "
              f"(across {len(dates)} dates)")
        ledger = _load_ledger(FEAT_PROGRESS)
        # group pending by asset -> dates needed
        need: dict[str, list[str]] = {}
        for k in todo:
            a, d = todo[k]["asset"], todo[k]["date"]
            need.setdefault(a, []).append(d)
        for n, (asset_id, want_dates) in enumerate(sorted(need.items()), 1):
            rows = fetch_all(
                conn, "SELECT trade_date, open, high, low, close, preclose,"
                      " volume, amount, turnover_rate FROM market_daily_bar"
                      " WHERE asset_id=%s AND adjust_type='qfq'"
                      " AND trade_date<=%s ORDER BY trade_date",
                [asset_id, end])
            if not rows:
                continue
            feats = compute_daily_technical_features(pd.DataFrame(rows))
            feats["asset_id"] = asset_id
            feats["ts_code"] = asset_id
            feats["adjust_type"] = "qfq"
            feats["source"] = "r2_downstream_rebuild"
            feats["source_data_version"] = SOURCE_VERSION
            feats["calc_version"] = "full_history_v1"
            sub = feats[feats["trade_date"].map(str).isin(want_dates)]
            if not sub.empty:
                sub = sub.reindex(columns=TECHNICAL_FEATURE_TABLE_COLUMNS)
                upsert_stock_technical_features_daily(sub)
            for d in want_dates:
                ledger[f"{d}|{asset_id}"] = {"factor_sig": sigs[asset_id]}
            conn.commit()
            if n % 5 == 0:
                with open(FEAT_PROGRESS, "w") as f:
                    json.dump(ledger, f)
                print(f"[{n}/{len(need)}] {asset_id} features rows="
                      f"{len(sub)} ({time.time()-t0:.0f}s)", flush=True)
        with open(FEAT_PROGRESS, "w") as f:
            json.dump(ledger, f)
    print(f"features phase done: {len(need)} assets, "
          f"{sum(len(v) for v in need.values())} asset-dates")


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
