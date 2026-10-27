"""M2-0 rev — append-only financial statement version event store.

Deployment chain (M2-0-D):

  * content fingerprint is NOT the event identity — identity is
    version_event_id + (key, version_seq). Identical metric vectors may
    recur (A->B->A) and each is its own immutable event.
  * every fetch observation is recorded in finver_observation
    (raw_payload_id/hash/seen_at); committed events are NEVER mutated —
    mutable metadata lives only in the observation/state layer.
  * per-key serialization uses a transaction-scoped advisory lock so
    concurrent ingests cannot collide on version_seq or orphan events.
  * read_as_of uses first_seen_at = PLATFORM observation time. It can
    never stand in for the market's first publication date.
  * out-of-order arrivals are handled by comparing fetched_at against
    the key's latest seen_at plus fingerprint history:
      - identical to head          -> identical sighting
      - match older event, late    -> 'late_arrival_repeat' on the OLD
                                      event; head never regresses
      - match older event, fresh   -> true reversion: NEW event
                                      (A->B->A preserved)
      - unseen content             -> new event ('arrived_out_of_order'
                                      counted when fetched_at predates
                                      prior sightings)
  * supported sources are explicit (ENDPOINT_TO_STATEMENT); unknown
    endpoints are counted, never silently dropped.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

PERIOD_KEYS = ("REPORT_DATE", "REPORTDATE", "报告期", "报告日")
ANN_KEYS = ("NOTICE_DATE", "公告日期")
META_KEYS = {"UPDATE_DATE", "更新日期", "ORG_CODE", "ORG_TYPE", "CURRENCY",
             "SECUCODE", "SECURITY_CODE", "SECURITY_NAME_ABBR", "公告日期",
             "NOTICE_DATE", "REPORT_DATE", "REPORT_TYPE", "REPORT_DATE_NAME",
             "REPORTDATE", "报告期", "报告日", "序号", "变动日期"}
SENT = "1900-01-01"
_IDENT = re.compile(r"[a-z_][a-z0-9_]*")

ENDPOINT_TO_STATEMENT = {
    "stock_profit_sheet_by_report_em": "income",
    "stock_balance_sheet_by_report_em": "balance",
    "stock_cash_flow_sheet_by_report_em": "cash_flow",
    "stock_financial_report_sina": "sina_report",
    "stock_share_change_cninfo": "share_change",
}


def ddl(schema: str = "finver") -> str:
    if not _IDENT.fullmatch(schema):
        raise ValueError(f"bad schema: {schema!r}")
    return f"""
    CREATE SCHEMA IF NOT EXISTS {schema};
    CREATE TABLE IF NOT EXISTS {schema}.finver_event (
      version_event_id   bigserial PRIMARY KEY,
      asset_id           text NOT NULL,
      statement_type     text NOT NULL,
      endpoint           text NOT NULL,
      report_period      date NOT NULL,
      report_type        text NOT NULL DEFAULT '',
      version_seq        int  NOT NULL,
      supersedes_event_id bigint
        REFERENCES {schema}.finver_event(version_event_id),
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
      ON {schema}.finver_event
      (asset_id, statement_type, endpoint, report_period,
       report_type, version_seq);
    CREATE INDEX IF NOT EXISTS finver_event_fp_idx
      ON {schema}.finver_event
      (asset_id, statement_type, endpoint, report_period,
       report_type, metric_fingerprint);
    CREATE TABLE IF NOT EXISTS {schema}.finver_observation (
      observation_id   bigserial PRIMARY KEY,
      version_event_id bigint NOT NULL
        REFERENCES {schema}.finver_event(version_event_id),
      raw_payload_id   bigint,
      raw_payload_hash text,
      seen_at          timestamptz NOT NULL,
      change_class     text NOT NULL,
      UNIQUE (version_event_id, raw_payload_id)
    );
    CREATE INDEX IF NOT EXISTS finver_observation_seen_idx
      ON {schema}.finver_observation (seen_at);
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
    return "unknown" if (not ann or ann == SENT) else "vendor_supplied_date"


def _lock_key(conn, schema, asset, st, ep, period, rt):
    """Serialize ingest per key inside the transaction."""
    from stock_research.db import execute
    execute(conn, "SELECT pg_advisory_xact_lock(hashtext(%s))",
            [f"{asset}|{st}|{ep}|{period}|{rt}"])


def _obs(conn, schema, event_id, raw_payload_id, raw_payload_hash,
         seen_at, change_class):
    from stock_research.db import execute
    execute(conn, f"""
      INSERT INTO {schema}.finver_observation
        (version_event_id, raw_payload_id, raw_payload_hash,
         seen_at, change_class)
      VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            [event_id, raw_payload_id, raw_payload_hash, seen_at,
             change_class])


def _new_event(conn, schema, asset_id, st, endpoint, period, rt,
               seq, supersedes, fp, metrics, ann, fetched_at):
    from stock_research.db import fetch_all
    return fetch_all(conn, f"""
      INSERT INTO {schema}.finver_event
        (asset_id, statement_type, endpoint, report_period,
         report_type, version_seq, supersedes_event_id,
         metric_fingerprint, metrics, announcement_date,
         announcement_evidence, first_seen_at)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      RETURNING version_event_id""",
            [asset_id, st, endpoint, period, rt, seq, supersedes, fp,
             json.dumps(metrics), ann, _ann_evidence(ann),
             fetched_at])[0]["version_event_id"]


def ingest_payload(conn, schema: str, asset_id: str, endpoint: str,
                   fetched_at, payload, raw_payload_id=None,
                   raw_payload_hash=None,
                   report_type_default: str = "") -> dict:
    """Expand one raw payload into immutable version events +
    observation records. Idempotent per (event, raw_payload_id)."""
    from stock_research.db import execute, fetch_all
    out = {"processed": 0, "new_version": 0, "identical_bump": 0,
           "changed": 0, "reversion": 0, "late_arrival_repeat": 0,
           "arrived_out_of_order": 0, "no_period": 0,
           "missing_period": 0, "empty_metrics": 0,
           "unknown_source": 0, "failed": 0}
    st = ENDPOINT_TO_STATEMENT.get(endpoint)
    if st is None:
        st = endpoint
        out["unknown_source"] += 1
    for row in to_rows(payload):
        period = _pick(row, PERIOD_KEYS)
        if not period:
            out["no_period"] += 1
            out["missing_period"] += 1
            continue
        metrics = metrics_of(row)
        if not metrics:
            out["empty_metrics"] += 1
            continue
        out["processed"] += 1
        ann = _pick(row, ANN_KEYS)
        rt = str(row.get("REPORT_TYPE") or report_type_default)
        fp = fingerprint(metrics)
        _lock_key(conn, schema, asset_id, st, endpoint, period, rt)
        chain = fetch_all(conn, f"""
          SELECT c.latest_event_id, c.n_versions, e.metrics,
                 e.metric_fingerprint
          FROM {schema}.finver_key_chain c
          JOIN {schema}.finver_event e
            ON e.version_event_id = c.latest_event_id
          WHERE c.asset_id=%s AND c.statement_type=%s AND c.endpoint=%s
            AND c.report_period=%s AND c.report_type=%s""",
                          [asset_id, st, endpoint, period, rt])
        if not chain:
            eid = _new_event(conn, schema, asset_id, st, endpoint,
                             period, rt, 1, None, fp, metrics, ann,
                             fetched_at)
            execute(conn, f"""
              INSERT INTO {schema}.finver_key_chain
                (asset_id, statement_type, endpoint, report_period,
                 report_type, n_versions, latest_event_id)
              VALUES (%s,%s,%s,%s,%s,1,%s)""",
                    [asset_id, st, endpoint, period, rt, eid])
            _obs(conn, schema, eid, raw_payload_id, raw_payload_hash,
                 fetched_at, "initial_observed")
            out["new_version"] += 1
            out["changed"] += 1
            continue
        cur = chain[0]
        max_seen = fetch_all(conn, f"""
          SELECT max(o.seen_at) mx FROM {schema}.finver_observation o
          JOIN {schema}.finver_event e
            ON e.version_event_id=o.version_event_id
          WHERE e.asset_id=%s AND e.statement_type=%s AND e.endpoint=%s
            AND e.report_period=%s AND e.report_type=%s""",
                             [asset_id, st, endpoint, period, rt]
                             )[0]["mx"]
        late = max_seen is not None and str(fetched_at) <= str(max_seen)
        if fp == cur["metric_fingerprint"]:
            _obs(conn, schema, cur["latest_event_id"], raw_payload_id,
                 raw_payload_hash, fetched_at, "identical")
            out["identical_bump"] += 1
            continue
        older = fetch_all(conn, f"""
          SELECT version_event_id, version_seq
          FROM {schema}.finver_event
          WHERE asset_id=%s AND statement_type=%s AND endpoint=%s
            AND report_period=%s AND report_type=%s
            AND metric_fingerprint=%s""",
                          [asset_id, st, endpoint, period, rt, fp])
        if older:
            if late:
                # late-arriving replay of superseded content — the head
                # must never regress; record the sighting on the old
                # event instead of appending a bogus new version
                _obs(conn, schema, older[0]["version_event_id"],
                     raw_payload_id, raw_payload_hash, fetched_at,
                     "late_arrival_repeat")
                out["late_arrival_repeat"] += 1
                continue
            # genuine content reversion (A->B->A) — a third event
            eid = _new_event(conn, schema, asset_id, st, endpoint,
                             period, rt, cur["n_versions"] + 1,
                             cur["latest_event_id"], fp, metrics, ann,
                             fetched_at)
            execute(conn, f"""
              UPDATE {schema}.finver_key_chain
              SET n_versions=%s, latest_event_id=%s
              WHERE asset_id=%s AND statement_type=%s AND endpoint=%s
                AND report_period=%s AND report_type=%s""",
                    [cur["n_versions"] + 1, eid, asset_id, st, endpoint,
                     period, rt])
            _obs(conn, schema, eid, raw_payload_id, raw_payload_hash,
                 fetched_at, "reversion")
            out["new_version"] += 1
            out["reversion"] += 1
            out["changed"] += 1
            continue
        cls = field_class(cur["metrics"], metrics)
        eid = _new_event(conn, schema, asset_id, st, endpoint, period,
                         rt, cur["n_versions"] + 1,
                         cur["latest_event_id"], fp, metrics, ann,
                         fetched_at)
        # head = event with the LATEST first_seen_at (not last-append):
        # an out-of-order arrival must not demote a newer head
        execute(conn, f"""
          UPDATE {schema}.finver_key_chain c
          SET n_versions=%s,
              latest_event_id=(
                SELECT version_event_id FROM {schema}.finver_event
                WHERE asset_id=c.asset_id AND statement_type=c.statement_type
                  AND endpoint=c.endpoint AND report_period=c.report_period
                  AND report_type=c.report_type
                ORDER BY first_seen_at DESC, version_seq DESC LIMIT 1)
          WHERE asset_id=%s AND statement_type=%s AND endpoint=%s
            AND report_period=%s AND report_type=%s""",
                [cur["n_versions"] + 1, asset_id, st, endpoint,
                 period, rt])
        _obs(conn, schema, eid, raw_payload_id, raw_payload_hash,
             fetched_at, cls)
        out["new_version"] += 1
        out["changed"] += 1
        if late:
            out["arrived_out_of_order"] += 1
    return out


def latest(conn, schema: str, asset_id: str, statement_type: str,
           report_period: str, endpoint: str | None = None) -> dict | None:
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
      ORDER BY e.first_seen_at DESC, e.version_seq DESC,
               e.endpoint LIMIT 1""", params)
    return rows[0] if rows else None


def read_as_of(conn, schema: str, asset_id: str, statement_type: str,
               report_period: str, as_of,
               endpoint: str | None = None) -> dict | None:
    """Version first OBSERVED BY THE PLATFORM at/before as_of.

    first_seen_at is platform observation time — never proof of the
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
      ORDER BY first_seen_at DESC, version_seq DESC, endpoint
      LIMIT 1""", params)
    return rows[0] if rows else None
