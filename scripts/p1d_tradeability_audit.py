#!/usr/bin/env python3
"""DATA-R3-P1d read-only audit driver.

Produces:
- tradeability_edge_cases.json : real (asset, date) cases evaluated through
  stock_research.tradeability.tradeability_at on live DB context.
- regression disagreement aggregates comparing stored is_limit_* flags in
  core.asset_status_daily with the effective-dated historical rule table.

This script is strictly read-only: SELECTs against core/market/public tables,
writes only the JSON artifact. It does not touch strategy fill logic.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, "src")

from stock_research.db import connect, fetch_all  # noqa: E402
from stock_research.tradeability import (  # noqa: E402
    TradeabilityContext,
    load_tradeability_context,
    tradeability_at,
)

OUT_DIR = Path("docs/research_upgrade/p1d")

# Hand-picked real cases verified during the audit (asset, date, expectation).
CASES = [
    # pre-listing
    {"asset": "CN:SH:688287", "date": "2022-05-24", "side": "buy",
     "case": "pre_listing", "expect": {"eligible_for_universe": False}},
    # post-delisting (退市观典 delisted 2026-06-10)
    {"asset": "CN:SH:688287", "date": "2026-06-11", "side": "sell",
     "case": "post_delisting", "expect": {"eligible_for_universe": False}},
    # delisted asset still valid inside its listing window (survivorship)
    {"asset": "CN:SH:688287", "date": "2026-05-20", "side": "buy",
     "case": "survivorship_in_window", "expect": {"eligible_for_universe": True}},
    # ST as of historical date (600815 ST in 2018)
    {"asset": "CN:SH:600815", "date": "2018-01-02", "side": "buy",
     "case": "st_point_in_time", "expect": {"limit_rule_id": "st_main_5pct"}},
    # suspended day (600126 2019-06-03)
    {"asset": "CN:SH:600126", "date": "2019-06-03", "side": "buy",
     "case": "suspended_day", "expect": {"can_attempt_buy": False}},
    # real limit-up (600519 +10.00% 2015-04-16)
    {"asset": "CN:SH:600519", "date": "2015-04-16", "side": "buy",
     "case": "limit_up_buy", "expect": {"can_attempt_buy": False}},
    # real limit-down (600519 -10.00% 2018-10-29)
    {"asset": "CN:SH:600519", "date": "2018-10-29", "side": "sell",
     "case": "limit_down_sell", "expect": {"can_attempt_sell": False}},
    # regime boundary: ChiNext +10.02% 2019-03-11 under old ±10% rule
    {"asset": "CN:SZ:300001", "date": "2019-03-11", "side": "buy",
     "case": "chinext_old_10pct_limit", "expect": {"can_attempt_buy": False,
                                                  "stored_flag_disagrees": True}},
    # same magnitude post-2020-08-24: NOT a limit day
    {"asset": "CN:SZ:300001", "date": "2020-08-25", "side": "buy",
     "case": "chinext_new_20pct_not_limit", "expect": {}},
    # STAR IPO day1 +875.82% (688808, 2026-04-24) — no-limit window
    {"asset": "CN:SH:688808", "date": "2026-04-24", "side": "buy",
     "case": "star_ipo_no_limit_window", "expect": {}},
    # Main-board IPO post-2023-04-10 day1 +66.32% (001312) — 5-day window
    {"asset": "CN:SZ:001312", "date": "2026-04-21", "side": "buy",
     "case": "main_ipo_postreg_no_limit", "expect": {}},
    # residual FACTOR_GAP asset keeps minute readiness blocked
    {"asset": "CN:SH:603213", "date": "2026-10-22", "side": "buy",
     "case": "factor_gap_residual", "blocks": ("minute_factor_gap",),
     "expect": {"data_ready_minute": False}},
]

# Aggregate regression scans: stored flag vs effective-rule evaluation.
DISAGREE_SCANS = {
    "chinext_pre_20200824_pct_9.9_19.8_stored_not_limit_up": """
        SELECT s.asset_id, s.trade_date::text AS d, b.pct_chg, s.is_limit_up
        FROM core.asset_status_daily s
        JOIN public.market_daily_bar b
          ON b.asset_id = s.asset_id AND b.trade_date = s.trade_date
         AND b.adjust_type = 'hfq'
        JOIN core.asset_master a ON a.asset_id = s.asset_id
        WHERE a.is_chinext
          AND s.trade_date < '2020-08-24'
          AND b.pct_chg >= 9.90 AND b.pct_chg < 19.75
          AND NOT s.is_limit_up
    """,
    "ipo_no_limit_window_stored_limit_up": """
        SELECT s.asset_id, s.trade_date::text AS d, b.pct_chg, s.is_limit_up
        FROM core.asset_status_daily s
        JOIN public.market_daily_bar b
          ON b.asset_id = s.asset_id AND b.trade_date = s.trade_date
         AND b.adjust_type = 'hfq'
        JOIN core.asset_master a ON a.asset_id = s.asset_id
        WHERE s.is_limit_up
          AND (
            (a.is_star AND a.list_date >= '2019-07-22')
            OR (a.is_chinext AND a.list_date >= '2020-08-24')
            OR (NOT a.is_star AND NOT a.is_chinext AND NOT a.is_beijing
                AND a.list_date >= '2023-04-10')
          )
          AND s.trade_date < a.list_date + INTERVAL '10 days'
    """,
    "st_on_20pct_board_pct_5_19.8_stored_not_limit": """
        SELECT s.asset_id, s.trade_date::text AS d, b.pct_chg, s.is_limit_up
        FROM core.asset_status_daily s
        JOIN public.market_daily_bar b
          ON b.asset_id = s.asset_id AND b.trade_date = s.trade_date
         AND b.adjust_type = 'hfq'
        JOIN core.asset_master a ON a.asset_id = s.asset_id
        WHERE (a.is_chinext OR a.is_star OR a.is_beijing)
          AND s.is_st
          AND b.pct_chg >= 9.90 AND b.pct_chg < 19.75
          AND NOT s.is_limit_up
    """,
}


def run_cases(conn) -> list[dict]:
    out = []
    for c in CASES:
        blocks = tuple(c.get("blocks", ()))
        ctx = load_tradeability_context(conn, c["asset"], c["date"],
                                        data_quality_blocks=blocks)
        if ctx is None:
            out.append({"case": c["case"], "asset": c["asset"], "date": c["date"],
                        "error": "asset_not_in_master"})
            continue
        if c["case"].startswith(("star_ipo", "main_ipo")):
            # IPO-day cases: session age = 1 by construction.
            ctx = TradeabilityContext(**{**ctx.__dict__,
                                         "listing_age_trading_days": 1})
        res = tradeability_at(ctx, side=c["side"], data_version="full_history_v1")
        d = asdict(res)
        d["case"] = c["case"]
        d["expect"] = c.get("expect", {})
        mismatches = {
            k: {"expect": v, "actual": d.get(k)}
            for k, v in c.get("expect", {}).items() if d.get(k) != v
        }
        d["expect_mismatches"] = mismatches
        d["pass"] = not mismatches
        out.append(d)
    return out


def run_disagreement_scans(conn) -> dict:
    out = {}
    for name, sql in DISAGREE_SCANS.items():
        rows = fetch_all(conn, sql)
        out[name] = {
            "count": len(rows),
            "examples": [
                {k: (float(v) if k == "pct_chg" else v)
                 for k, v in r.items()}
                for r in rows[:25]
            ],
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DIR / "tradeability_edge_cases.json"))
    args = ap.parse_args()
    with connect("stock_research") as conn:
        cases = run_cases(conn)
        disagreements = run_disagreement_scans(conn)
    artifact = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "contract_version": "tradeability_pit_v1",
        "scope": "read-only audit; no strategy fill logic modified",
        "cases": cases,
        "disagreement_scans": disagreements,
        "case_pass_count": sum(1 for c in cases if c.get("pass")),
        "case_total": len(cases),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2))
    failed = [c["case"] for c in cases if not c.get("pass")]
    print(f"cases: {artifact['case_pass_count']}/{artifact['case_total']} pass")
    for name, s in disagreements.items():
        print(f"  {name}: {s['count']} rows")
    if failed:
        print("FAILED:", failed)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
