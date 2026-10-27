"""M1-C — append-only financial statement version event store.

Purpose: stop losing NEWLY OBSERVED version evidence to same-key
UPSERTs in the normalized finance tables. The store is an independent
event layer — the production statement tables are untouched.

Design:
  finver.event      immutable version observations
  finver.key_chain  materialized pointer to the latest event per key

A "version key" = (asset_id, statement_type, endpoint, report_period,
report_type). Each event carries the normalized metric fingerprint,
the raw payload evidence (id + hash), observation times, a per-key
version sequence, a supersedes link, and a change_class relative to the
prior observed version:

  identical          same fingerprint — idempotent, bumps last_seen only
  metadata_only      hash changed but metric vector equal
  precision_only     within 1e-4 relative tolerance
  null_asymmetry     NULL<->value flips only
  field_missing      fields present/absent asymmetrically
  metrics_changed    real numeric change — the append-only restatement

Observed vendor mutation is NOT proof of a formal corporate
restatement announcement; change_class records only what the data did.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

PERIOD_KEYS = ("REPORT_DATE", "REPORTDATE", "报告期")
ANN_KEYS = ("NOTICE_DATE", "公告日期")
META_KEYS = {"UPDATE_DATE", "更新日期", "ORG_CODE", "ORG_TYPE", "CURRENCY",
             "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR", "公告日期",
             "NOTICE_DATE", "REPORT_DATE", "REPORT_TYPE", "REPORT_DATE_NAME",
             "REPORTDATE", "报告期", "序号", "变动日期"}
SENT = "1900-01-01"
_IDENT = re.compile(r"[a-z_][a-z0-9_]*")

ENDPOINT_TO_STATEMENT = {
    "stock_profit_sheet_by_report_em": "income",
    "stock_balance_sheet_by_report_em": "balance",
    "stock_cash_flow_sheet_by_report_em": "cash_flow",
    "stock_financial_report_sina": "sina_report",
    "stock_share_change_cninfo": "share_change",
}


def ddl(schema: str = "m1_shadow") -> str:
    if not _IDENT.fullmatch(schema):
        raise ValueError(f"bad schema: {schema!r}")
    return f"""
    CREATE SCHEMA IF NOT EXISTS {schema};
    CREATE TABLE IF NOT EXISTS {schema}.finver_event (
      version_event_id  bigserial PRIMARY KEY,
      asset_id          text        NOT NULL,
      statement_type    text        NOT NULL,
      endpoint          text        NOT NULL,
      report_period     date        NOT NULL,
      report_type       text        NOT NULL DEFAULT '',
      metric_fingerprint text       NOT NULL,
      metrics           jsonb       NOT NULL,
      announcement_date date,
      announcement_evidence text    NOT NULL DEFAULT 'unknown',
      raw_payload_id    bigint,
      raw_payload_hash  text,
      first_seen_at     timestamptz NOT NULL,
      last_seen_at      timestamptz NOT NULL,
      version_seq       int         NOT NULL,
      supersedes_event_id bigint REFERENCES {schema}.finver_event(version_event_id),
      change_class      text        NOT NULL,
      created_at        timestamptz NOT NULL DEFAULT now(),
      UNIQUE (asset_id, statement_type, endpoint, report_period,
              report_type, metric_fingerprint)
    );
    CREATE INDEX IF NOT EXISTS finver_event_key_idx
      ON {schema}.finver_event
      (asset_id, statement_type, report_period, version_seq);
    CREATE TABLE IF NOT EXISTS {schema}.finver_key_chain (
      asset_id        text NOT NULL,
      statement_type  text NOT NULL,
      endpoint        text NOT NULL,
      report_period   date NOT NULL,
      report_type     text NOT NULL DEFAULT '',
      n_versions      int  NOT NULL,
      latest_event_id bigint NOT NULL
        REFERENCES {schema}.finver_event(version_event_id),
      PRIMARY KEY (asset_id, statement_type, endpoint,
                   report_period, report_type)
    );"""


def to_rows(payload: Any) -> list[dict]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in ("data", "result", "rows"):
            if isinstance(payload.get(k), list):
                return [r for r in payload[k] if isinstance(r, dict)]
        return [payload]
    return []


def _pick(row: dict, keys) -> str | None:
    for k in keys:
        if row.get(k):
            return str(row[k])[:10]
    return None


def metrics_of(row: dict) -> dict:
    return {k: v for k, v in row.items()
            if k not in META_KEYS and not str(k).endswith("_YOY")}


def _norm(v):
    if v is None:
        return None
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return str(v)


def fingerprint(metrics: dict) -> str:
    canon = {k: _norm(v) for k, v in sorted(metrics.items())}
    return hashlib.sha256(
        json.dumps(canon, sort_keys=True).encode()).hexdigest()[:32]


def field_class(a: dict, b: dict) -> str:
    """a = prior metrics, b = new metrics."""
    keys = set(a) | set(b)
    worst = "identical"
    rank = {"metrics_changed": 5, "field_missing": 4,
            "null_asymmetry": 3, "precision_only": 2,
            "identical": 1}
    for k in keys:
        va, vb = a.get(k, "∅"), b.get(k, "∅")
        if va == "∅" or vb == "∅":
            c = "field_missing"
        elif va is None or vb is None:
            c = "null_asymmetry" if va != vb else "identical"
        else:
            try:
                fa, fb = float(va), float(vb)
                if fa == fb:
                    c = "identical"
                elif abs(fa - fb) <= max(abs(fa), abs(fb)) * 1e-4:
                    c = "precision_only"
                else:
                    c = "metrics_changed"
            except (TypeError, ValueError):
                c = "metrics_changed" if str(va) != str(vb) \
                    else "identical"
        if rank[c] > rank[worst]:
            worst = c
    return worst


def _ann_evidence(ann: str | None) -> str:
    if not ann or ann == SENT:
        return "unknown"
    return "vendor_supplied_date"


def ingest_payload(conn, schema: str, asset_id: str, endpoint: str,
                   fetched_at, payload, raw_payload_id=None,
                   raw_payload_hash=None,
                   report_type_default: str = "") -> dict:
    """Expand one raw payload into version events. Idempotent.

    Returns counters: new_version / identical_bump / no_period /
    empty_metrics / skipped_rows.
    """
    from stock_research.db import execute, fetch_all
    out = {"new_version": 0, "identical_bump": 0, "no_period": 0,
           "empty_metrics": 0, "skipped_rows": 0}
    st = ENDPOINT_TO_STATEMENT.get(endpoint, endpoint)
    for row in to_rows(payload):
        period = _pick(row, PERIOD_KEYS)
        if not period:
            out["no_period"] += 1
            continue
        metrics = metrics_of(row)
        if not metrics:
            out["empty_metrics"] += 1
            continue
        ann = _pick(row, ANN_KEYS)
        rt = str(row.get("REPORT_TYPE") or report_type_default)
        fp = fingerprint(metrics)
        chain = fetch_all(conn, f"""
          SELECT c.latest_event_id, c.n_versions, e.metrics, e.change_class
          FROM {schema}.finver_key_chain c
          JOIN {schema}.finver_event e
            ON e.version_event_id = c.latest_event_id
          WHERE c.asset_id=%s AND c.statement_type=%s AND c.endpoint=%s
            AND c.report_period=%s AND c.report_type=%s""",
                          [asset_id, st, endpoint, period, rt])
        if not chain:
            execute(conn, f"""
              INSERT INTO {schema}.finver_event
                (asset_id, statement_type, endpoint, report_period,
                 report_type, metric_fingerprint, metrics,
                 announcement_date, announcement_evidence,
                 raw_payload_id, raw_payload_hash,
                 first_seen_at, last_seen_at, version_seq, change_class)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,'initial_observed')
              RETURNING version_event_id""",
                    [asset_id, st, endpoint, period, rt, fp,
                     json.dumps(metrics), ann, _ann_evidence(ann),
                     raw_payload_id, raw_payload_hash, fetched_at,
                     fetched_at])
            eid = fetch_all(conn, "SELECT lastval() i")[0]["i"]
            execute(conn, f"""
              INSERT INTO {schema}.finver_key_chain
                (asset_id, statement_type, endpoint, report_period,
                 report_type, n_versions, latest_event_id)
              VALUES (%s,%s,%s,%s,%s,1,%s)""",
                    [asset_id, st, endpoint, period, rt, eid])
            out["new_version"] += 1
            continue
        cur = chain[0]
        cls = field_class(cur["metrics"], metrics)
        if cls == "identical":
            execute(conn, f"""
              UPDATE {schema}.finver_event SET last_seen_at=%s
              WHERE version_event_id=%s""", [fetched_at,
                                            cur["latest_event_id"]])
            out["identical_bump"] += 1
            continue
        if cls in ("metrics_changed", "field_missing", "null_asymmetry",
                   "precision_only"):
            execute(conn, f"""
              INSERT INTO {schema}.finver_event
                (asset_id, statement_type, endpoint, report_period,
                 report_type, metric_fingerprint, metrics,
                 announcement_date, announcement_evidence,
                 raw_payload_id, raw_payload_hash,
                 first_seen_at, last_seen_at, version_seq,
                 supersedes_event_id, change_class)
              VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
              RETURNING version_event_id""",
                    [asset_id, st, endpoint, period, rt, fp,
                     json.dumps(metrics), ann, _ann_evidence(ann),
                     raw_payload_id, raw_payload_hash, fetched_at,
                     fetched_at, cur["n_versions"] + 1,
                     cur["latest_event_id"], cls])
            eid = fetch_all(conn, "SELECT lastval() i")[0]["i"]
            execute(conn, f"""
              UPDATE {schema}.finver_key_chain
              SET n_versions=%s, latest_event_id=%s
              WHERE asset_id=%s AND statement_type=%s AND endpoint=%s
                AND report_period=%s AND report_type=%s""",
                    [cur["n_versions"] + 1, eid, asset_id, st, endpoint,
                     period, rt])
            out["new_version"] += 1
        else:  # identical metric vector, different payload hash
            execute(conn, f"""
              UPDATE {schema}.finver_event SET last_seen_at=%s
              WHERE version_event_id=%s""", [fetched_at,
                                            cur["latest_event_id"]])
            out["identical_bump"] += 1
    return out


def latest(conn, schema: str, asset_id: str, statement_type: str,
           report_period: str, endpoint: str | None = None) -> dict | None:
    """Latest observed version for a key (any endpoint or pinned)."""
    from stock_research.db import fetch_all
    cond = "AND e.endpoint=%s" if endpoint else ""
    params = [asset_id, statement_type, report_period] + (
        [endpoint] if endpoint else [])
    rows = fetch_all(conn, f"""
      SELECT e.* FROM {schema}.finver_event e
      JOIN {schema}.finver_key_chain c
        ON c.latest_event_id = e.version_event_id
      WHERE c.asset_id=%s AND c.statement_type=%s
        AND c.report_period=%s {cond}
      ORDER BY e.version_seq DESC, e.endpoint LIMIT 1""", params)
    return rows[0] if rows else None


def read_as_of(conn, schema: str, asset_id: str, statement_type: str,
               report_period: str, as_of,
               endpoint: str | None = None) -> dict | None:
    """Version observed by the platform at as_of (first_seen_at <= as_of).

    first_seen_at proves PLATFORM observation time only — never the
    market's first publication date.
    """
    from stock_research.db import fetch_all
    cond = "AND endpoint=%s" if endpoint else ""
    params = [asset_id, statement_type, report_period, as_of] + (
        [endpoint] if endpoint else [])
    rows = fetch_all(conn, f"""
      SELECT * FROM {schema}.finver_event
      WHERE asset_id=%s AND statement_type=%s AND report_period=%s
        AND first_seen_at <= %s {cond}
      ORDER BY version_seq DESC, endpoint LIMIT 1""", params)
    return rows[0] if rows else None
