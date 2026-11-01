-- Gate A rollback. Restores the legacy UNIQUE (run_id, digest_key) contract.
-- Older versions of a (run_id, digest_key) are MOVED (not deleted) into
-- *_version_archive tables so no snapshot content is lost.
-- ops.data_run_attempt is kept by default (it has no readers in the legacy
-- code); drop it explicitly only if required.
BEGIN;
DROP VIEW IF EXISTS ops.review_item_snapshot_current;
DROP VIEW IF EXISTS ops.evidence_digest_snapshot_current;

CREATE TABLE IF NOT EXISTS ops.review_item_snapshot_version_archive
    (LIKE ops.review_item_snapshot INCLUDING DEFAULTS);
WITH ranked AS (
    SELECT snapshot_id, row_number() OVER (
        PARTITION BY run_id, digest_key ORDER BY created_at DESC, snapshot_id) AS rn
    FROM ops.review_item_snapshot)
, moved AS (
    DELETE FROM ops.review_item_snapshot s USING ranked r
     WHERE s.snapshot_id = r.snapshot_id AND r.rn > 1
    RETURNING s.*)
INSERT INTO ops.review_item_snapshot_version_archive SELECT * FROM moved;

CREATE TABLE IF NOT EXISTS ops.evidence_digest_snapshot_version_archive
    (LIKE ops.evidence_digest_snapshot INCLUDING DEFAULTS);
WITH ranked AS (
    SELECT snapshot_id, row_number() OVER (
        PARTITION BY run_id, digest_key ORDER BY created_at DESC, snapshot_id) AS rn
    FROM ops.evidence_digest_snapshot)
, moved AS (
    DELETE FROM ops.evidence_digest_snapshot s USING ranked r
     WHERE s.snapshot_id = r.snapshot_id AND r.rn > 1
    RETURNING s.*)
INSERT INTO ops.evidence_digest_snapshot_version_archive SELECT * FROM moved;

DROP INDEX IF EXISTS ops.uq_review_item_snapshot_version;
DROP INDEX IF EXISTS ops.uq_evidence_digest_snapshot_version;
ALTER TABLE ops.review_item_snapshot
    ADD CONSTRAINT review_item_snapshot_run_id_digest_key_key UNIQUE (run_id, digest_key);
ALTER TABLE ops.evidence_digest_snapshot
    ADD CONSTRAINT evidence_digest_snapshot_run_id_digest_key_key UNIQUE (run_id, digest_key);
-- provenance columns are left in place (nullable, ignored by legacy code).
COMMIT;
