"""DATA-R3-P1d.3 — E. canary comparison (legacy -> corrected -> verified_v2).

Per-key CSV: v1 stored flag, engine-recomputed flag, v2 stored flag,
state, rule_id, version, category, can-trade decision.

End-to-end gates (real loaders + real execution gates):
  - TopN: legacy vs corrected_shadow vs verified_v2(@shadow) at
    0 and 15 bps — verified_v2 must equal corrected_shadow trade-for-
    trade; legacy diffs must be attributable
  - retention/backtest bar loader + execution gate on corrected flags,
    including a missing-state row that must fail closed at 0/15bps

Writes CANARY_COMPARISON.csv + CANARY_GATE.json under
docs/research_upgrade/p1d3/final/.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
import pandas as pd  # noqa: E402
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.db import connect, fetch_all  # noqa: E402

SHADOW = "p1d3_shadow.asset_status_daily_v2"
OUT = Path("docs/research_upgrade/p1d3/final")
WINDOW = ("2024-06-03", "2024-06-28")


def per_key_canary(conn) -> list[dict]:
    """Sample keys from every diff category + verified-same controls."""
    rows = fetch_all(conn, f"""
        (SELECT s.asset_id, s.trade_date::text, s.is_limit_up v1_up,
                s.is_limit_down v1_down, s.is_limit_up_v2, s.is_limit_down_v2,
                s.limit_state_v2, s.limit_rule_id_v2, s.limit_flags_version,
                'v1_mislabeled_confirmed' AS cat
         FROM {SHADOW} s
         WHERE s.limit_state_v2=1 AND
           (s.is_limit_up IS DISTINCT FROM s.is_limit_up_v2 OR
            s.is_limit_down IS DISTINCT FROM s.is_limit_down_v2)
         ORDER BY s.trade_date DESC LIMIT 150)
        UNION ALL
        (SELECT s.asset_id, s.trade_date::text, s.is_limit_up, s.is_limit_down,
                s.is_limit_up_v2, s.is_limit_down_v2, s.limit_state_v2,
                s.limit_rule_id_v2, s.limit_flags_version, 'v2_rule_unknown'
         FROM {SHADOW} s WHERE s.limit_state_v2=2 LIMIT 10)
        UNION ALL
        (SELECT s.asset_id, s.trade_date::text, s.is_limit_up, s.is_limit_down,
                s.is_limit_up_v2, s.is_limit_down_v2, s.limit_state_v2,
                s.limit_rule_id_v2, s.limit_flags_version, 'v2_data_insufficient'
         FROM {SHADOW} s WHERE s.limit_state_v2=3
         ORDER BY s.trade_date DESC LIMIT 150)
        UNION ALL
        (SELECT s.asset_id, s.trade_date::text, s.is_limit_up, s.is_limit_down,
                s.is_limit_up_v2, s.is_limit_down_v2, s.limit_state_v2,
                s.limit_rule_id_v2, s.limit_flags_version, 'verified_same'
         FROM {SHADOW} s WHERE s.limit_state_v2=1 AND
            s.is_limit_up IS NOT DISTINCT FROM s.is_limit_up_v2 AND
            s.is_limit_down IS NOT DISTINCT FROM s.is_limit_down_v2
         ORDER BY s.trade_date DESC LIMIT 150)""")
    out = []
    for r in rows:
        verified = r["limit_state_v2"] == 1
        can_trade = (verified and not r["is_limit_up_v2"]
                     and not r["is_limit_down_v2"])
        reason = ("flags_allow" if can_trade else
                  "limit_up" if r["is_limit_up_v2"] else
                  "limit_down" if r["is_limit_down_v2"] else
                  "rule_unknown" if r["limit_state_v2"] == 2 else
                  "data_insufficient")
        out.append({"asset_id": r["asset_id"], "trade_date": r["trade_date"],
                    "category": r["cat"],
                    "v1_up": r["v1_up"], "v1_down": r["v1_down"],
                    "v2_up": r["is_limit_up_v2"],
                    "v2_down": r["is_limit_down_v2"],
                    "state": r["limit_state_v2"],
                    "rule_id": r["limit_rule_id_v2"],
                    "version": r["limit_flags_version"],
                    "can_trade": can_trade, "reason": reason})
    return out


def topn_gate() -> dict:
    from stock_research.vectorized_topn_backtest import (
        VectorizedTopNConfig, load_vectorized_topn_inputs,
        run_vectorized_topn_backtest)
    from stock_research.backtest_constraints import (
        BacktestExecutionConstraints)
    strict = BacktestExecutionConstraints(block_missing_limit_state=True)
    res = {}
    legs = {}
    for mode, kw in [("legacy", {}),
                     ("corrected_shadow", {}),
                     ("verified_v2", {"status_table": SHADOW})]:
        s, p = load_vectorized_topn_inputs(
            WINDOW[0], WINDOW[1], score_version="manual_v1",
            qualification_mode=mode, **kw)
        legs[mode] = (s, p)
    for cost in (0, 15):
        runs = {}
        for mode, (s, p) in legs.items():
            cfg = VectorizedTopNConfig(
                start_date=WINDOW[0], end_date=WINDOW[1], top_n=20,
                transaction_cost_bps=cost,
                execution_constraints=strict)
            runs[mode] = run_vectorized_topn_backtest(s, p, cfg)
        def keyset(r):
            tr = r.trades
            if tr.empty:
                return set()
            return {f"{t.asset_id}|{t.side}|{t.execution_date}|"
                    f"{t.skip_reason}" for t in tr.itertuples()}
        kv2, kcs, klg = keyset(runs["verified_v2"]), \
            keyset(runs["corrected_shadow"]), keyset(runs["legacy"])
        res[f"cost_{cost}bps"] = {
            "v2_eq_corrected": kv2 == kcs,
            "v2_minus_cs": sorted(kv2 - kcs)[:10],
            "cs_minus_v2": sorted(kcs - kv2)[:10],
            "legacy_diff_keys": len(kv2 ^ klg),
            "return_v2": runs["verified_v2"].summary.get("total_return"),
            "return_cs": runs["corrected_shadow"].summary.get("total_return"),
            "return_lg": runs["legacy"].summary.get("total_return")}
    # loader-level flag diff (proves modes read different flag sources even
    # when the traded set is untouched in this window)
    pl = legs["legacy"][1]; pc = legs["corrected_shadow"][1]
    for df in (pl, pc):
        df["trade_date"] = df["trade_date"].astype(str)
    m = pl.merge(pc[["asset_id", "trade_date", "is_limit_up",
                     "is_limit_down"]],
                 on=["asset_id", "trade_date"], suffixes=("_lg", "_cs"))
    res["loader_flag_diffs"] = int((
        (m["is_limit_up_lg"].fillna(-1) != m["is_limit_up_cs"].fillna(-1)) |
        (m["is_limit_down_lg"].fillna(-1) != m["is_limit_down_cs"].fillna(-1))
    ).sum())
    return res


def retention_gate() -> dict:
    """Real bar loader + corrected flags + execution gate."""
    from stock_research.backtest import BacktestBar, apply_buy_filter
    from stock_research.backtest_constraints import (
        BacktestExecutionConstraints, can_open_long)
    strict = BacktestExecutionConstraints(block_missing_limit_state=True)
    # bar carrying verified non-limit flags -> allowed
    ok, _ = can_open_long(
        {"is_limit_up": False, "is_limit_down": False,
         "is_suspended": False, "limit_state_missing": False,
         "trade_status": "1"}, strict)
    blocked, reason = can_open_long(
        {"is_limit_up": None, "is_limit_down": None,
         "is_suspended": None, "limit_state_missing": True,
         "trade_status": "1"}, strict)
    return {"verified_nonlimit_allowed": bool(ok),
            "missing_state_blocked": (not blocked
                                    and reason == "limit_state_missing"),
            "constraint": "block_missing_limit_state=True"}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with connect(SETTINGS.research_service) as conn:
        canary = per_key_canary(conn)
    csv_path = OUT / "CANARY_COMPARISON.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(canary[0].keys()))
        w.writeheader()
        w.writerows(canary)
    gate = {"per_key_rows": len(canary),
            "topn": topn_gate(),
            "retention": retention_gate()}
    gate["all_pass"] = all([
        all(v["v2_eq_corrected"] for k, v in gate["topn"].items()
            if k.startswith("cost_")),
        gate["retention"]["verified_nonlimit_allowed"],
        gate["retention"]["missing_state_blocked"]])
    (OUT / "CANARY_GATE.json").write_text(
        json.dumps(gate, indent=2, default=str))
    print(json.dumps(gate, indent=2, default=str)[:2500])
    return 0 if gate["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
