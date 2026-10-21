"""R2 rollback v5 — manifest-owned surgical rollback, aborts on violation.

Ownership comes from three manifest tables written in the SAME
transaction as the data writes:
  backup.r2_write_manifest        (batch_id, asset_id, trade_date, adjust_type, op)
  backup.r2_write_manifest_factor (batch_id, asset_id, trade_date, source_version, op)
  backup.r2_write_manifest_action (batch_id, asset_id, event_date, action_type, source_version, op)

op semantics: 'update' -> key existed pre-batch, restore backup pre-image;
'insert' -> key created by batch, delete it; 'delete' -> key removed by
batch, restore backup pre-image.

HARD ABORTS (rollback transaction, exit 1, nothing committed):
  - a LATER batch's manifest claims any of our keys
  - an update/delete key lacks a backup pre-image (backup inconsistent)
  - a manifest key's current row was changed by a non-revision source
    with values differing from the backup pre-image (foreign write)
  - post-rollback daily diffs > 0
  - batch has NO manifest at all and --apply requested: legacy batches
    must not auto-rollback; an audit plan is printed instead.
    (dry-run still reports what the legacy path would do.)

Usage: r2_rollback_batch.py <batch_id> [--apply]
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
BAR_DIFF_COLS = ("open", "high", "low", "close", "preclose", "volume", "amount")


def fail(msg: str) -> None:
    print(f"!! {msg}")
    sys.exit(1)


def key_conflicts(conn, batch_id, table, key_cols) -> list:
    cols = ", ".join(key_cols)
    return fetch_all(conn, f"""
        SELECT m2.batch_id, count(*) c FROM backup.{table} m
        JOIN backup.{table} m2 ON m2.batch_id <> %s
          AND m2.asset_id = m.asset_id
          {' '.join(f'AND m2.{c} = m.{c}' for c in key_cols[1:])}
        WHERE m.batch_id = %s GROUP BY m2.batch_id""",
        [batch_id, batch_id])


def main() -> None:
    batch_id = sys.argv[1]
    apply = "--apply" in sys.argv
    b = f"backup.market_daily_bar_r2_{batch_id}"
    fb = f"backup.adjustment_factor_r2_{batch_id}"
    ab = f"backup.corporate_action_r2_{batch_id}"
    mb, mf, ma = ("backup.r2_write_manifest", "backup.r2_write_manifest_factor",
                  "backup.r2_write_manifest_action")
    with connect("stock_research") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """CREATE TABLE IF NOT EXISTS backup.r2_write_manifest (
                    batch_id text, asset_id text, trade_date date,
                    adjust_type text, op text,
                    written_at timestamptz DEFAULT now(),
                    PRIMARY KEY (batch_id, asset_id, trade_date, adjust_type))""")
            cur.execute(
                """CREATE TABLE IF NOT EXISTS backup.r2_write_manifest_factor (
                    batch_id text, asset_id text, trade_date date,
                    source_version text, op text,
                    written_at timestamptz DEFAULT now(),
                    PRIMARY KEY (batch_id, asset_id, trade_date, source_version))""")
            cur.execute(
                """CREATE TABLE IF NOT EXISTS backup.r2_write_manifest_action (
                    batch_id text, asset_id text, event_date date,
                    action_type text, source_version text, op text,
                    written_at timestamptz DEFAULT now(),
                    PRIMARY KEY (batch_id, asset_id, event_date,
                                 action_type, source_version))""")
        conn.commit()
        assets = [r["asset_id"] for r in fetch_all(
            conn, f"SELECT DISTINCT asset_id FROM {b}")]
        meta = fetch_all(
            conn, "SELECT created_at FROM backup.r2_batch_meta WHERE batch_id=%s",
            [batch_id])
        meta_ts = meta[0]["created_at"] if meta else None
        bars = fetch_all(conn, f"SELECT * FROM {mb} WHERE batch_id=%s", [batch_id])
        factors = fetch_all(conn, f"SELECT * FROM {mf} WHERE batch_id=%s", [batch_id])
        actions = fetch_all(conn, f"SELECT * FROM {ma} WHERE batch_id=%s", [batch_id])
        print(f"rollback {batch_id}: assets={len(assets)} "
              f"manifest bars={len(bars)} factors={len(factors)} "
              f"actions={len(actions)} apply={apply}")

        if not bars and apply:
            print("AUDIT PLAN (no manifest — refusing auto-apply):")
            print(f"  backup {b}: {len(assets)} assets would be restored "
                  "by legacy wide-scope rules")
            print("  -> generate per-asset review before any writes; "
                  "refusing to auto-apply on a no-manifest batch")
            sys.exit(1)

        # ---- conflict guards (manifest era) ----
        if bars:
            for later in key_conflicts(conn, batch_id, "r2_write_manifest",
                                       ("asset_id", "trade_date", "adjust_type")):
                fail(f"CONFLICT: batch {later['batch_id']} also wrote "
                     f"{later['c']} shared daily-bar keys — resolve first")
            backup_keys = {tuple(str(r[c]) for c in ("asset_id", "trade_date", "adjust_type"))
                           for r in fetch_all(
                               conn, f"SELECT asset_id, trade_date, adjust_type FROM {b}")}
            missing_pre = [r for r in bars if r["op"] in ("update", "delete")
                           and (r["asset_id"], str(r["trade_date"]),
                                r["adjust_type"]) not in backup_keys]
            if missing_pre:
                fail(f"CONFLICT: {len(missing_pre)} manifest keys lack backup "
                     f"pre-image e.g. {missing_pre[:3]}")
            foreign = fetch_all(
                conn, f"""SELECT count(*) c FROM market_daily_bar s
                    JOIN {mb} m
                      ON m.asset_id=s.asset_id AND m.trade_date=s.trade_date
                     AND m.adjust_type=s.adjust_type
                    JOIN {b} bk ON bk.asset_id=s.asset_id
                      AND bk.trade_date=s.trade_date AND bk.adjust_type=s.adjust_type
                    WHERE m.batch_id=%s AND m.op='update' AND s.source <> %s
                      AND ({' OR '.join(f's.{c} IS DISTINCT FROM bk.{c}' for c in BAR_DIFF_COLS)})""",
                [batch_id, REVISION_SOURCE])
            if foreign[0]["c"]:
                fail(f"CONFLICT: {foreign[0]['c']} manifest keys overwritten by "
                     "foreign (non-revision) source with different values")

        # factor/action: same ownership proofs — shared keys across batches
        # and pre-image existence for update/delete ops
        for later in key_conflicts(conn, batch_id, "r2_write_manifest_factor",
                                   ("asset_id", "trade_date", "source_version")):
            fail(f"CONFLICT: batch {later['batch_id']} also wrote "
                 f"{later['c']} shared factor keys — resolve first")
        for later in key_conflicts(conn, batch_id, "r2_write_manifest_action",
                                   ("asset_id", "event_date", "action_type",
                                    "source_version")):
            fail(f"CONFLICT: batch {later['batch_id']} also wrote "
                 f"{later['c']} shared action keys — resolve first")
        if factors:
            factor_bk = {tuple(str(r[c]) for c in
                               ("asset_id", "trade_date", "source_version"))
                         for r in fetch_all(
                             conn, f"SELECT asset_id, trade_date, source_version FROM {fb}")}
            missing = [r for r in factors if r["op"] in ("update", "delete")
                       and (r["asset_id"], str(r["trade_date"]),
                            r["source_version"]) not in factor_bk]
            if missing:
                fail(f"CONFLICT: {len(missing)} factor manifest keys lack "
                     f"backup pre-image e.g. {missing[:3]}")
        if actions:
            action_bk = {tuple(str(r[c]) for c in
                               ("asset_id", "event_date", "action_type",
                                "source_version"))
                         for r in fetch_all(
                             conn, f"SELECT asset_id, event_date, action_type,"
                                   f" source_version FROM {ab}")}
            missing = [r for r in actions if r["op"] in ("update", "delete")
                       and (r["asset_id"], str(r["event_date"]),
                            r["action_type"], r["source_version"]) not in action_bk]
            if missing:
                fail(f"CONFLICT: {len(missing)} action manifest keys lack "
                     f"backup pre-image e.g. {missing[:3]}")

        with conn.cursor() as cur:
            # ---- daily bars ----
            if bars:
                bk_cols = ", ".join(f"bk.{c.strip()}" for c in COLUMNS.split(","))
                cur.execute(
                    f"""INSERT INTO market_daily_bar ({COLUMNS})
                        SELECT {bk_cols} FROM {b} bk
                        JOIN {mb} m ON m.batch_id=%s AND m.asset_id=bk.asset_id
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
                print("bar update-keys restored:", cur.rowcount)
                cur.execute(
                    f"""DELETE FROM market_daily_bar s USING {mb} m
                        WHERE m.batch_id=%s AND m.op='insert'
                          AND s.asset_id=m.asset_id AND s.trade_date=m.trade_date
                          AND s.adjust_type=m.adjust_type AND s.source=%s""",
                    [batch_id, REVISION_SOURCE])
                print("bar insert-keys deleted:", cur.rowcount)
            else:
                print("(legacy path, dry-run counts only)")
                cur.execute(
                    f"""SELECT count(*) c FROM {b}""")
                print(f"  would restore {cur.fetchone()['c']} backup rows")

            # ---- factors (manifest or meta-window legacy) ----
            if factors:
                fb_cols = ", ".join(f"bk.{c}" for c in
                    ("asset_id","trade_date","raw_close","qfq_close","hfq_close",
                     "qfq_factor","hfq_factor","source","source_version","updated_at"))
                cur.execute(
                    f"""INSERT INTO market.adjustment_factor
                        SELECT {fb_cols} FROM {fb} bk
                        JOIN {mf} m ON m.batch_id=%s AND m.asset_id=bk.asset_id
                          AND m.trade_date=bk.trade_date
                          AND m.source_version=bk.source_version
                        WHERE m.op IN ('update','delete')
                        ON CONFLICT (asset_id, trade_date, source_version) DO UPDATE SET
                            raw_close=EXCLUDED.raw_close, qfq_close=EXCLUDED.qfq_close,
                            hfq_close=EXCLUDED.hfq_close, qfq_factor=EXCLUDED.qfq_factor,
                            hfq_factor=EXCLUDED.hfq_factor, source=EXCLUDED.source,
                            updated_at=EXCLUDED.updated_at""", [batch_id])
                print("factor update/delete-keys restored:", cur.rowcount)
                cur.execute(
                    f"""DELETE FROM market.adjustment_factor s USING {mf} m
                        WHERE m.batch_id=%s AND m.op='insert'
                          AND s.asset_id=m.asset_id AND s.trade_date=m.trade_date
                          AND s.source_version=m.source_version""",
                    [batch_id])
                print("factor insert-keys deleted:", cur.rowcount)
            elif meta_ts is not None and not bars:
                pass  # legacy dry-run: no writes
            elif not bars:
                print("!! no factor manifest and no meta — skipped")

            # ---- corporate actions ----
            if actions:
                ab_cols = ", ".join(f"bk.{c}" for c in
                    ("asset_id","event_date","action_type","factor_before",
                     "factor_after","source","source_version","updated_at"))
                cur.execute(
                    f"""INSERT INTO market.corporate_action
                        SELECT {ab_cols} FROM {ab} bk
                        JOIN {ma} m ON m.batch_id=%s AND m.asset_id=bk.asset_id
                          AND m.event_date=bk.event_date
                          AND m.action_type=bk.action_type
                          AND m.source_version=bk.source_version
                        WHERE m.op IN ('update','delete')
                        ON CONFLICT (asset_id, event_date, action_type, source_version)
                        DO UPDATE SET factor_before=EXCLUDED.factor_before,
                            factor_after=EXCLUDED.factor_after,
                            source=EXCLUDED.source, updated_at=EXCLUDED.updated_at""",
                    [batch_id])
                print("action update/delete-keys restored:", cur.rowcount)
                cur.execute(
                    f"""DELETE FROM market.corporate_action s USING {ma} m
                        WHERE m.batch_id=%s AND m.op='insert'
                          AND s.asset_id=m.asset_id AND s.event_date=m.event_date
                          AND s.action_type=m.action_type
                          AND s.source_version=m.source_version""",
                    [batch_id])
                print("action insert-keys deleted:", cur.rowcount)

            # ---- verification: any nonzero diff aborts the txn ----
            cur.execute(
                f"""SELECT count(*) c FROM market_daily_bar s
                    JOIN {b} bk ON bk.asset_id=s.asset_id
                      AND bk.trade_date=s.trade_date AND bk.adjust_type=s.adjust_type
                    WHERE s.asset_id=ANY(%s) AND (
                        {' OR '.join(f's.{c} IS DISTINCT FROM bk.{c}' for c in BAR_DIFF_COLS)})""",
                [assets])
            diffs = cur.fetchone()["c"]
            print("post-rollback daily diffs:", diffs)
            if bars:
                cur.execute(
                    f"""SELECT count(*) c FROM market_daily_bar s
                        JOIN {mb} m ON m.batch_id=%s AND m.op='insert'
                          AND s.asset_id=m.asset_id AND s.trade_date=m.trade_date
                          AND s.adjust_type=m.adjust_type""", [batch_id])
                insert_left = cur.fetchone()["c"]
                print("bar insert-keys still present:", insert_left)
                diffs += insert_left
            factor_diffs = 0
            if factors:
                cur.execute(
                    f"""SELECT count(*) c FROM market.adjustment_factor s
                        JOIN {fb} bk ON bk.asset_id=s.asset_id
                          AND bk.trade_date=s.trade_date
                          AND bk.source_version=s.source_version
                        JOIN {mf} m ON m.batch_id=%s AND m.asset_id=s.asset_id
                          AND m.trade_date=s.trade_date
                          AND m.source_version=s.source_version
                          AND m.op IN ('update','delete')
                        WHERE s.raw_close IS DISTINCT FROM bk.raw_close
                           OR s.qfq_close IS DISTINCT FROM bk.qfq_close
                           OR s.hfq_close IS DISTINCT FROM bk.hfq_close
                           OR s.qfq_factor IS DISTINCT FROM bk.qfq_factor
                           OR s.hfq_factor IS DISTINCT FROM bk.hfq_factor""",
                    [batch_id])
                factor_diffs = cur.fetchone()["c"]
                cur.execute(
                    f"""SELECT count(*) c FROM {mf} m
                        LEFT JOIN market.adjustment_factor s
                          ON s.asset_id=m.asset_id AND s.trade_date=m.trade_date
                         AND s.source_version=m.source_version
                        WHERE m.batch_id=%s AND m.op IN ('update','delete')
                          AND s.asset_id IS NULL""", [batch_id])
                factor_diffs += cur.fetchone()["c"]
                cur.execute(
                    f"""SELECT count(*) c FROM market.adjustment_factor s
                        JOIN {mf} m ON m.batch_id=%s AND m.op='insert'
                          AND s.asset_id=m.asset_id AND s.trade_date=m.trade_date
                          AND s.source_version=m.source_version""", [batch_id])
                factor_diffs += cur.fetchone()["c"]
                print("post-rollback factor diffs:", factor_diffs)
            action_diffs = 0
            if actions:
                cur.execute(
                    f"""SELECT count(*) c FROM market.corporate_action s
                        JOIN {ab} bk ON bk.asset_id=s.asset_id
                          AND bk.event_date=s.event_date
                          AND bk.action_type=s.action_type
                          AND bk.source_version=s.source_version
                        JOIN {ma} m ON m.batch_id=%s AND m.asset_id=s.asset_id
                          AND m.event_date=s.event_date
                          AND m.action_type=s.action_type
                          AND m.source_version=s.source_version
                          AND m.op IN ('update','delete')
                        WHERE s.factor_before IS DISTINCT FROM bk.factor_before
                           OR s.factor_after IS DISTINCT FROM bk.factor_after""",
                    [batch_id])
                action_diffs = cur.fetchone()["c"]
                cur.execute(
                    f"""SELECT count(*) c FROM {ma} m
                        LEFT JOIN market.corporate_action s
                          ON s.asset_id=m.asset_id AND s.event_date=m.event_date
                         AND s.action_type=m.action_type
                         AND s.source_version=m.source_version
                        WHERE m.batch_id=%s AND m.op IN ('update','delete')
                          AND s.asset_id IS NULL""", [batch_id])
                action_diffs += cur.fetchone()["c"]
                cur.execute(
                    f"""SELECT count(*) c FROM market.corporate_action s
                        JOIN {ma} m ON m.batch_id=%s AND m.op='insert'
                          AND s.asset_id=m.asset_id AND s.event_date=m.event_date
                          AND s.action_type=m.action_type
                          AND s.source_version=m.source_version""", [batch_id])
                action_diffs += cur.fetchone()["c"]
                print("post-rollback action diffs:", action_diffs)
            if diffs or factor_diffs or action_diffs:
                cur.execute("ROLLBACK")
                fail(f"post-rollback verification failed: bars={diffs} "
                     f"factors={factor_diffs} actions={action_diffs} — "
                     "transaction rolled back, nothing committed")
        if apply:
            conn.commit()
            print("rollback committed")
        else:
            conn.rollback()
            print("dry-run only — pass --apply to commit")


if __name__ == "__main__":
    main()
