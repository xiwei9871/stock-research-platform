"""R2 controlled batch repair for CONFIRMED_DIRTY assets (hardened v2).

Per asset, strictly in order:
  1. backup gate — backup table must already cover the asset's ORIGINAL
     stored qfq/hfq rows; missing keys are topped up from the live table
     ONLY when the asset has no prior revision writes (otherwise the copy
     would record post-repair values as originals → asset skipped as
     BACKUP_UNCERTAIN instead).
  2. fetch live qfq+hfq from baostock (full history, one shot per asset).
  3. diff-driven upsert of changed rows only; raw rows are never written.
  4. scoped adjustment_factor rebuild for the asset.
  5. in-loop post-diff: re-read stored closes and compare against the
     live rows already in memory — zero extra baostock calls; asset is
     marked COMPLETE only when writes committed AND post_diff == 0.

After all assets: scoped corporate_action rebuild (asset_ids=only this
batch, min_factor_change filters float noise), incremental JSON report.

Usage: r2_repair_batch.py <batch_id> <asset_id,asset_id,...|file:path>
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import baostock as bs

sys.path.insert(0, "src")
from stock_research.adjustment_revision import (  # noqa: E402
    assert_no_raw_rows,
    diff_driven_update_rows,
    diff_stored_vs_live,
)
from stock_research.db import connect, fetch_all  # noqa: E402

BASE = "outputs/research/data01r1_finance_q2_20261020"
END = "2026-10-20"
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,tradestatus,isST"
ADJUSTFLAG = {"qfq": "2", "hfq": "1"}
REVISION_SOURCE = "baostock_revision_r2"


def bs_code(asset_id: str) -> str:
    _, exch, sym = asset_id.split(":")
    return f"{exch.lower()}.{sym}"


def num(v: Any):
    try:
        return float(v) if v not in ("", None) else None
    except (TypeError, ValueError):
        return None


def fetch_live_rows(code, adjustflag, start, adj, asset_id):
    rs = bs.query_history_k_data_plus(
        code, FIELDS, start_date=start, end_date=END,
        frequency="d", adjustflag=adjustflag,
    )
    if rs.error_code != "0":
        raise RuntimeError(f"{code} {adj}: {rs.error_code} {rs.error_msg}")
    rows = []
    while rs.next():
        d = rs.get_row_data()
        rows.append({
            "asset_id": asset_id, "trade_date": d[0],
            "open": num(d[2]), "high": num(d[3]), "low": num(d[4]),
            "close": num(d[5]), "preclose": num(d[6]), "volume": num(d[7]),
            "amount": num(d[8]), "turnover_rate": num(d[9]), "pct_chg": num(d[10]),
            "trade_status": d[11] or "1", "is_st": d[12] == "1",
            "adjust_type": adj, "source": REVISION_SOURCE,
        })
    return rows


UPSERT = """
INSERT INTO market_daily_bar (
    asset_id, trade_date, open, high, low, close, preclose, volume, amount,
    turnover_rate, pct_chg, trade_status, is_st, adjust_type, source
) VALUES (
    %(asset_id)s, %(trade_date)s, %(open)s, %(high)s, %(low)s, %(close)s,
    %(preclose)s, %(volume)s, %(amount)s, %(turnover_rate)s, %(pct_chg)s,
    %(trade_status)s, %(is_st)s, %(adjust_type)s, %(source)s
)
ON CONFLICT (asset_id, trade_date, adjust_type) DO UPDATE SET
    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low, close=EXCLUDED.close,
    preclose=EXCLUDED.preclose, volume=EXCLUDED.volume, amount=EXCLUDED.amount,
    turnover_rate=EXCLUDED.turnover_rate, pct_chg=EXCLUDED.pct_chg,
    trade_status=EXCLUDED.trade_status, is_st=EXCLUDED.is_st,
    source=EXCLUDED.source, updated_at=now()
"""

REBUILD_FACTOR = """
INSERT INTO market.adjustment_factor (
    asset_id, trade_date, raw_close, qfq_close, hfq_close,
    qfq_factor, hfq_factor, source, source_version)
