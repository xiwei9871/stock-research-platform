#!/usr/bin/env python3
"""P1d.2 A4 — real-DB edge cases with explicit per-field assertions.

Every case declares expected values; each produces
{expected_state, actual_state, rule_id, reason, pass} rows. ANY mismatch
fails the run (exit 1) — 'errors=[]' is no longer the acceptance signal.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from stock_research.db import connect  # noqa: E402
from stock_research.tradeability import (  # noqa: E402
    LedgerMinuteQualificationProvider,
    load_tradeability_context,
    tradeability_at,
)

OUT_DIR = Path("docs/research_upgrade/p1d2")

# (asset, date, side, order_time, expectations)
CASES = [
    {"case": "pre_listing", "asset": "CN:SH:688287", "date": "2022-05-24",
     "side": "buy",
     "expect": {"universe_state": "INELIGIBLE",
                "reasons_contain": ["not_yet_listed"],
                "can_attempt_buy": False}},
    {"case": "post_delisting", "asset": "CN:SH:688287", "date": "2026-06-11",
     "side": "sell",
     "expect": {"universe_state": "INELIGIBLE",
                "reasons_contain": ["delisted"],
                "can_attempt_sell": False}},
    {"case": "in_window_delisted_asset", "asset": "CN:SH:688287",
     "date": "2026-05-20", "side": "buy",
     "expect": {"universe_state": "ELIGIBLE"}},
    {"case": "st_2018", "asset": "CN:SH:600815", "date": "2018-01-02",
     "side": "buy",
     "expect": {"limit_rule_id": "main_st_5pct",
                "reasons_contain": ["st_risk_warning"]}},
    {"case": "suspended_20190603", "asset": "CN:SH:600126",
     "date": "2019-06-03", "side": "buy",
     "expect": {"can_attempt_buy": False,
                "reasons_contain": ["suspended"]}},
    {"case": "limit_up_20150416", "asset": "CN:SH:600519",
     "date": "2015-04-16", "side": "buy",
     "expect": {"limit_rule_id": "main_10pct",
                "can_attempt_buy": False}},
    {"case": "limit_down_20181029", "asset": "CN:SH:600519",
     "date": "2018-10-29", "side": "sell",
     "expect": {"limit_rule_id": "main_10pct",
                "can_attempt_sell": False}},
    {"case": "chinext_old10pct_limit", "asset": "CN:SZ:300001",
     "date": "2019-03-11", "side": "buy",
     "expect": {"limit_rule_id": "chinext_10pct_pre_20200824",
                "can_attempt_buy": False}},
    {"case": "chinext_new20pct_not_limit", "asset": "CN:SZ:300001",
     "date": "2020-08-25", "side": "buy",
     "expect": {"limit_rule_id": "chinext_20pct_from_20200824",
                "can_attempt_buy": True}},
    {"case": "star_ipo_day1_875pct", "asset": "CN:SH:688808",
     "date": "2026-04-24", "side": "buy",
     "expect": {"limit_rule_id": "star_ipo_window5",
                "reasons_contain": ["ipo_no_limit_window"],
                "can_attempt_buy": True}},
    {"case": "main_fullreg_ipo_day1", "asset": "CN:SZ:001312",
     "date": "2026-04-21", "side": "buy",
     "expect": {"limit_rule_id": "main_ipo_fullreg_window5",
                "reasons_contain": ["ipo_no_limit_window"],
                "can_attempt_buy": True}},
    # 603213: terminal baostock gap; akshare key done BUT akshare rows exist
    # only on 2026-06-17 — key-level done must NOT self-declare readiness on
    # 2026-10-22 (P1d.2a C: date-bound verification, honest degrade).
    {"case": "factor_gap_residual", "asset": "CN:SH:603213",
     "date": "2026-10-22", "side": "buy",
     "expect": {"data_ready_minute": False,
                "reasons_contain": ["minute_date_unverified"]}},
    # ...but on 2026-06-17 (where akshare rows actually exist, 5min/qfq) the
    # same asset IS date-verified while keeping the gap audit marker.
    {"case": "alt_source_date_rows_verified", "asset": "CN:SH:603213",
     "date": "2026-06-17", "side": "buy",
     "expect": {"data_ready_minute": True,
                "reasons_contain": ["factor_gap_covered_by_alt_source"]}},
    {"case": "post_diff_isolation", "asset": "CN:SH:600153",
     "date": "2026-10-22", "side": "buy",
     "expect": {"data_ready_minute": False,
                "reasons_contain": ["post_diff_isolated"]}},
    {"case": "pre_limit_era", "asset": "CN:SZ:000001",
     "date": "1993-11-22", "side": "buy",
     "expect": {"limit_rule_id": "pre_19961216_no_limit"}},
    # A1 additions: minute qualification through the REAL provider
    # 605077: same thin-coverage reality — asset-level akshare key does not
    # extend to dates without akshare qfq rows.
    {"case": "alt_source_qualified", "asset": "CN:SH:605077",
     "date": "2026-10-22", "side": "buy",
     "expect": {"data_ready_minute": False,
                "reasons_contain": ["minute_date_unverified"]}},
    {"case": "alt_source_date_rows_verified_605077", "asset": "CN:SH:605077",
     "date": "2026-06-17", "side": "buy",
     "expect": {"data_ready_minute": True,
                "reasons_contain": ["factor_gap_covered_by_alt_source"]}},
    {"case": "no_done_key_blocked", "asset": "CN:SH:600590",
     "date": "2026-10-22", "side": "buy",
     "expect": {"data_ready_minute": False,
                "reasons_contain": ["factor_gap_residual"]}},
]


def run(conn, provider) -> list[dict]:
    out = []
    for c in CASES:
        ctx = load_tradeability_context(
            conn, c["asset"], c["date"], minute_provider=provider)
        if ctx is None:
            out.append({"case": c["case"], "pass": False,
                        "actual": {"error": "asset_not_in_master"},
                        "expected": c["expect"]})
            continue
        res = asdict(tradeability_at(ctx, side=c["side"],
                                     data_version="full_history_v1"))
        exp = c["expect"]
        checks = []
        for k, v in exp.items():
            if k == "reasons_contain":
                for r_ in v:
                    checks.append({
                        "field": f"restriction_reasons contains '{r_}'",
                        "expected": True,
                        "actual": r_ in res["restriction_reasons"],
                        "pass": r_ in res["restriction_reasons"]})
            elif k == "reasons_absent":
                for r_ in v:
                    ok = r_ not in res["restriction_reasons"]
                    checks.append({"field": f"restriction_reasons lacks '{r_}'",
                                   "expected": True, "actual": ok, "pass": ok})
            else:
                actual = res.get(k)
                checks.append({"field": k, "expected": v,
                               "actual": actual, "pass": actual == v})
        out.append({
            "case": c["case"], "asset": c["asset"], "date": c["date"],
            "side": c["side"],
            "rule_id": res.get("limit_rule_id"),
            "universe_state": res.get("universe_state"),
            "buy_state": res.get("buy_state"),
            "sell_state": res.get("sell_state"),
            "checks": checks,
            "pass": all(ch["pass"] for ch in checks),
            "actual_full": res,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    provider = LedgerMinuteQualificationProvider.from_repo()
    with connect("stock_research") as conn:
        rows = run(conn, provider)
    artifact = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "contract_version": "tradeability_pit_v2.1",
        "cases_total": len(rows),
        "cases_pass": sum(1 for r in rows if r["pass"]),
        "cases": [{k: v for k, v in r.items() if k != "actual_full"}
                  for r in rows],
    }
    (out_dir / "DB_EDGE_ASSERTIONS.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, default=str))
    failed = [r["case"] for r in rows if not r["pass"]]
    print(f"{artifact['cases_pass']}/{artifact['cases_total']} pass; "
          f"failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
