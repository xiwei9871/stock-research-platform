# EOD Manifest Readiness V2 Batch A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a v0.1 local EOD operational manifest, machine-readable daily summary, and readiness v2 status contract without changing strategy logic or dashboard layout.

**Architecture:** Reuse `ops.daily_job_run` as the legacy coarse step log and add `ops.data_run_manifest` as the normalized readiness source. `daily_data_pipeline.py` writes local `run_manifest.json` and upgraded `run_summary.json`; database writes are available through a small manifest store. `dashboard/readiness.py` consumes the latest summary/manifest when present and falls back to lightweight probes.

**Tech Stack:** Python 3.14, PostgreSQL DDL via existing schema helpers, FastAPI/TestClient, pytest, existing React/Vitest/Playwright smoke only.

---

## File Structure

- Create `src/stock_research/data_run_manifest.py`
  - Manifest dataclass/normalization.
  - DDL for `ops.data_run_manifest`.
  - Upsert/load helpers.
  - Tier/status aggregation helpers.
- Modify `src/stock_research/schema.py`
  - Add `ops.data_run_manifest` DDL to the existing schema path.
- Modify `src/stock_research/daily_data_pipeline.py`
  - Map existing EOD steps to Batch A modules/tiers.
  - Write `run_manifest.json`.
  - Upgrade `run_summary.json` while preserving existing `steps`.
- Modify `src/stock_research/dashboard/readiness.py`
  - Add readiness v2 response fields.
  - Prefer latest daily summary/manifest.
  - Preserve compatibility fields `mode`, `latest_market_date`, `checks`, and `warnings`.
- Modify `tests/test_schema.py`
  - Assert schema contains `ops.data_run_manifest`.
- Create `tests/test_data_run_manifest.py`
  - Cover manifest DDL/store/aggregation.
- Modify `tests/test_daily_data_pipeline.py`
  - Cover v2 summary shape and manifest module statuses.
- Modify `tests/test_dashboard_readiness.py`
  - Cover `OK`, `PARTIAL`, `BLOCKED`, TopN missing, Tier 2 partial, and response shape.
- Modify `docs/dashboard-local-runbook.md`
  - Add smoke command only if needed; avoid broader runbook rewrite.

Do not modify HomeCockpit layout, strategy catalog logic, backtest logic, or experimental modules in this batch.

---

## Task 1: Manifest Schema And Store

**Files:**
- Create: `src/stock_research/data_run_manifest.py`
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`
- Create: `tests/test_data_run_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

Add `tests/test_data_run_manifest.py`:

```python
from datetime import datetime

from stock_research import data_run_manifest as manifest


class _Cursor:
    def __init__(self):
        self.calls = []
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.cursor_obj = _Cursor()

    def cursor(self):
        return self.cursor_obj


class _Context:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        return False


def test_apply_data_run_manifest_schema_creates_ops_table(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(manifest, "connect", lambda service: _Context(conn))

    manifest.apply_data_run_manifest_schema()

    sql = conn.cursor_obj.calls[0][0]
    assert "CREATE TABLE IF NOT EXISTS ops.data_run_manifest" in sql
    assert "tier text NOT NULL" in sql
    assert "status text NOT NULL" in sql


def test_manifest_entry_normalizes_status_and_counts():
    entry = manifest.build_manifest_entry(
        run_id="eod-2026-06-12-local",
        run_date="2026-06-15",
        trade_date="2026-06-12",
        module="daily_bars",
        source="run-daily-incremental",
        tier="tier1",
        status="success",
        row_count=5200,
        warnings=["thin coverage"],
        artifact_path="outputs/daily/logs/daily_bars.log",
    )

    assert entry["manifest_id"].startswith("eod-2026-06-12-local:daily_bars:")
    assert entry["warning_count"] == 1
    assert entry["warnings"] == ["thin coverage"]
    assert entry["row_count"] == 5200


def test_upsert_data_run_manifest_writes_json_metadata(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(manifest, "connect", lambda service: _Context(conn))

    entry = manifest.build_manifest_entry(
        run_id="eod-2026-06-12-local",
        run_date="2026-06-15",
        trade_date="2026-06-12",
        module="news",
        source="public_news",
        tier="tier2",
        status="partial",
        warnings=["news partial"],
        metadata={"items": 3},
    )
    manifest.upsert_data_run_manifest(entry)

    sql, params = conn.cursor_obj.calls[0]
    assert "INSERT INTO ops.data_run_manifest" in sql
    assert params["run_id"] == "eod-2026-06-12-local"
    assert params["module"] == "news"
    assert params["tier"] == "tier2"
    assert params["status"] == "partial"
    assert '"items": 3' in params["metadata"]


def test_summarize_manifest_modules_blocks_on_tier1_failure():
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "failed", "warnings": [], "error_message": "no scores"},
        {"module": "news", "tier": "tier2", "status": "failed", "warnings": ["news down"], "error_message": "down"},
    ]

    summary = manifest.summarize_manifest_modules(modules)

    assert summary["status"] == "BLOCKED"
    assert summary["tier1_status"] == "BLOCKED"
    assert summary["tier2_status"] == "PARTIAL"
    assert "score_topn" in summary["missing_data"]
    assert "news down" in summary["warnings"]


def test_summarize_manifest_modules_marks_tier2_failure_partial():
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_queue", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "news", "tier": "tier2", "status": "failed", "warnings": ["news down"], "error_message": "down"},
    ]

    summary = manifest.summarize_manifest_modules(modules)

    assert summary["status"] == "PARTIAL"
    assert summary["tier1_status"] == "OK"
    assert summary["tier2_status"] == "PARTIAL"
    assert "news" in summary["partial_data"]
```