SELECT q.asset_id, q.trade_date, r.close, q.close, h.close,
    q.close/NULLIF(r.close,0), h.close/NULLIF(r.close,0),
    'derived:market_daily_bar', 'derived_market_daily_bar_v1'
FROM market_daily_bar q
JOIN market_daily_bar h ON h.asset_id=q.asset_id AND h.trade_date=q.trade_date AND h.adjust_type='hfq'
LEFT JOIN market_daily_bar r ON r.asset_id=q.asset_id AND r.trade_date=q.trade_date AND r.adjust_type='raw'
WHERE q.adjust_type='qfq' AND q.asset_id = ANY(%s)
ON CONFLICT (asset_id, trade_date, source_version) DO UPDATE SET
    raw_close=EXCLUDED.raw_close, qfq_close=EXCLUDED.qfq_close,
    hfq_close=EXCLUDED.hfq_close, qfq_factor=EXCLUDED.qfq_factor,
    hfq_factor=EXCLUDED.hfq_factor, updated_at=now()
"""

# top-up only keys absent from the backup — never overwrite originals
BACKUP_TOPUP = """
INSERT INTO {backup_table}
SELECT s.* FROM market_daily_bar s
WHERE s.asset_id = %s AND s.adjust_type IN ('qfq','hfq')
  AND NOT EXISTS (
      SELECT 1 FROM {backup_table} b
      WHERE b.asset_id = s.asset_id AND b.trade_date = s.trade_date
        AND b.adjust_type = s.adjust_type)
