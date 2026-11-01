-- Gate A forward migration (reviewed manual apply; NOT run automatically).
-- 1) ops.data_run_attempt  2) snapshot versioning + *_current views.
-- Online-safe: ADD COLUMN without default, CREATE UNIQUE INDEX, view swap.
-- Run inside one transaction. Take a table-level dump of
-- ops.review_item_snapshot / ops.evidence_digest_snapshot / ops.data_run_manifest first.
BEGIN;
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.data_run_attempt (
    attempt_id text PRIMARY KEY,
    run_id text NOT NULL,
    trade_date date,
    module text NOT NULL,
    trigger text NOT NULL CHECK (trigger IN ('cron', 'repair', 'manual')),
    status text NOT NULL CHECK (status IN (
        'running', 'published', 'succeeded', 'failed', 'skipped', 'abandoned')),
    failure_class text CHECK (failure_class IS NULL OR failure_class IN (
        'dependency', 'environment', 'compute', 'publish', 'notify', 'abandoned')),
    parent_attempt_id text,
    git_sha text,
    input_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_message text,
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    recorded_from text NOT NULL DEFAULT 'db' CHECK (recorded_from IN ('db', 'local_backfill')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_run_attempt_run
    ON ops.data_run_attempt (run_id, module, started_at DESC);

ALTER TABLE ops.review_item_snapshot
    ADD COLUMN IF NOT EXISTS publication_attempt_id text,
    ADD COLUMN IF NOT EXISTS snapshot_attempt_id text,
    ADD COLUMN IF NOT EXISTS source_manifest_sha256 text;
ALTER TABLE ops.evidence_digest_snapshot
    ADD COLUMN IF NOT EXISTS publication_attempt_id text,
    ADD COLUMN IF NOT EXISTS snapshot_attempt_id text,
    ADD COLUMN IF NOT EXISTS source_manifest_sha256 text;
ALTER TABLE ops.review_item_snapshot
    DROP CONSTRAINT IF EXISTS review_item_snapshot_run_id_digest_key_key;
ALTER TABLE ops.evidence_digest_snapshot
    DROP CONSTRAINT IF EXISTS evidence_digest_snapshot_run_id_digest_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_item_snapshot_version
    ON ops.review_item_snapshot (run_id, digest_key, payload_hash);
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_digest_snapshot_version
    ON ops.evidence_digest_snapshot (run_id, digest_key, payload_hash);
-- Current version = the latest publication batch of a run (rows sharing a
-- publication_attempt_id; legacy rows with NULL form one batch), then the
-- newest row per item inside that batch. Never mixes two publications.
CREATE OR REPLACE VIEW ops.review_item_snapshot_current AS
SELECT DISTINCT ON (s.run_id, s.digest_key) s.*
  FROM ops.review_item_snapshot s
  JOIN (
        SELECT DISTINCT ON (run_id) run_id, publication_attempt_id
          FROM ops.review_item_snapshot
         GROUP BY run_id, publication_attempt_id
         ORDER BY run_id, max(created_at) DESC
       ) cur
    ON cur.run_id = s.run_id
   AND cur.publication_attempt_id IS NOT DISTINCT FROM s.publication_attempt_id
 ORDER BY s.run_id, s.digest_key, s.created_at DESC, s.snapshot_id;

CREATE OR REPLACE VIEW ops.evidence_digest_snapshot_current AS
SELECT DISTINCT ON (s.run_id, s.digest_key) s.*
  FROM ops.evidence_digest_snapshot s
  JOIN (
        SELECT DISTINCT ON (run_id) run_id, publication_attempt_id
          FROM ops.evidence_digest_snapshot
         GROUP BY run_id, publication_attempt_id
         ORDER BY run_id, max(created_at) DESC
       ) cur
    ON cur.run_id = s.run_id
   AND cur.publication_attempt_id IS NOT DISTINCT FROM s.publication_attempt_id
 ORDER BY s.run_id, s.digest_key, s.created_at DESC, s.snapshot_id;

COMMIT;
