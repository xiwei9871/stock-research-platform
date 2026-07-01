# EOD Auto Repair Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build one idempotent EOD repair command that diagnoses missing daily data, minute bars, factors, scores, watchlists, market monitor, strategy publishing, reports, review queue, and ops health for a trade date, then runs the minimum safe repair actions and verifies the platform is ready.

**Architecture:** Add a small orchestration layer around existing pipelines rather than replacing them. The orchestrator builds a dependency graph of checks, runs repairs in order, records each attempt, enforces known safety rules such as Baostock single-worker minute backfill, and emits a machine-readable run summary plus human-readable Markdown report.

**Tech Stack:** Python, PostgreSQL via existing `stock_research.db`, existing pipeline modules, pytest, shell cron wrapper.

---

## File Structure

- Create `src/stock_research/eod_auto_repair_models.py`
  - Defines `RepairStatus`, `RepairCheckResult`, `RepairActionResult`, `RepairRunSummary`, and JSON serialization helpers.
- Create `src/stock_research/eod_auto_repair_checks.py`
  - Read-only checks for daily bars, minute5 bars, LHB source/features, technical factors, scores, watchlist, market monitor, strategy manifests, review queue API payload shape, reports, evidence snapshots, and ops health.
- Create `src/stock_research/eod_auto_repair_actions.py`
  - Thin wrappers around existing repair/build functions. Each action is idempotent and returns structured counts and paths.
- Create `src/stock_research/eod_auto_repair.py`
  - Main orchestrator and module CLI: `python -m stock_research.eod_auto_repair --trade-date 2026-06-29`.
- Create `scripts/run_eod_auto_repair_cron.sh`
  - Cron-safe wrapper using `rtk`, logs, lock file, and nonzero exit on hard failures.
- Add tests in `tests/test_eod_auto_repair_models.py`, `tests/test_eod_auto_repair_checks.py`, `tests/test_eod_auto_repair.py`, and `tests/test_eod_auto_repair_actions.py`.
- Modify `README.md`
  - Add a short operator runbook for the new command after the existing dashboard/API checks.

---

## Repair Contract

The command must support:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date 2026-06-29 \
  --output-dir outputs/research/eod_auto_repair/2026-06-29 \
  --mode repair
```

Modes:

- `check`: run diagnostics only, no writes.
- `repair`: run diagnostics, execute missing repair actions, verify again.
- `publish-only`: assume raw/factor data exists, run strategy/report/review publication and verify.

Exit codes:

- `0`: ready or degraded-ready with only documented optional partials.
- `2`: repair attempted but hard readiness failed.
- `3`: unsafe action blocked, such as requested Baostock workers greater than 1.

Hard rules:

- Baostock minute backfill must always run with `workers=1`.
- A repair action must not run if its prerequisite hard check failed and no repair action exists for that prerequisite.
- All actions must be idempotent for the same `trade_date`.
- The final report must show checks before repair, actions taken, checks after repair, and remaining blockers.

---

## Known Incident Coverage Matrix

This orchestrator must be driven by the actual incidents already seen in daily operation. It is not enough to reproduce the old `platform_ready` status probe.

| Incident observed | Old cron behavior | New required check | New repair action | Final verification |
|---|---|---|---|---|
| 5min bars missing for 2026-06-29 | Could report partial/not ready, but did not refill | Check `ops.daily_pipeline_quality` and `market.stock_minute_bar` for raw/qfq rows, expected assets, 48 bars per asset, first/last bar times | Run Baostock minute backfill for the date with `workers=1` only; refresh minute5 quality row | `minute5_bars` is `success` or documented `degraded` under allowed missing ratio |
| Baostock accidentally run with multiple workers | No guard in readiness check | Validate planned minute action config before execution | Block action and return exit code `3` if `workers != 1` | Report `unsafe_action_blocked` with the exact worker count |
| LHB source stayed at 2026-06-26, causing strategy publish base gate failure | Did not check LHB source freshness | Check `market.lhb_top_list_daily`, `market.lhb_top_inst_daily`, and `factor.lhb_event_features_daily` latest date and row counts | Run `run_free_enrichment_backfill(dataset='lhb')`, then `run_lhb_event_features_build` | LHB source and features latest date equals target trade date |
| Lightweight strategy EOD wrote files but review queue still displayed 2026-06-26 | Old check looked at `strategy_daily_eod_status`, not the actual dashboard display gate | Check `ops.data_run_manifest` for `strategy_lhb_shortline`, `strategy_mid_trend`, `strategy_tech_bottleneck`, `review_queue_strategy_manifest`; run `select_display_date` | Run full `publish_strategy_eod`, not lightweight `run_strategy_daily_eod` | `/api/review-queue` returns target trade date |
| `strategy_tech_bottleneck` was 0 because only fallback/lightweight path ran | Did not validate per-strategy row counts | Require each strategy module success and row count above strategy-specific threshold; Tech threshold is `>= 1` unless explicitly configured empty-ok | Run full Tech bottleneck EOD candidate flow via `publish_strategy_eod` | Tech group in review queue has `count >= 1` |
| LHB and Mid Trend queues were identical due to score fallback | Did not compare strategy groups | Compare strategy review asset sets and source names; flag identical asset lists across different strategies unless explicitly allowed | Run full strategy publish; if still identical, mark hard blocker requiring strategy source investigation | Review queue strategy groups have distinct source lineage and non-identical asset sets |
| Mid Trend rank 2/3/4 showed score `0.0` because continued holdings had no same-day score | Did not check score completeness inside review queue | Check every strategy review row has a non-null `score_total` and valid `score_source`; for Mid Trend continued holdings allow latest prior signal score but mark stale source | Rebuild strategy publish after score lookup fix; fail if rows still have null score | API group items have nonzero or intentional-null scores with explicit warnings |
| Market monitor, reports, evidence snapshots can lag after daily close | Old check only counted coarse availability | Check manifest modules `market_monitor`, `news`, `news_features`, `news_enrichment`, `research_reports`, `generated_reports`, `review_evidence_snapshots` for date/status | Run the existing market monitor/report/evidence builders in dependency order | Manifest and dashboard readiness show these modules success or documented partial |
| API cache/process can show stale or intermittent review queue data | Old cron did not validate served API payload | Fetch `/api/review-queue` and parse `trade_date`, groups, counts, scores | If API process is down, report service blocker; if cache stale, trigger configured refresh/restart hook in a later phase | HTTP 200 and parsed payload matches file/manifest state |

The MVP is accepted only if this matrix is represented in tests or explicit E2E verification steps.

---

## Task 1: Models And Summary Serialization

**Files:**
- Create: `src/stock_research/eod_auto_repair_models.py`
- Test: `tests/test_eod_auto_repair_models.py`

- [ ] **Step 1: Write the failing tests**

```python
from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairRunSummary,
    RepairStatus,
)


