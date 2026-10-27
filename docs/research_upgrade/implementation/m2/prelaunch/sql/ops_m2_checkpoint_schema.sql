-- ops_m2.v2_backfill_checkpoint — REVIEWED MIGRATION (not auto-created).
-- Separate operational schema so the backfill executor never creates
-- objects inside a business schema. Apply BEFORE any --mode write run.
-- Rollback (only while no checkpoint history needed):
--   DROP TABLE ops_m2.v2_backfill_checkpoint; DROP SCHEMA ops_m2;

BEGIN;
SET lock_timeout = '5s';

CREATE SCHEMA IF NOT EXISTS ops_m2;

CREATE TABLE IF NOT EXISTS ops_m2.v2_backfill_checkpoint (
  target_table   text        NOT NULL,
  trade_date     date        NOT NULL,
  flags_version  text        NOT NULL,
  status         text        NOT NULL
                 CHECK (status IN ('running','done','failed')),
  row_count      integer,
  checksum       text,       -- "n=..;ss=..;ru=..;v=.." per-batch audit
  run_id         text,
  started_at     timestamptz NOT NULL DEFAULT now(),
  finished_at    timestamptz,
  PRIMARY KEY (target_table, trade_date)
);

COMMIT;

-- post-apply verification:
-- SELECT column_name FROM information_schema.columns
--  WHERE table_schema='ops_m2' AND table_name='v2_backfill_checkpoint';
