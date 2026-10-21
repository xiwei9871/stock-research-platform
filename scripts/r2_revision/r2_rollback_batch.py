"""R2 rollback: restore market_daily_bar / adjustment_factor /
corporate_action rows for a batch from its backup table.

Usage: r2_rollback_batch.py <batch_id>
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402

COLUMNS = ("asset_id, trade_date, open, high, low, close, preclose, volume, "
           "amount, turnover_rate, pct_chg, trade_status, is_st, adjust_type, "
           "source, updated_at")


def main() -> None:
    batch_id = sys.argv[1]
    b = f"backup.market_daily_bar_r2_{batch_id}"
    fb = f"backup.adjustment_factor_r2_{batch_id}"
    ab = f"backup.corporate_action_r2_{batch_id}"
    with connect("stock_research") as conn:
        assets = [r["asset_id"] for r in fetch_all(
            conn, f"SELECT DISTINCT asset_id FROM {b}")]
        print(f"rolling back {len(assets)} assets from {b}")
        with conn.cursor() as cur:
            cur.execute(
                f"""INSERT INTO market_daily_bar ({COLUMNS})
                    SELECT {COLUMNS} FROM {b}
                    ON CONFLICT (asset_id, trade_date, adjust_type) DO UPDATE SET
                        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                        close=EXCLUDED.close, preclose=EXCLUDED.preclose,
                        volume=EXCLUDED.volume, amount=EXCLUDED.amount,
                        turnover_rate=EXCLUDED.turnover_rate,
                        pct_chg=EXCLUDED.pct_chg, trade_status=EXCLUDED.trade_status,
                        is_st=EXCLUDED.is_st, source=EXCLUDED.source,
                        updated_at=EXCLUDED.updated_at""",
            )
            print("daily rows restored:", cur.rowcount)
            cur.execute(
                "DELETE FROM market_daily_bar "
                "WHERE asset_id = ANY(%s) AND adjust_type IN ('qfq','hfq') "
                "AND (asset_id, trade_date, adjust_type) NOT IN "
                f"(SELECT asset_id, trade_date, adjust_type FROM {b})",
                [assets],
            )
            print("extra rows deleted:", cur.rowcount)
            cur.execute(
                f"""INSERT INTO market.adjustment_factor
                    SELECT * FROM {fb}
                    ON CONFLICT (asset_id, trade_date, source_version) DO UPDATE SET
                        raw_close=EXCLUDED.raw_close, qfq_close=EXCLUDED.qfq_close,
                        hfq_close=EXCLUDED.hfq_close, qfq_factor=EXCLUDED.qfq_factor,
                        hfq_factor=EXCLUDED.hfq_factor, source=EXCLUDED.source,
                        updated_at=EXCLUDED.updated_at""",
            )
            print("factor rows restored:", cur.rowcount)
            cur.execute(
                "DELETE FROM market.corporate_action WHERE asset_id = ANY(%s)",
                [assets],
            )
            cur.execute(
                f"INSERT INTO market.corporate_action SELECT * FROM {ab}",
            )
            print("corporate actions restored:", cur.rowcount)
        conn.commit()
        print("rollback committed")


if __name__ == "__main__":
    main()
