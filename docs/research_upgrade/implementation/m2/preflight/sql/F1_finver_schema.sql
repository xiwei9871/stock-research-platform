-- M2-F1 — finver schema deploy
-- UNEXECUTED. For production approval step F1 only.
-- Generated from stock_research.financial_version_store.ddl('finver')
-- verified on stock_m2_test (local PG16) 2026-10-27.
--
-- Append-only audit tables; additive to a NEW schema — zero risk to
-- existing objects. Rollback of THIS step = DROP SCHEMA finver CASCADE
-- (only while no production evidence has been written).

BEGIN;
SET LOCAL lock_timeout = '5s';

CREATE SCHEMA IF NOT EXISTS finver;

CREATE TABLE IF NOT EXISTS finver.finver_event (
  version_event_id   bigserial PRIMARY KEY,
  asset_id           text NOT NULL,
  statement_type     text NOT NULL,
  endpoint           text NOT NULL,
  report_period      date NOT NULL,
  report_type        text NOT NULL DEFAULT '',
  version_seq        int  NOT NULL,
  supersedes_event_id bigint
    REFERENCES finver.finver_event(version_event_id),
  metric_fingerprint text NOT NULL,
  metrics            jsonb NOT NULL,
  announcement_date  date,
  announcement_evidence text NOT NULL DEFAULT 'unknown',
  first_seen_at      timestamptz NOT NULL,
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (asset_id, statement_type, endpoint, report_period,
          report_type, version_seq)
);

CREATE INDEX IF NOT EXISTS finver_event_key_idx
  ON finver.finver_event
  (asset_id, statement_type, endpoint, report_period,
   report_type, version_seq);
CREATE INDEX IF NOT EXISTS finver_event_fp_idx
  ON finver.finver_event
  (asset_id, statement_type, endpoint, report_period,
   report_type, metric_fingerprint);

CREATE TABLE IF NOT EXISTS finver.finver_observation (
  observation_id   bigserial PRIMARY KEY,
  version_event_id bigint NOT NULL
    REFERENCES finver.finver_event(version_event_id),
  raw_payload_id   bigint,
  raw_payload_hash text,
  seen_at          timestamptz NOT NULL,
  change_class     text NOT NULL,
  UNIQUE (version_event_id, raw_payload_id)
);
CREATE INDEX IF NOT EXISTS finver_observation_seen_idx
  ON finver.finver_observation (seen_at);

CREATE TABLE IF NOT EXISTS finver.finver_key_chain (
  asset_id        text NOT NULL,
  statement_type  text NOT NULL,
  endpoint        text NOT NULL,
  report_period   date NOT NULL,
  report_type     text NOT NULL DEFAULT '',
  n_versions      int  NOT NULL,
  latest_event_id bigint NOT NULL
    REFERENCES finver.finver_event(version_event_id),
  PRIMARY KEY (asset_id, statement_type, endpoint,
               report_period, report_type)
);

COMMIT;
