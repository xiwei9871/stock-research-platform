#!/usr/bin/env python3
"""P1d.1 P0-G: baseline-vs-shadow backtest impact audit.

Isolation contract:
  * same scores, same price bars, same VectorizedTopNConfig for both runs;
  * the ONLY difference is the is_limit_up / is_limit_down columns of the
    price frame the engine consumes:
      - BASELINE: stored core.asset_status_daily flags (what market_daily_bar
        served historically);
      - SHADOW:   flags recomputed from raw OHLC + the P1d.1 historical rule
        engine (resolve_limit_rule + legal_limit_price + real listing
        session index), fail-closed on rule_unknown / missing raw bar.
  * no production code path is modified; run_vectorized_topn_backtest is
    invoked twice on in-memory frames.

Outputs (docs/research_upgrade/p1d1/):
  * BACKTEST_SHADOW_COMPARISON.csv : per-trade diff rows + summary rows
  * BACKTEST_SHADOW_SUMMARY.json   : aggregate metrics + flip attribution
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import json
import sys
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.tradeability import (  # noqa: E402
    classify_board,
    legal_limit_price,
    resolve_limit_rule,
)
from stock_research.vectorized_topn_backtest import (  # noqa: E402
    VectorizedTopNConfig,
    run_vectorized_topn_backtest,
)

OUT_DIR = Path("docs/research_upgrade/p1d1")

CONTEXT_SQL = """
SELECT s.asset_id, s.trade_date::text AS trade_date,
       a.symbol, a.exchange, a.board, a.is_star, a.is_chinext, a.is_beijing,
       a.list_date::text AS list_date,
       s.is_st, s.is_suspended,
       b.close AS close_raw, b.preclose AS preclose_raw
FROM core.asset_status_daily s
JOIN core.asset_master a ON a.asset_id = s.asset_id
LEFT JOIN public.market_daily_bar b
  ON b.asset_id = s.asset_id AND b.trade_date = s.trade_date
 AND b.adjust_type = 'raw'
