# Platform Hardening From Expert Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert `/Users/xiwei/Downloads/deep-research-report.md` into an executable first-wave hardening program for security, readiness governance, read models, observability, CI gates, and operator decision quality.

**Architecture:** Keep the existing PostgreSQL + FastAPI + React canonical frontend architecture. Add guardrails at existing seams instead of rewriting the platform: readiness policy around `ops.daily_pipeline_status` and `ops.data_run_manifest`, read models around heavy dashboard paths, endpoint-local API guardrails around write/admin endpoints, and CI/observability around current test/build commands.

**Tech Stack:** Python 3.11, FastAPI, psycopg/PostgreSQL, pytest, React 19, Vite, Vitest, Playwright, GitHub Actions, optional OpenTelemetry/Prometheus/Sentry follow-up.

---

## Source Inputs

- Expert report: `/Users/xiwei/Downloads/deep-research-report.md`
- Current platform inventory: `docs/stock_research_platform_inventory_2026-07-06.md`
- Readiness code: `src/stock_research/dashboard/readiness.py`, `src/stock_research/dashboard/ops_snapshot.py`, `src/stock_research/platform_ready.py`
- Dashboard app/API: `src/stock_research/dashboard/app.py`
- Platform summary: `src/stock_research/dashboard/platform.py`
- Operator decisions: `src/stock_research/dashboard/decisions.py`, `src/stock_research/operator_decision/`
- Data manifest: `src/stock_research/data_run_manifest.py`
- Strategy EOD status: `src/stock_research/strategy_daily_eod_store.py`, `src/stock_research/strategy_eod_publish.py`
- Frontend API and shell: `dashboard/src/api/client.ts`, `dashboard/src/components/AppShell.tsx`
- Existing tests: `tests/test_dashboard_ops_snapshot.py`, `tests/test_dashboard_app.py`, `tests/test_dashboard_readiness.py`, `tests/test_strategy_daily_eod.py`, `dashboard/tests/client.test.ts`, `dashboard/tests/app-shell.test.tsx`

## Scope Boundary

This is a first-wave engineering hardening plan, not a new strategy plan.

In scope:

- Define degraded-readiness blocking policy.
- Add first stable read-model path for dashboard summary and strategy review surfaces.
- Add endpoint-local guardrails for write/admin/replay APIs.
- Make operator decisions more structured and evidence-linked.
- Add CI gates for backend focused tests, dashboard Vitest, dashboard build, and Playwright smoke.
- Add minimal observability hooks and runbook.

Out of scope for this plan:

- Real broker integration.
- Automated trading.
- Shadow-to-production promotion implementation.
- Full i18n migration.
- Full container/Kubernetes/Argo CD migration.
- Full OpenTelemetry/Sentry rollout across every module.

## File Structure

New files:

- `.github/workflows/platform-smoke.yml` - first CI gate for backend and dashboard smoke.
- `docs/ops/platform-hardening-runbook.md` - operating runbook for readiness, API guardrails, read models, and CI response.
- `src/stock_research/dashboard/readiness_policy.py` - centralized degraded-readiness policy.
- `src/stock_research/dashboard/api_guardrails.py` - endpoint-local request guard helpers for write/admin/replay surfaces.
- `src/stock_research/dashboard/read_models.py` - stable dashboard read-model loaders.
- `tests/test_dashboard_readiness_policy.py` - unit tests for degraded-readiness policy.
- `tests/test_dashboard_api_guardrails.py` - unit tests for API guard helpers.
- `tests/test_dashboard_read_models.py` - unit tests for read-model fallback and shape.

Modify files:

