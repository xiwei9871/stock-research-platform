# Research Closed Loop Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the second-wave “投研闭环底座” so every opportunity, claim, evidence item, agent run, decision, publication, and later review can be linked and audited.

**Architecture:** Keep the current PostgreSQL + FastAPI + React dashboard architecture. Add a small `research` domain layer with stable tables, store functions, dashboard read APIs, and UI surfaces; do not introduce LangGraph, Phoenix, pgvector, or Qlib as hard dependencies in the first PRs. Third-party agent/RAG/quant tools remain behind future adapters after the internal object model is stable.

**Tech Stack:** Python 3.11+, FastAPI, psycopg/PostgreSQL, pytest, React 19, Vite/Vitest. Future adapter candidates: LangGraph for durable stateful agent workflows, Phoenix for traces/evals, PydanticAI for typed single-step extraction, pgvector for early vector retrieval.

---

## Feasibility Judgment

The suggestion is directionally correct and feasible, but should be staged.

Good recommendations to adopt immediately:

- Create a first-class research lifecycle model.
- Promote evidence linkage from “operator decision validation” into a reusable evidence registry.
- Add internal agent trace tables before adding complex agent orchestration.
- Turn the home/dashboard experience into a research queue rather than only an information cockpit.

Recommendations to defer:

- Do not introduce LangGraph as a required runtime until we have `agent_run` and human-review data. LangGraph is useful for long-running stateful agents with persistence and human-in-the-loop, but it should sit on top of our trace model, not define it.
- Do not introduce Phoenix until traces exist locally. Phoenix is a good next layer for model/tool/retrieval trace inspection and evaluations, but first we need stable IDs and payload capture.
- Do not add Qlib, Neo4j, OpenSearch, or a large RAG framework in the next PR. The first bottleneck is not tool capability; it is missing research objects and evidence reuse.

Primary external references used for tool positioning:

- LangGraph docs describe it as an orchestration runtime for durable execution, streaming, human-in-the-loop, and persistence: `https://docs.langchain.com/oss/python/langgraph/overview`
- Phoenix docs describe tracing, evaluations, prompts, datasets, and experiments for AI applications: `https://arize.com/docs/phoenix`
- PydanticAI docs position it around agents, outputs, tools, model providers, testing, and MCP: `https://ai.pydantic.dev/`
- pgvector provides vector similarity search inside PostgreSQL: `https://github.com/pgvector/pgvector`

## Existing Project Context

Relevant existing assets:

- `src/stock_research/schema.py` already owns many canonical SQL tables and `apply_schema()`.
- `src/stock_research/data_run_manifest.py` models run/module readiness.
- `src/stock_research/review_evidence_snapshots.py` already creates `ops.review_item_snapshot` and `ops.evidence_digest_snapshot`.
- `src/stock_research/operator_decision/*` already has decision, outcome, shadow, replay, follow-up, and analytics read models.
- `src/stock_research/dashboard/app.py` is the FastAPI route host.
- `src/stock_research/dashboard/evidence_digest.py`, `review_queue.py`, `decisions.py`, and `outcomes.py` are the closest dashboard integration points.
- `dashboard/src/components/HomeCockpit.tsx`, `StockWorkspace.tsx`, and API client/types are the primary frontend integration points.

## Scope Split

Immediate PRs:

1. `research_objects_v1`: create the research object model and read APIs.
2. `evidence_registry_v1`: register existing evidence artifacts and expose them consistently.
3. `agent_trace_v1`: create agent run/event trace tables and headers, without adding a full agent framework.

Follow-up PRs:

4. `research_workbench_v1`: add “今日研究工作台” UI using the new read models.
5. `factor_experiment_registry_v1`: structure factor/backtest experiment metadata.
6. `rag_index_v1`: add pgvector-backed document chunk registry after evidence artifacts are stable.

Out of scope for this plan:

- Automated trading.
- Real broker integration.
- Neo4j/OpenSearch knowledge graph.
- Full LangGraph/Phoenix deployment.
- Qlib replacement of the current pipeline.

## Proposed Data Model

Use a new `research` schema for lifecycle objects. Keep `ops.*` for pipeline and operator execution artifacts.

Core tables:

