#!/usr/bin/env python3
"""P1d.1 read-only audit driver.

Outputs (docs/research_upgrade/p1d1/):
- LIMIT_FLAG_RECONCILIATION.csv : row-level stored-vs-effective-rule recompute
  inside every regime segment where the static threshold could diverge
  (ChiNext reform + ST transitions, STAR/BSE, IPO windows, delisting
  arrangement, pre-limit era). NOT a re-scan of the old 28,205/1,305 guess —
  a bidirectional recount: stored_true_but_not_limit (FP) and
  stored_false_but_limit (FN), plus boundary classes.
- TRADEABILITY_FAIL_CLOSED_TESTS.json : real-DB edge cases through the v2 gate.
- MINUTE_VERSION_GATE_AUDIT stats (embedded in json 'minute_gate' + md doc).

Classification per row:
  CONFIRMED_MISLABEL / SUSPECTED_MISLABEL / RULE_UNKNOWN / DATA_INSUFFICIENT / CORRECT
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, "src")

from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.tradeability import (  # noqa: E402
    CHINEXT_REFORM_DATE,
    FULL_REGISTRATION_DATE,
    LedgerMinuteQualificationProvider,
    LimitClass,
    TradeabilityContext,
    classify_board,
    classify_limit_day,
    legal_limit_price,
    load_tradeability_context,
    resolve_limit_rule,
    tradeability_at,
)

OUT_DIR = Path("docs/research_upgrade/p1d1")

# Regime segments where the static threshold can diverge from the effective
# rule. Each row carries raw prices so the legal-limit comparison is real.
SCAN_SQL = """
SELECT s.asset_id, s.trade_date::text AS trade_date,
       a.symbol, a.exchange, a.board, a.is_star, a.is_chinext, a.is_beijing,
       a.list_date::text AS list_date, a.delist_date::text AS delist_date,
       s.is_st, s.is_suspended, s.is_limit_up, s.is_limit_down,
       s.limit_up_price, s.limit_down_price,
       b.open, b.high, b.low, b.close, b.preclose, b.pct_chg, b.trade_status
FROM core.asset_status_daily s
JOIN core.asset_master a ON a.asset_id = s.asset_id
JOIN public.market_daily_bar b
  ON b.asset_id = s.asset_id AND b.trade_date = s.trade_date AND b.adjust_type = 'raw'