- `src/stock_research/dashboard/readiness.py` - call centralized readiness policy.
- `src/stock_research/dashboard/ops_snapshot.py` - align ops/public readiness semantics with policy.
- `src/stock_research/platform_ready.py` - align CLI readiness semantics with policy.
- `src/stock_research/dashboard/app.py` - apply API guard helpers to write/admin/replay endpoints.
- `src/stock_research/dashboard/platform.py` - use read-model loader instead of repeating heavy base-table summary queries.
- `src/stock_research/dashboard/decisions.py` - validate structured operator decision fields and evidence linkage.
- `dashboard/src/api/types.ts` - add types for readiness policy and operator decision validation errors.
- `dashboard/src/api/client.ts` - preserve existing endpoint paths while accepting stricter response shapes.
- `dashboard/tests/client.test.ts` - cover guarded write endpoints and new error shapes.
- `dashboard/tests/app-shell.test.tsx` - verify degraded readiness is visible and not presented as clean ready.

## Task 1: Centralize Readiness Policy

**Files:**

- Create: `src/stock_research/dashboard/readiness_policy.py`
- Modify: `src/stock_research/dashboard/readiness.py`
- Modify: `src/stock_research/dashboard/ops_snapshot.py`
- Modify: `src/stock_research/platform_ready.py`
- Test: `tests/test_dashboard_readiness_policy.py`
- Existing regression tests: `tests/test_dashboard_ops_snapshot.py`, `tests/test_dashboard_readiness.py`, `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write the failing readiness policy tests**

Create `tests/test_dashboard_readiness_policy.py`:

```python
from stock_research.dashboard.readiness_policy import (
    ReadinessDecision,
    classify_pipeline_readiness,
)


def test_ready_status_allows_dashboard_and_publication():
    decision = classify_pipeline_readiness(
        {
            "pipeline_status": "READY",
            "daily_status": "success",
            "minute5_status": "success",
            "deps_status": "success",
            "market_monitor_status": "success",
            "latest_ready_trade_date": "2026-07-03",
        },
        requested_trade_date="2026-07-03",
    )

    assert decision == ReadinessDecision(
        status="ready",
        ready_for_dashboard=True,
        ready_for_publication=True,
        blocking_reasons=[],
        warnings=[],
    )


def test_degraded_ready_allows_dashboard_but_blocks_publication_when_daily_partial():
    decision = classify_pipeline_readiness(
        {
            "pipeline_status": "DEGRADED_READY",
            "daily_status": "partial_success",
            "minute5_status": "success",
            "deps_status": "success",
            "market_monitor_status": "success",
            "latest_ready_trade_date": "2026-07-03",
        },
        requested_trade_date="2026-07-03",
    )

    assert decision.status == "degraded_ready"
    assert decision.ready_for_dashboard is True
    assert decision.ready_for_publication is False
    assert decision.blocking_reasons == ["daily_status=partial_success"]
    assert decision.warnings == ["pipeline_status=DEGRADED_READY"]