- `research.research_case`: one opportunity or investigation thread.
- `research.research_claim`: a hypothesis, risk, catalyst, or conclusion attached to a case.
- `research.evidence_artifact`: canonical evidence object for reports, news, filings, snapshots, generated reports, backtests, and human notes.
- `research.evidence_link`: many-to-many links from evidence to claims, cases, decisions, publications, and agent runs.
- `research.decision_snapshot`: immutable view of an operator decision at creation time.
- `research.publication_snapshot`: immutable view of what was published and why.
- `research.agent_run`: one AI/automation run.
- `research.agent_run_event`: tool calls, model calls, retrieval calls, human review checkpoints, errors, and outputs.

Identifier convention:

- `research_case:<trade_date>:<asset_or_theme>:<hash>`
- `research_claim:<case_id>:<hash>`
- `evidence_artifact:<source_type>:<source_id_or_hash>`
- `decision_snapshot:<operator_decision_event_id>`
- `publication_snapshot:<trade_date>:<channel>:<hash>`
- `agent_run:<workflow>:<trade_date>:<hash>`

## PR 1: `research_objects_v1`

### Task 1: Add Research Object Schema

**Files:**

- Create: `src/stock_research/research_objects.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_research_objects.py`

- [ ] **Step 1: Write failing schema test**

Create `tests/test_research_objects.py`:

```python
from stock_research import research_objects


def test_research_object_schema_contains_core_tables():
    sql = research_objects.RESEARCH_OBJECTS_SQL

    assert "CREATE SCHEMA IF NOT EXISTS research" in sql
    assert "CREATE TABLE IF NOT EXISTS research.research_case" in sql
    assert "CREATE TABLE IF NOT EXISTS research.research_claim" in sql
    assert "CREATE TABLE IF NOT EXISTS research.evidence_artifact" in sql
    assert "CREATE TABLE IF NOT EXISTS research.evidence_link" in sql
    assert "CREATE TABLE IF NOT EXISTS research.decision_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS research.publication_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS research.agent_run" in sql
    assert "CREATE TABLE IF NOT EXISTS research.agent_run_event" in sql
```

- [ ] **Step 2: Run RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_objects.py -q
```

Expected: import error for `stock_research.research_objects`.

- [ ] **Step 3: Implement schema SQL**

Create `src/stock_research/research_objects.py` with:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


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
"""


def apply_research_object_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(RESEARCH_OBJECTS_SQL)
        conn.commit()


def stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_objects.py -q
```

Expected: pass.

### Task 2: Add Research Object Store Functions

**Files:**

- Modify: `src/stock_research/research_objects.py`
- Test: `tests/test_research_objects.py`

- [ ] **Step 1: Add failing upsert test**

Append to `tests/test_research_objects.py`:

```python
def test_upsert_research_case_writes_expected_sql(monkeypatch):
    captured = []

    class _Cursor:
        def execute(self, sql, params=None):
            captured.append((sql, params))

    class _Conn:
        def cursor(self):
            return self
        def __enter__(self):
            return _Cursor()
        def __exit__(self, exc_type, exc, tb):
            return False
        def commit(self):
            captured.append(("COMMIT", None))

    class _Ctx:
        def __enter__(self):
            return _Conn()
        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx())

    case_id = research_objects.upsert_research_case(
        {
            "trade_date": "2026-07-06",
            "asset_id": "CN:SZ:000001",
            "theme": "bank_reversal",
            "title": "Bank reversal candidate",
            "source_type": "review_queue",
            "source_id": "review:1",
        },
        service="research",
    )

    assert case_id.startswith("research_case:")
    sql, params = captured[0]
    assert "INSERT INTO research.research_case" in sql
    assert params["asset_id"] == "CN:SZ:000001"
    assert params["status"] == "open"
```