def test_repair_summary_serializes_nested_results():
    summary = RepairRunSummary(
        trade_date="2026-06-29",
        mode="repair",
        final_status=RepairStatus.SUCCESS,
        checks_before=[
            RepairCheckResult(
                name="lhb_features",
                status=RepairStatus.FAILED,
                message="missing",
                metrics={"row_count": 0},
            )
        ],
        actions=[
            RepairActionResult(
                name="build_lhb_features",
                status=RepairStatus.SUCCESS,
                message="built",
                metrics={"row_count": 102},
                artifact_paths=["outputs/research/strategy_daily_eod/2026-06-29/lhb_event_features_daily_sample.csv"],
            )
        ],
        checks_after=[
            RepairCheckResult(
                name="lhb_features",
                status=RepairStatus.SUCCESS,
                message="ready",
                metrics={"row_count": 102},
            )
        ],
    )

    payload = summary.to_dict()

    assert payload["trade_date"] == "2026-06-29"
    assert payload["final_status"] == "success"
    assert payload["checks_before"][0]["metrics"]["row_count"] == 0
    assert payload["actions"][0]["artifact_paths"][0].endswith("lhb_event_features_daily_sample.csv")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_models.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.eod_auto_repair_models'`.

- [ ] **Step 3: Implement the models**

Create `src/stock_research/eod_auto_repair_models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RepairStatus(str, Enum):
    SUCCESS = "success"
    DEGRADED = "degraded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class RepairCheckResult:
    name: str
    status: RepairStatus
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    blocker: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "metrics": self.metrics,
            "blocker": self.blocker,
        }


@dataclass(frozen=True)
class RepairActionResult:
    name: str
    status: RepairStatus
    message: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "metrics": self.metrics,
            "artifact_paths": self.artifact_paths,
        }


@dataclass(frozen=True)
class RepairRunSummary:
    trade_date: str
    mode: str
    final_status: RepairStatus
    checks_before: list[RepairCheckResult] = field(default_factory=list)
    actions: list[RepairActionResult] = field(default_factory=list)
    checks_after: list[RepairCheckResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "mode": self.mode,
            "final_status": self.final_status.value,
            "checks_before": [check.to_dict() for check in self.checks_before],
            "actions": [action.to_dict() for action in self.actions],
            "checks_after": [check.to_dict() for check in self.checks_after],
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_models.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/eod_auto_repair_models.py tests/test_eod_auto_repair_models.py
git commit -m "feat: add eod auto repair result models"
```

---

## Task 2: Read-Only EOD Checks

**Files:**
- Create: `src/stock_research/eod_auto_repair_checks.py`
- Test: `tests/test_eod_auto_repair_checks.py`

- [ ] **Step 1: Write failing tests for query-based checks**

```python
from stock_research.eod_auto_repair_checks import (
    build_check_plan,
    evaluate_count_check,
)
from stock_research.eod_auto_repair_models import RepairStatus


def test_evaluate_count_check_success_when_count_meets_minimum():
    result = evaluate_count_check(
        name="score_topn",
        row_count=5187,
        min_rows=1,
        latest_trade_date="2026-06-29",
        trade_date="2026-06-29",
    )

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["row_count"] == 5187
    assert result.blocker is False


def test_evaluate_count_check_failed_when_latest_date_stale():
    result = evaluate_count_check(
        name="review_queue_strategy_manifest",
        row_count=10,
        min_rows=1,
        latest_trade_date="2026-06-26",
        trade_date="2026-06-29",
    )

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert "2026-06-26" in result.message


def test_build_check_plan_contains_required_gate_names():
    names = [check.name for check in build_check_plan("2026-06-29")]

    assert names == [
        "daily_bars",
        "minute5_bars",
        "lhb_source",
        "lhb_features",
        "technical_features",
        "score_topn",
        "watchlist",
        "market_monitor",
        "strategy_publish",
        "review_queue",
        "reports",
        "review_evidence_snapshots",
        "ops_health",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py -q
```

Expected: FAIL because `stock_research.eod_auto_repair_checks` does not exist.

