# Display Date Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a backend display-date gate so the dashboard defaults to the latest completed and contract-valid strategy trading day instead of the newest partial data date.

**Architecture:** Implement a focused read-side module that groups manifest rows by trade date, validates required strategy summaries against balanced contracts, and returns the authoritative `display_trade_date`. Wire the result into readiness, strategy cards, and default workspace date selection without changing raw data ingestion.

**Tech Stack:** Python, FastAPI dashboard backend, PostgreSQL manifest table, pytest, existing React/Vite dashboard client.

---

## File Structure

- Create: `src/stock_research/dashboard/display_date_gate.py`
  - Owns display-date selection, cutoff logic, manifest grouping, and contract validation summaries.
- Modify: `src/stock_research/dashboard/readiness.py`
  - Adds display gate fields to readiness payload and uses display date instead of raw latest market date for dashboard defaults.
- Modify: `src/stock_research/dashboard/backtests.py`
  - Prevents contract-failed strategy artifacts from exposing stale return/drawdown metrics.
- Modify: `src/stock_research/dashboard/review_queue.py`
  - Uses display gate date when the caller does not pass an explicit `trade_date`.
- Modify: `src/stock_research/dashboard/market_monitor.py`
  - Uses display gate date when the caller does not pass an explicit `trade_date`.
- Modify: `src/stock_research/dashboard/app.py`
  - Exposes `GET /api/platform/display-date`.
- Modify: `dashboard/src/api/types.ts`, `dashboard/src/api/client.ts`
  - Adds display gate typing if a dedicated endpoint is exposed.
- Modify: Home/workspace components under `dashboard/src/components/`
  - Reads `display_trade_date` from readiness/summary for default page state.
- Test: `tests/test_dashboard_display_date_gate.py`
- Test: `tests/test_dashboard_readiness.py`
- Test: `tests/test_dashboard_backtests.py`
- Test: `tests/test_dashboard_review_queue.py`
- Test: `tests/test_dashboard_market_monitor.py`
- Test: dashboard Vitest files under `dashboard/tests/`

---

### Task 1: Add Display Date Gate Core

**Files:**
- Create: `src/stock_research/dashboard/display_date_gate.py`
- Test: `tests/test_dashboard_display_date_gate.py`

- [ ] **Step 1: Write failing tests for cutoff and valid date selection**

Add `tests/test_dashboard_display_date_gate.py`:

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from stock_research.dashboard.display_date_gate import select_display_date


def _module(trade_date, module, *, status="success", summary=None):
    return {
        "run_id": f"strategy-eod-{trade_date}-local",
        "trade_date": trade_date,
        "latest_trade_date": trade_date,
        "module": module,
        "status": status,
        "metadata": {"summary": summary or {}},
    }


def _valid_strategy_summary(strategy_id):
    if strategy_id == "lhb_shortline":
        return {
            "engine_version": "lhb_shortline_v1",
            "phase18c_strategy": "auction_enhanced_rerank",
            "risk_profile": "balanced",
            "top_n": 5,
            "transaction_cost_bps": 10.0,
            "adjust_type": "hfq",
            "frequency": "daily",
            "total_return": 0.1,
            "max_drawdown": -0.02,
        }
    if strategy_id == "mid_trend":
        return {
            "engine_version": "mid_trend_v1",
            "variant_name": "top5_weekly_max_2_replacements",
            "benchmark_variant": "top5_weekly_max_2_replacements",
            "top_n": 5,
            "transaction_cost_bps": 20.0,
            "adjust_type": "hfq",
            "frequency": "weekly",
            "total_return": 0.2,
            "max_drawdown": -0.1,
        }
    return {
        "engine_version": "tech_bottleneck_v1",
        "universe": "strict_153_st_only_financial_state",
        "frequency": "biweekly",
        "protection_name": "rank_exit_top10_1d",
        "top_n": 3,
        "transaction_cost_bps": 20.0,
        "adjust_type": "hfq",
        "total_return": 0.3,
        "max_drawdown": -0.1,
    }


