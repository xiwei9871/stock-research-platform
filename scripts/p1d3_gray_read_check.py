"""DATA-R3-P1d.3 — gray read-path validation for verified_v2.

Point load_vectorized_topn_inputs(qualification_mode='verified_v2') at the
rehearsal shadow table and prove it agrees with corrected_shadow on every
verified key, and that every non-verified state stays fail-closed.

Writes docs/research_upgrade/p1d3/GRAY_READ_VALIDATION.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
import pandas as pd  # noqa: E402
from stock_research.vectorized_topn_backtest import (  # noqa: E402
    load_vectorized_topn_inputs)

SHADOW = "p1d3_shadow.asset_status_daily_v2"
WINDOWS = [
    ("2024-06-03", "2024-06-07"),   # populated early (smoke batch)
    ("2019-08-01", "2019-08-09"),   # STAR reform era
    ("2023-04-10", "2023-04-14"),   # main-board registration era
    ("1996-12-02", "1996-12-06"),   # pre-limit rule era
]


def compare(start, end):
    try:
        _, pv2 = load_vectorized_topn_inputs(
            start, end, score_version="manual_v1",
            qualification_mode="verified_v2", status_table=SHADOW)
        _, pcs = load_vectorized_topn_inputs(
            start, end, score_version="manual_v1",
            qualification_mode="corrected_shadow")
    except Exception as exc:  # noqa: BLE001
        return {"window": [start, end], "error": str(exc)}
    if pv2.empty or pcs.empty:
        return {"window": [start, end], "rows_v2": len(pv2),
                "rows_cs": len(pcs), "note": "empty price set"}
    for df in (pv2, pcs):
        df["trade_date"] = df["trade_date"].astype(str)
    m = pv2.merge(
        pcs[["asset_id", "trade_date", "is_limit_up", "is_limit_down",
             "qualification_state", "limit_rule_id"]],
        on=["asset_id", "trade_date"], suffixes=("_v2", "_cs"))
    ok = m[~m["limit_state_missing"]]
    mismatched = ok[(ok["is_limit_up_v2"] != ok["is_limit_up_cs"]) |
                    (ok["is_limit_down_v2"] != ok["is_limit_down_cs"])]
    missing_rows = m[m["limit_state_missing"]]
    blocked_states = missing_rows["qualification_state"].value_counts()\
        .to_dict() if len(missing_rows) else {}
    leaked = missing_rows[missing_rows["qualification_state"]
                          == "verified"]
    return {
        "window": [start, end],
        "rows": len(m),
        "verified_rows": len(ok),
        "missing_rows": len(missing_rows),
        "flag_mismatches_on_verified": len(mismatched),
        "missing_state_breakdown": blocked_states,
        "verified_rows_marked_missing": int(len(leaked)),
        "rule_id_coverage_v2": float(m["limit_rule_id_v2"].notna().mean()),
        "pass": len(mismatched) == 0 and len(leaked) == 0 and len(ok) > 0,
    }


def main() -> int:
    out = [compare(s, e) for s, e in WINDOWS]
    res = {"shadow_table": SHADOW, "checks": out,
           "all_pass": all(r.get("pass") for r in out if "pass" in r)}
    p = Path("docs/research_upgrade/p1d3/GRAY_READ_VALIDATION.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(res, indent=2, default=str))
    print(json.dumps(res, indent=2, default=str)[:3000])
    return 0 if res["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