Add to `tests/test_schema.py`:

```python
def test_schema_declares_data_run_manifest_table():
    from stock_research import schema

    assert "CREATE TABLE IF NOT EXISTS ops.data_run_manifest" in schema.CREATE_TABLES_SQL
    assert "idx_data_run_manifest_run" in schema.CREATE_TABLES_SQL
```

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_data_run_manifest.py tests/test_schema.py -k 'data_run_manifest' -q
```

Expected: fail because `stock_research.data_run_manifest` and schema DDL do not exist.

- [ ] **Step 3: Implement manifest store**

Create `src/stock_research/data_run_manifest.py` with:

```python
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

VALID_TIERS = {"tier1", "tier2", "tier3"}
VALID_STATUSES = {"success", "partial", "skipped", "failed", "unavailable"}
BLOCKING_STATUSES = {"failed", "unavailable"}
PARTIAL_STATUSES = {"partial", "failed", "unavailable"}

CREATE_DATA_RUN_MANIFEST_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.data_run_manifest (
    manifest_id text PRIMARY KEY,
    run_id text NOT NULL,
    run_date date NOT NULL,
    trade_date date,
    module text NOT NULL,
    source text NOT NULL,
    tier text NOT NULL CHECK (tier IN ('tier1', 'tier2', 'tier3')),
    status text NOT NULL CHECK (status IN ('success', 'partial', 'skipped', 'failed', 'unavailable')),
    started_at timestamptz,
    ended_at timestamptz,
    duration_seconds numeric,
    row_count bigint,
    asset_count bigint,
    coverage_ratio numeric,
    latest_trade_date date,
    freshness_lag integer,
    warning_count integer NOT NULL DEFAULT 0,
    warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
    error_message text,
    artifact_path text,
    code_version text,
    config_version text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_data_run_manifest_run
    ON ops.data_run_manifest (run_id, tier, module);

CREATE INDEX IF NOT EXISTS idx_data_run_manifest_trade_date
    ON ops.data_run_manifest (trade_date DESC, tier, status);
"""


def apply_data_run_manifest_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_DATA_RUN_MANIFEST_SQL)


def build_manifest_entry(
    *,
    run_id: str,
    run_date: object,
    trade_date: object | None,
    module: str,
    source: str,
    tier: str,
    status: str,
    started_at: object | None = None,
    ended_at: object | None = None,
    duration_seconds: float | None = None,
    row_count: int | None = None,
    asset_count: int | None = None,
    coverage_ratio: float | None = None,
    latest_trade_date: object | None = None,
    freshness_lag: int | None = None,
    warnings: list[str] | None = None,
    error_message: str | None = None,
    artifact_path: str | Path | None = None,
    code_version: str | None = None,
    config_version: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_tier = _validate(tier, VALID_TIERS, "tier")
    normalized_status = _validate(status, VALID_STATUSES, "status")
    normalized_warnings = [str(warning) for warning in (warnings or []) if str(warning)]
    entry = {
        "manifest_id": _manifest_id(run_id, module, source),
        "run_id": str(run_id),
        "run_date": _date_text(run_date),
        "trade_date": _optional_date_text(trade_date),
        "module": str(module),
        "source": str(source),
        "tier": normalized_tier,
        "status": normalized_status,
        "started_at": _optional_datetime_text(started_at),
        "ended_at": _optional_datetime_text(ended_at),
        "duration_seconds": duration_seconds,
        "row_count": row_count,
        "asset_count": asset_count,
        "coverage_ratio": coverage_ratio,
        "latest_trade_date": _optional_date_text(latest_trade_date),
        "freshness_lag": freshness_lag,
        "warning_count": len(normalized_warnings),
        "warnings": normalized_warnings,
        "error_message": error_message or "",
        "artifact_path": str(artifact_path) if artifact_path else "",
        "code_version": code_version or "",
        "config_version": config_version or "",
        "metadata": _jsonable(metadata or {}),
    }
    return entry


def upsert_data_run_manifest(entry: dict[str, Any], service: str = SETTINGS.research_service) -> str:
    params = _db_params(entry)
    sql = """
    INSERT INTO ops.data_run_manifest (
        manifest_id, run_id, run_date, trade_date, module, source, tier, status,
        started_at, ended_at, duration_seconds, row_count, asset_count,
        coverage_ratio, latest_trade_date, freshness_lag, warning_count,
        warnings, error_message, artifact_path, code_version, config_version,
        metadata
    )
    VALUES (
        %(manifest_id)s, %(run_id)s, %(run_date)s, %(trade_date)s, %(module)s,
        %(source)s, %(tier)s, %(status)s, %(started_at)s, %(ended_at)s,
        %(duration_seconds)s, %(row_count)s, %(asset_count)s,
        %(coverage_ratio)s, %(latest_trade_date)s, %(freshness_lag)s,
        %(warning_count)s, %(warnings)s::jsonb, %(error_message)s,
        %(artifact_path)s, %(code_version)s, %(config_version)s, %(metadata)s::jsonb
    )
    ON CONFLICT (manifest_id)
    DO UPDATE SET
        status = EXCLUDED.status,
        ended_at = EXCLUDED.ended_at,
        duration_seconds = EXCLUDED.duration_seconds,
        row_count = EXCLUDED.row_count,
        asset_count = EXCLUDED.asset_count,
        coverage_ratio = EXCLUDED.coverage_ratio,
        latest_trade_date = EXCLUDED.latest_trade_date,
        freshness_lag = EXCLUDED.freshness_lag,
        warning_count = EXCLUDED.warning_count,
        warnings = EXCLUDED.warnings,
        error_message = EXCLUDED.error_message,
        artifact_path = EXCLUDED.artifact_path,
        code_version = EXCLUDED.code_version,
        config_version = EXCLUDED.config_version,
        metadata = EXCLUDED.metadata,
        updated_at = now()
    """
    with connect(service) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
    return str(entry["manifest_id"])


def load_latest_data_run_manifest(
    *,
    trade_date: str | None = None,
    service: str = SETTINGS.research_service,
) -> list[dict[str, Any]]:
    where = "WHERE trade_date = %(trade_date)s" if trade_date else ""
    latest_sql = f"""
    WITH latest AS (
        SELECT run_id
        FROM ops.data_run_manifest
        {where}
        ORDER BY COALESCE(ended_at, created_at) DESC
        LIMIT 1
    )
    SELECT *
    FROM ops.data_run_manifest
    WHERE run_id = (SELECT run_id FROM latest)
    ORDER BY tier, module
    """
    params = {"trade_date": trade_date} if trade_date else None
    with connect(service) as conn:
        return list(fetch_all(conn, latest_sql, params))


def summarize_manifest_modules(modules: list[dict[str, Any]]) -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []
    missing_data: list[str] = []
    partial_data: list[str] = []
    tier_statuses = {"tier1": "OK", "tier2": "OK", "tier3": "OK"}

    for item in modules:
        module = str(item.get("module") or "")
        tier = str(item.get("tier") or "tier3")
        status = str(item.get("status") or "unavailable")
        warnings.extend(str(warning) for warning in item.get("warnings") or [])
        error = str(item.get("error_message") or "")
        if error:
            errors.append(f"{module}: {error}")
        if tier == "tier1" and status in BLOCKING_STATUSES:
            tier_statuses["tier1"] = "BLOCKED"
            missing_data.append(module)
        elif status in PARTIAL_STATUSES:
            partial_data.append(module)
            if tier_statuses.get(tier) != "BLOCKED":
                tier_statuses[tier] = "PARTIAL"

    overall = "BLOCKED" if tier_statuses["tier1"] == "BLOCKED" else (
        "PARTIAL" if any(value == "PARTIAL" for value in tier_statuses.values()) else "OK"
    )
    return {
        "status": overall,
        "tier1_status": tier_statuses["tier1"],
        "tier2_status": tier_statuses["tier2"],
        "tier3_status": tier_statuses["tier3"],
        "warnings": _dedupe(warnings),
        "errors": _dedupe(errors),
        "missing_data": _dedupe(missing_data),
        "partial_data": _dedupe(partial_data),
    }


def _db_params(entry: dict[str, Any]) -> dict[str, Any]:
    params = dict(entry)
    params["warnings"] = json.dumps(entry.get("warnings") or [], ensure_ascii=False)
    params["metadata"] = json.dumps(entry.get("metadata") or {}, ensure_ascii=False, sort_keys=True)
    return params


def _manifest_id(run_id: str, module: str, source: str) -> str:
    payload = f"{run_id}|{module}|{source}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return f"{run_id}:{module}:{digest}"


def _validate(value: str, allowed: set[str], field: str) -> str:
    normalized = str(value)
    if normalized not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")
    return normalized


def _date_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _optional_date_text(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    return _date_text(value)


def _optional_datetime_text(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat(timespec="seconds")
    return str(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
```

- [ ] **Step 4: Add schema DDL**

Append `CREATE_DATA_RUN_MANIFEST_SQL` content to `CREATE_TABLES_SQL` in `src/stock_research/schema.py`, keeping it under the existing `ops` schema.

- [ ] **Step 5: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_data_run_manifest.py tests/test_schema.py -k 'data_run_manifest' -q
```

Expected: pass.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/stock_research/data_run_manifest.py src/stock_research/schema.py tests/test_data_run_manifest.py tests/test_schema.py
git commit -m "feat: add eod data run manifest"
```

---

## Task 2: Daily Pipeline Summary V2

**Files:**
- Modify: `src/stock_research/daily_data_pipeline.py`
- Modify: `tests/test_daily_data_pipeline.py`

- [ ] **Step 1: Write failing summary tests**

Add tests to `tests/test_daily_data_pipeline.py`:

```python
def test_run_stock_daily_data_pipeline_writes_v2_summary_and_manifest(tmp_path: Path) -> None:
    result = run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=lambda command, timeout_seconds: {
            "returncode": 0,
            "stdout": "rows|12",
            "stderr": "",
        },
        send_feishu=False,
    )

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    manifest_payload = json.loads((tmp_path / "run_manifest.json").read_text())

    assert summary["run_id"] == "eod-2026-06-05-local"
    assert summary["run_date"]
    assert summary["latest_market_date"] == "2026-06-05"
    assert summary["status"] == "PARTIAL"
    assert summary["tier1_status"] == "OK"
    assert "modules" in summary
    assert "steps" in summary
    assert summary["topn_generated"] is True
    assert summary["topn_count"] == 12
    assert summary["review_queue_count"] == 12
    assert summary["readiness_status"] == summary["status"]
    assert summary["dashboard_readiness_url"].endswith("/api/platform/readiness")
    assert manifest_payload["run_id"] == summary["run_id"]
    assert {item["module"] for item in manifest_payload["modules"]} >= {
        "assets_universe",
        "daily_bars",
        "factor_pipeline",
        "score_topn",
        "review_queue",
        "news",
        "research_reports",
        "minute_bars",
    }
    assert result["run_id"] == summary["run_id"]


def test_run_stock_daily_data_pipeline_tier1_failure_blocks_summary(tmp_path: Path) -> None:
    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        if "load_market_bars" in command:
            return {"returncode": 1, "stdout": "", "stderr": "market failed"}
        return {"returncode": 0, "stdout": "rows|10", "stderr": ""}

    run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    assert summary["status"] == "BLOCKED"
    assert summary["tier1_status"] == "BLOCKED"
    assert "daily_bars" in summary["missing_data"]
    assert any("market failed" in error for error in summary["errors"])


def test_run_stock_daily_data_pipeline_tier2_failure_is_partial(tmp_path: Path) -> None:
    def fake_runner(command: list[str], timeout_seconds: int) -> dict[str, object]:
        if "free-enrichment-backfill" in command:
            return {"returncode": 1, "stdout": "", "stderr": "lhb failed"}
        return {"returncode": 0, "stdout": "rows|10", "stderr": ""}

    run_stock_daily_data_pipeline(
        trade_date="2026-06-05",
        output_dir=tmp_path,
        command_runner=fake_runner,
        send_feishu=False,
    )

    summary = json.loads((tmp_path / "run_summary.json").read_text())
    assert summary["status"] == "PARTIAL"
    assert summary["tier1_status"] == "OK"
    assert summary["tier2_status"] == "PARTIAL"
    assert "lhb" in summary["partial_data"]
```

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_daily_data_pipeline.py -q
```

Expected: fail because summary v2 fields and `run_manifest.json` do not exist.

- [ ] **Step 3: Implement step-to-module mapping and v2 summary**

In `daily_data_pipeline.py`, import:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_research.data_run_manifest import build_manifest_entry, summarize_manifest_modules
```

Add mapping:

```python
STEP_MODULES = {
    "sync_core_assets": ("assets_universe", "core_assets", "tier1"),
    "load_market_bars": ("daily_bars", "market_daily_bar", "tier1"),
    "check_market_data_freshness": ("trading_calendar", "market_calendar", "tier1"),
    "build_asset_status": ("assets_universe", "core_asset_status", "tier1"),
    "daily_feature_build": ("factor_pipeline", "factor_pipeline", "tier1"),
    "daily_event_refresh": ("lhb", "free_enrichment_lhb", "tier2"),
    "sync_industry_memberships": ("industry", "industry_membership", "tier2"),
    "build_industry_bars": ("industry", "industry_bars", "tier2"),
    "minute_incremental_refresh": ("minute_bars", "minute_backfill", "tier3"),
    "label_incremental_refresh": ("experimental_enrichment", "labels", "tier3"),
    "daily_report_delivery": ("generated_reports", "reports", "tier2"),
}
```

Add helper functions:

```python
def _run_id(trade_date: str) -> str:
    return f"eod-{trade_date}-local"


def _now_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _manifest_for_step(*, run_id: str, trade_date: str, step: dict[str, Any]) -> dict[str, Any]:
    module, source, tier = STEP_MODULES.get(step["step"], (step["step"], step["step"], "tier3"))
    status = _manifest_status(step)
    warnings = [step["error"]] if status in {"partial", "failed", "unavailable"} and step.get("error") else []
    return build_manifest_entry(
        run_id=run_id,
        run_date=_now_shanghai()[:10],
        trade_date=trade_date,
        module=module,
        source=source,
        tier=tier,
        status=status,
        row_count=int(step.get("rows") or 0),
        latest_trade_date=trade_date if status == "success" else None,
        warnings=warnings,
        error_message=step.get("error") or "",
        artifact_path=step.get("log_path") or "",
        metadata={"step": step["step"], "returncode": step.get("returncode")},
    )


def _manifest_status(step: dict[str, Any]) -> str:
    status = str(step.get("status") or "")
    if status == "success":
        return "success"
    if status == "skipped":
        return "skipped"
    if status == "skipped_dependency_failed":
        return "unavailable"
    if status in {"failed", "partial_failed"}:
        return "failed"
    if status == "running":
        return "partial"
    return "unavailable"
```

Update `_write_summary` to build `modules`, summarize tier status, write
`run_manifest.json`, and include v2 summary fields while preserving `steps`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_daily_data_pipeline.py tests/test_data_run_manifest.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/stock_research/daily_data_pipeline.py tests/test_daily_data_pipeline.py
git commit -m "feat: write eod manifest summary"
```

---

## Task 3: Readiness V2

**Files:**
- Modify: `src/stock_research/dashboard/readiness.py`
- Modify: `tests/test_dashboard_readiness.py`

- [ ] **Step 1: Write failing readiness v2 tests**

Add tests to `tests/test_dashboard_readiness.py`:

```python
def test_build_platform_readiness_v2_ok_from_manifest(monkeypatch):
    modules = [
        {"module": "daily_bars", "source": "market", "tier": "tier1", "status": "success", "row_count": 5200, "warnings": [], "error_message": ""},
        {"module": "score_topn", "source": "factor", "tier": "tier1", "status": "success", "row_count": 30, "warnings": [], "error_message": ""},
        {"module": "review_queue", "source": "dashboard", "tier": "tier1", "status": "success", "row_count": 20, "warnings": [], "error_message": ""},
        {"module": "news", "source": "public_news", "tier": "tier2", "status": "success", "row_count": 10, "warnings": [], "error_message": ""},
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(readiness, "load_platform_summary", lambda score_version, top_n: {"latest_market_date": "2026-06-12", "topn_preview": [{"asset_id": "CN:SH:600519"}]})
    monkeypatch.setattr(readiness, "_has_public_news", lambda: True)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "OK"
    assert payload["source"] == "data_run_manifest"
    assert payload["latest_trade_date"] == "2026-06-12"
    assert payload["tiers"][0]["status"] == "OK"
    assert payload["missing_data"] == []


def test_build_platform_readiness_v2_tier2_failure_is_partial(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_queue", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "news", "tier": "tier2", "status": "failed", "warnings": ["news down"], "error_message": "news down"},
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(readiness, "load_platform_summary", lambda score_version, top_n: {"latest_market_date": "2026-06-12", "topn_preview": [{"asset_id": "CN:SH:600519"}]})
    monkeypatch.setattr(readiness, "_has_public_news", lambda: False)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "PARTIAL"
    assert "news" in payload["partial_data"]
    assert "news down" in payload["warnings"]


def test_build_platform_readiness_v2_tier1_failure_is_blocked(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "failed", "warnings": [], "error_message": "market failed"},
        {"module": "score_topn", "tier": "tier1", "status": "unavailable", "warnings": [], "error_message": "no scores"},
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(readiness, "load_platform_summary", lambda score_version, top_n: {"latest_market_date": "2026-06-12", "topn_preview": [{"asset_id": "CN:SH:600519"}]})
    monkeypatch.setattr(readiness, "_has_public_news", lambda: True)
    monkeypatch.setattr(readiness, "_has_research_reports", lambda: True)
    monkeypatch.setattr(readiness, "_has_generated_reports", lambda latest_market_date: True)

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "BLOCKED"
    assert "daily_bars" in payload["missing_data"]
    assert "score_topn" in payload["missing_data"]
    assert any("market failed" in error for error in payload["errors"])


def test_build_platform_readiness_v2_missing_topn_blocks_even_with_manifest(monkeypatch):
    modules = [
        {"module": "daily_bars", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "score_topn", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
        {"module": "review_queue", "tier": "tier1", "status": "success", "warnings": [], "error_message": ""},
    ]
    monkeypatch.setattr(readiness, "load_latest_data_run_manifest", lambda trade_date=None: modules)
    monkeypatch.setattr(readiness, "load_platform_summary", lambda score_version, top_n: {"latest_market_date": "2026-06-12", "topn_preview": []})

    payload = readiness.build_platform_readiness()

    assert payload["status"] == "BLOCKED"
    assert "score_topn" in payload["missing_data"]
    assert "Review Queue unavailable" in payload["warnings"]
```

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py -q
```

Expected: fail because readiness v2 fields/statuses do not exist.

- [ ] **Step 3: Implement readiness v2**

In `readiness.py`, import:

```python
from stock_research.data_run_manifest import load_latest_data_run_manifest, summarize_manifest_modules
```

Update `aggregate_readiness_status` to support both old and v2 statuses:

```python
def aggregate_readiness_status(checks: list[dict[str, Any]]) -> str:
    statuses = [str(check.get("status") or "unknown") for check in checks]
    if "BLOCKED" in statuses or "missing_data" in statuses:
        return "BLOCKED" if "BLOCKED" in statuses else "missing_data"
    if any(status in {"PARTIAL", "partial", "unknown"} for status in statuses):
        return "PARTIAL" if "PARTIAL" in statuses else "partial"
    return "OK" if "OK" in statuses else "ready"
```

Add v2 helpers:

```python
def _manifest_payload(modules: list[dict[str, Any]], latest_market_date: str, topn_preview: list[dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    summary = summarize_manifest_modules(modules)
    missing_data = list(summary["missing_data"])
    partial_data = list(summary["partial_data"])
    errors = list(summary["errors"])
    if not topn_preview:
        missing_data.append("score_topn")
        missing_data.append("review_queue")
        warnings.append(UNAVAILABLE_WARNINGS["topn_preview"])
        warnings.append(UNAVAILABLE_WARNINGS["review_queue"])
    status = "BLOCKED" if missing_data else summary["status"]
    tiers = [
        {"tier": "tier1", "status": "BLOCKED" if missing_data and any(item in {"score_topn", "review_queue", "daily_bars"} for item in missing_data) else summary["tier1_status"]},
        {"tier": "tier2", "status": summary["tier2_status"]},
        {"tier": "tier3", "status": summary["tier3_status"]},
    ]
    return {
        "source": "data_run_manifest",
        "status": status,
        "latest_trade_date": latest_market_date,
        "tiers": tiers,
        "modules": modules,
        "warnings": _dedupe([*summary["warnings"], *warnings]),
        "errors": errors,
        "missing_data": _dedupe(missing_data),
        "partial_data": _dedupe(partial_data),
        "next_actions": _next_actions(status, missing_data, partial_data),
    }
```

Update `build_platform_readiness()` to:

1. load platform summary as today;
2. attempt `load_latest_data_run_manifest()`;
3. if manifest rows exist, return v2 fields plus compatibility `checks`;
4. if no manifest, return fallback probe with v2 fields and `source: "lightweight_probe"`.

Keep `checks` in the response so existing frontend/tests continue to work.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py tests/test_dashboard_app.py -q
```

Expected: pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/stock_research/dashboard/readiness.py tests/test_dashboard_readiness.py
git commit -m "feat: upgrade platform readiness v2"
```

---

## Task 4: Runbook And Smoke

**Files:**
- Modify: `docs/dashboard-local-runbook.md`
- Optional Modify: `dashboard/tests/platform-full-flow.spec.ts` only if v2 mock shape is required for existing e2e.

- [ ] **Step 1: Add runbook smoke notes**

Append a short Batch A section to `docs/dashboard-local-runbook.md`:

```markdown
## EOD Manifest Smoke

Run the local EOD pipeline with an explicit output directory:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli run-stock-daily-data-pipeline \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/stock_daily_data_pipeline/YYYY-MM-DD \
  --no-feishu
```

Inspect:

- `run_summary.json`
- `run_manifest.json`
- `http://127.0.0.1:8765/api/platform/readiness`
```

- [ ] **Step 2: Run focused backend tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_data_run_manifest.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_app.py \
  -q
```

Expected: pass.

- [ ] **Step 3: Run frontend compatibility smoke**

Run:

```bash
cd dashboard
pnpm test -- --run tests/client.test.ts tests/home-cockpit.test.tsx
pnpm build
pnpm exec playwright test tests/platform-full-flow.spec.ts
```

Expected: pass. If existing uncommitted HomeCockpit/layout changes cause frontend failures unrelated to Batch A, document that as dirty-worktree risk and keep Batch A backend verified.

- [ ] **Step 4: Commit docs/smoke updates**

```bash
git add docs/dashboard-local-runbook.md dashboard/tests/platform-full-flow.spec.ts
git commit -m "docs: add eod manifest readiness smoke"
```

If `dashboard/tests/platform-full-flow.spec.ts` is not changed, commit only the runbook.

---

## Final Verification

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_data_run_manifest.py \
  tests/test_daily_data_pipeline.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_app.py \
  -q
```

Then, if frontend dirty-worktree state permits:

```bash
cd dashboard
pnpm test -- --run tests/client.test.ts tests/home-cockpit.test.tsx
pnpm build
pnpm exec playwright test tests/platform-full-flow.spec.ts
```

Report any skipped frontend verification explicitly.
