"""R2 rollback v3 — surgically restores what a repair batch modified.

Safety rules:
- daily bars: restore every backup row via upsert; DELETE only rows whose
  key is absent from the backup AND whose source is the revision tag —
  i.e. rows this batch actually inserted. Rows written later by other
  pipelines (different source) are never touched, even on the same asset.
- adjustment_factor: upsert backup rows; delete only rows for batch
  assets with updated_at > batch meta created_at (created during repair)
  whose key is absent from backup.
- corporate_action: restore backup rows; delete only derived events for
  batch assets created after meta time whose key is absent from backup.
  Other sources' events are never touched.
- everything runs in ONE transaction; row-level verification prints
  remaining diffs before commit.

Usage: r2_rollback_batch.py <batch_id>
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")
from stock_research.db import connect, fetch_all  # noqa: E402

COLUMNS = ("asset_id, trade_date, open, high, low, close, preclose, volume, "
           "amount, turnover_rate, pct_chg, trade_status, is_st, adjust_type, "
           "source, updated_at")
REVISION_SOURCE = "baostock_revision_r2"
DERIVED_ACTION_VERSION = "derived_adjustment_factor_v1"


def main() -> None:
    batch_id = sys.argv[1]
    b = f"backup.market_daily_bar_r2_{batch_id}"
    fb = f"backup.adjustment_factor_r2_{batch_id}"
    ab = f"backup.corporate_action_r2_{batch_id}"
    with connect("stock_research") as conn:
        assets = [r["asset_id"] for r in fetch_all(
            conn, f"SELECT DISTINCT asset_id FROM {b}")]
        meta = fetch_all(
            conn, "SELECT created_at FROM backup.r2_batch_meta WHERE batch_id=%s",
            [batch_id])
        meta_ts = meta[0]["created_at"] if meta else None
        print(f"rolling back {len(assets)} assets from {b} meta_ts={meta_ts}")
        with conn.cursor() as cur:
            # 1) restore backup rows (only rows the batch modified have
            #    backup pre-images; others are skipped by NOT EXISTS below)
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
                        updated_at=EXCLUDED.updated_at""")
            print("daily rows restored:", cur.rowcount)
            # 2) delete ONLY rows this batch inserted (revision source AND
            #    key absent from backup) — other pipelines' later rows kept
            cur.execute(
                f"""DELETE FROM market_daily_bar s
                    WHERE s.asset_id = ANY(%s) AND s.adjust_type IN ('qfq','hfq')
                      AND s.source = %s
                      AND NOT EXISTS (
                          SELECT 1 FROM {b} bk WHERE bk.asset_id=s.asset_id
                            AND bk.trade_date=s.trade_date
                            AND bk.adjust_type=s.adjust_type)""",
                [assets, REVISION_SOURCE])
            print("batch-inserted rows deleted:", cur.rowcount)
            # 3) factor: restore backup, drop repair-created extras
            cur.execute(
                f"""INSERT INTO market.adjustment_factor
                    SELECT * FROM {fb}
                    ON CONFLICT (asset_id, trade_date, source_version) DO UPDATE SET
                        raw_close=EXCLUDED.raw_close, qfq_close=EXCLUDED.qfq_close,
                        hfq_close=EXCLUDED.hfq_close, qfq_factor=EXCLUDED.qfq_factor,
                        hfq_factor=EXCLUDED.hfq_factor, source=EXCLUDED.source,
                        updated_at=EXCLUDED.updated_at""")
            print("factor rows restored:", cur.rowcount)
            if meta_ts is None:
                print("!! no batch meta — skipping factor/action extras deletion "
                      "(conservative: extra rows retained, review manually)")
            else:
                cur.execute(
                    f"""DELETE FROM market.adjustment_factor s
                        WHERE s.asset_id = ANY(%s)
                          AND s.updated_at > %s
                          AND NOT EXISTS (
                              SELECT 1 FROM {fb} bk WHERE bk.asset_id=s.asset_id
                                AND bk.trade_date=s.trade_date
                                AND bk.source_version=s.source_version)""",
                    [assets, meta_ts])
                print("factor extras deleted:", cur.rowcount)
            # 4) corporate_action: restore backup, drop repair-created extras
            cur.execute(
                f"INSERT INTO market.corporate_action SELECT * FROM {ab} "
                "ON CONFLICT (asset_id, event_date, action_type, source_version) "
                "DO UPDATE SET factor_before=EXCLUDED.factor_before, "
                "factor_after=EXCLUDED.factor_after, source=EXCLUDED.source, "
                "updated_at=EXCLUDED.updated_at")
            print("actions restored:", cur.rowcount)
            if meta_ts is not None:
                cur.execute(
                    f"""DELETE FROM market.corporate_action s
                        WHERE s.asset_id = ANY(%s) AND s.source_version=%s
                          AND s.updated_at > %s
                          AND NOT EXISTS (
                              SELECT 1 FROM {ab} bk WHERE bk.asset_id=s.asset_id
                                AND bk.event_date=s.event_date
                                AND bk.action_type=s.action_type
                                AND bk.source_version=s.source_version)""",
                    [assets, DERIVED_ACTION_VERSION, meta_ts])
                print("action extras deleted:", cur.rowcount)
            # 5) row-level verification: stored qfq/hfq rows for batch
            #    assets must equal backup on every restored key
            cur.execute(
                f"""SELECT count(*) c FROM market_daily_bar s
                    JOIN {b} bk ON bk.asset_id=s.asset_id
                      AND bk.trade_date=s.trade_date AND bk.adjust_type=s.adjust_type
                    WHERE s.asset_id=ANY(%s) AND (
                        s.open IS DISTINCT FROM bk.open OR
                        s.high IS DISTINCT FROM bk.high OR
                        s.low IS DISTINCT FROM bk.low OR
                        s.close IS DISTINCT FROM bk.close OR
                        s.preclose IS DISTINCT FROM bk.preclose OR
                        s.volume IS DISTINCT FROM bk.volume OR
                        s.amount IS DISTINCT FROM bk.amount)""",
                [assets])
            print("post-rollback daily diffs:", cur.fetchone()["c"])
        conn.commit()
        print("rollback committed")


if __name__ == "__main__":
    main()
