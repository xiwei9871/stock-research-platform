#!/usr/bin/env python3
"""P1d.2 regime-window decision-diff audit.

Aggregates the P1d.1 LIMIT_FLAG_RECONCILIATION.csv into the historical
windows required by the P1d.2 shadow matrix, de-duplicated by
(asset_id, trade_date, side). Windows without factor.stock_score_daily
coverage cannot run a real backtest — their impact is expressed as
execution-decision diffs (wrongly-blocked vs wrongly-released orders)
instead of equity deltas, and they stay NEEDS_REVALIDATION.
"""
import json
from pathlib import Path

import pandas as pd

RECON = Path("docs/research_upgrade/p1d1/LIMIT_FLAG_RECONCILIATION.csv")
OUT = Path("docs/research_upgrade/p1d2")

# (name, start, end, board_filter or None, score_coverage)
WINDOWS = [
    ("pre_1996_no_limit_era", "1990-01-01", "1996-12-13", None, False),
    ("chinext_prereform_10pct", "2010-01-01", "2020-08-23", "chinext", False),
    ("star_reform_era_2019_2020", "2019-07-22", "2020-12-31", "star", False),
    ("chinext_20pct_transition", "2020-08-24", "2021-12-31", "chinext", False),
    ("main_fullreg_2023", "2023-01-01", "2023-12-31", None, True),
    ("modern_2024_2026", "2024-01-01", "2026-12-31", None, True),
]


def main() -> int:
    df = pd.read_csv(RECON)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    dedup = df.drop_duplicates(["asset_id", "trade_date", "side"])
    rows = []
    for name, s, e, board, has_scores in WINDOWS:
        w = dedup[(dedup.trade_date >= s) & (dedup.trade_date <= e)]
        if board:
            w = w[w.board == board]
        # direction: old_flag True + corrected False = wrongly blocked/flagged (FP)
        #            old_flag False + corrected True = wrongly released (FN)
        fp = int(((w.old_flag == True) & (w.corrected_flag == False)).sum())
        fn = int(((w.old_flag == False) & (w.corrected_flag == True)).sum())
        c = w.classification.value_counts()
        rows.append({
            "window": name,
            "start": s, "end": e, "board": board or "all",
            "unique_decisions": len(w),
            "correct": int(c.get("CORRECT", 0)),
            "confirmed_mislabel": int(c.get("CONFIRMED_MISLABEL", 0)),
            "wrongly_flagged_FP": fp,
            "wrongly_passed_FN": fn,
            "rule_unknown": int(c.get("RULE_UNKNOWN", 0)),
            "score_coverage": "yes" if has_scores else "no_scores_needs_revalidation",
        })
    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "REGIME_WINDOW_DECISION_AUDIT.csv", index=False)
    print(out.to_string(index=False))
    print(f"\nwrote {OUT/'REGIME_WINDOW_DECISION_AUDIT.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