- [ ] **Step 2: Run RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_objects.py::test_upsert_research_case_writes_expected_sql -q
```

Expected: `AttributeError: module has no attribute upsert_research_case`.

- [ ] **Step 3: Implement upsert functions**

Add to `src/stock_research/research_objects.py`:

```python
def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def upsert_research_case(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    case_id = str(payload.get("case_id") or stable_id(
        "research_case",
        payload.get("trade_date"),
        payload.get("asset_id"),
        payload.get("theme"),
        payload.get("title"),
    ))
    params = {
        "case_id": case_id,
        "trade_date": payload.get("trade_date"),
        "asset_id": str(payload.get("asset_id") or ""),
        "theme": str(payload.get("theme") or ""),
        "title": str(payload.get("title") or ""),
        "status": str(payload.get("status") or "open"),
        "priority": int(payload.get("priority") or 50),
        "source_type": str(payload.get("source_type") or "manual"),
        "source_id": str(payload.get("source_id") or ""),
        "created_by": str(payload.get("created_by") or "system"),
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
        conn.commit()
    return case_id
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_objects.py -q
```

Expected: pass.

### Task 3: Add Dashboard Read APIs

**Files:**

- Create: `src/stock_research/dashboard/research_cases.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_research_cases.py`

- [ ] **Step 1: Write failing route test**

Create `tests/test_dashboard_research_cases.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_research_cases_route_returns_items(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_research_cases",
        lambda **kwargs: [
            {
                "case_id": "research_case:abc",
                "trade_date": "2026-07-06",
                "asset_id": "CN:SZ:000001",
                "theme": "bank_reversal",
                "title": "Bank reversal candidate",
                "status": "open",
                "priority": 30,
                "evidence_count": 2,
                "claim_count": 1,
            }
        ],
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/cases?trade_date=2026-07-06&status=open")

    assert response.status_code == 200
    assert response.json()["items"][0]["case_id"] == "research_case:abc"
```

- [ ] **Step 2: Run RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_research_cases.py -q
```

Expected: 404 route not found or missing import.

- [ ] **Step 3: Implement list API**

Create `src/stock_research/dashboard/research_cases.py`:

```python
from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def list_research_cases(
    *,
    trade_date: str | None = None,
    status: str | None = None,
    asset_id: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if trade_date:
        clauses.append("c.trade_date = %s")
        params.append(trade_date)
    if status:
        clauses.append("c.status = %s")
        params.append(status)
    if asset_id:
        clauses.append("c.asset_id = %s")
        params.append(asset_id)
    params.append(limit)
    sql = f"""
    SELECT
        c.case_id,
        c.trade_date::text AS trade_date,
        c.asset_id,
        c.theme,
        c.title,
        c.status,
        c.priority,
        COALESCE(claims.claim_count, 0) AS claim_count,
        COALESCE(evidence.evidence_count, 0) AS evidence_count
    FROM research.research_case c
    LEFT JOIN (
        SELECT case_id, count(*) AS claim_count
        FROM research.research_claim
        GROUP BY case_id
    ) claims USING (case_id)
    LEFT JOIN (
        SELECT target_id AS case_id, count(DISTINCT evidence_id) AS evidence_count
        FROM research.evidence_link
        WHERE target_type = 'research_case'
        GROUP BY target_id
    ) evidence ON evidence.case_id = c.case_id
    WHERE {" AND ".join(clauses)}
    ORDER BY c.priority ASC, c.updated_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [dict(row) for row in rows]
```

Modify `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.research_cases import list_research_cases
```

Inside `create_app()`:

```python
    @app.get("/api/research/cases")
    def research_cases(
        trade_date: str | None = None,
        status: str | None = None,
        asset_id: str | None = None,
        limit: int = 50,
    ):
        return {
            "items": list_research_cases(
                trade_date=trade_date,
                status=status,
                asset_id=asset_id,
                limit=limit,
            )
        }
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_research_cases.py tests/test_dashboard_app.py -q
```

Expected: pass.

## PR 2: `evidence_registry_v1`

### Task 4: Register Existing Evidence Snapshots

**Files:**

- Create: `src/stock_research/research_evidence_registry.py`
- Test: `tests/test_research_evidence_registry.py`

- [ ] **Step 1: Write failing mapper test**

Create `tests/test_research_evidence_registry.py`:

```python
from stock_research.research_evidence_registry import evidence_from_digest_snapshot


def test_evidence_from_digest_snapshot_maps_core_fields():
    evidence = evidence_from_digest_snapshot(
        {
            "snapshot_id": "evidence_digest_snapshot:abc",
            "asset_id": "CN:SZ:000001",
            "trade_date": "2026-07-06",
            "digest_key": "2026-07-06:manual_v1:CN:SZ:000001",
            "payload_hash": "hash123",
            "digest_payload": {"title": "Strong evidence", "score": 81},
        }
    )

    assert evidence["evidence_id"] == "evidence_artifact:evidence_digest_snapshot:abc"
    assert evidence["source_type"] == "evidence_digest_snapshot"
    assert evidence["source_id"] == "evidence_digest_snapshot:abc"
    assert evidence["asset_id"] == "CN:SZ:000001"
    assert evidence["title"] == "Strong evidence"
    assert evidence["content_hash"] == "hash123"
```

- [ ] **Step 2: Run RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_evidence_registry.py -q
```

Expected: import error.

- [ ] **Step 3: Implement mapper and upsert**

Create `src/stock_research/research_evidence_registry.py`:

```python
from __future__ import annotations

import json
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect


def evidence_from_digest_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("digest_payload") if isinstance(row.get("digest_payload"), dict) else {}
    snapshot_id = str(row.get("snapshot_id") or "")
    return {
        "evidence_id": f"evidence_artifact:evidence_digest_snapshot:{snapshot_id}",
        "source_type": "evidence_digest_snapshot",
        "source_id": snapshot_id,
        "asset_id": str(row.get("asset_id") or ""),
        "trade_date": str(row.get("trade_date") or ""),
        "title": str(payload.get("title") or payload.get("bucket") or ""),
        "uri": "",
        "content_hash": str(row.get("payload_hash") or ""),
        "payload": payload,
        "metadata": {"digest_key": str(row.get("digest_key") or "")},
    }


def upsert_evidence_artifact(evidence: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
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
    params = {
        **evidence,
        "payload": json.dumps(evidence.get("payload") or {}, ensure_ascii=False, sort_keys=True),
        "metadata": json.dumps(evidence.get("metadata") or {}, ensure_ascii=False, sort_keys=True),
    }
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()
    return str(evidence["evidence_id"])
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_evidence_registry.py -q
```

Expected: pass.

### Task 5: Expose Evidence Registry API

**Files:**

- Create: `src/stock_research/dashboard/evidence_registry.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_evidence_registry.py`

- [ ] **Step 1: Write failing route test**

Create `tests/test_dashboard_evidence_registry.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard import app as dashboard_app


def test_evidence_registry_route_filters_by_asset(monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "list_evidence_artifacts",
        lambda **kwargs: [
            {
                "evidence_id": "evidence_artifact:evidence_digest_snapshot:abc",
                "source_type": "evidence_digest_snapshot",
                "asset_id": "CN:SZ:000001",
                "trade_date": "2026-07-06",
                "title": "Strong evidence",
            }
        ],
    )
    client = TestClient(dashboard_app.create_app())

    response = client.get("/api/research/evidence?asset_id=CN%3ASZ%3A000001")

    assert response.status_code == 200
    assert response.json()["items"][0]["title"] == "Strong evidence"
```

- [ ] **Step 2: Run RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_evidence_registry.py -q
```

Expected: missing route/import.

- [ ] **Step 3: Implement dashboard evidence registry**

Create `src/stock_research/dashboard/evidence_registry.py`:

```python
from __future__ import annotations

from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def list_evidence_artifacts(
    *,
    asset_id: str | None = None,
    source_type: str | None = None,
    limit: int = 50,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if asset_id:
        clauses.append("asset_id = %s")
        params.append(asset_id)
    if source_type:
        clauses.append("source_type = %s")
        params.append(source_type)
    params.append(limit)
    sql = f"""
    SELECT
        evidence_id,
        source_type,
        source_id,
        asset_id,
        trade_date::text AS trade_date,
        title,
        uri,
        content_hash,
        metadata
    FROM research.evidence_artifact
    WHERE {" AND ".join(clauses)}
    ORDER BY trade_date DESC NULLS LAST, created_at DESC
    LIMIT %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, params)
    return [dict(row) for row in rows]
```

Modify `src/stock_research/dashboard/app.py`:

```python
from stock_research.dashboard.evidence_registry import list_evidence_artifacts
```

Inside `create_app()`:

```python
    @app.get("/api/research/evidence")
    def research_evidence(asset_id: str | None = None, source_type: str | None = None, limit: int = 50):
        return {"items": list_evidence_artifacts(asset_id=asset_id, source_type=source_type, limit=limit)}
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_evidence_registry.py tests/test_dashboard_app.py -q
```

Expected: pass.

## PR 3: `agent_trace_v1`

### Task 6: Add Agent Run Store

**Files:**

- Modify: `src/stock_research/research_objects.py`
- Test: `tests/test_research_agent_runs.py`

- [ ] **Step 1: Write failing agent run test**

Create `tests/test_research_agent_runs.py`:

```python
from stock_research import research_objects


def test_record_agent_run_writes_run_and_events(monkeypatch):
    captured = []

    class _Cursor:
        def execute(self, sql, params=None):
            captured.append((sql, params))

    class _Conn:
        def cursor(self):
            return self
        def __enter__(self):
            return _Cursor()
        def __exit__(self, exc_type, exc, tb):
            return False
        def commit(self):
            captured.append(("COMMIT", None))

    class _Ctx:
        def __enter__(self):
            return _Conn()
        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(research_objects, "connect", lambda service: _Ctx())

    run_id = research_objects.record_agent_run(
        {
            "workflow": "daily_brief_draft",
            "request_id": "req-1",
            "trade_date": "2026-07-06",
            "input_payload": {"asset_id": "CN:SZ:000001"},
            "events": [
                {"event_type": "model_call", "status": "ok", "payload": {"model": "test"}},
                {"event_type": "human_review", "status": "pending", "payload": {"reviewer": "operator"}},
            ],
        },
        service="research",
    )

    assert run_id.startswith("agent_run:")
    assert any("INSERT INTO research.agent_run" in sql for sql, _params in captured)
    assert any("INSERT INTO research.agent_run_event" in sql for sql, _params in captured)
```

- [ ] **Step 2: Run RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_agent_runs.py -q
```

Expected: missing `record_agent_run`.

- [ ] **Step 3: Implement agent run recording**

Add to `src/stock_research/research_objects.py`:

```python
def record_agent_run(payload: dict[str, Any], *, service: str = SETTINGS.research_service) -> str:
    workflow = str(payload.get("workflow") or "")
    if not workflow:
        raise ValueError("workflow_required")
    agent_run_id = str(payload.get("agent_run_id") or stable_id(
        "agent_run",
        workflow,
        payload.get("request_id"),
        payload.get("trade_date"),
        payload.get("asset_id"),
        payload.get("input_payload"),
    ))
    run_params = {
        "agent_run_id": agent_run_id,
        "workflow": workflow,
        "status": str(payload.get("status") or "created"),
        "request_id": str(payload.get("request_id") or ""),
        "trade_date": payload.get("trade_date"),
        "asset_id": str(payload.get("asset_id") or ""),
        "case_id": str(payload.get("case_id") or ""),
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
                        "event_type": str(event.get("event_type") or ""),
                        "status": str(event.get("status") or "ok"),
                        "payload": _json(event.get("payload") or {}),
                    },
                )
        conn.commit()
    return agent_run_id
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_research_agent_runs.py tests/test_research_objects.py -q
```

Expected: pass.

### Task 7: Extend API Request Headers

**Files:**

- Modify: `src/stock_research/dashboard/observability.py`
- Test: `tests/test_dashboard_observability.py`

- [ ] **Step 1: Write failing `X-Agent-Run-ID` test**

Create or append to `tests/test_dashboard_observability.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard.app import create_app


def test_dashboard_api_echoes_agent_run_id_header(monkeypatch):
    from stock_research.dashboard import app as dashboard_app

    monkeypatch.setattr(dashboard_app, "load_platform_summary", lambda **kwargs: {"latest_market_date": "2026-07-06"})
    client = TestClient(create_app())

    response = client.get("/api/platform/summary", headers={"X-Agent-Run-ID": "agent_run:test"})

    assert response.status_code == 200
    assert response.headers["x-agent-run-id"] == "agent_run:test"
```

- [ ] **Step 2: Run RED**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_observability.py -q
```

Expected: missing `x-agent-run-id` response header.

- [ ] **Step 3: Implement header echo**

Modify `src/stock_research/dashboard/observability.py`:

```python
def install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request_id = (request.headers.get("x-request-id") or "").strip() or uuid4().hex
        agent_run_id = (request.headers.get("x-agent-run-id") or "").strip()
        request.state.request_id = request_id
        if agent_run_id:
            request.state.agent_run_id = agent_run_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if agent_run_id:
            response.headers["X-Agent-Run-ID"] = agent_run_id
        return response
```

- [ ] **Step 4: Run GREEN**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_observability.py tests/test_dashboard_app.py -q
```

Expected: pass.

## PR 4: `research_workbench_v1`

This PR should start only after PR 1 and PR 2 are merged.

### Task 8: Add Research Workbench API Client Types

**Files:**

- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Test: `dashboard/tests/client.test.ts`

Expected client functions:

- `fetchResearchCases({ tradeDate, status, assetId, limit })`
- `fetchResearchEvidence({ assetId, sourceType, limit })`

### Task 9: Add Home Research Queue Panel

**Files:**

- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Test: `dashboard/tests/home-cockpit.test.tsx`

UI requirements:

- Show “今日研究队列”.
- Show open case count.
- Show evidence gap count.
- Show blocked publication count.
- Show top 5 cases with asset/theme/status/evidence count.
- Do not use cards inside cards.

## PR 5: `factor_experiment_registry_v1`

This PR should start after research objects are stable.

Core tables:

- `research.factor_definition`
- `research.label_definition`
- `research.strategy_experiment`
- `research.strategy_experiment_result`

Minimum fields:

- factor id/name/version/expression/input columns.
- label id/horizon/definition/leakage policy.
- experiment id/strategy id/sample window/cost assumptions.
- result metrics/attribution/failure reason/artifact path.

Do not integrate Qlib yet. Use this registry to describe existing backtests first.

## PR 6: `rag_index_v1`

This PR should start after evidence registry has real data.

Recommended first implementation:

- PostgreSQL tables for document chunks and embeddings.
- Optional pgvector extension behind a feature flag.
- Index evidence artifacts, reports, daily reviews, and operator notes.
- Search API must return source, date, title, summary, score, and freshness warning.

Do not introduce OpenSearch until Postgres-backed search becomes measurably insufficient.

## Tool Adoption Decision Matrix

| Tool | Decision | When to adopt |
| --- | --- | --- |
| LangGraph | Defer as runtime dependency | After `agent_run`/`agent_run_event` exist and we have one multi-step workflow needing resume or human interrupt |
| PydanticAI | Candidate for single-step structured extraction | After evidence registry exists; start with report-claim extraction |
| Phoenix | Candidate for LLM observability | After local trace IDs and events exist; mirror traces to Phoenix, do not replace DB traces |
| pgvector | Candidate for RAG v1 | After evidence registry has enough text artifacts |
| Qlib | Study/reference only | After strategy experiment registry exists |
| Dagster | Later orchestration option | After current cron/watchdog pain is measured against asset lineage needs |
| Neo4j/OpenSearch | P2 only | After claim/evidence/decision data is stable and relational queries are insufficient |

## Verification Commands

Backend focused:

```bash
rtk .venv/bin/pytest tests/test_research_objects.py tests/test_research_evidence_registry.py tests/test_research_agent_runs.py tests/test_dashboard_research_cases.py tests/test_dashboard_evidence_registry.py tests/test_dashboard_observability.py tests/test_dashboard_app.py -q
```

Frontend focused:

```bash
rtk pnpm vitest run tests/client.test.ts tests/home-cockpit.test.tsx
```

Run frontend command with working directory:

```bash
/Users/xiwei/stock_research/dashboard
```

Build:

```bash
rtk pnpm build
```

## Acceptance Criteria

- Every research case can show linked claims and evidence counts.
- Every evidence artifact has stable source type, source id, hash, and optional asset/trade date.
- Operator decisions can be mirrored into `research.decision_snapshot`.
- Agent runs can be recorded without installing LangGraph or Phoenix.
- Dashboard APIs expose read models only; no raw internal payload leaks unless explicitly whitelisted.
- The new UI workbench consumes the APIs without needing to know source table details.

## Self-Review Checklist

- Spec coverage: The plan covers research object model, evidence registry, agent trace baseline, workbench UI, factor experiment registry, and RAG staging.
- Scope control: Heavy external tools are deferred behind adapters and adoption gates.
- Placeholder scan: No task relies on unresolved placeholder wording.
- Type consistency: Table and function names are stable across tasks.
- Verification: Each implementation group has focused backend/frontend commands.