WHERE ({where})
"""

SEGMENTS = {
    # ChiNext all history: 10->20 regime change, ST 5->20, delisting transition
    "chinext_all": "a.is_chinext",
    # STAR all: 20% regime + IPO windows
    "star_all": "a.is_star",
    # BSE all
    "beijing_all": "a.is_beijing",
    # main-board IPO events: within 40 days of listing (covers prereg day-1 cap
    # and post-2023 window-5)
    "main_ipo_recent": """NOT a.is_star AND NOT a.is_chinext AND NOT a.is_beijing
        AND s.trade_date <= a.list_date + INTERVAL '40 days'
        AND s.trade_date >= a.list_date""",
    # main-board ST rows near the 5% bound (sanity direction) + any stored flag
    "main_st_flags": """NOT a.is_star AND NOT a.is_chinext AND NOT a.is_beijing
        AND s.is_st AND (b.pct_chg >= 4.5 OR b.pct_chg <= -4.5)""",
    # pre-limit era
    "pre_19961216": "s.trade_date < '1996-12-16'",
    # relisting candidates (>1 listed event) — whole history around re-listing
    "relisting": """a.asset_id IN (SELECT asset_id FROM core.asset_lifecycle_event
        WHERE event_type='listed' GROUP BY asset_id HAVING count(*)>=2)
        AND s.trade_date <= (SELECT max(le2.event_date) + INTERVAL '15 days'
            FROM core.asset_lifecycle_event le2
            WHERE le2.asset_id=a.asset_id AND le2.event_type='listed')
        AND s.trade_date >= (SELECT max(le3.event_date)
            FROM core.asset_lifecycle_event le3
            WHERE le3.asset_id=a.asset_id AND le3.event_type='listed')""",
}

EDGE_CASES = [
    {"asset": "CN:SH:688287", "date": "2022-05-24", "side": "buy", "case": "pre_listing"},
    {"asset": "CN:SH:688287", "date": "2026-06-11", "side": "sell", "case": "post_delisting"},
    {"asset": "CN:SH:688287", "date": "2026-05-20", "side": "buy", "case": "in_window_delisted_asset"},
    {"asset": "CN:SH:600815", "date": "2018-01-02", "side": "buy", "case": "st_2018"},
    {"asset": "CN:SH:600126", "date": "2019-06-03", "side": "buy", "case": "suspended_20190603"},
    {"asset": "CN:SH:600519", "date": "2015-04-16", "side": "buy", "case": "limit_up_20150416"},
    {"asset": "CN:SH:600519", "date": "2018-10-29", "side": "sell", "case": "limit_down_20181029"},
    {"asset": "CN:SZ:300001", "date": "2019-03-11", "side": "buy", "case": "chinext_old10pct_limit"},
    {"asset": "CN:SZ:300001", "date": "2020-08-25", "side": "buy", "case": "chinext_new20pct_not_limit"},
    {"asset": "CN:SH:688808", "date": "2026-04-24", "side": "buy", "case": "star_ipo_day1_875pct"},
    {"asset": "CN:SZ:001312", "date": "2026-04-21", "side": "buy", "case": "main_fullreg_ipo_day1"},
    {"asset": "CN:SH:603213", "date": "2026-10-22", "side": "buy", "case": "factor_gap_residual"},
    {"asset": "CN:SH:600153", "date": "2026-10-22", "side": "buy", "case": "post_diff_isolation"},
    {"asset": "CN:SZ:000001", "date": "1993-11-22", "side": "buy", "case": "pre_limit_era"},
]


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


def recount_segment(conn, name: str, where: str,
                    open_days: dict[str, list[dt.date]]) -> list[dict]:
    import bisect
    rows = fetch_all(conn, SCAN_SQL.format(where=where))
    out = []
    for r in rows:
        board = classify_board(
            symbol=str(r.get("symbol") or ""), exchange=str(r.get("exchange") or ""),
            is_star=bool(r.get("is_star")), is_chinext=bool(r.get("is_chinext")),
            is_beijing=bool(r.get("is_beijing")), board=r.get("board"))
        trade_date = _d(r["trade_date"])
        list_date = _d(r.get("list_date"))
        exchange = str(r.get("exchange") or "")
        status_class = "risk_warning" if r.get("is_st") else "normal"
        # exact listing-session index from the exchange open-day calendar
        sess_idx = None
        if list_date is not None and open_days.get(exchange):
            days = open_days[exchange]
            lo = bisect.bisect_left(days, list_date)
            hi = bisect.bisect_right(days, trade_date)
            sess_idx = hi - lo if hi > lo else None
        # event only inside the early sessions; beyond that it is continuous
        if sess_idx is not None:
            event = "ipo" if sess_idx <= 10 else "continuous"
        else:
            event = "ipo" if list_date and (trade_date - list_date).days <= 30 else "continuous"
        rule = resolve_limit_rule(
            board=board, exchange=exchange,
            status_class=status_class, event_class=event, trade_date=trade_date,
            listing_age_trading_days=sess_idx)
        for side in ("buy", "sell"):
            stored = r["is_limit_up"] if side == "buy" else r["is_limit_down"]
            day1_cap = rule.day1_up_pct if side == "buy" else rule.day1_down_pct
            eff_pct = rule.up_limit_pct if side == "buy" else rule.down_limit_pct
            if sess_idx == 1 and day1_cap is not None:
                eff_pct = day1_cap
            legal = legal_limit_price(_f(r.get("preclose")), eff_pct,
                                      "up" if side == "buy" else "down")
            no_limit = bool(
                rule.no_limit_window_days
                and event in {"ipo", "relisting"}
                and sess_idx is not None
                and 1 <= sess_idx <= rule.no_limit_window_days
            )
            cls = classify_limit_day(
                open_raw=_f(r.get("open")), high_raw=_f(r.get("high")),
                low_raw=_f(r.get("low")), close_raw=_f(r.get("close")),
                legal_limit_price_value=legal, pct_chg=_f(r.get("pct_chg")),
                rule_up_pct=eff_pct if side == "buy" else None,
                rule_down_pct=eff_pct if side == "sell" else None,
                side=side, no_limit_window=no_limit, rule=rule)
            corrected = cls in {LimitClass.CLOSE_AT_LIMIT.value,
                                LimitClass.ONE_WAY_LOCKED.value,
                                LimitClass.PCT_NEAR_LIMIT_UNVERIFIED.value}
            if cls == LimitClass.DATA_INSUFFICIENT.value:
                klass = "DATA_INSUFFICIENT"
            elif rule.rule_id == "rule_unknown" or not rule.verified:
                klass = "RULE_UNKNOWN"
            elif bool(stored) == corrected and cls not in {
                    LimitClass.PCT_NEAR_LIMIT_UNVERIFIED.value}:
                klass = "CORRECT"
            elif cls == LimitClass.PCT_NEAR_LIMIT_UNVERIFIED.value and not stored:
                klass = "SUSPECTED_MISLABEL"   # near-limit, unproven
            else:
                klass = "CONFIRMED_MISLABEL"
            if klass != "CORRECT" or bool(stored):
                out.append({
                    "asset_id": r["asset_id"], "trade_date": r["trade_date"],
                    "side": side, "segment": name, "board": board,
                    "status_class": status_class, "event": event,
                    "session_index": sess_idx,
                    "old_flag": bool(stored),
                    "historical_rule": rule.rule_id,
                    "rule_up_pct": rule.up_limit_pct, "effective_pct_used": eff_pct,
                    "legal_limit_price": legal,
                    "close_raw": _f(r.get("close")), "preclose_raw": _f(r.get("preclose")),
                    "pct_chg": _f(r.get("pct_chg")),
                    "limit_class": cls,
                    "corrected_flag": corrected,
                    "classification": klass,
                    "evidence_source": "raw_bar+asset_status_daily+LIMIT_RULES",
                })
    return out


def run_edge_cases(conn, provider) -> list[dict]:
    out = []
    for c in EDGE_CASES:
        ctx = load_tradeability_context(conn, c["asset"], c["date"],
                                        minute_provider=provider)
        if ctx is None:
            out.append({"case": c["case"], "error": "asset_not_in_master"})
            continue
        res = tradeability_at(ctx, side=c["side"], data_version="full_history_v1")
        d = asdict(res)
        d["case"] = c["case"]
        out.append(d)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--segments", default="all")
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    provider = LedgerMinuteQualificationProvider.from_repo()
    recon_rows: list[dict] = []
    edge: list[dict] = []
    minute_gate: dict = {}
    with connect("stock_research") as conn:
        # per-exchange open-day lists for exact listing-session index
        open_days: dict[str, list[dt.date]] = {}
        for r in fetch_all(conn,
                "select exchange, trade_date::text d from market.trading_calendar where is_open order by exchange, trade_date"):
            open_days.setdefault(r["exchange"], []).append(dt.date.fromisoformat(r["d"]))
        wanted = list(SEGMENTS) if args.segments == "all" else args.segments.split(",")
        for name in wanted:
            rows = recount_segment(conn, name, SEGMENTS[name], open_days)
            recon_rows.extend(rows)
            print(f"segment {name}: {len(rows)} non-correct rows", flush=True)
        edge = run_edge_cases(conn, provider)

    import csv
    if recon_rows:
        cols = list(recon_rows[0])
        with open(out_dir / "LIMIT_FLAG_RECONCILIATION.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(recon_rows)
    from collections import Counter
    klass = Counter(r["classification"] for r in recon_rows)
    seg_klass = {}
    for r in recon_rows:
        seg_klass.setdefault(r["segment"], Counter())[r["classification"]] += 1

    # minute gate audit numbers
    done_led = json.load(open("outputs/research/data01r1_finance_q2_20261020/r2_downstream_minute_done.json"))
    gap = set(json.load(open("outputs/research/data01r1_finance_q2_20261020/factor_gap_155_reconciliation.json"))["minute_residual_gap_assets"])
    done_assets = {k.split("|")[0] for k in done_led}
    minute_gate = {
        "done_keys": len(done_led),
        "done_assets": len(done_assets),
        "terminal_gap_assets": len(gap),
        "gap_with_alt_source_done": len(gap & done_assets),
        "gap_no_done_key": sorted(gap - done_assets),
        "post_diff_isolated": ["CN:SH:600153"],
    }

    artifact = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "contract_version": "tradeability_pit_v2",
        "edge_cases": edge,
        "edge_pass_summary": {
            "total": len(edge),
            "errors": [e for e in edge if "error" in e],
        },
        "reconciliation_classification_counts": dict(klass),
        "reconciliation_by_segment": {k: dict(v) for k, v in seg_klass.items()},
        "minute_gate": minute_gate,
    }
    (out_dir / "TRADEABILITY_FAIL_CLOSED_TESTS.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2))
    print(json.dumps({"classifications": dict(klass), "edge_cases": len(edge)},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