- [ ] **Step 3: Implement check helpers and plan skeleton**

Create `src/stock_research/eod_auto_repair_checks.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from stock_research.eod_auto_repair_models import RepairCheckResult, RepairStatus


@dataclass(frozen=True)
class RepairCheck:
    name: str
    run: Callable[[], RepairCheckResult]


def evaluate_count_check(
    *,
    name: str,
    row_count: int,
    min_rows: int,
    latest_trade_date: str | None,
    trade_date: str,
    blocker: bool = True,
) -> RepairCheckResult:
    metrics = {"row_count": int(row_count), "latest_trade_date": latest_trade_date}
    if int(row_count) >= int(min_rows) and latest_trade_date == trade_date:
        return RepairCheckResult(name=name, status=RepairStatus.SUCCESS, message="ready", metrics=metrics)
    message = f"{name} not ready for {trade_date}: row_count={row_count}, latest_trade_date={latest_trade_date}"
    return RepairCheckResult(
        name=name,
        status=RepairStatus.FAILED,
        message=message,
        metrics=metrics,
        blocker=blocker,
    )


def _not_implemented_check(name: str) -> RepairCheck:
    return RepairCheck(
        name=name,
        run=lambda: RepairCheckResult(name=name, status=RepairStatus.SKIPPED, message="check runner not wired"),
    )


def build_check_plan(trade_date: str) -> list[RepairCheck]:
    return [
        _not_implemented_check("daily_bars"),
        _not_implemented_check("minute5_bars"),
        _not_implemented_check("lhb_source"),
        _not_implemented_check("lhb_features"),
        _not_implemented_check("technical_features"),
        _not_implemented_check("score_topn"),
        _not_implemented_check("watchlist"),
        _not_implemented_check("market_monitor"),
        _not_implemented_check("strategy_publish"),
        _not_implemented_check("review_queue"),
        _not_implemented_check("reports"),
        _not_implemented_check("review_evidence_snapshots"),
        _not_implemented_check("ops_health"),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/eod_auto_repair_checks.py tests/test_eod_auto_repair_checks.py
git commit -m "feat: add eod auto repair check plan"
```

---

## Task 3: Wire Database Checks

**Files:**
- Modify: `src/stock_research/eod_auto_repair_checks.py`
- Test: `tests/test_eod_auto_repair_checks.py`

- [ ] **Step 1: Write failing tests for DB-backed checks with injected fetcher**

Append:

```python
from stock_research.eod_auto_repair_checks import (
    check_lhb_features,
    check_strategy_publish,
)


def test_check_lhb_features_reads_factor_table_with_fetcher():
    captured = {}

    def fetcher(sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [{"row_count": 102, "asset_count": 102, "latest_trade_date": "2026-06-29"}]

    result = check_lhb_features("2026-06-29", fetcher=fetcher)

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["asset_count"] == 102
    assert "factor.lhb_event_features_daily" in captured["sql"]
    assert captured["params"] == ["2026-06-29"]


def test_check_strategy_publish_requires_three_strategy_modules_and_manifest():
    rows = [
        {"module": "strategy_lhb_shortline", "status": "success", "row_count": 4, "asset_count": 4, "latest_trade_date": "2026-06-29"},
        {"module": "strategy_mid_trend", "status": "success", "row_count": 5, "asset_count": 5, "latest_trade_date": "2026-06-29"},
        {"module": "strategy_tech_bottleneck", "status": "success", "row_count": 5, "asset_count": 5, "latest_trade_date": "2026-06-29"},
        {"module": "review_queue_strategy_manifest", "status": "success", "row_count": 14, "asset_count": 14, "latest_trade_date": "2026-06-29"},
    ]

    result = check_strategy_publish("2026-06-29", manifest_loader=lambda trade_date: rows)

    assert result.status == RepairStatus.SUCCESS
    assert result.metrics["strategy_ready"] == "3/3"
    assert result.metrics["review_rows"] == 14
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py -q
```

Expected: FAIL because `check_lhb_features` and `check_strategy_publish` are missing.

- [ ] **Step 3: Implement DB-backed check functions**

Add to `src/stock_research/eod_auto_repair_checks.py`:

