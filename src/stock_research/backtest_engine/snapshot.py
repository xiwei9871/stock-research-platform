"""Read-only research snapshot export + bar preparation for the engine.

Two stages, so the database step can be run by an authorized operator and
the rest offline:

  1. export_raw_snapshot(service, ...)   READ ONLY transaction against a
     restore/replica instance -> raw CSVs (never writes to the database).
  2. build_engine_bars(raw_dir)          pure pandas: joins raw bars, status,
     asset master and adjustment factors, derives limit prices with the
     existing tradeability rules, writes bars.csv / calendar.csv and a
     SHA256 manifest.

Limit price encoding (engine contract): NaN = unknown rule or missing
preclose (fail-closed); +inf / 0.0 = no price limit that day (IPO window).
"""

from __future__ import annotations

import argparse
import bisect
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.tradeability import (
    TRADEABILITY_CONTRACT_VERSION,
    classify_board,
    legal_limit_price,
    resolve_limit_rule,
)

RAW_FILES = ("bars_raw.csv", "asset_status.csv", "asset_master.csv",
             "adjustment_factor.csv", "trading_calendar.csv")

EXPORT_SQL = {
    "bars_raw.csv": """
        SELECT asset_id, trade_date::text AS trade_date, open, high, low, close, preclose,
               volume, amount, trade_status, adjust_type
        FROM public.market_daily_bar
        WHERE adjust_type = 'raw' AND trade_date BETWEEN %(start)s AND %(end)s
          AND asset_id = ANY(%(assets)s)
        ORDER BY trade_date, asset_id""",
    "asset_status.csv": """
        SELECT asset_id, trade_date::text AS trade_date, is_trade, is_st, is_suspended
        FROM core.asset_status_daily
        WHERE trade_date BETWEEN %(start)s AND %(end)s AND asset_id = ANY(%(assets)s)
        ORDER BY trade_date, asset_id""",
    "asset_master.csv": """
        SELECT asset_id, symbol, exchange, board, is_star, is_chinext, is_beijing,
               list_date::text AS list_date, delist_date::text AS delist_date
        FROM core.asset_master WHERE asset_id = ANY(%(assets)s) ORDER BY asset_id""",
    "adjustment_factor.csv": """
        SELECT asset_id, trade_date::text AS trade_date, hfq_factor, source_version
        FROM market.adjustment_factor
        WHERE source_version = %(adj_source_version)s
          AND trade_date BETWEEN %(start)s AND %(end)s AND asset_id = ANY(%(assets)s)
        ORDER BY trade_date, asset_id""",
    "trading_calendar.csv": """
        SELECT exchange, trade_date::text AS trade_date
        FROM market.trading_calendar
        WHERE is_open AND source_version = %(calendar_source_version)s
          AND trade_date BETWEEN %(list_floor)s AND %(end)s
        ORDER BY exchange, trade_date""",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_raw_snapshot(
    *,
    service: str,
    start: str,
    end: str,
    assets: list[str],
    adj_source_version: str,
    calendar_source_version: str,
    out_dir: str | Path,
    list_floor: str = "1990-01-01",
) -> dict[str, Any]:
    """Read-only export. Run against a restore/replica instance only."""
    import psycopg
    from psycopg.rows import dict_row

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    params = {"start": start, "end": end, "assets": sorted(set(assets)),
              "adj_source_version": adj_source_version,
              "calendar_source_version": calendar_source_version, "list_floor": list_floor}
    with psycopg.connect(f"service={service}", row_factory=dict_row) as conn:
        conn.read_only = True
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                cur.execute("SELECT current_setting('transaction_read_only') AS ro, "
                            "inet_server_addr()::text AS host, current_database() AS db, "
                            "pg_is_in_recovery() AS in_recovery")
                identity = cur.fetchone()
                if identity["ro"] != "on":
                    raise RuntimeError("export transaction is not read-only")
                for name, sql in EXPORT_SQL.items():
                    cur.execute(sql, params)
                    pd.DataFrame(cur.fetchall()).to_csv(out / name, index=False)
    manifest = {
        "kind": "raw_snapshot_export", "service": service, "server": identity,
        "params": {k: v for k, v in params.items() if k != "assets"},
        "asset_count": len(params["assets"]),
        "assets_sha256": hashlib.sha256("\n".join(params["assets"]).encode()).hexdigest(),
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": {name: {"sha256": sha256_file(out / name),
                         "rows": int(sum(1 for _ in open(out / name)) - 1)} for name in RAW_FILES},
    }
    (out / "raw_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def _bool(value: Any) -> bool | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, str):
        v = value.strip().lower()
        return True if v in {"t", "true", "1"} else False if v in {"f", "false", "0"} else None
    return bool(value)


def limit_prices_for_row(row: dict[str, Any], open_days: dict[str, list[dt.date]]) -> tuple[float, float, str]:
    """(limit_up_price, limit_down_price, rule_id) using tradeability rules."""
    preclose = row.get("preclose")
    exchange = str(row.get("exchange") or "")
    board = classify_board(symbol=str(row.get("symbol") or ""), exchange=exchange,
                           is_star=bool(_bool(row.get("is_star"))),
                           is_chinext=bool(_bool(row.get("is_chinext"))),
                           is_beijing=bool(_bool(row.get("is_beijing"))), board=row.get("board"))
    trade_date = dt.date.fromisoformat(str(row["trade_date"]))
    list_date = (dt.date.fromisoformat(str(row["list_date"]))
                 if isinstance(row.get("list_date"), str) and row["list_date"] else None)
    sess_idx = None
    days = open_days.get(exchange)
    # Session index only when the calendar actually covers the listing date;
    # otherwise it would be undercounted and misread as an IPO window.
    if list_date is not None and days and days[0] <= list_date:
        lo, hi = bisect.bisect_left(days, list_date), bisect.bisect_right(days, trade_date)
        sess_idx = hi - lo if hi > lo else None
    if sess_idx is not None:
        event = "ipo" if sess_idx <= 10 else "continuous"
    else:
        event = "ipo" if list_date and (trade_date - list_date).days <= 30 else "continuous"
    is_st = _bool(row.get("is_st"))
    if is_st is None:
        return float("nan"), float("nan"), "st_state_missing"
    rule = resolve_limit_rule(board=board, exchange=exchange,
                              status_class="risk_warning" if is_st else "normal",
                              event_class=event, trade_date=trade_date,
                              listing_age_trading_days=sess_idx)
    if rule.rule_id == "rule_unknown" or not rule.verified:
        return float("nan"), float("nan"), rule.rule_id
    if (rule.no_limit_window_days and event in {"ipo", "relisting"} and sess_idx is not None
            and 1 <= sess_idx <= rule.no_limit_window_days):
        return float("inf"), 0.0, rule.rule_id
    if preclose is None or pd.isna(preclose) or float(preclose) <= 0:
        return float("nan"), float("nan"), rule.rule_id
    up = rule.day1_up_pct if sess_idx == 1 and rule.day1_up_pct is not None else rule.up_limit_pct
    dn = rule.day1_down_pct if sess_idx == 1 and rule.day1_down_pct is not None else rule.down_limit_pct
    lu = legal_limit_price(float(preclose), up, "up")
    ld = legal_limit_price(float(preclose), dn, "down")
    return (float("nan") if lu is None else lu, float("nan") if ld is None else ld, rule.rule_id)


def build_engine_bars(raw_dir: str | Path, out_dir: str | Path, *, calendar_exchange: str = "SH") -> dict[str, Any]:
    raw = Path(raw_dir)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    bars = pd.read_csv(raw / "bars_raw.csv", dtype={"asset_id": str})
    status = pd.read_csv(raw / "asset_status.csv", dtype={"asset_id": str})
    master = pd.read_csv(raw / "asset_master.csv", dtype={"asset_id": str, "symbol": str})
    adj = pd.read_csv(raw / "adjustment_factor.csv", dtype={"asset_id": str})
    cal = pd.read_csv(raw / "trading_calendar.csv")
    if set(bars["adjust_type"].astype(str)) != {"raw"}:
        raise ValueError("bars_raw.csv must contain only adjust_type='raw'")
    open_days = {ex: sorted(dt.date.fromisoformat(d) for d in frame["trade_date"])
                 for ex, frame in cal.groupby("exchange")}
    frame = bars.merge(status, on=["asset_id", "trade_date"], how="left", indicator="_status")
    frame = frame.merge(master, on="asset_id", how="left")
    frame = frame.merge(adj[["asset_id", "trade_date", "hfq_factor"]],
                        on=["asset_id", "trade_date"], how="left")
    prices = [limit_prices_for_row(r, open_days) for r in frame.to_dict("records")]
    frame["limit_up_price"] = [p[0] for p in prices]
    frame["limit_down_price"] = [p[1] for p in prices]
    frame["limit_rule_id"] = [p[2] for p in prices]
    # unknown status row -> suspension unknown (engine fails closed)
    frame["is_suspended"] = frame["is_suspended"].map(_bool).astype(object)
    frame.loc[frame["_status"] != "both", "is_suspended"] = None
    frame = frame.rename(columns={"hfq_factor": "adj_factor"})
    cols = ["trade_date", "asset_id", "adjust_type", "open", "high", "low", "close", "volume",
            "amount", "preclose", "is_suspended", "is_st", "limit_up_price", "limit_down_price",
            "limit_rule_id", "adj_factor"]
    frame = frame[cols].sort_values(["trade_date", "asset_id"]).reset_index(drop=True)
    frame.to_csv(out / "bars.csv", index=False, float_format="%.6f")
    lo, hi = frame["trade_date"].min(), frame["trade_date"].max()
    days = sorted(d for d in cal.loc[cal["exchange"] == calendar_exchange, "trade_date"] if lo <= d <= hi)
    pd.DataFrame({"trade_date": days}).to_csv(out / "calendar.csv", index=False)
    quality = {
        "rows": int(len(frame)),
        "assets": int(frame["asset_id"].nunique()),
        "date_range": [lo, hi],
        "status_missing_rows": int(frame["is_suspended"].isna().sum()),
        "preclose_missing_rows": int(frame["preclose"].isna().sum()),
        "limit_unknown_rows": int(frame["limit_up_price"].isna().sum()),
        "no_limit_rows": int((frame["limit_up_price"] == float("inf")).sum()),
        "adj_factor_missing_rows": int(frame["adj_factor"].isna().sum()),
        "limit_rule_ids": {str(k): int(v) for k, v in frame["limit_rule_id"].value_counts().items()},
    }
    raw_manifest = raw / "raw_manifest.json"
    manifest = {
        "kind": "engine_bar_snapshot",
        "tradeability_contract_version": TRADEABILITY_CONTRACT_VERSION,
        "raw_inputs": {name: sha256_file(raw / name) for name in RAW_FILES},
        "raw_manifest_sha256": sha256_file(raw_manifest) if raw_manifest.exists() else None,
        "outputs": {name: sha256_file(out / name) for name in ("bars.csv", "calendar.csv")},
        "quality": quality,
    }
    manifest["snapshot_id"] = "bars:" + hashlib.sha256(
        json.dumps(manifest["outputs"], sort_keys=True).encode()).hexdigest()[:16]
    (out / "snapshot_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Research snapshot export / preparation")
    sub = parser.add_subparsers(dest="cmd", required=True)
    exp = sub.add_parser("export", help="READ ONLY export from a restore instance")
    exp.add_argument("--service", required=True, help="pg_service name of the RESTORE instance")
    exp.add_argument("--start", required=True)
    exp.add_argument("--end", required=True)
    exp.add_argument("--assets-file", required=True, help="one asset_id per line")
    exp.add_argument("--adj-source-version", required=True)
    exp.add_argument("--calendar-source-version", required=True)
    exp.add_argument("--out-dir", required=True)
    bld = sub.add_parser("build", help="offline: raw CSVs -> engine bars + manifest")
    bld.add_argument("--raw-dir", required=True)
    bld.add_argument("--out-dir", required=True)
    args = parser.parse_args(argv)
    if args.cmd == "export":
        assets = [a.strip() for a in Path(args.assets_file).read_text().splitlines() if a.strip()]
        result = export_raw_snapshot(service=args.service, start=args.start, end=args.end,
                                     assets=assets, adj_source_version=args.adj_source_version,
                                     calendar_source_version=args.calendar_source_version,
                                     out_dir=args.out_dir)
    else:
        result = build_engine_bars(args.raw_dir, args.out_dir)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