def _ready_modules(trade_date):
    return [
        _module(trade_date, "daily_bars"),
        _module(trade_date, "technical_features"),
        _module(trade_date, "score_topn"),
        _module(trade_date, "lhb_features"),
        _module(trade_date, "review_queue_strategy_manifest"),
        _module(trade_date, "strategy_lhb_shortline", summary=_valid_strategy_summary("lhb_shortline")),
        _module(trade_date, "strategy_mid_trend", summary=_valid_strategy_summary("mid_trend")),
        _module(trade_date, "strategy_tech_bottleneck", summary=_valid_strategy_summary("tech_bottleneck")),
    ]


def test_select_display_date_keeps_prior_ready_date_before_cutoff(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    now = datetime(2026, 6, 18, 20, 10, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        [*_ready_modules("2026-06-17"), *_ready_modules("2026-06-18")],
        now=now,
        latest_market_date="2026-06-18",
    )

    assert result["display_trade_date"] == "2026-06-17"
    assert result["candidate_trade_date"] == "2026-06-18"
    assert result["candidate_status"] == "before_cutoff"


def test_select_display_date_switches_after_cutoff_when_today_ready(monkeypatch):
    monkeypatch.setattr(
        "stock_research.dashboard.display_date_gate.load_strategy_contracts",
        lambda profile="balanced": {},
    )
    now = datetime(2026, 6, 18, 20, 40, tzinfo=ZoneInfo("Asia/Shanghai"))

    result = select_display_date(
        [*_ready_modules("2026-06-17"), *_ready_modules("2026-06-18")],
        now=now,
        latest_market_date="2026-06-18",
    )

    assert result["display_trade_date"] == "2026-06-18"
    assert result["display_status"] == "ready"
    assert result["strategy_ready"] == "3/3"
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_display_date_gate.py -q
```

Expected: FAIL because `stock_research.dashboard.display_date_gate` does not exist.

- [ ] **Step 3: Implement minimal display gate module**

Create `src/stock_research/dashboard/display_date_gate.py`:

```python
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from stock_research.strategy_contracts import (
    load_strategy_contracts,
    validate_strategy_summary_against_contract,
)

REQUIRED_BASE_MODULES = {"daily_bars", "technical_features", "score_topn", "lhb_features"}
REQUIRED_STRATEGY_MODULES = {
    "strategy_lhb_shortline": "lhb_shortline",
    "strategy_mid_trend": "mid_trend",
    "strategy_tech_bottleneck": "tech_bottleneck",
}
REQUIRED_REVIEW_MODULES = {"review_queue_strategy_manifest"}
DISPLAY_CUTOFF = time(20, 30)
LOCAL_ZONE = ZoneInfo("Asia/Shanghai")


def select_display_date(
    modules: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    latest_market_date: str = "",
) -> dict[str, Any]:
    current_time = now.astimezone(LOCAL_ZONE) if now else datetime.now(LOCAL_ZONE)
    grouped = _modules_by_trade_date(modules)
    candidate_trade_date = str(latest_market_date or _latest_trade_date(grouped) or "")
    ready_by_date = {
        trade_date: _evaluate_trade_date(trade_date, rows)
        for trade_date, rows in grouped.items()
    }
    ready_dates = sorted(
        trade_date
        for trade_date, status in ready_by_date.items()
        if status["display_status"] == "ready"
    )

    candidate = ready_by_date.get(candidate_trade_date)
    if candidate_trade_date and current_time.time() < DISPLAY_CUTOFF:
        prior_ready = [value for value in ready_dates if value < candidate_trade_date]
        display_date = prior_ready[-1] if prior_ready else (ready_dates[-1] if ready_dates else "")
        return _payload(
            display_date=display_date,
            candidate_trade_date=candidate_trade_date,
            candidate_status="before_cutoff",
            candidate=candidate,
            ready_by_date=ready_by_date,
        )

    if candidate and candidate["display_status"] == "ready":
        return _payload(
            display_date=candidate_trade_date,
            candidate_trade_date=candidate_trade_date,
            candidate_status="ready",
            candidate=candidate,
            ready_by_date=ready_by_date,
        )

    display_date = ready_dates[-1] if ready_dates else ""
    return _payload(
        display_date=display_date,
        candidate_trade_date=candidate_trade_date,
        candidate_status=(candidate or {}).get("display_status") or "missing",
        candidate=candidate,
        ready_by_date=ready_by_date,
    )


def _modules_by_trade_date(modules: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in modules:
        trade_date = str(row.get("trade_date") or row.get("latest_trade_date") or "")[:10]
        if trade_date:
            grouped[trade_date].append(row)
    return dict(grouped)


def _latest_trade_date(grouped: dict[str, list[dict[str, Any]]]) -> str:
    return max(grouped) if grouped else ""


def _evaluate_trade_date(trade_date: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_module = {str(row.get("module") or ""): row for row in rows}
    missing = [
        module for module in sorted(REQUIRED_BASE_MODULES | REQUIRED_REVIEW_MODULES | set(REQUIRED_STRATEGY_MODULES))
        if str((by_module.get(module) or {}).get("status") or "") != "success"
    ]
    contract_failures = _contract_failures(by_module)
    status = "ready"
    if missing:
        status = "incomplete"
    elif contract_failures:
        status = "contract_mismatch"
    return {
        "trade_date": trade_date,
        "display_status": status,
        "strategy_ready_count": sum(
            1 for module in REQUIRED_STRATEGY_MODULES if str((by_module.get(module) or {}).get("status") or "") == "success"
        ),
        "strategy_total_count": len(REQUIRED_STRATEGY_MODULES),
        "contract_valid_count": len(REQUIRED_STRATEGY_MODULES) - len(contract_failures),
        "contract_total_count": len(REQUIRED_STRATEGY_MODULES),
        "blocking_reasons": [f"missing:{module}" for module in missing] + contract_failures,
    }


def _contract_failures(by_module: dict[str, dict[str, Any]]) -> list[str]:
    try:
        contracts = load_strategy_contracts(profile="balanced")
    except Exception:
        contracts = {}
    failures: list[str] = []
    for module, strategy_id in REQUIRED_STRATEGY_MODULES.items():
        contract = contracts.get(strategy_id)
        if contract is None:
            continue
        metadata = by_module.get(module, {}).get("metadata")
        summary = metadata.get("summary") if isinstance(metadata, dict) else {}
        result = validate_strategy_summary_against_contract(dict(summary or {}), contract)
        if result.status != "success":
            failures.append(f"{strategy_id}:{result.reason}")
    return failures


def _payload(
    *,
    display_date: str,
    candidate_trade_date: str,
    candidate_status: str,
    candidate: dict[str, Any] | None,
    ready_by_date: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    selected = ready_by_date.get(display_date, {})
    blocking_reasons = list((candidate or {}).get("blocking_reasons") or [])
    return {
        "display_trade_date": display_date,
        "candidate_trade_date": candidate_trade_date,
        "cutoff_time": "20:30",
        "timezone": "Asia/Shanghai",
        "display_status": selected.get("display_status") or ("ready" if display_date else "missing"),
        "candidate_status": candidate_status,
        "strategy_ready": f"{selected.get('strategy_ready_count', 0)}/{len(REQUIRED_STRATEGY_MODULES)}",
        "contract_valid": f"{selected.get('contract_valid_count', 0)}/{len(REQUIRED_STRATEGY_MODULES)}",
        "blocking_reasons": blocking_reasons,
    }
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_display_date_gate.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/display_date_gate.py tests/test_dashboard_display_date_gate.py
git commit -m "feat: add dashboard display date gate"
```

---

### Task 2: Wire Display Gate Into Readiness

**Files:**
- Modify: `src/stock_research/dashboard/readiness.py`
- Test: `tests/test_dashboard_readiness.py`

- [ ] **Step 1: Add failing readiness test**

Append to `tests/test_dashboard_readiness.py`:

```python
def test_readiness_includes_display_date_gate(monkeypatch):
    from stock_research.dashboard import readiness

    monkeypatch.setattr(
        readiness,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-18",
            "topn_preview": [{"asset_id": "A"}],
        },
    )
    monkeypatch.setattr(
        readiness,
        "_load_manifest_modules",
        lambda: [
            {"run_id": "r1", "trade_date": "2026-06-17", "module": "daily_bars", "status": "success"},
        ],
    )
    monkeypatch.setattr(
        readiness,
        "select_display_date",
        lambda modules, latest_market_date, **kwargs: {
            "display_trade_date": "2026-06-17",
            "candidate_trade_date": "2026-06-18",
            "display_status": "ready",
            "candidate_status": "before_cutoff",
            "strategy_ready": "3/3",
            "contract_valid": "3/3",
            "blocking_reasons": [],
        },
    )

    payload = readiness.build_platform_readiness()

    assert payload["display_trade_date"] == "2026-06-17"
    assert payload["candidate_trade_date"] == "2026-06-18"
    assert payload["display_gate"]["candidate_status"] == "before_cutoff"
```

- [ ] **Step 2: Run test and verify fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py::test_readiness_includes_display_date_gate -q
```

Expected: FAIL because readiness does not import or return `select_display_date`.

- [ ] **Step 3: Wire display gate into readiness**

In `src/stock_research/dashboard/readiness.py`, add:

```python
from stock_research.dashboard.display_date_gate import select_display_date
```

Inside `_build_manifest_readiness`, before the return dict:

```python
    display_gate = select_display_date(
        manifest_modules,
        latest_market_date=latest_trade_date,
    )
```

Add these keys to the returned payload:

```python
        "display_trade_date": display_gate["display_trade_date"],
        "candidate_trade_date": display_gate["candidate_trade_date"],
        "display_gate": display_gate,
```

- [ ] **Step 4: Run readiness tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_readiness.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/readiness.py tests/test_dashboard_readiness.py
git commit -m "feat: expose dashboard display date readiness"
```

---

### Task 3: Hide Strategy Metrics When Contract Validation Fails

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Test: `tests/test_dashboard_backtests.py`

- [ ] **Step 1: Add failing strategy metrics test**

Append to `tests/test_dashboard_backtests.py`:

```python
def test_strategy_metrics_hide_performance_when_contract_mismatched(monkeypatch, tmp_path):
    from stock_research.dashboard import backtests

    artifact = tmp_path / "strategy_mid_trend_review.csv"
    artifact.write_text(
        "trade_date,asset_id,rank,strategy_id,stock_name\n"
        "2026-06-17,CN:SH:601000,1,mid_trend,测试股票\n",
        encoding="utf-8",
    )

    class Contract:
        strategy_id = "mid_trend"
        profile = "balanced"
        engine = "mid_trend_v1"
        variant = "top5_weekly_max_2_replacements"
        top_n = 5
        frequency = "weekly"
        protection_name = None
        transaction_cost_bps = 20.0
        adjust_type = "hfq"
        contract_id = "mid_trend:balanced:test"

    monkeypatch.setattr(backtests, "load_strategy_contracts", lambda profile="balanced": {"mid_trend": Contract()})
    monkeypatch.setattr(
        backtests,
        "load_latest_data_run_manifest",
        lambda: [
            {
                "module": "strategy_mid_trend",
                "status": "success",
                "latest_trade_date": "2026-06-17",
                "row_count": 1,
                "artifact_path": str(artifact),
                "metadata": {
                    "summary": {
                        "engine_version": "mid_trend_v1",
                        "variant_name": "old_wrong_variant",
                        "top_n": 5,
                        "total_return": 9.0,
                        "max_drawdown": -0.1,
                    }
                },
            }
        ],
    )

    enriched = backtests._with_latest_eod_strategy_metrics(
        {"strategy_id": "mid_trend", "strategy_name": "Mid Trend Combo", "latest_metrics": {}}
    )

    assert enriched["latest_metrics"]["signal_status"] == "contract_mismatch"
    assert "total_return_pct" not in enriched["latest_metrics"]
    assert "max_drawdown_pct" not in enriched["latest_metrics"]
```

- [ ] **Step 2: Run test and verify fail or confirm current behavior**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py::test_strategy_metrics_hide_performance_when_contract_mismatched -q
```

Expected: PASS if the previous contract-mismatch patch already removed stale metrics, otherwise FAIL with stale performance keys present.

- [ ] **Step 3: Implement metric clearing if needed**

If the test fails, change the contract mismatch branch in `_with_latest_eod_strategy_metrics` so it does not merge prior performance metrics:

```python
            next_strategy["latest_metrics"] = {
                "as_of_date": latest_trade_date or metrics.get("as_of_date"),
                "signal_status": "contract_mismatch",
                "signal_count": signal_count,
                "contract_status": status,
                "contract_reason": reason,
            }
```

- [ ] **Step 4: Run backtests tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/backtests.py tests/test_dashboard_backtests.py
git commit -m "fix: hide stale strategy metrics on contract mismatch"
```

---

### Task 4: Default Review Queue And Market Monitor To Display Date

**Files:**
- Modify: `src/stock_research/dashboard/review_queue.py`
- Modify: `src/stock_research/dashboard/market_monitor.py`
- Test: `tests/test_dashboard_review_queue.py`
- Test: `tests/test_dashboard_market_monitor.py`

- [ ] **Step 1: Add failing tests for default date selection**

Add to `tests/test_dashboard_review_queue.py`:

```python
def test_review_queue_defaults_to_display_trade_date(monkeypatch):
    from stock_research.dashboard import review_queue

    monkeypatch.setattr(
        review_queue,
        "current_display_trade_date",
        lambda: "2026-06-17",
        raising=False,
    )

    selected = review_queue._selected_review_trade_date(None)

    assert selected == "2026-06-17"
```

Add to `tests/test_dashboard_market_monitor.py`:

```python
def test_market_monitor_defaults_to_display_trade_date(monkeypatch):
    from stock_research.dashboard import market_monitor

    monkeypatch.setattr(
        market_monitor,
        "current_display_trade_date",
        lambda: "2026-06-17",
        raising=False,
    )

    assert market_monitor._selected_market_monitor_trade_date(None) == "2026-06-17"
```

- [ ] **Step 2: Run tests and verify fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_review_queue.py::test_review_queue_defaults_to_display_trade_date \
  tests/test_dashboard_market_monitor.py::test_market_monitor_defaults_to_display_trade_date -q
```

Expected: FAIL because the helper functions do not exist yet.

- [ ] **Step 3: Add shared display date helper usage**

In `src/stock_research/dashboard/display_date_gate.py`, add:

```python
from stock_research.data_run_manifest import load_latest_data_run_manifest


def current_display_trade_date() -> str:
    modules = list(load_latest_data_run_manifest())
    latest_market_date = max(
        (str(row.get("latest_trade_date") or row.get("trade_date") or "")[:10] for row in modules),
        default="",
    )
    return str(select_display_date(modules, latest_market_date=latest_market_date).get("display_trade_date") or "")
```

In `review_queue.py` and `market_monitor.py`, import `current_display_trade_date` and add a small date helper:

```python
def _selected_review_trade_date(trade_date: str | None) -> str:
    return str(trade_date or current_display_trade_date() or "")
```

```python
def _selected_market_monitor_trade_date(trade_date: str | None) -> str:
    return str(trade_date or current_display_trade_date() or "")
```

Use those helpers wherever the default latest date is currently selected.

- [ ] **Step 4: Run dashboard default-date tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_market_monitor.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/dashboard/display_date_gate.py src/stock_research/dashboard/review_queue.py src/stock_research/dashboard/market_monitor.py tests/test_dashboard_review_queue.py tests/test_dashboard_market_monitor.py
git commit -m "feat: default workspaces to display trade date"
```

---

### Task 5: Add API Smoke And Frontend Default Date Wiring

**Files:**
- Modify: `src/stock_research/dashboard/app.py`
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/src/components/HomeWorkspace.tsx` or the current Home component
- Test: `tests/test_dashboard_app.py`
- Test: dashboard Vitest files under `dashboard/tests/`

- [ ] **Step 1: Add backend route test**

Append to `tests/test_dashboard_app.py`:

```python
def test_platform_display_date_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from stock_research.dashboard import app as dashboard_app

    monkeypatch.setattr(
        dashboard_app,
        "current_display_gate",
        lambda: {
            "display_trade_date": "2026-06-17",
            "candidate_trade_date": "2026-06-18",
            "display_status": "ready",
            "candidate_status": "before_cutoff",
        },
        raising=False,
    )

    client = TestClient(dashboard_app.create_app())
    response = client.get("/api/platform/display-date")

    assert response.status_code == 200
    assert response.json()["display_trade_date"] == "2026-06-17"
```

- [ ] **Step 2: Run route test and verify fail**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py::test_platform_display_date_endpoint -q
```

Expected: FAIL because the route does not exist.

- [ ] **Step 3: Add route**

In `src/stock_research/dashboard/display_date_gate.py`, add:

```python
def current_display_gate() -> dict[str, Any]:
    modules = list(load_latest_data_run_manifest())
    latest_market_date = max(
        (str(row.get("latest_trade_date") or row.get("trade_date") or "")[:10] for row in modules),
        default="",
    )
    return select_display_date(modules, latest_market_date=latest_market_date)
```

In `src/stock_research/dashboard/app.py`, import and route:

```python
from stock_research.dashboard.display_date_gate import current_display_gate
```

```python
    @app.get("/api/platform/display-date")
    def platform_display_date() -> dict[str, Any]:
        return current_display_gate()
```

- [ ] **Step 4: Wire frontend types/client**

In `dashboard/src/api/types.ts`, add:

```ts
export interface DisplayDateGate {
  display_trade_date: string;
  candidate_trade_date: string;
  cutoff_time?: string;
  timezone?: string;
  display_status: string;
  candidate_status: string;
  strategy_ready?: string;
  contract_valid?: string;
  blocking_reasons?: string[];
}
```

In `dashboard/src/api/client.ts`, add:

```ts
export async function fetchDisplayDateGate(): Promise<DisplayDateGate> {
  return getJson<DisplayDateGate>('/api/platform/display-date');
}
```

- [ ] **Step 5: Run backend and frontend tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_app.py::test_platform_display_date_endpoint -q
cd dashboard && pnpm test -- --run
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/dashboard/app.py src/stock_research/dashboard/display_date_gate.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components dashboard/tests
git commit -m "feat: expose display trade date to dashboard"
```

---

### Task 6: Add Operator Runbook For 20:00 And 20:30 Jobs

**Files:**
- Create or modify: `docs/ops/display-date-gate-runbook.md`
- Modify: `deploy/launchd/` or `docs/deployment-dashboard.md` only if existing deployment docs already describe local schedules.

- [ ] **Step 1: Write runbook**

Create `docs/ops/display-date-gate-runbook.md`:

```markdown
# Display Date Gate Runbook

## Daily Local Schedule

- 20:00 Asia/Shanghai: run data completion.
- 20:30 Asia/Shanghai: run official strategy EOD from balanced contracts.

The dashboard must keep showing the latest `display_ready` trading day until the 20:30 strategy job completes and all three strategy contracts validate.

## Manual Checks

```bash
curl -s http://127.0.0.1:8765/api/platform/display-date | python -m json.tool
curl -s http://127.0.0.1:8765/api/platform/readiness | python -m json.tool
curl -s http://127.0.0.1:8765/api/backtests/strategies | python -m json.tool
```

## Failure Handling

If `candidate_status` is `contract_mismatch`, do not trust current-day strategy metrics. Re-run the official 20:30 strategy EOD job after fixing the mismatched strategy contract parameters.
```

- [ ] **Step 2: Run markdown/link sanity check**

Run:

```bash
test -f docs/ops/display-date-gate-runbook.md
```

Expected: PASS with exit code 0.

- [ ] **Step 3: Commit**

```bash
git add docs/ops/display-date-gate-runbook.md
git commit -m "docs: add display date gate runbook"
```

---

### Task 7: Final Verification

**Files:**
- No new files.

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_dashboard_display_date_gate.py \
  tests/test_dashboard_readiness.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_review_queue.py \
  tests/test_dashboard_market_monitor.py \
  tests/test_dashboard_app.py -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests**

Run:

```bash
cd dashboard && pnpm test -- --run
```

Expected: PASS.

- [ ] **Step 3: Run API smoke locally**

Run:

```bash
curl -s http://127.0.0.1:8765/api/platform/display-date | /Users/xiwei/stock_research/.venv/bin/python -m json.tool
curl -s http://127.0.0.1:8765/api/platform/readiness | /Users/xiwei/stock_research/.venv/bin/python -m json.tool | head -120
curl -s http://127.0.0.1:8765/api/backtests/strategies | /Users/xiwei/stock_research/.venv/bin/python -m json.tool | head -160
```

Expected:

- `display_trade_date` is present.
- `candidate_status` explains whether today is blocked, ready, or before cutoff.
- contract-failed strategies do not expose stale performance metrics.

- [ ] **Step 4: Run diff check**

Run:

```bash
git diff --check
```

Expected: PASS with no output.