```python
from stock_research.config import SETTINGS
from stock_research.data_run_manifest import load_recent_data_run_manifest
from stock_research.db import connect, fetch_all


def _default_fetcher(sql: str, params: list[object]) -> list[dict[str, object]]:
    with connect(SETTINGS.research_service) as conn:
        return list(fetch_all(conn, sql, params))


def check_lhb_features(trade_date: str, *, fetcher=_default_fetcher) -> RepairCheckResult:
    sql = """
        SELECT count(*) AS row_count,
               count(DISTINCT ts_code) AS asset_count,
               max(trade_date)::text AS latest_trade_date
        FROM factor.lhb_event_features_daily
        WHERE trade_date = %s
    """
    rows = fetcher(sql, [trade_date])
    row = dict(rows[0]) if rows else {}
    result = evaluate_count_check(
        name="lhb_features",
        row_count=int(row.get("row_count") or 0),
        min_rows=1,
        latest_trade_date=str(row.get("latest_trade_date") or ""),
        trade_date=trade_date,
    )
    return RepairCheckResult(
        name=result.name,
        status=result.status,
        message=result.message,
        metrics={**result.metrics, "asset_count": int(row.get("asset_count") or 0)},
        blocker=result.blocker,
    )


def check_strategy_publish(
    trade_date: str,
    *,
    manifest_loader=load_recent_data_run_manifest,
) -> RepairCheckResult:
    required = {
        "strategy_lhb_shortline",
        "strategy_mid_trend",
        "strategy_tech_bottleneck",
        "review_queue_strategy_manifest",
    }
    rows = [dict(row) for row in manifest_loader(trade_date=trade_date)]
    latest = {row.get("module"): row for row in rows if row.get("module") in required}
    missing = sorted(module for module in required if module not in latest)
    failed = sorted(
        module
        for module, row in latest.items()
        if row.get("status") != "success" or str(row.get("latest_trade_date") or "") != trade_date
    )
    strategy_ready = sum(
        1
        for module in ("strategy_lhb_shortline", "strategy_mid_trend", "strategy_tech_bottleneck")
        if module in latest
        and latest[module].get("status") == "success"
        and str(latest[module].get("latest_trade_date") or "") == trade_date
    )
    review_rows = int((latest.get("review_queue_strategy_manifest") or {}).get("row_count") or 0)
    metrics = {
        "strategy_ready": f"{strategy_ready}/3",
        "review_rows": review_rows,
        "missing_modules": missing,
        "failed_modules": failed,
    }
    if not missing and not failed and review_rows > 0:
        return RepairCheckResult("strategy_publish", RepairStatus.SUCCESS, "ready", metrics)
    return RepairCheckResult("strategy_publish", RepairStatus.FAILED, "strategy publish incomplete", metrics, blocker=True)
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/eod_auto_repair_checks.py tests/test_eod_auto_repair_checks.py
git commit -m "feat: add db-backed eod repair checks"
```

---

## Task 4: Repair Actions With Safety Guards

**Files:**
- Create: `src/stock_research/eod_auto_repair_actions.py`
- Test: `tests/test_eod_auto_repair_actions.py`

- [ ] **Step 1: Write failing tests for Baostock single-worker guard and LHB repair**

```python
import pytest

from stock_research.eod_auto_repair_actions import (
    repair_lhb_source_and_features,
    repair_minute5_bars,
)
from stock_research.eod_auto_repair_models import RepairStatus


def test_repair_minute5_bars_rejects_multiple_workers():
    with pytest.raises(ValueError, match="Baostock minute backfill must use workers=1"):
        repair_minute5_bars("2026-06-29", workers=2, runner=lambda **kwargs: {})


def test_repair_minute5_bars_passes_single_worker_to_runner():
    captured = {}

    def runner(**kwargs):
        captured.update(kwargs)
        return {"raw_success": 5209, "qfq_success": 5209}

    result = repair_minute5_bars("2026-06-29", workers=1, runner=runner)

    assert result.status == RepairStatus.SUCCESS
    assert captured["workers"] == 1
    assert captured["start_date"] == "2026-06-29"
    assert captured["end_date"] == "2026-06-29"


def test_repair_lhb_source_and_features_runs_enrichment_then_feature_build():
    calls = []

    def enrichment_runner(**kwargs):
        calls.append(("enrichment", kwargs))
        return {"results": ["ok"]}

    def feature_runner(**kwargs):
        calls.append(("features", kwargs))
        return {
            "lhb_event_features": "frame",
            "paths": {"lhb_event_features": "/tmp/lhb_event_features_daily_sample.csv"},
        }

    result = repair_lhb_source_and_features(
        "2026-06-29",
        output_dir="/tmp/out",
        enrichment_runner=enrichment_runner,
        feature_runner=feature_runner,
    )

    assert result.status == RepairStatus.SUCCESS
    assert [call[0] for call in calls] == ["enrichment", "features"]
    assert result.artifact_paths == ["/tmp/lhb_event_features_daily_sample.csv"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_actions.py -q
```

Expected: FAIL because module is missing.

- [ ] **Step 3: Implement repair action wrappers**

Create `src/stock_research/eod_auto_repair_actions.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from stock_research.eod_auto_repair_models import RepairActionResult, RepairStatus


def repair_minute5_bars(
    trade_date: str,
    *,
    workers: int = 1,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    if int(workers) != 1:
        raise ValueError("Baostock minute backfill must use workers=1")
    result = runner(
        start_date=trade_date,
        end_date=trade_date,
        freq="5min",
        adjust_types=["raw", "qfq"],
        workers=1,
    )
    return RepairActionResult(
        name="repair_minute5_bars",
        status=RepairStatus.SUCCESS,
        message="minute5 repair submitted",
        metrics=dict(result or {}),
    )


def repair_lhb_source_and_features(
    trade_date: str,
    *,
    output_dir: str | Path,
    enrichment_runner: Callable[..., dict[str, Any]],
    feature_runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    out = Path(output_dir)
    enrichment_runner(
        dataset="lhb",
        start_date=trade_date,
        end_date=trade_date,
        output_dir=out / "free_enrichment_lhb",
        batch_size=1,
        sleep_seconds=0,
    )
    feature_result = feature_runner(
        start_date=trade_date,
        end_date=trade_date,
        ts_codes=None,
        output_dir=out,
    )
    paths = feature_result.get("paths") or {}
    artifact_paths = [str(value) for value in paths.values()]
    return RepairActionResult(
        name="repair_lhb_source_and_features",
        status=RepairStatus.SUCCESS,
        message="lhb source and features repaired",
        artifact_paths=artifact_paths,
    )
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_actions.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/eod_auto_repair_actions.py tests/test_eod_auto_repair_actions.py
git commit -m "feat: add eod repair action wrappers"
```