def test_mismatched_latest_ready_date_blocks_dashboard_and_publication():
    decision = classify_pipeline_readiness(
        {
            "pipeline_status": "READY",
            "daily_status": "success",
            "minute5_status": "success",
            "deps_status": "success",
            "market_monitor_status": "success",
            "latest_ready_trade_date": "2026-07-02",
        },
        requested_trade_date="2026-07-03",
    )

    assert decision.status == "blocked"
    assert decision.ready_for_dashboard is False
    assert decision.ready_for_publication is False
    assert decision.blocking_reasons == ["latest_ready_trade_date=2026-07-02"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_readiness_policy.py -q
```

Expected before implementation: import failure for `stock_research.dashboard.readiness_policy`.

- [ ] **Step 3: Implement `readiness_policy.py`**

Create `src/stock_research/dashboard/readiness_policy.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReadinessDecision:
    status: str
    ready_for_dashboard: bool
    ready_for_publication: bool
    blocking_reasons: list[str]
    warnings: list[str]


def classify_pipeline_readiness(
    row: dict[str, Any],
    *,
    requested_trade_date: str,
) -> ReadinessDecision:
    pipeline_status = str(row.get("pipeline_status") or "")
    latest_ready_trade_date = str(row.get("latest_ready_trade_date") or "")[:10]
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    if latest_ready_trade_date != requested_trade_date:
        blocking_reasons.append(f"latest_ready_trade_date={latest_ready_trade_date or 'missing'}")

    if pipeline_status == "DEGRADED_READY":
        warnings.append("pipeline_status=DEGRADED_READY")
        for key in ("daily_status", "minute5_status", "deps_status", "market_monitor_status"):
            value = str(row.get(key) or "")
            if value not in {"success", "skipped_optional"}:
                blocking_reasons.append(f"{key}={value or 'missing'}")
    elif pipeline_status == "READY":
        for key in ("daily_status", "minute5_status", "deps_status", "market_monitor_status"):
            value = str(row.get(key) or "")
            if value and value not in {"success", "skipped_optional"}:
                warnings.append(f"{key}={value}")
    else:
        blocking_reasons.append(f"pipeline_status={pipeline_status or 'missing'}")

    ready_for_dashboard = not blocking_reasons and pipeline_status in {"READY", "DEGRADED_READY"}
    ready_for_publication = pipeline_status == "READY" and not blocking_reasons
    status = "blocked" if blocking_reasons else ("degraded_ready" if pipeline_status == "DEGRADED_READY" else "ready")
    return ReadinessDecision(
        status=status,
        ready_for_dashboard=ready_for_dashboard,
        ready_for_publication=ready_for_publication,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
    )
```

- [ ] **Step 4: Wire policy into existing readiness surfaces**

Modify `src/stock_research/dashboard/ops_snapshot.py` inside `_build_readiness(...)` to call `classify_pipeline_readiness(...)` using the latest `ops.daily_pipeline_status` context already loaded there. Preserve existing response keys, but set:

- `ready_status = decision.status`
- `ready_for_dashboard = decision.ready_for_dashboard`
- `ready_for_publication = decision.ready_for_publication`
- `blocking_issue_count = len(decision.blocking_reasons)`
- append `decision.blocking_reasons` and `decision.warnings` to existing issue lists.

Modify `src/stock_research/dashboard/readiness.py` so manifest readiness includes a `policy` object:

```python
"policy": {
    "status": decision.status,
    "ready_for_dashboard": decision.ready_for_dashboard,
    "ready_for_publication": decision.ready_for_publication,
    "blocking_reasons": decision.blocking_reasons,
    "warnings": decision.warnings,
}
```

Modify `src/stock_research/platform_ready.py` to stop treating all `DEGRADED_READY` rows as automatically acceptable. Use the same policy helper and only pass publication readiness when `ready_for_publication` is true.

- [ ] **Step 5: Run focused readiness tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_readiness_policy.py tests/test_dashboard_ops_snapshot.py tests/test_dashboard_readiness.py tests/test_eod_auto_repair.py -q
```

Expected: all selected tests pass after updating existing expected values for degraded-ready blocking semantics.

## Task 2: Add Endpoint-Local API Guardrails

**Files:**

- Create: `src/stock_research/dashboard/api_guardrails.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_api_guardrails.py`
- Existing regression tests: `tests/test_dashboard_app.py`, `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write guardrail tests**

Create `tests/test_dashboard_api_guardrails.py`:

```python
import pytest

from stock_research.dashboard.api_guardrails import (
    GuardrailConfig,
    require_guarded_operation,
)


def test_guard_allows_readonly_when_disabled():
    assert require_guarded_operation(
        operation="operator_decision_write",
        headers={},
        config=GuardrailConfig(enabled=False, shared_token=""),
    ) == {"operation": "operator_decision_write", "authenticated": False}


def test_guard_blocks_missing_token_when_enabled():
    with pytest.raises(PermissionError, match="missing_dashboard_write_token"):
        require_guarded_operation(
            operation="operator_decision_write",
            headers={},
            config=GuardrailConfig(enabled=True, shared_token="secret"),
        )


def test_guard_blocks_wrong_token_when_enabled():
    with pytest.raises(PermissionError, match="invalid_dashboard_write_token"):
        require_guarded_operation(
            operation="operator_decision_write",
            headers={"x-dashboard-write-token": "wrong"},
            config=GuardrailConfig(enabled=True, shared_token="secret"),
        )


def test_guard_accepts_correct_token_when_enabled():
    assert require_guarded_operation(
        operation="operator_decision_write",
        headers={"x-dashboard-write-token": "secret"},
        config=GuardrailConfig(enabled=True, shared_token="secret"),
    ) == {"operation": "operator_decision_write", "authenticated": True}
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_api_guardrails.py -q
```

Expected before implementation: import failure for `stock_research.dashboard.api_guardrails`.

- [ ] **Step 3: Implement guard helper**

Create `src/stock_research/dashboard/api_guardrails.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class GuardrailConfig:
    enabled: bool
    shared_token: str


def guardrail_config_from_env() -> GuardrailConfig:
    token = os.environ.get("STOCK_RESEARCH_DASHBOARD_WRITE_TOKEN", "").strip()
    enabled = os.environ.get("STOCK_RESEARCH_DASHBOARD_WRITE_GUARD", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return GuardrailConfig(enabled=enabled, shared_token=token)


def require_guarded_operation(
    *,
    operation: str,
    headers: Mapping[str, str],
    config: GuardrailConfig | None = None,
) -> dict[str, object]:
    selected = config or guardrail_config_from_env()
    if not selected.enabled:
        return {"operation": operation, "authenticated": False}
    token = str(headers.get("x-dashboard-write-token") or headers.get("X-Dashboard-Write-Token") or "")
    if not token:
        raise PermissionError("missing_dashboard_write_token")
    if not selected.shared_token or token != selected.shared_token:
        raise PermissionError("invalid_dashboard_write_token")
    return {"operation": operation, "authenticated": True}
```

- [ ] **Step 4: Wire guard into write/admin/replay endpoints**

Modify `src/stock_research/dashboard/app.py` so these endpoints call `require_guarded_operation(...)` with `request.headers`:

- `POST /api/operator-decisions`
- `PATCH /api/operator-decisions/{event_id}`
- `POST /api/public-news/refresh`
- `POST /api/dashboard/cache/clear`
- `POST /api/backtests/jobs`
- `POST /api/backtests/run`
- `POST /api/backtests/run-fresh`
- `POST /api/backtests/run-replay`

Use FastAPI `Request` and translate `PermissionError` to HTTP 403:

```python
from fastapi import HTTPException, Request
from stock_research.dashboard.api_guardrails import require_guarded_operation


def _require_guard(request: Request, operation: str) -> None:
    try:
        require_guarded_operation(operation=operation, headers=request.headers)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
```

- [ ] **Step 5: Run focused guard/API tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_api_guardrails.py tests/test_dashboard_app.py -q
```

Expected: all selected tests pass. If existing tests call guarded endpoints without enabling `STOCK_RESEARCH_DASHBOARD_WRITE_GUARD`, they should continue passing because the default guard mode is disabled.

## Task 3: Introduce First Dashboard Read Model Loader

**Files:**

- Create: `src/stock_research/dashboard/read_models.py`
- Modify: `src/stock_research/dashboard/platform.py`
- Test: `tests/test_dashboard_read_models.py`
- Existing regression tests: `tests/test_dashboard_platform.py`, `tests/test_dashboard_overview.py`, `dashboard/tests/platform-client.test.ts`

- [ ] **Step 1: Write tests for stable read-model shape**

Create `tests/test_dashboard_read_models.py`:

```python
from stock_research.dashboard.read_models import build_platform_summary_read_model


def test_platform_summary_read_model_uses_fallback_when_no_rows(monkeypatch):
    calls = []

    def fake_fetch_all(_conn, sql, params=None):
        calls.append((sql, params))
        if "ops.data_run_manifest" in sql:
            return []
        if "max(trade_date)" in sql and "market_daily_bar" in sql:
            return [{"latest_market_date": "2026-07-03", "market_asset_count": 5190}]
        if "factor.stock_score_daily" in sql and "max(trade_date)" in sql:
            return [{"latest_score_date": "2026-07-03", "score_asset_count": 5190}]
        if "factor.factor_daily" in sql:
            return [{"factor_count": 2, "latest_factor_date": "2026-07-03"}]
        if "market.industry_daily_bar" in sql:
            return [{"latest_market_monitor_date": "2026-07-03"}]
        if "SELECT DISTINCT score_version" in sql:
            return [{"score_version": "manual_v1"}]
        if "ORDER BY rank" in sql:
            return [
                {
                    "trade_date": "2026-07-03",
                    "asset_id": "000001.SZ",
                    "rank": 1,
                    "score_total": 99.0,
                    "score_version": "manual_v1",
                    "score_components": {},
                }
            ]
        return []

    monkeypatch.setattr("stock_research.dashboard.read_models.fetch_all", fake_fetch_all)
    monkeypatch.setattr("stock_research.dashboard.read_models.connect", lambda _service: _Context())

    payload = build_platform_summary_read_model(score_version="manual_v1", top_n=5, service="research")

    assert payload["latest_market_date"] == "2026-07-03"
    assert payload["score_versions"] == ["manual_v1"]
    assert payload["topn_preview"][0]["asset_id"] == "000001.SZ"
    assert payload["source"] == "base_table_fallback"


class _Context:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_read_models.py -q
```

Expected before implementation: import failure for `stock_research.dashboard.read_models`.

- [ ] **Step 3: Implement read-model loader**

Create `src/stock_research/dashboard/read_models.py` by moving the current `load_platform_summary(...)` query logic from `platform.py` into `build_platform_summary_read_model(...)`, preserving output keys and adding `"source": "base_table_fallback"`.

Then modify `src/stock_research/dashboard/platform.py`:

```python
from typing import Any

from stock_research.config import SETTINGS
from stock_research.dashboard.read_models import build_platform_summary_read_model


def load_platform_summary(
    score_version: str = "manual_v1",
    top_n: int = 5,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    return build_platform_summary_read_model(
        score_version=score_version,
        top_n=top_n,
        service=service,
    )
```

- [ ] **Step 4: Add documented future materialized-view path**

In `src/stock_research/dashboard/read_models.py`, add a private function `_load_materialized_platform_summary(...)` that returns `None` when `ops.dashboard_platform_summary_daily` does not exist. Do not create the materialized table in this task. This keeps the first change behavior-preserving while creating the extension point.

- [ ] **Step 5: Run focused read-model tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_read_models.py tests/test_dashboard_platform.py tests/test_dashboard_overview.py -q
```

Expected: all selected tests pass, and platform summary response shape remains compatible.

## Task 4: Strengthen Operator Decision Payloads

**Files:**

- Modify: `src/stock_research/dashboard/decisions.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_operator_decisions.py` or existing nearest test file if present.
- Frontend tests: `dashboard/tests/operator-decision-panel.test.tsx`, `dashboard/tests/client.test.ts`

- [ ] **Step 1: Add tests for structured decision requirements**

Add a backend test that posting a new operator decision requires:

- `asset_id`
- `decision_label`
- `evidence_artifact_id` or `source_context.evidence_digest_snapshot_id`
- `manual_review_required=true`
- `auto_trade_enabled=false`

Expected invalid payload response: HTTP 400 with detail `operator_decision_missing_evidence_linkage`.

- [ ] **Step 2: Implement validator**

In `src/stock_research/dashboard/decisions.py`, add:

```python
REQUIRED_DECISION_FIELDS = {"asset_id", "decision_label"}


def validate_operator_decision_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("invalid_payload")
    missing = sorted(field for field in REQUIRED_DECISION_FIELDS if not str(payload.get(field) or "").strip())
    if missing:
        raise ValueError(f"operator_decision_missing_fields:{','.join(missing)}")
    source_context = payload.get("source_context") if isinstance(payload.get("source_context"), dict) else {}
    has_evidence = bool(
        str(payload.get("evidence_artifact_id") or "").strip()
        or str(source_context.get("evidence_digest_snapshot_id") or "").strip()
        or str(source_context.get("review_item_snapshot_id") or "").strip()
    )
    if not has_evidence:
        raise ValueError("operator_decision_missing_evidence_linkage")
    if payload.get("auto_trade_enabled") is True:
        raise ValueError("operator_decision_auto_trade_forbidden")
    payload["manual_review_required"] = True
    payload["auto_trade_enabled"] = False
    return payload
```

- [ ] **Step 3: Wire validator before DB insert**

Find the existing `POST /api/operator-decisions` path in `src/stock_research/dashboard/app.py` and call `validate_operator_decision_payload(payload)` before writing. Return HTTP 400 on `ValueError`.

- [ ] **Step 4: Update frontend error handling test**

In `dashboard/tests/operator-decision-panel.test.tsx`, add a test that a 400 response with `operator_decision_missing_evidence_linkage` is shown in the panel as a local validation error and does not clear the currently loaded stock evidence.

- [ ] **Step 5: Run focused decision tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_app.py tests/test_operator_decision_outcome_analytics.py -q
cd dashboard && rtk pnpm test -- --run tests/operator-decision-panel.test.tsx tests/client.test.ts
```

Expected: backend and frontend focused tests pass.

## Task 5: Add CI Smoke Gate

**Files:**

- Create: `.github/workflows/platform-smoke.yml`
- Modify: `docs/ops/platform-hardening-runbook.md`

- [ ] **Step 1: Create workflow file**

Create `.github/workflows/platform-smoke.yml`:

```yaml
name: Platform Smoke

on:
  pull_request:
  push:
    branches:
      - factor-scoring-daily-pipeline

jobs:
  backend-focused:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install backend dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e ".[dev,dashboard]"
      - name: Run focused backend smoke
        run: |
          pytest tests/test_dashboard_app.py tests/test_dashboard_ops_snapshot.py tests/test_strategy_daily_eod.py tests/test_schema.py -q

  dashboard-focused:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: dashboard
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with:
          version: 10.33.0
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
          cache: pnpm
          cache-dependency-path: dashboard/pnpm-lock.yaml
      - name: Install dashboard dependencies
        run: pnpm install --frozen-lockfile
      - name: Run dashboard unit smoke
        run: pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
      - name: Build dashboard
        run: pnpm build
```

- [ ] **Step 2: Document local equivalent commands**

Create `docs/ops/platform-hardening-runbook.md` with these commands:

```bash
rtk .venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_ops_snapshot.py tests/test_strategy_daily_eod.py tests/test_schema.py -q
cd dashboard && rtk pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
cd dashboard && rtk pnpm build
```

Also document that Playwright smoke remains a local/pre-release gate until CI browser dependencies are explicitly enabled.

- [ ] **Step 3: Run local smoke commands**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_app.py tests/test_dashboard_ops_snapshot.py tests/test_strategy_daily_eod.py tests/test_schema.py -q
cd dashboard && rtk pnpm test -- --run tests/client.test.ts tests/app-shell.test.tsx
cd dashboard && rtk pnpm build
```

Expected: all commands exit 0 before the workflow is considered ready to merge.

## Task 6: Observability Minimal Baseline

**Files:**

- Create: `src/stock_research/dashboard/observability.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_observability.py`
- Docs: `docs/ops/platform-hardening-runbook.md`

- [ ] **Step 1: Add tests for request ID middleware**

Create `tests/test_dashboard_observability.py`:

```python
from fastapi.testclient import TestClient

from stock_research.dashboard.app import create_app


def test_dashboard_api_adds_request_id_header():
    client = TestClient(create_app())

    response = client.get("/api/platform/summary")

    assert "x-request-id" in response.headers
    assert response.headers["x-request-id"]
```

- [ ] **Step 2: Implement request ID middleware**

Create `src/stock_research/dashboard/observability.py`:

```python
from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request


def install_request_id_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid4().hex
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response
```

Modify `create_app()` in `src/stock_research/dashboard/app.py` to call `install_request_id_middleware(app)` immediately after app construction.

- [ ] **Step 3: Document future observability hooks**

In `docs/ops/platform-hardening-runbook.md`, add a section:

- Request ID is first baseline.
- Prometheus/OpenTelemetry/Sentry are explicitly second-wave integrations.
- Every bug report should include `x-request-id`, API path, trade date, and workspace.

- [ ] **Step 4: Run focused observability test**

Run:

```bash
rtk .venv/bin/pytest tests/test_dashboard_observability.py tests/test_dashboard_app.py -q
```

Expected: all selected tests pass.

## Task 7: Dashboard UX Honesty For Degraded State

**Files:**

- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/components/HomeCockpit.tsx`
- Modify: `dashboard/src/components/DailyReviewLiteWorkspace.tsx`
- Test: `dashboard/tests/home-cockpit.test.tsx`
- Test: `dashboard/tests/daily-review-lite-workspace.test.tsx`

- [ ] **Step 1: Add frontend test for degraded-ready copy**

In `dashboard/tests/home-cockpit.test.tsx`, add a test where `fetchPlatformReadiness()` returns:

```ts
{
  status: 'PARTIAL',
  policy: {
    status: 'degraded_ready',
    ready_for_dashboard: true,
    ready_for_publication: false,
    blocking_reasons: ['daily_status=partial_success'],
    warnings: ['pipeline_status=DEGRADED_READY']
  }
}
```

Expected UI copy:

- `部分可用`
- `不可发布`
- `daily_status=partial_success`

- [ ] **Step 2: Update types and rendering**

Add a `ReadinessPolicy` type in `dashboard/src/api/types.ts` and include it in the platform readiness response type.

Update `HomeCockpit.tsx` to render the policy state without presenting degraded-ready as fully ready.

- [ ] **Step 3: Run focused frontend tests**

Run:

```bash
cd dashboard && rtk pnpm test -- --run tests/home-cockpit.test.tsx tests/daily-review-lite-workspace.test.tsx
```

Expected: focused frontend tests pass.

## Self-Review Checklist

- [ ] Spec coverage: This plan covers the expert report’s first-wave items: readiness, API guards, read models, operator decision structure, CI gates, observability, and degraded-state UX.
- [ ] Scope split: Shadow-to-production promotion, full i18n, full a11y, Argo CD, and full observability are explicitly future plans because they span independent subsystems.
- [ ] Placeholder scan: No step uses unresolved placeholder language.
- [ ] Type consistency: `ReadinessDecision`, `GuardrailConfig`, `classify_pipeline_readiness`, `require_guarded_operation`, and `ReadinessPolicy` are named consistently across tasks.
- [ ] Verification: Each implementation task has focused backend/frontend commands and expected outcomes.

## Execution Order

Recommended order:

1. Task 1: Centralize readiness policy.
2. Task 7: Dashboard UX honesty for degraded state.
3. Task 2: API guardrails.
4. Task 4: Operator decision payloads.
5. Task 3: Dashboard read model loader.
6. Task 6: Observability baseline.
7. Task 5: CI smoke gate.

Reasoning: readiness semantics should be settled before frontend copy and CI gates; guardrails and operator decision structure reduce immediate risk; read models and observability make later performance work safer; CI should be added after focused tests are stable locally.
