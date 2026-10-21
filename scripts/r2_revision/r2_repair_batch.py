"""R2 controlled batch repair for CONFIRMED_DIRTY assets (hardened v3).

Per asset, strictly in order:
  1. backup gate — backup tables must provably cover the FULL PRIMARY-KEY
     SET of every row the repair may modify (daily qfq/hfq, factors,
     actions). Missing keys are topped up from the live table ONLY when
     the asset carries no prior revision writes; otherwise the copy would
     record post-repair values as originals -> asset skipped as
     BACKUP_UNCERTAIN.
  2. fetch live qfq+hfq from baostock (full history, one shot per asset).
  3. diff-driven upsert of changed rows only; raw rows are never written.
  4. scoped adjustment_factor rebuild for the asset.
  5. in-loop post-diff on ALL core price fields (not just close) plus
     date-set completeness vs live — zero extra baostock calls.
     -> status WRITTEN.

After all assets: batch meta row + scoped corporate_action rebuild that
first deletes stale derived events for THIS batch's assets in-window
(asset_ids scope + source_version filter), then rebuilds. Assets flip to
COMPLETE only when the event rebuild succeeded — report JSON is written
incrementally after every asset, so resume is always consistent.

Usage: r2_repair_batch.py <batch_id> <asset_id,asset_id,...|file:path>
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

# socket hang guard MUST precede bs.login(): setdefaulttimeout only
# applies to sockets created AFTER the call, including baostock's own.
import socket
socket.setdefaulttimeout(120)

import baostock as bs  # noqa: E402

sys.path.insert(0, "src")
from stock_research.adjustment_revision import (  # noqa: E402
    assert_no_raw_rows,
    diff_driven_update_rows,
)
from stock_research.db import connect, fetch_all  # noqa: E402

BASE = "outputs/research/data01r1_finance_q2_20261020"
END = "2026-10-20"
FIELDS = "date,code,open,high,low,close,preclose,volume,amount,turn,pctChg,tradestatus,isST"
ADJUSTFLAG = {"qfq": "2", "hfq": "1"}
REVISION_SOURCE = "baostock_revision_r2"
FACTOR_SOURCE_VERSION = "derived_market_daily_bar_v1"
ACTION_SOURCE_VERSION = "derived_adjustment_factor_v1"
PRICE_FIELDS = ("open", "high", "low", "close", "preclose",
                "volume", "amount", "turnover_rate", "pct_chg")
DIFF_TOLERANCE = 0.0005


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


def keyset(conn, table: str, asset_id: str, key_cols: tuple[str, ...],
           extra: str = "", params: list | None = None) -> set[tuple]:
    cols = ", ".join(key_cols)
    sql = f"SELECT {cols} FROM {table} WHERE asset_id=%s {extra}"
    return {tuple(str(r[c]) for c in key_cols) for r in
            fetch_all(conn, sql, [asset_id] + (params or []))}


def ensure_asset_backup(cur, conn, asset_id: str,
                        backup_table: str, factor_backup: str,
                        action_backup: str) -> str:
    """Full key-set backup gate across daily/factor/action tables.
    Returns 'OK', 'NO_STORED_ROWS', or 'BACKUP_UNCERTAIN'."""
    bar_keys = keyset(conn, "market_daily_bar", asset_id,
                      ("trade_date", "adjust_type"),
                      "AND adjust_type IN ('qfq','hfq')")
    if not bar_keys:
        return "NO_STORED_ROWS"
    bak_keys = keyset(conn, backup_table, asset_id,
                      ("trade_date", "adjust_type"))
    factor_keys = keyset(conn, "market.adjustment_factor", asset_id,
                         ("trade_date", "source_version"))
    factor_bak = keyset(conn, factor_backup, asset_id,
                        ("trade_date", "source_version"))
    action_keys = keyset(conn, "market.corporate_action", asset_id,
                         ("event_date", "action_type", "source_version"))
    action_bak = keyset(conn, action_backup, asset_id,
                        ("event_date", "action_type", "source_version"))
    missing_bars = bar_keys - bak_keys
    missing_factors = factor_keys - factor_bak
    missing_actions = action_keys - action_bak
    if not (missing_bars or missing_factors or missing_actions):
        return "OK"
    revised = fetch_all(
        conn, "SELECT count(*) c FROM market_daily_bar "
              "WHERE asset_id=%s AND source=%s",
        [asset_id, REVISION_SOURCE])[0]["c"]
    if revised:
        return "BACKUP_UNCERTAIN"
    if missing_bars:
        cur.execute(
            f"""INSERT INTO {backup_table}
                SELECT s.* FROM market_daily_bar s
                WHERE s.asset_id=%s AND s.adjust_type IN ('qfq','hfq')
                  AND (s.trade_date::text, s.adjust_type) <> ALL (
                      SELECT (b.trade_date::text, b.adjust_type)
                      FROM {backup_table} b WHERE b.asset_id=%s)""",
            [asset_id, asset_id])
    if missing_factors:
        cur.execute(
            f"""INSERT INTO {factor_backup}
                SELECT s.* FROM market.adjustment_factor s
                WHERE s.asset_id=%s
                  AND (s.trade_date::text, s.source_version) <> ALL (
                      SELECT (b.trade_date::text, b.source_version)
                      FROM {factor_backup} b WHERE b.asset_id=%s)""",
            [asset_id, asset_id])
    if missing_actions:
        cur.execute(
            f"""INSERT INTO {action_backup}
                SELECT s.* FROM market.corporate_action s
                WHERE s.asset_id=%s
                  AND (s.event_date::text, s.action_type, s.source_version) <> ALL (
                      SELECT (b.event_date::text, b.action_type, b.source_version)
                      FROM {action_backup} b WHERE b.asset_id=%s)""",
            [asset_id, asset_id])
    # re-verify full coverage
    ok_bars = not (bar_keys - keyset(conn, backup_table, asset_id,
                                     ("trade_date", "adjust_type")))
    ok_fac = not (factor_keys - keyset(conn, factor_backup, asset_id,
                                       ("trade_date", "source_version")))
    ok_act = not (action_keys - keyset(conn, action_backup, asset_id,
                                       ("event_date", "action_type", "source_version")))
    return "OK" if (ok_bars and ok_fac and ok_act) else "BACKUP_UNCERTAIN"


def post_diff_full(conn, asset_id: str, live_rows: dict[str, list]) -> dict:
    """Compare stored vs live on all core price fields + date sets."""
    out = {}
    for adj in ADJUSTFLAG:
        stored = {str(x["trade_date"]): x for x in fetch_all(
            conn, "SELECT trade_date,open,high,low,close,preclose,volume,"
                  "amount,turnover_rate,pct_chg FROM market_daily_bar "
                  "WHERE asset_id=%s AND adjust_type=%s AND trade_date<=%s",
            [asset_id, adj, END])}
        live = {x["trade_date"]: x for x in live_rows[adj]}
        diffs = []
        for d, s in stored.items():
            lv = live.get(d)
            if lv is None:
                diffs.append(d)
                continue
            for f in PRICE_FIELDS:
                sv, lvv = s.get(f), lv.get(f)
                if sv is None and lvv is None:
                    continue
                if sv is None or lvv is None:
                    diffs.append(d)
                    break
                try:
                    if abs(float(lvv) - float(sv)) > max(abs(float(sv)) * DIFF_TOLERANCE, 1e-9):
                        diffs.append(d)
                        break
                except (TypeError, ValueError):
                    if str(sv) != str(lvv):
                        diffs.append(d)
                        break
        missing_dates = [d for d in live if d not in stored]
        out[adj] = {"field_diffs": len(diffs), "missing_dates": len(missing_dates)}
    return out


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
    t0 = time.time()
    try:
        with connect("stock_research") as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE SCHEMA IF NOT EXISTS backup")
                cur.execute(
                    """CREATE TABLE IF NOT EXISTS backup.r2_batch_meta (
                        batch_id text PRIMARY KEY, created_at timestamptz DEFAULT now())""")
                cur.execute(
                    "INSERT INTO backup.r2_batch_meta (batch_id) VALUES (%s) "
                    "ON CONFLICT (batch_id) DO NOTHING", [batch_id])
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
                if report.get(asset_id, {}).get("status") in ("COMPLETE", "WRITTEN"):
                    continue
                arep: dict[str, Any] = {"status": "STARTED"}
                try:
                    with conn.cursor() as cur:
                        gate = ensure_asset_backup(
                            cur, conn, asset_id, backup_table,
                            factor_backup, action_backup)
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

                    ver = post_diff_full(conn, asset_id, live_rows)
                    arep["post_diff"] = ver
                    bad = any(v["field_diffs"] or v["missing_dates"]
                              for v in ver.values())
                    arep["status"] = "POST_DIFF" if bad else "WRITTEN"
                except Exception as exc:  # per-asset isolation
                    conn.rollback()
                    arep["status"] = "ERROR"
                    arep["error"] = str(exc)[:300]
                report[asset_id] = arep
                with open(report_path, "w") as f:
                    json.dump(report, f, ensure_ascii=False, indent=2, default=str)
                print(f"{asset_id}: {arep['status']} qfq+{arep.get('qfq_updated')} "
                      f"hfq+{arep.get('hfq_updated')}", flush=True)

        # scoped corporate-action rebuild for THIS batch only:
        # delete stale derived events for batch assets in-window first,
        # then rebuild — no residue, no market-wide churn
        from stock_research.corporate_actions import (
            build_corporate_actions_from_factors)
        written = [a for a, r in report.items()
                   if a.startswith("CN:") and r.get("status") == "WRITTEN"]
        with connect("stock_research") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM market.corporate_action "
                    "WHERE asset_id=ANY(%s) AND source_version=%s "
                    "AND event_date>='2026-01-01' AND event_date<=%s",
                    [written, ACTION_SOURCE_VERSION, END])
                stale_deleted = cur.rowcount
            build_corporate_actions_from_factors(
                conn, start_date="2026-01-01", end_date=END,
                asset_ids=written, require_preclose_evidence=True)
            conn.commit()
        for a in written:
            report[a]["events_rebuilt"] = True
            report[a]["status"] = "COMPLETE"
        report["__meta"] = {"batch_id": batch_id, "assets": len(assets),
                            "complete": len(written),
                            "stale_events_deleted": stale_deleted,
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
