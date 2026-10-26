"""DATA-R3-P1d.3 preflight — full-table v1/v2 diff classification.

Reads ONLY the completed shadow table (no recompute). Classifies every
row where v1 != v2 into:

  v1_mislabeled_confirmed : v1 flag set AND v2 state=verified disagrees
  v1_null_v2_verified     : v1 flag NULL, v2 verified -> confirmed value
  v2_rule_unknown         : v2 state=2 (unverified rule; not a mislabel
                            verdict — rule coverage gap)
  v2_data_insufficient    : v2 state=3 (bar data missing)
  other_state_change      : residual

Outputs docs/research_upgrade/p1d3/final/FULL_DIFF_CLASSIFICATION.csv
(per year x board x direction x category) + summary JSON + sample rows.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, "src")
from stock_research.config import SETTINGS  # noqa: E402
from stock_research.db import connect, fetch_all  # noqa: E402

T = "p1d3_shadow.asset_status_daily_v2"
OUT = Path("docs/research_upgrade/p1d3/final")

CASE = """
CASE
  WHEN s.limit_state_v2 = 2 THEN 'v2_rule_unknown'
  WHEN s.limit_state_v2 = 3 THEN 'v2_data_insufficient'
  WHEN s.limit_state_v2 = 1 AND
       ((s.is_limit_up IS NOT NULL AND s.is_limit_up IS DISTINCT FROM
            s.is_limit_up_v2) OR
        (s.is_limit_down IS NOT NULL AND s.is_limit_down IS DISTINCT FROM
            s.is_limit_down_v2)) THEN 'v1_mislabeled_confirmed'
  WHEN s.limit_state_v2 = 1 AND
       ((s.is_limit_up IS NULL OR s.is_limit_down IS NULL)) THEN
          'v1_null_v2_verified'
  ELSE 'other_state_change'
END
"""

DIFF_WHERE = """
    (s.is_limit_up IS DISTINCT FROM s.is_limit_up_v2
     OR s.is_limit_down IS DISTINCT FROM s.is_limit_down_v2)
"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with connect(SETTINGS.research_service) as conn:
        totals = fetch_all(conn, f"""
            SELECT {CASE} AS category, count(*) AS n,
                   count(*) FILTER (WHERE s.is_limit_up IS DISTINCT FROM
                        s.is_limit_up_v2) AS up_diff,
                   count(*) FILTER (WHERE s.is_limit_down IS DISTINCT FROM
                        s.is_limit_down_v2) AS down_diff
            FROM {T} s WHERE {DIFF_WHERE}
            GROUP BY 1 ORDER BY 2 DESC""")
        by_year = fetch_all(conn, f"""
            SELECT EXTRACT(YEAR FROM s.trade_date)::int AS y,
                   {CASE} AS category, count(*) AS n
            FROM {T} s WHERE {DIFF_WHERE}
            GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
        by_board = fetch_all(conn, f"""
            SELECT coalesce(a.board,
                     CASE WHEN a.is_star THEN 'star'
                          WHEN a.is_chinext THEN 'chinext'
                          WHEN a.is_beijing THEN 'beijing'
                          ELSE 'main' END) AS board,
                   {CASE} AS category, count(*) AS n
            FROM {T} s
            LEFT JOIN core.asset_master a ON a.asset_id = s.asset_id
            WHERE {DIFF_WHERE}
            GROUP BY 1, 2 ORDER BY 3 DESC""")
        samples = fetch_all(conn, f"""
            SELECT s.asset_id, s.trade_date::text AS trade_date,
                   s.is_limit_up AS v1_up, s.is_limit_down AS v1_down,
                   s.is_limit_up_v2, s.is_limit_down_v2,
                   s.limit_state_v2, s.limit_rule_id_v2,
                   {CASE} AS category
            FROM {T} s WHERE {DIFF_WHERE}
            ORDER BY s.trade_date, s.asset_id
            LIMIT 400""")
    rows = []
    for r in by_year:
        rows.append({"dim": "year", "key": r["y"],
                     "category": r["category"], "n": int(r["n"])})
    for r in by_board:
        rows.append({"dim": "board", "key": r["board"],
                     "category": r["category"], "n": int(r["n"])})
    for r in totals:
        rows.append({"dim": "total", "key": "all",
                     "category": r["category"], "n": int(r["n"]),
                     "up_diff": int(r["up_diff"]),
                     "down_diff": int(r["down_diff"])})
    csv_path = OUT / "FULL_DIFF_CLASSIFICATION.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["dim", "key", "category", "n",
                                           "up_diff", "down_diff"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    samp_path = OUT / "FULL_DIFF_SAMPLES.csv"
    with samp_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(samples[0].keys()))
        w.writeheader()
        w.writerows(samples)
    summary = {"total_diff": sum(int(t["n"]) for t in totals),
               "categories": {t["category"]: int(t["n"]) for t in totals},
               "csv": str(csv_path), "samples": str(samp_path)}
    (OUT / "FULL_DIFF_CLASSIFICATION.json").write_text(
        json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