WHERE s.trade_date BETWEEN %s AND %s
"""


def _f(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        f = float(v)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _d(v):
    return dt.date.fromisoformat(str(v)[:10]) if v else None


@lru_cache(maxsize=None)
def _rule(board, exchange, status_class, event, date_iso, sess_idx):
    return resolve_limit_rule(
        board=board,
        exchange=exchange,
        status_class=status_class,
        event_class=event,
        trade_date=dt.date.fromisoformat(date_iso),
        listing_age_trading_days=sess_idx,
    )


def recompute_flags(conn, start: str, end: str,
                    open_days: dict[str, list[dt.date]]) -> pd.DataFrame:
    """Return DataFrame[(asset_id, trade_date)] with corrected flags.

    shadow_limit_up/down: True only when raw close reaches the legal limit
    price under the historically effective rule (no-limit window -> False).
    shadow_rule_unknown : no verified rule OR raw bar missing while the
    status row claims a traded day -> fail-closed marker.
    shadow_rule_id      : traceability back to LIMIT_RULES.
    """
    rows = fetch_all(conn, CONTEXT_SQL, [start, end])
    recs = []
    for r in rows:
        board = classify_board(
            symbol=str(r.get("symbol") or ""),
            exchange=str(r.get("exchange") or ""),
            is_star=bool(r.get("is_star")),
            is_chinext=bool(r.get("is_chinext")),
            is_beijing=bool(r.get("is_beijing")),
            board=r.get("board"),
        )
        trade_date = _d(r["trade_date"])
        list_date = _d(r.get("list_date"))
        exchange = str(r.get("exchange") or "")
        status_class = "risk_warning" if r.get("is_st") else "normal"
        sess_idx = None
        if list_date is not None and open_days.get(exchange):
            days = open_days[exchange]
            lo = bisect.bisect_left(days, list_date)
            hi = bisect.bisect_right(days, trade_date)
            sess_idx = hi - lo if hi > lo else None
        if sess_idx is not None:
            event = "ipo" if sess_idx <= 10 else "continuous"
        else:
            event = ("ipo" if list_date and (trade_date - list_date).days <= 30
                     else "continuous")
        rule = _rule(board, exchange, status_class, event,
                     trade_date.isoformat(), sess_idx)
        close_raw = _f(r.get("close_raw"))
        preclose_raw = _f(r.get("preclose_raw"))
        no_limit = bool(
            rule.no_limit_window_days
            and event in {"ipo", "relisting"}
            and sess_idx is not None
            and 1 <= sess_idx <= rule.no_limit_window_days
        )
        unknown = rule.rule_id == "rule_unknown" or not rule.verified
        if unknown or close_raw is None or preclose_raw is None:
            recs.append({
                "asset_id": r["asset_id"], "trade_date": r["trade_date"],
                "shadow_limit_up": False, "shadow_limit_down": False,
                "shadow_rule_unknown": True,
                "shadow_rule_id": rule.rule_id,
            })
            continue
        lim_up = lim_dn = False
        if not no_limit:
            eff_up = (rule.day1_up_pct if sess_idx == 1
                      and rule.day1_up_pct is not None else rule.up_limit_pct)
            eff_dn = (rule.day1_down_pct if sess_idx == 1
                      and rule.day1_down_pct is not None else rule.down_limit_pct)
            legal_up = legal_limit_price(preclose_raw, eff_up, "up")
            legal_dn = legal_limit_price(preclose_raw, eff_dn, "down")
            lim_up = legal_up is not None and close_raw >= legal_up - 1e-9
            lim_dn = legal_dn is not None and close_raw <= legal_dn + 1e-9
        recs.append({
            "asset_id": r["asset_id"], "trade_date": r["trade_date"],
            "shadow_limit_up": lim_up, "shadow_limit_down": lim_dn,
            "shadow_rule_unknown": False,
            "shadow_rule_id": rule.rule_id,
        })
    return pd.DataFrame(recs)


def apply_shadow_flags(prices: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of prices with corrected limit flags.

    rule_unknown rows fail closed: both limit flags forced True so
    can_open_long/can_close_long block the attempt (conservative).
    """
    flags = flags.copy()
    flags["trade_date"] = pd.to_datetime(flags["trade_date"])
    merged = prices.copy()
    merged["trade_date"] = pd.to_datetime(merged["trade_date"])
    merged = merged.merge(flags, on=["asset_id", "trade_date"], how="left")
    for col in ("shadow_limit_up", "shadow_limit_down", "shadow_rule_unknown"):
        merged[col] = merged[col].fillna(False).astype(bool)
    # rows absent from status context entirely -> fail closed too
    merged["is_limit_up"] = merged["shadow_limit_up"] | merged["shadow_rule_unknown"]
    merged["is_limit_down"] = merged["shadow_limit_down"] | merged["shadow_rule_unknown"]
    return merged.drop(columns=["shadow_limit_up", "shadow_limit_down"])


PRICE_WITH_STATUS_SQL = """
SELECT b.trade_date, b.asset_id, b.open, b.close, b.amount, b.trade_status,
       s.is_limit_up, s.is_limit_down, s.is_suspended
FROM public.market_daily_bar b
LEFT JOIN core.asset_status_daily s
  ON s.asset_id = b.asset_id AND s.trade_date = b.trade_date
WHERE b.adjust_type = %s
  AND b.trade_date BETWEEN %s AND %s
ORDER BY b.trade_date, b.asset_id
"""

SCORE_SQL = """
SELECT trade_date, asset_id, rank, score_total
FROM factor.stock_score_daily
WHERE score_version = %s AND trade_date BETWEEN %s AND %s
ORDER BY trade_date, rank, asset_id
"""


