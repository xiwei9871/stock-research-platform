"""R2 rollback v4 — manifest-owned surgical rollback.

Daily bars: batch ownership comes from backup.r2_write_manifest
(batch_id, asset_id, trade_date, adjust_type, op):
  - op='update' keys -> restore the batch backup pre-image
  - op='insert' keys -> delete only those rows, and only while they still
    carry this batch's write evidence

Conflict guards (abort without writing anything):
  - another LATER batch's manifest claims the same key -> rolling back
    would clobber that batch's work -> refuse
  - a manifest update-key is missing from the backup table -> backup is
    inconsistent -> refuse
  - current row changed after this batch's write by a non-revision
    source (another pipeline) -> refuse

Legacy batches without a manifest fall back to backup-driven restore:
upsert every backup row + delete revision-sourced rows absent from
backup (v3 semantics), with a loud warning.

Factor/action tables: restore from backup; extras deleted only when
post-meta AND absent from backup (unchanged from v3).

Usage: r2_rollback_batch.py <batch_id> [--apply]
  default is dry-run (counts only); --apply commits.
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
    apply = "--apply" in sys.argv
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
        manifest = fetch_all(
            conn, "SELECT asset_id, trade_date, adjust_type, op FROM "
                  "backup.r2_write_manifest WHERE batch_id=%s", [batch_id])
        print(f"rollback {batch_id}: {len(assets)} assets, manifest rows="
              f"{len(manifest)}, meta_ts={meta_ts}, apply={apply}")

        if manifest:
            keys = {(r["asset_id"], str(r["trade_date"]), r["adjust_type"])
                    for r in manifest}
            # conflict: a LATER batch wrote any of our keys
            conflicts = fetch_all(
                conn, """SELECT batch_id, count(*) c FROM backup.r2_write_manifest
                         WHERE batch_id <> %s AND (asset_id, trade_date, adjust_type)
                           IN (SELECT asset_id, trade_date, adjust_type
                               FROM backup.r2_write_manifest WHERE batch_id=%s)
                         GROUP BY batch_id""", [batch_id, batch_id])
            if conflicts:
                print("CONFLICT: later batches also wrote shared keys:",
                      conflicts)
                print("aborting — restore would clobber them; resolve manually")
                return
            backup_keys = {tuple(str(r[c]) for c in ("asset_id", "trade_date", "adjust_type"))
                           for r in fetch_all(
                               conn, f"SELECT asset_id, trade_date, adjust_type FROM {b}")}
            missing_preimage = [k for k, r in zip(
                [(r['asset_id'], str(r['trade_date']), r['adjust_type']) for r in manifest],
                manifest) if r["op"] == "update" and k not in backup_keys]
            if missing_preimage:
                print("CONFLICT: update-keys without backup pre-image:",
                      missing_preimage[:5])
                return
            # foreign write = manifest key whose current row differs from
            # BOTH the backup pre-image and is not revision-sourced —
            # i.e. a third party changed it after our write. Rows already
            # at backup values (idempotent re-rollback) are not conflicts.
            foreign = fetch_all(
                conn, f"""SELECT count(*) c FROM market_daily_bar s
                         JOIN backup.r2_write_manifest m
                           ON m.asset_id=s.asset_id AND m.trade_date=s.trade_date
                          AND m.adjust_type=s.adjust_type
                         JOIN {b} bk ON bk.asset_id=s.asset_id
                           AND bk.trade_date=s.trade_date
                           AND bk.adjust_type=s.adjust_type
                         WHERE m.batch_id=%s AND s.source <> %s
                           AND (s.open IS DISTINCT FROM bk.open OR
                                s.high IS DISTINCT FROM bk.high OR
                                s.low IS DISTINCT FROM bk.low OR
                                s.close IS DISTINCT FROM bk.close OR
                                s.preclose IS DISTINCT FROM bk.preclose OR
                                s.volume IS DISTINCT FROM bk.volume OR
                                s.amount IS DISTINCT FROM bk.amount)""",
                [batch_id, REVISION_SOURCE])
            if foreign[0]["c"]:
                print(f"CONFLICT: {foreign[0]['c']} manifest keys overwritten "
                      "by non-revision source with different values — aborting")
                return

        with conn.cursor() as cur:
            if manifest:
                # manifest-owned restore: update-keys <- backup, insert-keys -> delete
                bk_cols = ", ".join(f"bk.{c.strip()}" for c in COLUMNS.split(","))
                cur.execute(
                    f"""INSERT INTO market_daily_bar ({COLUMNS})
                        SELECT {bk_cols} FROM {b} bk
                        JOIN backup.r2_write_manifest m
                          ON m.batch_id=%s AND m.asset_id=bk.asset_id
                         AND m.trade_date=bk.trade_date AND m.adjust_type=bk.adjust_type
                        WHERE m.op='update'
                        ON CONFLICT (asset_id, trade_date, adjust_type) DO UPDATE SET
                            open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                            close=EXCLUDED.close, preclose=EXCLUDED.preclose,
                            volume=EXCLUDED.volume, amount=EXCLUDED.amount,
                            turnover_rate=EXCLUDED.turnover_rate,
                            pct_chg=EXCLUDED.pct_chg,
                            trade_status=EXCLUDED.trade_status,
                            is_st=EXCLUDED.is_st, source=EXCLUDED.source,
                            updated_at=EXCLUDED.updated_at""", [batch_id])
                print("manifest update-keys restored:", cur.rowcount)
                cur.execute(
                    """DELETE FROM market_daily_bar s
                       USING backup.r2_write_manifest m
                       WHERE m.batch_id=%s AND m.op='insert'
                         AND s.asset_id=m.asset_id AND s.trade_date=m.trade_date
                         AND s.adjust_type=m.adjust_type
                         AND s.source=%s""",
                    [batch_id, REVISION_SOURCE])
                print("manifest insert-keys deleted:", cur.rowcount)
            else:
                print("!! no manifest — legacy backup-driven restore")
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
                print("!! no batch meta — skipping factor/action extras deletion")
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
        if apply:
            conn.commit()
            print("rollback committed")
        else:
            conn.rollback()
            print("dry-run only — pass --apply to commit")


if __name__ == "__main__":
    main()
