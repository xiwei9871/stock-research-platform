-- M2-T1 — core.asset_status_daily additive V2 columns
-- UNEXECUTED. For production approval step T1 only.
-- Verified on stock_m2_test (local PG16) 2026-10-27.
--
-- Properties: additive; no V1 column touched; nullable, no default
-- (no table rewrite); no index added (17.3M rows — index cost must be
-- a separate decision); lock_timeout guarded.
--
-- Rollback of THIS step: the five columns are nullable and untouched
-- by V1 readers; DROP COLUMN is safe ONLY while no V2 data has been
-- written. After data lands, rollback = stop writer + leave columns
-- (do NOT drop populated audit columns — see E3 rollback tiers).

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

ALTER TABLE core.asset_status_daily
  ADD COLUMN IF NOT EXISTS is_limit_up_v2      boolean,
  ADD COLUMN IF NOT EXISTS is_limit_down_v2    boolean,
  ADD COLUMN IF NOT EXISTS limit_state_v2      smallint,
  ADD COLUMN IF NOT EXISTS limit_rule_id_v2    text,
  ADD COLUMN IF NOT EXISTS limit_flags_version text;

COMMIT;

-- post-check (run separately, read-only):
-- SELECT column_name, data_type, is_nullable
--   FROM information_schema.columns
--  WHERE table_schema='core' AND table_name='asset_status_daily'
--    AND (column_name LIKE '%_v2' OR column_name='limit_flags_version')
--  ORDER BY column_name;
-- expect 5 rows, all is_nullable='YES'