"""


def ensure_asset_backup(cur, conn, asset_id: str, backup_table: str) -> str:
    """Return 'OK' when the backup provably covers the asset's original
    stored qfq/hfq rows; otherwise 'BACKUP_UNCERTAIN' (caller skips)."""
    stored = fetch_all(
        conn,
        "SELECT count(*) c FROM market_daily_bar "
        "WHERE asset_id=%s AND adjust_type IN ('qfq','hfq')", [asset_id])[0]["c"]
    if stored == 0:
        return "NO_STORED_ROWS"
    backed = fetch_all(
        conn,
        f"SELECT count(*) c FROM {backup_table} WHERE asset_id=%s", [asset_id])[0]["c"]
    if backed >= stored:
        return "OK"
    revised = fetch_all(
        conn,
        "SELECT count(*) c FROM market_daily_bar "
        "WHERE asset_id=%s AND source=%s", [asset_id, REVISION_SOURCE])[0]["c"]
    if revised:
        # partially repaired earlier; a top-up would snapshot post-repair
        # values as 'originals' — refuse rather than corrupt the backup
        return "BACKUP_UNCERTAIN"
    cur.execute(BACKUP_TOPUP.format(backup_table=backup_table), [asset_id])
    backed = fetch_all(
        conn,
        f"SELECT count(*) c FROM {backup_table} WHERE asset_id=%s", [asset_id])[0]["c"]
    return "OK" if backed >= stored else "BACKUP_UNCERTAIN"


def main() -> None:
    batch_id, target = sys.argv[1], sys.argv[2]
    if target.startswith("file:"):
        assets = [l.strip() for l in open(target[5:]) if l.strip()]
    else:
        assets = target.split(",")
    backup_table = f"backup.market_daily_bar_r2_{batch_id}"
    factor_backup = f"backup.adjustment_factor_r2_{batch_id}"
    action_backup = f"backup.corporate_action_r2_{batch_id}"
    report_path = f"{BASE}/r2_repair_{batch_id}.json"

    report: dict[str, Any] = {}
    if os.path.exists(report_path):
        report = json.load(open(report_path))

    login = bs.login()
    if login.error_code != "0":
        raise SystemExit(f"login failed {login.error_code} {login.error_msg}")
    import socket
    socket.setdefaulttimeout(120)  # baostock socket hang guard
    t0 = time.time()
    try:
        with connect("stock_research") as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS backup")
                # keep ORIGINAL pre-repair backup on retry
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS {backup_table} AS SELECT * FROM market_daily_bar "
                    "WHERE asset_id = ANY(%s) AND adjust_type IN ('qfq','hfq')", [assets])
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS {factor_backup} AS SELECT * FROM market.adjustment_factor "
                    "WHERE asset_id = ANY(%s)", [assets])
                cur.execute(
                    f"CREATE TABLE IF NOT EXISTS {action_backup} AS SELECT * FROM market.corporate_action "
                    "WHERE asset_id = ANY(%s)", [assets])
            conn.commit()
            print(f"backups: {backup_table} {factor_backup} {action_backup}", flush=True)

            for asset_id in assets:
                if report.get(asset_id, {}).get("status") == "COMPLETE":
                    print(f"{asset_id}: already COMPLETE, skip", flush=True)
                    continue
                arep: dict[str, Any] = {"status": "STARTED"}
                try:
                    with conn.cursor() as cur:
                        gate = ensure_asset_backup(cur, conn, asset_id, backup_table)
                    conn.commit()
                    arep["backup_gate"] = gate
                    if gate != "OK":
                        arep["status"] = gate
                        report[asset_id] = arep
                        print(f"{asset_id}: {gate}", flush=True)
                        continue

                    code = bs_code(asset_id)
                    r = fetch_all(conn, "SELECT min(trade_date) lo FROM market_daily_bar "
                                  "WHERE asset_id=%s AND adjust_type='raw'", [asset_id])
                    start = str(r[0]["lo"])
                    arep["history_start"] = start
                    live_rows = {}
                    with conn.cursor() as cur:
                        for adj, flag in ADJUSTFLAG.items():
                            live = fetch_live_rows(code, flag, start, adj, asset_id)
                            live_rows[adj] = live
                            stored = fetch_all(
                                conn,
                                "SELECT * FROM market_daily_bar WHERE asset_id=%s "
                                "AND adjust_type=%s AND trade_date<=%s",
                                [asset_id, adj, END])
                            updates = diff_driven_update_rows(stored, live)
                            assert_no_raw_rows(updates)
                            if updates:
                                cur.executemany(UPSERT, updates)
                            arep[f"{adj}_live"] = len(live)
                            arep[f"{adj}_updated"] = len(updates)
                    conn.commit()
                    with conn.cursor() as cur:
                        cur.execute(REBUILD_FACTOR, [[asset_id]])
                        arep["factor_rows"] = cur.rowcount
                    conn.commit()

                    # post-diff using live rows already fetched (no extra API)
                    ver = {}
                    for adj in ADJUSTFLAG:
                        stored = {str(x["trade_date"]): float(x["close"]) for x in fetch_all(
                            conn, "SELECT trade_date, close FROM market_daily_bar "
                            "WHERE asset_id=%s AND adjust_type=%s AND trade_date<=%s",
                            [asset_id, adj, END])}
                        live_close = {x["trade_date"]: x["close"] for x in live_rows[adj]}
                        ver[adj] = diff_stored_vs_live(stored, live_close)["diff_count"]
                    arep["post_diff"] = ver
                    arep["status"] = "COMPLETE" if not (ver["qfq"] or ver["hfq"]) else "POST_DIFF"
                except Exception as exc:  # per-asset isolation
                    conn.rollback()
                    arep["status"] = "ERROR"
                    arep["error"] = str(exc)[:300]
                report[asset_id] = arep
                with open(report_path, "w") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2, default=str)
                print(f"{asset_id}: {arep['status']} qfq+{arep.get('qfq_updated')} "
                      f"hfq+{arep.get('hfq_updated')}", flush=True)

        # scoped corporate-action rebuild for THIS batch only
        from stock_research.corporate_actions import build_corporate_actions_from_factors
        complete = [a for a, r in report.items()
                    if a.startswith("CN:") and r.get("status") == "COMPLETE"]
        with connect("stock_research") as conn:
            build_corporate_actions_from_factors(
                conn, start_date="2026-01-01", end_date=END, asset_ids=complete)
        report["__meta"] = {"batch_id": batch_id, "assets": len(assets),
                            "complete": len(complete),
                            "elapsed_s": round(time.time() - t0, 1),
                            "backup_table": backup_table}
    finally:
        bs.logout()
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"batch {batch_id} done: {report['__meta']['complete']}/{len(assets)} "
          f"complete in {report['__meta']['elapsed_s']}s")


if __name__ == "__main__":
    main()
