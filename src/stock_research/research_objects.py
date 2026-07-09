from __future__ import annotations

import hashlib
import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


RESEARCH_OBJECTS_SQL = """
CREATE SCHEMA IF NOT EXISTS research;

CREATE TABLE IF NOT EXISTS research.research_case (
    case_id text PRIMARY KEY,
    trade_date date,
    asset_id text,
    theme text,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    priority integer NOT NULL DEFAULT 50,
    source_type text NOT NULL DEFAULT 'manual',
    source_id text NOT NULL DEFAULT '',
    created_by text NOT NULL DEFAULT 'system',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS research.research_claim (
    claim_id text PRIMARY KEY,
    case_id text NOT NULL REFERENCES research.research_case(case_id) ON DELETE CASCADE,
    claim_type text NOT NULL,
    claim_text text NOT NULL,
    confidence numeric,
    status text NOT NULL DEFAULT 'draft',
    created_by text NOT NULL DEFAULT 'system',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS research.evidence_artifact (
    evidence_id text PRIMARY KEY,
    source_type text NOT NULL,
    source_id text NOT NULL,
    asset_id text,
    trade_date date,
    title text NOT NULL DEFAULT '',
    uri text NOT NULL DEFAULT '',
    content_hash text NOT NULL DEFAULT '',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_type, source_id)
);

CREATE TABLE IF NOT EXISTS research.evidence_link (
    link_id text PRIMARY KEY,
    evidence_id text NOT NULL REFERENCES research.evidence_artifact(evidence_id) ON DELETE CASCADE,
    target_type text NOT NULL,
    target_id text NOT NULL,
    relation text NOT NULL DEFAULT 'supports',
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (evidence_id, target_type, target_id, relation)
);

CREATE TABLE IF NOT EXISTS research.decision_snapshot (
    decision_snapshot_id text PRIMARY KEY,
    decision_event_id text NOT NULL,
    case_id text,
    asset_id text NOT NULL,
    decision_label text NOT NULL,
    decision_status text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.publication_snapshot (
    publication_snapshot_id text PRIMARY KEY,
    trade_date date NOT NULL,
    channel text NOT NULL,
    title text NOT NULL,
    payload jsonb NOT NULL,
    created_by text NOT NULL DEFAULT 'system',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research.agent_run (
    agent_run_id text PRIMARY KEY,
    workflow text NOT NULL,
    status text NOT NULL DEFAULT 'created',
    request_id text NOT NULL DEFAULT '',
    trade_date date,
    asset_id text,
    case_id text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    input_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS research.agent_run_event (
    event_id text PRIMARY KEY,
    agent_run_id text NOT NULL REFERENCES research.agent_run(agent_run_id) ON DELETE CASCADE,
    event_index integer NOT NULL,
    event_type text NOT NULL,
    status text NOT NULL DEFAULT 'ok',
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (agent_run_id, event_index)
);

CREATE TABLE IF NOT EXISTS research.review_action (
    review_action_id text PRIMARY KEY,
    case_id text NOT NULL REFERENCES research.research_case(case_id) ON DELETE CASCADE,
    trade_date date,
    asset_id text,
    action_type text NOT NULL,
    gap_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
    reviewer text NOT NULL DEFAULT 'operator',
    comment text NOT NULL DEFAULT '',
    source_context jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS research.external_delivery_attempt (
    delivery_attempt_id text PRIMARY KEY,
    publication_snapshot_id text NOT NULL,
    trade_date date,
    channel text NOT NULL,
    mode text NOT NULL,
    status text NOT NULL,
    external_send_enabled boolean NOT NULL DEFAULT false,
    dry_run boolean NOT NULL DEFAULT true,
    delivery_plan_id text NOT NULL DEFAULT '',
    message_title text NOT NULL DEFAULT '',
    message_hash text NOT NULL DEFAULT '',
    created_by text NOT NULL DEFAULT 'system',
    created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    error_code text NOT NULL DEFAULT '',
    error_message text NOT NULL DEFAULT '',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS research.external_delivery_event (
    delivery_event_id text PRIMARY KEY,
    delivery_attempt_id text NOT NULL REFERENCES research.external_delivery_attempt(delivery_attempt_id) ON DELETE CASCADE,
    event_index integer NOT NULL,
    event_type text NOT NULL,
    status text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (delivery_attempt_id, event_index)
);

CREATE INDEX IF NOT EXISTS idx_research_case_trade_date
    ON research.research_case (trade_date DESC, status, priority);

CREATE INDEX IF NOT EXISTS idx_research_case_asset
    ON research.research_case (asset_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_research_claim_case
    ON research.research_claim (case_id, status);

CREATE INDEX IF NOT EXISTS idx_evidence_artifact_asset
    ON research.evidence_artifact (asset_id, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_link_target
    ON research.evidence_link (target_type, target_id);

CREATE INDEX IF NOT EXISTS idx_agent_run_workflow
    ON research.agent_run (workflow, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_review_action_case_created
    ON research.review_action (case_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_review_action_trade_date
    ON research.review_action (trade_date DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_delivery_attempt_snapshot
    ON research.external_delivery_attempt (publication_snapshot_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_delivery_attempt_trade_date
    ON research.external_delivery_attempt (trade_date DESC, channel, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_external_delivery_event_attempt
    ON research.external_delivery_event (delivery_attempt_id, event_index);
"""