def run_comparison(start: str, end: str, score_version: str,
                   top_n: int, frequency: str, cost_bps: float) -> dict:
    print(f"[{dt.datetime.now():%H:%M:%S}] loading inputs {start}..{end} "
          f"score_version={score_version}", flush=True)
    # NOTE: production load_vectorized_topn_inputs reads is_limit_up /
    # is_limit_down / is_suspended FROM market_daily_bar, but those columns
    # no longer exist there (UndefinedColumn at runtime on the current DB).
    # The shadow loader below performs the semantically intended join:
    # hfq prices from public.market_daily_bar, execution flags from
    # core.asset_status_daily. Baseline therefore uses the SAME stored
    # flags production would have consumed; only the flag VALUES differ
    # in the shadow leg. The loader defect itself is a Gate-2 finding.
    with connect("stock_research") as conn:
        scores = pd.DataFrame(fetch_all(
            conn, SCORE_SQL, [score_version, start, end]))
        prices = pd.DataFrame(fetch_all(
            conn, PRICE_WITH_STATUS_SQL, ["hfq", start, end]))
    print(f"  scores={len(scores):,} prices={len(prices):,}", flush=True)

    with connect("stock_research") as conn:
        open_days: dict[str, list[dt.date]] = {}
        for r in fetch_all(conn,
                "select exchange, trade_date::text d from market.trading_calendar "
                "where is_open order by exchange, trade_date"):
            open_days.setdefault(r["exchange"], []).append(
                dt.date.fromisoformat(r["d"]))
        print(f"[{dt.datetime.now():%H:%M:%S}] recomputing flags", flush=True)
        flags = recompute_flags(conn, start, end, open_days)
    print(f"  recomputed {len(flags):,} rows; "
          f"rule_unknown={int(flags['shadow_rule_unknown'].sum()):,}; "
          f"limit_up={int(flags['shadow_limit_up'].sum()):,}; "
          f"limit_down={int(flags['shadow_limit_down'].sum()):,}", flush=True)

    shadow_prices = apply_shadow_flags(prices, flags)
    flags_key = flags.assign(
        trade_date=pd.to_datetime(flags["trade_date"]).dt.strftime("%Y-%m-%d")
    ).set_index(["asset_id", "trade_date"])

    config = VectorizedTopNConfig(
        start_date=start, end_date=end, top_n=top_n,
        rebalance_frequency=frequency, transaction_cost_bps=cost_bps,
    )
    print(f"[{dt.datetime.now():%H:%M:%S}] baseline run", flush=True)
    base = run_vectorized_topn_backtest(scores, prices, config)
    print(f"[{dt.datetime.now():%H:%M:%S}] shadow run", flush=True)
    shad = run_vectorized_topn_backtest(scores, shadow_prices, config)

    def _tkey(df):
        return df.assign(
            k=(df["asset_id"].astype(str) + "|" + df["side"].astype(str)
               + "|" + df["execution_date"].astype(str))
        ).set_index("k")

    def _agg(df):
        """Collapse duplicate (asset|side|exec_date) rows to comparable scalars."""
        g = df.groupby("k", sort=False)
        return pd.DataFrame({
            "exec_w": g["executed_weight"].apply(
                lambda s: float(pd.to_numeric(s, errors="coerce").fillna(0).sum())),
            "skips": g["skip_reason"].apply(
                lambda s: ",".join(sorted({str(x) for x in s if pd.notna(x) and x}))),
            "rebalance_date": g["rebalance_date"].first(),
        })

    bt = _agg(_tkey(base.trades))
    st = _agg(_tkey(shad.trades))
    diff_rows = []
    all_keys = sorted(set(bt.index) | set(st.index))
    for k in all_keys:
        b = bt.loc[k] if k in bt.index else None
        s = st.loc[k] if k in st.index else None
        b_exec = float(b["exec_w"]) if b is not None else 0.0
        s_exec = float(s["exec_w"]) if s is not None else 0.0
        b_skip = str(b["skips"]) if b is not None else ""
        s_skip = str(s["skips"]) if s is not None else ""
        if b is not None and s is not None:
            if b_exec == s_exec and b_skip == s_skip:
                continue
            status = "CHANGED"
            ref = s
        else:
            status = "ONLY_BASELINE" if b is not None else "ONLY_SHADOW"
            ref = b if b is not None else s
        asset, side, ex_date = k.split("|")
        ex_date = ex_date[:10]
        fk = flags_key.loc[(asset, ex_date)] if (asset, ex_date) in flags_key.index else None
        diff_rows.append({
            "diff_status": status,
            "asset_id": asset, "side": side, "execution_date": ex_date,
            "baseline_executed_weight": b_exec,
            "shadow_executed_weight": s_exec,
            "baseline_skip_reason": b_skip,
            "shadow_skip_reason": s_skip,
            "shadow_rule_id": fk["shadow_rule_id"] if fk is not None else "",
            "shadow_rule_unknown": bool(fk["shadow_rule_unknown"]) if fk is not None else "",
            "rebalance_date": str(ref.get("rebalance_date", "")),
        })

    def _metrics(res):
        eq = res.equity_curve
        curve = eq["equity"].astype(float) if len(eq) else pd.Series([1.0])
        dd = float((curve / curve.cummax() - 1.0).min())
        tr = res.trades
        return {
            "final_equity": float(curve.iloc[-1]),
            "total_return": float(curve.iloc[-1] - 1.0),
            "max_drawdown": dd,
            "trade_rows": int(len(tr)),
            "buy_rows": int((tr["side"] == "buy").sum()) if len(tr) else 0,
            "sell_rows": int((tr["side"] == "sell").sum()) if len(tr) else 0,
            "skipped_limit_up": int((tr["skip_reason"] == "limit_up").sum()) if len(tr) else 0,
            "skipped_limit_down": int((tr["skip_reason"] == "limit_down").sum()) if len(tr) else 0,
            "skipped_suspended": int((tr["skip_reason"] == "suspended").sum()) if len(tr) else 0,
            "executed_weight": float(tr["executed_weight"].fillna(0).abs().sum()) if len(tr) else 0.0,
            "summary": res.summary,
        }

    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window": {"start": start, "end": end,
                   "score_version": score_version, "top_n": top_n,
                   "rebalance_frequency": frequency,
                   "transaction_cost_bps": cost_bps},
        "isolation": "same scores/prices/config; only is_limit_up/down differ",
        "flag_recompute": {
            "rows": int(len(flags)),
            "shadow_limit_up_true": int(flags["shadow_limit_up"].sum()),
            "shadow_limit_down_true": int(flags["shadow_limit_down"].sum()),
            "rule_unknown_fail_closed": int(flags["shadow_rule_unknown"].sum()),
        },
        "baseline": _metrics(base),
        "shadow": _metrics(shad),
        "trade_diff_rows": len(diff_rows),
    }
    return summary, diff_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-01-02")
    ap.add_argument("--end", default="2026-10-23")
    ap.add_argument("--score-version", default="manual_v1")
    ap.add_argument("--top-n", type=int, default=20)
    ap.add_argument("--frequency", default="daily")
    ap.add_argument("--cost-bps", type=float, default=0.0)
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    summary, diff_rows = run_comparison(
        args.start, args.end, args.score_version,
        args.top_n, args.frequency, args.cost_bps)

    if diff_rows:
        pd.DataFrame(diff_rows).to_csv(
            out_dir / "BACKTEST_SHADOW_COMPARISON.csv", index=False)
    else:
        (out_dir / "BACKTEST_SHADOW_COMPARISON.csv").write_text(
            "diff_status,asset_id,side,execution_date,"
            "baseline_executed_weight,shadow_executed_weight,"
            "baseline_skip_reason,shadow_skip_reason,"
            "shadow_rule_id,shadow_rule_unknown,rebalance_date\n")
    (out_dir / "BACKTEST_SHADOW_SUMMARY.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print(json.dumps({
        "trade_diff_rows": summary["trade_diff_rows"],
        "baseline": {k: v for k, v in summary["baseline"].items() if k != "summary"},
        "shadow": {k: v for k, v in summary["shadow"].items() if k != "summary"},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