---

## Task 5: Orchestrator Core

**Files:**
- Create: `src/stock_research/eod_auto_repair.py`
- Test: `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write failing orchestrator tests**

```python
from stock_research.eod_auto_repair import run_eod_auto_repair
from stock_research.eod_auto_repair_models import RepairActionResult, RepairCheckResult, RepairStatus


def test_run_eod_auto_repair_runs_action_for_failed_check_then_rechecks():
    calls = []
    check_results = [
        RepairCheckResult("lhb_features", RepairStatus.FAILED, "missing", blocker=True),
        RepairCheckResult("lhb_features", RepairStatus.SUCCESS, "ready"),
    ]

    def check_plan_builder(trade_date):
        def run_check():
            calls.append("check")
            return check_results.pop(0)
        return [type("Check", (), {"name": "lhb_features", "run": run_check})()]

    def action_runner(trade_date, output_dir):
        calls.append("repair_lhb")
        return RepairActionResult("repair_lhb_source_and_features", RepairStatus.SUCCESS, "fixed")

    summary = run_eod_auto_repair(
        trade_date="2026-06-29",
        output_dir="/tmp/out",
        mode="repair",
        check_plan_builder=check_plan_builder,
        action_registry={"lhb_features": action_runner},
    )

    assert calls == ["check", "repair_lhb", "check"]
    assert summary.final_status == RepairStatus.SUCCESS
    assert summary.actions[0].name == "repair_lhb_source_and_features"


def test_run_eod_auto_repair_check_mode_does_not_run_actions():
    calls = []

    def check_plan_builder(trade_date):
        def run_check():
            return RepairCheckResult("strategy_publish", RepairStatus.FAILED, "missing", blocker=True)
        return [type("Check", (), {"name": "strategy_publish", "run": run_check})()]

    def action_runner(trade_date, output_dir):
        calls.append("repair")
        return RepairActionResult("publish_strategy_eod", RepairStatus.SUCCESS)

    summary = run_eod_auto_repair(
        trade_date="2026-06-29",
        output_dir="/tmp/out",
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={"strategy_publish": action_runner},
    )

    assert calls == []
    assert summary.final_status == RepairStatus.FAILED
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: FAIL because `stock_research.eod_auto_repair` is missing.

- [ ] **Step 3: Implement orchestration function**

Create `src/stock_research/eod_auto_repair.py`:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

from stock_research.eod_auto_repair_checks import build_check_plan
from stock_research.eod_auto_repair_models import (
    RepairActionResult,
    RepairCheckResult,
    RepairRunSummary,
    RepairStatus,
)


ActionRunner = Callable[[str, str | Path], RepairActionResult]


def _final_status(checks: list[RepairCheckResult]) -> RepairStatus:
    blockers = [check for check in checks if check.blocker and check.status != RepairStatus.SUCCESS]
    if blockers:
        return RepairStatus.FAILED
    degraded = [check for check in checks if check.status == RepairStatus.DEGRADED]
    if degraded:
        return RepairStatus.DEGRADED
    return RepairStatus.SUCCESS