def apply_research_object_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(RESEARCH_OBJECTS_SQL)


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(_canonical_part(part) for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def upsert_research_case(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    case_id = str(
        payload.get("case_id")
        or stable_id(
            "research_case",
            payload.get("trade_date"),
            payload.get("asset_id"),
            payload.get("theme"),
            payload.get("title"),
        )
    )
    params = {
        "case_id": case_id,
        "trade_date": _optional_date(payload.get("trade_date")),
        "asset_id": _optional_text(payload.get("asset_id")),
        "theme": _optional_text(payload.get("theme")),
        "title": _text(payload.get("title")),
        "status": _text(payload.get("status") or "open"),
        "priority": int(payload.get("priority") or 50),
        "source_type": _text(payload.get("source_type") or "manual"),
        "source_id": _text(payload.get("source_id")),
        "created_by": _text(payload.get("created_by") or "system"),
        "metadata": _json(payload.get("metadata") or {}),
    }
    sql = """
    INSERT INTO research.research_case (
        case_id, trade_date, asset_id, theme, title, status, priority,
        source_type, source_id, created_by, metadata
    )
    VALUES (
        %(case_id)s, %(trade_date)s, %(asset_id)s, %(theme)s, %(title)s,
        %(status)s, %(priority)s, %(source_type)s, %(source_id)s,
        %(created_by)s, %(metadata)s::jsonb
    )
    ON CONFLICT (case_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        status = EXCLUDED.status,
        priority = EXCLUDED.priority,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return case_id


def upsert_research_claim(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    claim_id = str(
        payload.get("claim_id")
        or stable_id("research_claim", payload.get("case_id"), payload.get("claim_type"), payload.get("claim_text"))
    )
    params = {
        "claim_id": claim_id,
        "case_id": _text(payload.get("case_id")),
        "claim_type": _text(payload.get("claim_type")),
        "claim_text": _text(payload.get("claim_text")),
        "confidence": payload.get("confidence"),
        "status": _text(payload.get("status") or "draft"),
        "created_by": _text(payload.get("created_by") or "system"),
        "metadata": _json(payload.get("metadata") or {}),
    }
    sql = """
    INSERT INTO research.research_claim (
        claim_id, case_id, claim_type, claim_text, confidence, status, created_by, metadata
    )
    VALUES (
        %(claim_id)s, %(case_id)s, %(claim_type)s, %(claim_text)s,
        %(confidence)s, %(status)s, %(created_by)s, %(metadata)s::jsonb
    )
    ON CONFLICT (claim_id)
    DO UPDATE SET
        claim_text = EXCLUDED.claim_text,
        confidence = EXCLUDED.confidence,
        status = EXCLUDED.status,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return claim_id


def upsert_evidence_artifact(evidence: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    evidence_id = _text(evidence.get("evidence_id"))
    params = {
        "evidence_id": evidence_id,
        "source_type": _text(evidence.get("source_type")),
        "source_id": _text(evidence.get("source_id")),
        "asset_id": _optional_text(evidence.get("asset_id")),
        "trade_date": _optional_date(evidence.get("trade_date")),
        "title": _text(evidence.get("title")),
        "uri": _text(evidence.get("uri")),
        "content_hash": _text(evidence.get("content_hash")),
        "payload": _json(evidence.get("payload") or {}),
        "metadata": _json(evidence.get("metadata") or {}),
    }
    sql = """
    INSERT INTO research.evidence_artifact (
        evidence_id, source_type, source_id, asset_id, trade_date,
        title, uri, content_hash, payload, metadata
    )
    VALUES (
        %(evidence_id)s, %(source_type)s, %(source_id)s, %(asset_id)s,
        %(trade_date)s, %(title)s, %(uri)s, %(content_hash)s,
        %(payload)s::jsonb, %(metadata)s::jsonb
    )
    ON CONFLICT (source_type, source_id)
    DO UPDATE SET
        asset_id = EXCLUDED.asset_id,
        trade_date = EXCLUDED.trade_date,
        title = EXCLUDED.title,
        uri = EXCLUDED.uri,
        content_hash = EXCLUDED.content_hash,
        payload = EXCLUDED.payload,
        metadata = EXCLUDED.metadata
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return evidence_id


def upsert_evidence_link(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    evidence_id = _text(payload.get("evidence_id"))
    target_type = _text(payload.get("target_type"))
    target_id = _text(payload.get("target_id"))
    relation = _text(payload.get("relation") or "supports")
    link_id = _text(payload.get("link_id") or stable_id("evidence_link", evidence_id, target_type, target_id, relation))
    params = {
        "link_id": link_id,
        "evidence_id": evidence_id,
        "target_type": target_type,
        "target_id": target_id,
        "relation": relation,
        "metadata": _json(payload.get("metadata") or {}),
    }
    sql = """
    INSERT INTO research.evidence_link (
        link_id, evidence_id, target_type, target_id, relation, metadata
    )
    VALUES (
        %(link_id)s, %(evidence_id)s, %(target_type)s, %(target_id)s,
        %(relation)s, %(metadata)s::jsonb
    )
    ON CONFLICT (evidence_id, target_type, target_id, relation)
    DO UPDATE SET
        metadata = EXCLUDED.metadata
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return link_id


def mirror_operator_decision_to_research_snapshot(
    decision: dict[str, Any],
    *,
    service: str = SETTINGS.research_service,
    cursor: Any | None = None,
) -> str:
    event_id = _text(decision.get("event_id") or decision.get("decision_event_id"))
    snapshot_id = _text(decision.get("decision_snapshot_id") or f"decision_snapshot:{event_id}")
    params = {
        "decision_snapshot_id": snapshot_id,
        "decision_event_id": event_id,
        "case_id": _optional_text(decision.get("case_id")),
        "asset_id": _text(decision.get("asset_id")),
        "decision_label": _text(decision.get("decision_label")),
        "decision_status": _text(decision.get("decision_status") or "open"),
        "payload": _json(decision),
    }
    sql = """
    INSERT INTO research.decision_snapshot (
        decision_snapshot_id, decision_event_id, case_id, asset_id,
        decision_label, decision_status, payload
    )
    VALUES (
        %(decision_snapshot_id)s, %(decision_event_id)s, %(case_id)s,
        %(asset_id)s, %(decision_label)s, %(decision_status)s,
        %(payload)s::jsonb
    )
    ON CONFLICT (decision_snapshot_id)
    DO UPDATE SET
        case_id = EXCLUDED.case_id,
        decision_status = EXCLUDED.decision_status,
        payload = EXCLUDED.payload
    """
    if cursor is not None:
        cursor.execute(sql, params)
        return snapshot_id
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return snapshot_id


def upsert_publication_snapshot(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    snapshot_id = _text(
        payload.get("publication_snapshot_id")
        or stable_id("publication_snapshot", payload.get("trade_date"), payload.get("channel"), payload.get("title"), payload.get("payload"))
    )
    params = {
        "publication_snapshot_id": snapshot_id,
        "trade_date": _optional_date(payload.get("trade_date")),
        "channel": _text(payload.get("channel")),
        "title": _text(payload.get("title")),
        "payload": _json(payload.get("payload") or {}),
        "created_by": _text(payload.get("created_by") or "system"),
    }
    sql = """
    INSERT INTO research.publication_snapshot (
        publication_snapshot_id, trade_date, channel, title, payload, created_by
    )
    VALUES (
        %(publication_snapshot_id)s, %(trade_date)s, %(channel)s,
        %(title)s, %(payload)s::jsonb, %(created_by)s
    )
    ON CONFLICT (publication_snapshot_id)
    DO UPDATE SET
        title = EXCLUDED.title,
        payload = EXCLUDED.payload
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return snapshot_id


def record_publication_snapshot(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    channel = _text(payload.get("channel"))
    snapshot_id = _text(
        payload.get("publication_snapshot_id")
        or stable_id(
            f"publication_snapshot:{channel or 'unknown'}",
            payload.get("channel"),
            payload.get("trade_date"),
            payload.get("payload"),
            payload.get("created_by"),
        )
    )
    params = {
        "publication_snapshot_id": snapshot_id,
        "trade_date": _optional_date(payload.get("trade_date")),
        "channel": channel,
        "title": _text(payload.get("title")),
        "payload": _json(payload.get("payload") or {}),
        "created_by": _text(payload.get("created_by") or "system"),
    }
    sql = """
    INSERT INTO research.publication_snapshot (
        publication_snapshot_id, trade_date, channel, title, payload, created_by
    )
    VALUES (
        %(publication_snapshot_id)s, %(trade_date)s, %(channel)s,
        %(title)s, %(payload)s::jsonb, %(created_by)s
    )
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return snapshot_id


def record_agent_run(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    workflow = _text(payload.get("workflow"))
    if not workflow:
        raise ValueError("workflow_required")
    agent_run_id = _text(
        payload.get("agent_run_id")
        or stable_id(
            "agent_run",
            workflow,
            payload.get("request_id"),
            payload.get("trade_date"),
            payload.get("asset_id"),
            payload.get("input_payload"),
        )
    )
    run_params = {
        "agent_run_id": agent_run_id,
        "workflow": workflow,
        "status": _text(payload.get("status") or "created"),
        "request_id": _text(payload.get("request_id")),
        "trade_date": _optional_date(payload.get("trade_date")),
        "asset_id": _optional_text(payload.get("asset_id")),
        "case_id": _optional_text(payload.get("case_id")),
        "input_payload": _json(payload.get("input_payload") or {}),
        "output_payload": _json(payload.get("output_payload") or {}),
        "metadata": _json(payload.get("metadata") or {}),
    }
    run_sql = """
    INSERT INTO research.agent_run (
        agent_run_id, workflow, status, request_id, trade_date,
        asset_id, case_id, input_payload, output_payload, metadata
    )
    VALUES (
        %(agent_run_id)s, %(workflow)s, %(status)s, %(request_id)s,
        %(trade_date)s, %(asset_id)s, %(case_id)s, %(input_payload)s::jsonb,
        %(output_payload)s::jsonb, %(metadata)s::jsonb
    )
    ON CONFLICT (agent_run_id)
    DO UPDATE SET
        status = EXCLUDED.status,
        output_payload = EXCLUDED.output_payload,
        metadata = EXCLUDED.metadata
    """
    event_sql = """
    INSERT INTO research.agent_run_event (
        event_id, agent_run_id, event_index, event_type, status, payload
    )
    VALUES (
        %(event_id)s, %(agent_run_id)s, %(event_index)s, %(event_type)s,
        %(status)s, %(payload)s::jsonb
    )
    ON CONFLICT (agent_run_id, event_index)
    DO UPDATE SET
        event_type = EXCLUDED.event_type,
        status = EXCLUDED.status,
        payload = EXCLUDED.payload
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(run_sql, run_params)
            for index, event in enumerate(payload.get("events") or []):
                cur.execute(
                    event_sql,
                    {
                        "event_id": stable_id("agent_run_event", agent_run_id, index),
                        "agent_run_id": agent_run_id,
                        "event_index": index,
                        "event_type": _text(event.get("event_type")),
                        "status": _text(event.get("status") or "ok"),
                        "payload": _json(event.get("payload") or {}),
                    },
                )
    return agent_run_id


def _canonical_part(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value or "")


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _optional_date(value: Any) -> str | None:
    text = str(value or "").strip()
    return text[:10] if text else None


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _text(value: Any) -> str:
    return str(value or "").strip()