def run_eod_auto_repair(
    *,
    trade_date: str,
    output_dir: str | Path,
    mode: str = "repair",
    check_plan_builder=build_check_plan,
    action_registry: dict[str, ActionRunner] | None = None,
) -> RepairRunSummary:
    if mode not in {"check", "repair", "publish-only"}:
        raise ValueError("mode must be check, repair, or publish-only")
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    checks_before = [check.run() for check in check_plan_builder(trade_date)]
    actions: list[RepairActionResult] = []
    registry = action_registry or {}
    if mode != "check":
        for check in checks_before:
            if check.status == RepairStatus.SUCCESS:
                continue
            runner = registry.get(check.name)
            if runner is None:
                continue
            actions.append(runner(trade_date, out))
    checks_after = [check.run() for check in check_plan_builder(trade_date)] if actions else checks_before
    return RepairRunSummary(
        trade_date=trade_date,
        mode=mode,
        final_status=_final_status(checks_after),
        checks_before=checks_before,
        actions=actions,
        checks_after=checks_after,
    )


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run EOD auto repair checks and actions.")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--mode", choices=["check", "repair", "publish-only"], default="repair")
    args = parser.parse_args(argv)
    summary = run_eod_auto_repair(
        trade_date=args.trade_date,
        output_dir=args.output_dir,
        mode=args.mode,
    )
    path = Path(args.output_dir) / "run_summary.json"
    path.write_text(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0 if summary.final_status in {RepairStatus.SUCCESS, RepairStatus.DEGRADED} else 2


if __name__ == "__main__":
    raise SystemExit(_main())
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py
git commit -m "feat: add eod auto repair orchestrator"
```

---

## Task 6: Register Real Repair Actions

**Files:**
- Modify: `src/stock_research/eod_auto_repair.py`
- Modify: `src/stock_research/eod_auto_repair_actions.py`
- Test: `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write failing test for default action registry**

Append:

```python
from stock_research.eod_auto_repair import build_default_action_registry


def test_default_action_registry_contains_repairable_checks():
    registry = build_default_action_registry(output_root="outputs")

    assert "minute5_bars" in registry
    assert "lhb_features" in registry
    assert "strategy_publish" in registry
    assert "market_monitor" in registry
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: FAIL because `build_default_action_registry` is missing.

- [ ] **Step 3: Add real action wrappers**

Add to `src/stock_research/eod_auto_repair_actions.py`:

```python
def repair_strategy_publish(
    trade_date: str,
    *,
    output_root: str | Path,
    publisher: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = publisher(trade_date=trade_date, output_root=output_root)
    return RepairActionResult(
        name="repair_strategy_publish",
        status=RepairStatus.SUCCESS,
        message="strategy publish complete",
        metrics={"review_rows": int(result.get("review_rows") or 0)},
        artifact_paths=[str(result.get("output_dir") or "")],
    )


def repair_market_monitor(
    trade_date: str,
    *,
    runner: Callable[..., dict[str, Any]],
) -> RepairActionResult:
    result = runner(trade_date=trade_date)
    return RepairActionResult(
        name="repair_market_monitor",
        status=RepairStatus.SUCCESS,
        message="market monitor refreshed",
        metrics=dict(result or {}),
    )
```

- [ ] **Step 4: Wire default registry**

Add to `src/stock_research/eod_auto_repair.py`:

```python
def build_default_action_registry(*, output_root: str | Path = "outputs") -> dict[str, ActionRunner]:
    from stock_research.free_enrichment_data import run_free_enrichment_backfill
    from stock_research.lhb_data import run_lhb_event_features_build
    from stock_research.strategy_eod_publish import publish_strategy_eod
    from stock_research.eod_auto_repair_actions import (
        repair_lhb_source_and_features,
        repair_market_monitor,
        repair_minute5_bars,
        repair_strategy_publish,
    )

    def lhb_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        return repair_lhb_source_and_features(
            trade_date,
            output_dir=output_dir,
            enrichment_runner=run_free_enrichment_backfill,
            feature_runner=run_lhb_event_features_build,
        )

    def strategy_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        return repair_strategy_publish(
            trade_date,
            output_root=output_root,
            publisher=publish_strategy_eod,
        )

    def market_monitor_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        from stock_research.dashboard.market_monitor import build_market_monitor_eod

        return repair_market_monitor(trade_date, runner=build_market_monitor_eod)

    def minute_action(trade_date: str, output_dir: str | Path) -> RepairActionResult:
        from stock_research.minute_backfill import run_baostock_minute_backfill

        return repair_minute5_bars(trade_date, workers=1, runner=run_baostock_minute_backfill)

    return {
        "minute5_bars": minute_action,
        "lhb_source": lhb_action,
        "lhb_features": lhb_action,
        "market_monitor": market_monitor_action,
        "strategy_publish": strategy_action,
        "review_queue": strategy_action,
    }
```

Update `_main` to pass `action_registry=build_default_action_registry(output_root="outputs")`.

- [ ] **Step 5: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py tests/test_eod_auto_repair_actions.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/eod_auto_repair.py src/stock_research/eod_auto_repair_actions.py tests/test_eod_auto_repair.py
git commit -m "feat: wire default eod repair actions"
```

---

## Task 7: Final Verification Report

**Files:**
- Modify: `src/stock_research/eod_auto_repair.py`
- Test: `tests/test_eod_auto_repair.py`

- [ ] **Step 1: Write failing test for report files**

Append:

```python
import json
from pathlib import Path


def test_run_eod_auto_repair_writes_json_and_markdown_report(tmp_path):
    def check_plan_builder(trade_date):
        def run_check():
            return RepairCheckResult("review_queue", RepairStatus.SUCCESS, "ready", metrics={"row_count": 14})
        return [type("Check", (), {"name": "review_queue", "run": run_check})()]

    summary = run_eod_auto_repair(
        trade_date="2026-06-29",
        output_dir=tmp_path,
        mode="check",
        check_plan_builder=check_plan_builder,
        action_registry={},
        write_reports=True,
    )

    payload = json.loads((tmp_path / "run_summary.json").read_text())
    report = (tmp_path / "run_report.md").read_text()
    assert payload["trade_date"] == "2026-06-29"
    assert summary.final_status == RepairStatus.SUCCESS
    assert "review_queue" in report
    assert "row_count" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: FAIL because `write_reports` is not accepted.

- [ ] **Step 3: Implement report writing**

Add helper functions to `src/stock_research/eod_auto_repair.py`:

```python
def _write_summary_files(summary: RepairRunSummary, output_dir: str | Path) -> None:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = summary.to_dict()
    (out / "run_summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# EOD Auto Repair Report {summary.trade_date}",
        "",
        f"- Mode: {summary.mode}",
        f"- Final status: {summary.final_status.value}",
        "",
        "## Checks After",
    ]
    for check in summary.checks_after:
        lines.append(f"- {check.name}: {check.status.value} {json.dumps(check.metrics, ensure_ascii=False)}")
    lines.append("")
    lines.append("## Actions")
    for action in summary.actions:
        lines.append(f"- {action.name}: {action.status.value} {json.dumps(action.metrics, ensure_ascii=False)}")
    (out / "run_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
```

Update `run_eod_auto_repair` signature:

```python
def run_eod_auto_repair(..., write_reports: bool = False) -> RepairRunSummary:
```

Before return:

```python
    if write_reports:
        _write_summary_files(summary, out)
    return summary
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/eod_auto_repair.py tests/test_eod_auto_repair.py
git commit -m "feat: write eod auto repair reports"
```

---

## Task 8: Cron Wrapper

**Files:**
- Create: `scripts/run_eod_auto_repair_cron.sh`
- Test: `tests/test_eod_auto_repair_scripts.py`

- [ ] **Step 1: Write failing test for wrapper contents**

```python
from pathlib import Path


def test_eod_auto_repair_cron_uses_module_entrypoint_and_lock():
    script = Path("scripts/run_eod_auto_repair_cron.sh").read_text()

    assert "python -m stock_research.eod_auto_repair" in script
    assert "flock" in script
    assert "--mode repair" in script
    assert "logs/eod_auto_repair" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_scripts.py -q
```

Expected: FAIL because script is missing.

- [ ] **Step 3: Create cron script**

Create `scripts/run_eod_auto_repair_cron.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${STOCK_RESEARCH_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${STOCK_RESEARCH_PYTHON:-$ROOT/.venv/bin/python}"
TRADE_DATE="${1:-$(date +%F)}"
LOG_DIR="$ROOT/logs/eod_auto_repair"
OUTPUT_DIR="$ROOT/outputs/research/eod_auto_repair/$TRADE_DATE"
LOCK_FILE="$ROOT/.locks/eod_auto_repair.lock"

mkdir -p "$LOG_DIR" "$OUTPUT_DIR" "$(dirname "$LOCK_FILE")"

cd "$ROOT"
flock -n "$LOCK_FILE" \
  rtk "$PYTHON" -m stock_research.eod_auto_repair \
    --trade-date "$TRADE_DATE" \
    --output-dir "$OUTPUT_DIR" \
    --mode repair \
  2>&1 | tee "$LOG_DIR/$TRADE_DATE.log"
```

- [ ] **Step 4: Make script executable**

Run:

```bash
rtk chmod +x scripts/run_eod_auto_repair_cron.sh
```

Expected: exit code 0.

- [ ] **Step 5: Run test**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_scripts.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_eod_auto_repair_cron.sh tests/test_eod_auto_repair_scripts.py
git commit -m "feat: add eod auto repair cron wrapper"
```

---

## Task 9: End-To-End Dry Run On 2026-06-29

**Files:**
- No code changes unless this task exposes bugs.

- [ ] **Step 1: Run check-only mode**

Run:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date 2026-06-29 \
  --output-dir outputs/research/eod_auto_repair/2026-06-29-check \
  --mode check
```

Expected:
- Creates `outputs/research/eod_auto_repair/2026-06-29-check/run_summary.json`.
- Exit code is `0` if ready/degraded, `2` if hard blockers remain.
- No repair action is executed.

- [ ] **Step 2: Run repair mode**

Run:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date 2026-06-29 \
  --output-dir outputs/research/eod_auto_repair/2026-06-29 \
  --mode repair
```

Expected:
- LHB source/features are ready.
- Strategy publish reports `review_rows >= 14`.
- Review queue API returns `trade_date=2026-06-29`.
- `run_report.md` lists any remaining degraded-only warnings such as known partial daily/minute coverage.

- [ ] **Step 3: Verify dashboard API review queue**

Run:

```bash
rtk curl --max-time 10 -sS -o /tmp/review_queue_check.json -w '%{http_code}\n' http://127.0.0.1:8765/api/review-queue
```

Expected: `200`.

Run:

```bash
rtk .venv/bin/python - <<'PY'
import json
payload=json.load(open('/tmp/review_queue_check.json'))
print(payload["trade_date"])
print({g["bucket"]: g["count"] for g in payload["groups"]})
PY
```

Expected output includes:

```text
2026-06-29
{'strategy:lhb_shortline': 4, 'strategy:mid_trend': 5, 'strategy:tech_bottleneck': 5}
```

- [ ] **Step 4: Commit only if fixes were needed**

If this task required code changes, run the affected tests again and commit those fixes.

---

## Task 10: Incident Regression Checks

**Files:**
- Modify: `src/stock_research/eod_auto_repair_checks.py`
- Test: `tests/test_eod_auto_repair_checks.py`

- [ ] **Step 1: Write failing tests for strategy group quality**

Append:

```python
from stock_research.eod_auto_repair_checks import (
    evaluate_review_queue_groups,
    evaluate_strategy_review_scores,
)


def test_evaluate_review_queue_groups_fails_identical_lhb_and_midtrend_assets():
    payload = {
        "trade_date": "2026-06-29",
        "groups": [
            {"bucket": "strategy:lhb_shortline", "count": 2, "items": [{"asset_id": "A"}, {"asset_id": "B"}]},
            {"bucket": "strategy:mid_trend", "count": 2, "items": [{"asset_id": "A"}, {"asset_id": "B"}]},
            {"bucket": "strategy:tech_bottleneck", "count": 1, "items": [{"asset_id": "C"}]},
        ],
    }

    result = evaluate_review_queue_groups(payload, trade_date="2026-06-29")

    assert result.status == RepairStatus.FAILED
    assert result.blocker is True
    assert "identical" in result.message


def test_evaluate_review_queue_groups_fails_zero_tech_bottleneck_count():
    payload = {
        "trade_date": "2026-06-29",
        "groups": [
            {"bucket": "strategy:lhb_shortline", "count": 4, "items": [{"asset_id": "A"}]},
            {"bucket": "strategy:mid_trend", "count": 5, "items": [{"asset_id": "B"}]},
            {"bucket": "strategy:tech_bottleneck", "count": 0, "items": []},
        ],
    }

    result = evaluate_review_queue_groups(payload, trade_date="2026-06-29")

    assert result.status == RepairStatus.FAILED
    assert "tech_bottleneck" in result.message


def test_evaluate_strategy_review_scores_fails_null_scores():
    rows = [
        {"strategy_id": "mid_trend", "asset_id": "CN:SH:603733", "score_total": None, "score_source": ""},
    ]

    result = evaluate_strategy_review_scores(rows, trade_date="2026-06-29")

    assert result.status == RepairStatus.FAILED
    assert result.metrics["null_score_rows"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py -q
```

Expected: FAIL because the incident regression helpers do not exist.

- [ ] **Step 3: Implement strategy group evaluators**

Add to `src/stock_research/eod_auto_repair_checks.py`:

```python
def evaluate_review_queue_groups(payload: dict[str, object], *, trade_date: str) -> RepairCheckResult:
    payload_trade_date = str(payload.get("trade_date") or "")
    groups = list(payload.get("groups") or [])
    by_bucket = {str(group.get("bucket") or ""): dict(group) for group in groups if isinstance(group, dict)}
    required = ["strategy:lhb_shortline", "strategy:mid_trend", "strategy:tech_bottleneck"]
    missing = [bucket for bucket in required if bucket not in by_bucket]
    counts = {bucket: int((by_bucket.get(bucket) or {}).get("count") or 0) for bucket in required}
    assets = {
        bucket: [str(item.get("asset_id") or "") for item in (by_bucket.get(bucket) or {}).get("items", [])]
        for bucket in required
    }
    failures = []
    if payload_trade_date != trade_date:
        failures.append(f"trade_date={payload_trade_date}")
    if missing:
        failures.append(f"missing={missing}")
    if counts.get("strategy:tech_bottleneck", 0) < 1:
        failures.append("tech_bottleneck count is zero")
    if assets.get("strategy:lhb_shortline") and assets.get("strategy:lhb_shortline") == assets.get("strategy:mid_trend"):
        failures.append("lhb_shortline and mid_trend assets are identical")
    metrics = {"counts": counts, "missing": missing}
    if failures:
        return RepairCheckResult("review_queue_groups", RepairStatus.FAILED, "; ".join(failures), metrics, blocker=True)
    return RepairCheckResult("review_queue_groups", RepairStatus.SUCCESS, "ready", metrics)


def evaluate_strategy_review_scores(rows: list[dict[str, object]], *, trade_date: str) -> RepairCheckResult:
    null_rows = [
        row
        for row in rows
        if str(row.get("trade_date") or trade_date) == trade_date
        and str(row.get("strategy_id") or "") in {"lhb_shortline", "mid_trend", "tech_bottleneck"}
        and row.get("score_total") in {None, ""}
    ]
    metrics = {"row_count": len(rows), "null_score_rows": len(null_rows)}
    if null_rows:
        return RepairCheckResult("strategy_review_scores", RepairStatus.FAILED, "strategy review has null scores", metrics, blocker=True)
    return RepairCheckResult("strategy_review_scores", RepairStatus.SUCCESS, "ready", metrics)
```

- [ ] **Step 4: Run tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_eod_auto_repair_checks.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/eod_auto_repair_checks.py tests/test_eod_auto_repair_checks.py
git commit -m "test: add eod incident regression checks"
```

---

## Task 11: Operator Runbook

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add runbook section**

Add:

```markdown
## EOD Auto Repair

Run diagnostics only:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/eod_auto_repair/YYYY-MM-DD-check \
  --mode check
```

Run diagnostics, repair, publish strategies, and verify:

```bash
rtk .venv/bin/python -m stock_research.eod_auto_repair \
  --trade-date YYYY-MM-DD \
  --output-dir outputs/research/eod_auto_repair/YYYY-MM-DD \
  --mode repair
```

Important safety rule: Baostock minute repair is always single-worker. Do not bypass this in cron or manual runs.

Primary outputs:

- `outputs/research/eod_auto_repair/YYYY-MM-DD/run_summary.json`
- `outputs/research/eod_auto_repair/YYYY-MM-DD/run_report.md`
- `outputs/research/strategy_daily_eod/YYYY-MM-DD/review_queue_strategy_manifest.csv`
```

- [ ] **Step 2: Run documentation sanity check**

Run:

```bash
rtk rg -n "EOD Auto Repair|Baostock minute repair is always single-worker" README.md
```

Expected: both strings are found.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document eod auto repair workflow"
```

---

## Acceptance Criteria

- `python -m stock_research.eod_auto_repair --mode check` runs without importing the broken top-level CLI.
- `--mode repair` can repair at least:
  - LHB source/features.
  - Strategy publish/review queue manifest.
  - Market monitor refresh.
  - Minute5 repair through a single-worker-only wrapper.
- The command writes `run_summary.json` and `run_report.md`.
- The final summary distinguishes hard blockers from degraded optional partials.
- Tests cover:
  - Serialization.
  - Check plan.
  - DB-backed check behavior via injected fetchers/loaders.
  - Baostock single-worker guard.
  - Orchestration order.
  - Report output.
  - Cron wrapper contents.
- Manual E2E on `2026-06-29` shows review queue date `2026-06-29` and three strategy groups populated.

---

## Follow-Up After MVP

- Add persistent action history into `ops.data_run_manifest` or a new `ops.eod_auto_repair_run` table.
- Add dashboard panel for the repair report.
- Add Feishu notification with status, blockers, and changed modules.
- Add cache invalidation or dashboard API refresh hook after strategy publish.
- Add SLA thresholds per module, for example minute5 missing assets under 1% is degraded instead of failed.
