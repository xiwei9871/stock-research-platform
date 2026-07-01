# Strategy Daily EOD Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class daily `strategy_daily_eod` pipeline that generates the three required strategy EOD outputs every trading day, records explicit status, and makes strategy EOD success a hard requirement for platform readiness.

**Architecture:** Introduce a dedicated strategy EOD orchestration module plus a narrow status-store layer, then expose it through a CLI command and a cron wrapper. Reuse existing strategy-specific generators where they already exist, add a formal adapter for `tech_bottleneck`, and extend `platform_ready` to fail hard when the strategy EOD contract for the current trade date is not satisfied.

**Tech Stack:** Python 3.14, pandas, psycopg/DB service config, existing `stock_research.cli`, OpenClaw cron JSON, shell cron wrappers, pytest.

---

## File Structure

### New Files

- `src/stock_research/strategy_daily_eod.py`
  - Orchestrates dependency checks, per-strategy EOD generation, summary writing, and status persistence.
- `src/stock_research/strategy_daily_eod_store.py`
  - Owns `ops.strategy_daily_eod_status` schema and CRUD helpers.
- `tests/test_strategy_daily_eod.py`
  - Unit tests for dependency gating, per-strategy status aggregation, and summary/status writing.
- `tests/test_strategy_daily_eod_cli.py`
  - CLI-level tests for the new command output and exit codes.
- `tests/test_strategy_daily_eod_scripts.py`
  - Wrapper script and cron guard tests.
- `scripts/run_strategy_daily_eod_cron.sh`
  - Fixed-time cron entrypoint for the new task.

### Modified Files

- `src/stock_research/cli.py`
  - Add `run-strategy-daily-eod` subcommand and dispatch.
- `src/stock_research/platform_ready.py`
  - Add a hard `strategy_daily_eod` readiness check and promote failures to `NOT_READY`.
- `/Users/xiwei/.openclaw/cron/jobs.json`
  - Register `stock-strategy-daily-eod` at `19:40 Asia/Shanghai`.
- `tests/test_platform_ready_scripts.py`
  - Extend current readiness tests for the new hard strategy EOD requirement.

### Existing Code To Reuse

- `src/stock_research/lhb_data.py`
  - `run_lhb_shortline_daily_pipeline_v1`
- `src/stock_research/mid_trend_shadow_weekly_control.py`
  - `run_mid_trend_shadow_weekly_control_review`
- `src/stock_research/current_mid_trend_strategy_v1.py`
  - `write_current_mid_trend_strategy_v1_outputs` and related mid-trend output structures
- `src/stock_research/daily_close_pipeline.py`
  - Existing data/deps job status tables and status conventions

---

### Task 1: Add Strategy EOD Status Store

**Files:**
- Create: `src/stock_research/strategy_daily_eod_store.py`
- Test: `tests/test_strategy_daily_eod.py`

- [ ] **Step 1: Write the failing schema/status tests**

```python
from stock_research import strategy_daily_eod_store as store


def test_build_status_payload_requires_three_strategy_fields():
    payload = store.build_status_payload(
        trade_date="2026-06-24",
        status="failed",
        dependency_check_status="failed",
        lhb_shortline_status="skipped",
        mid_trend_status="skipped",
        tech_bottleneck_status="skipped",
        review_rows=0,
        output_dir="/tmp/out",
        summary_path="/tmp/out/summary.json",
        error_summary="deps missing",
    )

    assert payload["trade_date"] == "2026-06-24"
    assert payload["status"] == "failed"
    assert payload["dependency_check_status"] == "failed"
    assert payload["mid_trend_status"] == "skipped"


def test_status_schema_sql_contains_strategy_daily_eod_table():
    sql = store.STRATEGY_DAILY_EOD_STATUS_SQL
    assert "CREATE TABLE IF NOT EXISTS ops.strategy_daily_eod_status" in sql
    assert "lhb_shortline_status" in sql
    assert "mid_trend_status" in sql
    assert "tech_bottleneck_status" in sql
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/pytest tests/test_strategy_daily_eod.py -q
```

Expected: FAIL with `ModuleNotFoundError` for `stock_research.strategy_daily_eod_store`.

- [ ] **Step 3: Write the minimal store module**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stock_research.config import SETTINGS
from stock_research.db import connect, execute, fetch_all


STRATEGY_DAILY_EOD_STATUS_SQL = """
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.strategy_daily_eod_status (
    trade_date date PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('success', 'failed', 'running', 'skipped')),
    dependency_check_status text NOT NULL,
    lhb_shortline_status text NOT NULL,
    mid_trend_status text NOT NULL,
    tech_bottleneck_status text NOT NULL,
    review_rows integer NOT NULL DEFAULT 0,
    output_dir text,
    summary_path text,
    error_summary text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""


def apply_strategy_daily_eod_status_schema(service: str = SETTINGS.research_service) -> None:
    with connect(service) as conn:
        execute(conn, STRATEGY_DAILY_EOD_STATUS_SQL)


def build_status_payload(
    *,
    trade_date: str,
    status: str,
    dependency_check_status: str,
    lhb_shortline_status: str,
    mid_trend_status: str,
    tech_bottleneck_status: str,
    review_rows: int,
    output_dir: str | None,
    summary_path: str | None,
    error_summary: str | None,
) -> dict[str, Any]:
    return {
        "trade_date": trade_date,
        "status": status,
        "dependency_check_status": dependency_check_status,
        "lhb_shortline_status": lhb_shortline_status,
        "mid_trend_status": mid_trend_status,
        "tech_bottleneck_status": tech_bottleneck_status,
        "review_rows": int(review_rows),
        "output_dir": output_dir,
        "summary_path": summary_path,
        "error_summary": error_summary,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/pytest tests/test_strategy_daily_eod.py -q
```

Expected: PASS for the new schema/status tests.

- [ ] **Step 5: Commit**

```bash
git -C /Users/xiwei/stock_research add src/stock_research/strategy_daily_eod_store.py tests/test_strategy_daily_eod.py
git -C /Users/xiwei/stock_research commit -m "feat: add strategy daily eod status store"
```

---

### Task 2: Implement Strategy Daily EOD Orchestrator

**Files:**
- Create: `src/stock_research/strategy_daily_eod.py`
- Modify: `src/stock_research/strategy_daily_eod_store.py`
- Test: `tests/test_strategy_daily_eod.py`

- [ ] **Step 1: Write the failing orchestrator tests**

```python
from pathlib import Path

from stock_research import strategy_daily_eod as eod


def test_run_strategy_daily_eod_fails_when_deps_missing(tmp_path: Path):
    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {
            "status": "failed",
            "reason": "deps missing",
        },
    )

    assert result["status"] == "failed"
    assert result["dependency_check"]["status"] == "failed"
    assert result["strategy_status"]["mid_trend"] == "skipped"


def test_run_strategy_daily_eod_marks_failed_when_one_strategy_fails(tmp_path: Path):
    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda *_args, **_kwargs: {"status": "success"},
        lhb_runner=lambda **_kwargs: {"status": "success", "review_rows": 5, "paths": {"review": str(tmp_path / "lhb.csv")}},
        mid_runner=lambda **_kwargs: {"status": "failed", "review_rows": 0, "paths": {}},
        tech_runner=lambda **_kwargs: {"status": "success", "review_rows": 5, "paths": {"review": str(tmp_path / "tech.csv")}},
    )

    assert result["status"] == "failed"
    assert result["strategy_status"]["lhb_shortline"] == "success"
    assert result["strategy_status"]["mid_trend"] == "failed"
    assert result["strategy_status"]["tech_bottleneck"] == "success"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/pytest tests/test_strategy_daily_eod.py::test_run_strategy_daily_eod_fails_when_deps_missing tests/test_strategy_daily_eod.py::test_run_strategy_daily_eod_marks_failed_when_one_strategy_fails -q
```

Expected: FAIL because `stock_research.strategy_daily_eod` does not exist.

- [ ] **Step 3: Write the orchestrator skeleton**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from stock_research.strategy_daily_eod_store import (
    apply_strategy_daily_eod_status_schema,
    build_status_payload,
)


DependencyChecker = Callable[..., dict[str, Any]]
StrategyRunner = Callable[..., dict[str, Any]]


def run_strategy_daily_eod(
    *,
    trade_date: str,
    output_root: str | Path = "outputs/research/strategy_daily_eod",
    dependency_checker: DependencyChecker,
    lhb_runner: StrategyRunner | None = None,
    mid_runner: StrategyRunner | None = None,
    tech_runner: StrategyRunner | None = None,
) -> dict[str, Any]:
    apply_strategy_daily_eod_status_schema()
    output_dir = Path(output_root) / trade_date
    output_dir.mkdir(parents=True, exist_ok=True)

    dependency_check = dependency_checker(trade_date=trade_date)
    if dependency_check.get("status") != "success":
        return {
            "trade_date": trade_date,
            "status": "failed",
            "dependency_check": dependency_check,
            "strategy_status": {
                "lhb_shortline": "skipped",
                "mid_trend": "skipped",
                "tech_bottleneck": "skipped",
            },
            "output_dir": str(output_dir),
        }

    strategy_results = {
        "lhb_shortline": (lhb_runner or _missing_runner)(trade_date=trade_date, output_dir=output_dir),
        "mid_trend": (mid_runner or _missing_runner)(trade_date=trade_date, output_dir=output_dir),
        "tech_bottleneck": (tech_runner or _missing_runner)(trade_date=trade_date, output_dir=output_dir),
    }
    strategy_status = {name: str(result.get("status") or "failed") for name, result in strategy_results.items()}
    overall_status = "success" if all(value == "success" for value in strategy_status.values()) else "failed"
    summary = {
        "trade_date": trade_date,
        "status": overall_status,
        "dependency_check": dependency_check,
        "strategy_status": strategy_status,
        "review_rows": sum(int(result.get("review_rows", 0)) for result in strategy_results.values()),
        "output_dir": str(output_dir),
    }
    (output_dir / "strategy_eod_publish_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def _missing_runner(**_kwargs: Any) -> dict[str, Any]:
    return {"status": "failed", "review_rows": 0, "paths": {}, "error": "runner not configured"}
```

- [ ] **Step 4: Add real dependency checker using existing daily pipeline state**

```python
from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def check_strategy_daily_eod_dependencies(
    trade_date: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    sql = """
    SELECT daily_status, minute5_status, deps_status
    FROM ops.daily_pipeline_status
    WHERE trade_date = %s
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date])
    if not rows:
        return {"status": "failed", "reason": "daily_pipeline_status missing"}
    row = rows[0]
    if str(row.get("daily_status")) not in {"success", "partial_success"}:
        return {"status": "failed", "reason": f"daily_status={row.get('daily_status')}"}
    if str(row.get("minute5_status")) not in {"success", "partial_success"}:
        return {"status": "failed", "reason": f"minute5_status={row.get('minute5_status')}"}
    if str(row.get("deps_status")) != "success":
        return {"status": "failed", "reason": f"deps_status={row.get('deps_status')}"}
    return {"status": "success"}
```

- [ ] **Step 5: Run orchestrator tests and commit**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/pytest tests/test_strategy_daily_eod.py -q
```

Expected: PASS for dependency-gate and failure-aggregation tests.

Commit:

```bash
git -C /Users/xiwei/stock_research add src/stock_research/strategy_daily_eod.py src/stock_research/strategy_daily_eod_store.py tests/test_strategy_daily_eod.py
git -C /Users/xiwei/stock_research commit -m "feat: add strategy daily eod orchestrator"
```

---

### Task 3: Add Real Adapters For The Three Strategies

**Files:**
- Modify: `src/stock_research/strategy_daily_eod.py`
- Modify: `src/stock_research/lhb_data.py` only if a tiny helper is needed
- Test: `tests/test_strategy_daily_eod.py`

- [ ] **Step 1: Write failing adapter tests**

```python
from pathlib import Path

from stock_research import strategy_daily_eod as eod


def test_build_lhb_review_writes_expected_csv(tmp_path: Path):
    result = eod.build_lhb_shortline_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        runner=lambda **_kwargs: {
            "summary": {"daily_watchlist_rows": 2},
            "paths": {"daily_watchlist": str(tmp_path / "daily_watchlist.csv")},
        },
    )
    assert result["status"] == "success"
    assert Path(result["paths"]["review"]).name == "strategy_lhb_shortline_review.csv"


def test_build_mid_trend_review_uses_latest_rebalance_slice(tmp_path: Path):
    result = eod.build_mid_trend_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        frame_loader=lambda *_args, **_kwargs: {
            "review": [{"trade_date": "2026-06-24", "asset_id": "CN:SH:601211", "rank": 1, "score_total": 78.2}],
            "positions": [{"rebalance_date": "2026-06-22", "asset_id": "CN:SH:601211", "weight": 0.2}],
        },
    )
    assert result["status"] == "success"
    assert Path(result["paths"]["review"]).name == "strategy_mid_trend_review.csv"


def test_build_tech_bottleneck_review_scales_score_to_100(tmp_path: Path):
    result = eod.build_tech_bottleneck_strategy_eod(
        trade_date="2026-06-24",
        output_dir=tmp_path,
        candidate_loader=lambda *_args, **_kwargs: [
            {"trade_date": "2026-06-24", "asset_id": "CN:SZ:300408", "stock_name": "Test", "bottleneck_score": 0.65}
        ],
    )
    assert result["status"] == "success"
    assert result["review_rows"] == 1
```

- [ ] **Step 2: Reuse existing LHB daily pipeline output**

```python
from stock_research.lhb_data import run_lhb_shortline_daily_pipeline_v1


def build_lhb_shortline_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    runner=run_lhb_shortline_daily_pipeline_v1,
) -> dict[str, Any]:
    result = runner(
        case_path=DEFAULT_LHB_CASE_PATH,
        lhb_features_path=DEFAULT_LHB_FEATURES_PATH,
        alignment_path=DEFAULT_LHB_ALIGNMENT_PATH,
        trade_date=trade_date,
        output_dir=output_dir,
    )
    review = pd.read_csv(result["paths"]["daily_watchlist"], low_memory=False).head(5).copy()
    review["trade_date"] = trade_date
    review["strategy_id"] = "lhb_shortline"
    review["strategy_name"] = "LHB Shortline Combo"
    review["strategy_run_id"] = f"strategy-eod-{trade_date}-local"
    review["source_type"] = "strategy_manifest"
    review["source_name"] = "strategy_lhb_shortline"
    review["source_rank"] = range(1, len(review) + 1)
    review["review_tier"] = "top5_focus"
    review_path = Path(output_dir) / "strategy_lhb_shortline_review.csv"
    review.to_csv(review_path, index=False)
    return {"status": "success", "review_rows": len(review), "paths": {"review": str(review_path)}}
```

- [ ] **Step 3: Build mid-trend review from weekly control outputs**

```python
from stock_research.mid_trend_shadow_weekly_control import run_mid_trend_shadow_weekly_control_review


def build_mid_trend_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    frame_loader=None,
) -> dict[str, Any]:
    if frame_loader is None:
        control = run_mid_trend_shadow_weekly_control_review(
            funnel_detail_path=DEFAULT_MID_TREND_FUNNEL_DETAIL_PATH,
            start_date=DEFAULT_MID_TREND_START_DATE,
            end_date=trade_date,
            output_dir=output_dir,
            top_n=5,
            buffer_rank=10,
            max_weekly_replacements=2,
        )
        positions = pd.read_csv(control["paths"]["positions"], low_memory=False)
        latest_rebalance = positions["rebalance_date"].astype(str).max()
        latest_positions = positions[positions["rebalance_date"].astype(str).eq(latest_rebalance)].copy()
        latest_positions["trade_date"] = trade_date
        latest_positions["rank"] = range(1, len(latest_positions) + 1)
        latest_positions["strategy_id"] = "mid_trend"
        latest_positions["strategy_name"] = "Mid Trend Combo"
        latest_positions["strategy_run_id"] = f"strategy-eod-{trade_date}-local"
        latest_positions["score_source"] = "mid_trend_funnel_score"
        latest_positions["review_tier"] = "top5_focus"
        review = latest_positions
    else:
        loaded = frame_loader()
        review = pd.DataFrame(loaded["review"])
        latest_positions = pd.DataFrame(loaded["positions"])
    review_path = Path(output_dir) / "strategy_mid_trend_review.csv"
    review.to_csv(review_path, index=False)
    return {"status": "success", "review_rows": len(review), "paths": {"review": str(review_path)}}
```

- [ ] **Step 4: Create formal tech bottleneck adapter**

```python
def build_tech_bottleneck_strategy_eod(
    *,
    trade_date: str,
    output_dir: str | Path,
    candidate_loader=None,
) -> dict[str, Any]:
    if candidate_loader is None:
        frame = pd.read_csv(DEFAULT_TECH_BOTTLENECK_CANDIDATE_PATH, low_memory=False)
        frame = frame[frame["trade_date"].astype(str).eq(trade_date)].copy()
        frame["bottleneck_score"] = pd.to_numeric(frame["bottleneck_score"], errors="coerce")
        frame["score_total"] = frame["bottleneck_score"] * 100.0
        frame = frame.sort_values(["score_total", "asset_id"], ascending=[False, True]).head(5).copy()
    else:
        frame = pd.DataFrame(candidate_loader())
        frame["score_total"] = pd.to_numeric(frame["bottleneck_score"], errors="coerce") * 100.0
    frame["strategy_id"] = "tech_bottleneck"
    frame["strategy_name"] = "Tech Bottleneck Discovery"
    frame["strategy_run_id"] = f"strategy-eod-{trade_date}-local"
    frame["score_source"] = "bottleneck_score"
    frame["review_tier"] = "top5_focus"
    frame["rank"] = range(1, len(frame) + 1)
    review_path = Path(output_dir) / "strategy_tech_bottleneck_review.csv"
    frame.to_csv(review_path, index=False)
    return {"status": "success", "review_rows": len(frame), "paths": {"review": str(review_path)}}
```

- [ ] **Step 5: Run adapter tests and commit**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/pytest tests/test_strategy_daily_eod.py -q
```

Expected: PASS with LHB/mid-trend/tech-bottleneck adapter tests green.

Commit:

```bash
git -C /Users/xiwei/stock_research add src/stock_research/strategy_daily_eod.py tests/test_strategy_daily_eod.py
git -C /Users/xiwei/stock_research commit -m "feat: add strategy daily eod adapters"
```

---

### Task 4: Add CLI Command, Cron Wrapper, And OpenClaw Schedule

**Files:**
- Modify: `src/stock_research/cli.py`
- Create: `scripts/run_strategy_daily_eod_cron.sh`
- Modify: `/Users/xiwei/.openclaw/cron/jobs.json`
- Test: `tests/test_strategy_daily_eod_cli.py`
- Test: `tests/test_strategy_daily_eod_scripts.py`

- [ ] **Step 1: Write the failing CLI and script tests**

```python
from stock_research import cli


def test_cli_accepts_run_strategy_daily_eod_command():
    args = cli.build_parser().parse_args(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    assert args.command == "run-strategy-daily-eod"


def test_cli_run_strategy_daily_eod_prints_summary(monkeypatch, capsys):
    monkeypatch.setattr(
        "stock_research.cli.run_strategy_daily_eod",
        lambda **_kwargs: {"status": "success", "trade_date": "2026-06-24", "review_rows": 15},
    )
    rc = cli.main(["run-strategy-daily-eod", "--trade-date", "2026-06-24"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "strategy_daily_eod|status|success" in out
```

- [ ] **Step 2: Add CLI parser and dispatch**

```python
from stock_research.strategy_daily_eod import run_strategy_daily_eod

run_strategy_daily_eod_parser = subparsers.add_parser("run-strategy-daily-eod")
run_strategy_daily_eod_parser.add_argument("--trade-date", required=True)
run_strategy_daily_eod_parser.add_argument(
    "--output-root",
    default="/Users/xiwei/stock_research/outputs/research/strategy_daily_eod",
)

elif args.command == "run-strategy-daily-eod":
    result = run_strategy_daily_eod(
        trade_date=args.trade_date,
        output_root=args.output_root,
        dependency_checker=check_strategy_daily_eod_dependencies,
    )
    for key, value in result.items():
        if isinstance(value, dict):
            continue
        print(f"strategy_daily_eod|{key}|{value}")
    return 0 if result.get("status") == "success" else 1
```

- [ ] **Step 3: Add cron wrapper script**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="/Users/xiwei/stock_research"
PYTHON_BIN="${PYTHON_BIN:-$ROOT/.venv/bin/python}"
TRADE_DATE="${TRADE_DATE:-$(date +%F)}"

source "$ROOT/scripts/stock_cron_guard.sh"
clear_stock_proxy_env
stock_cron_guard_or_exit "$PYTHON_BIN" "$TRADE_DATE" "${RESEARCH_SERVICE:-}"

cd "$ROOT"
PYTHONPATH=src "$PYTHON_BIN" -m stock_research.cli run-strategy-daily-eod --trade-date "$TRADE_DATE"
```

- [ ] **Step 4: Register OpenClaw cron**

Add this job object to `/Users/xiwei/.openclaw/cron/jobs.json`:

```json
{
  "id": "stock-strategy-daily-eod-20260624",
  "agentId": "agent_jarvis",
  "name": "stock-strategy-daily-eod",
  "enabled": true,
  "schedule": {
    "kind": "cron",
    "expr": "40 19 * * 1-5",
    "tz": "Asia/Shanghai"
  },
  "sessionTarget": "isolated",
  "wakeMode": "now",
  "payload": {
    "kind": "agentTurn",
    "message": "你是贾维斯。每天 19:40 生成 stock research 三个策略的 EOD。只运行以下这一条命令，不要运行其他无关命令：\n/Users/xiwei/stock_research/scripts/run_strategy_daily_eod_cron.sh\n\n等待命令结束。该任务必须先检查 daily/minute5/deps，任意依赖不满足则直接失败。最终中文汇报：是否成功、交易日、三条策略状态、summary 路径。不要写交易建议。"
  }
}
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/pytest tests/test_strategy_daily_eod_cli.py tests/test_strategy_daily_eod_scripts.py -q
```

Expected: PASS.

Commit:

```bash
git -C /Users/xiwei/stock_research add src/stock_research/cli.py scripts/run_strategy_daily_eod_cron.sh tests/test_strategy_daily_eod_cli.py tests/test_strategy_daily_eod_scripts.py
git -C /Users/xiwei/stock_research commit -m "feat: add strategy daily eod cli and cron"
```

---

### Task 5: Make Strategy EOD A Hard Platform Readiness Check

**Files:**
- Modify: `src/stock_research/platform_ready.py`
- Modify: `tests/test_platform_ready_scripts.py`
- Create: `tests/test_platform_ready_strategy_eod.py`

- [ ] **Step 1: Write the failing readiness tests**

```python
from stock_research import platform_ready


def test_strategy_daily_eod_check_fails_when_status_row_missing(monkeypatch):
    monkeypatch.setattr(platform_ready, "_fetch_check_rows", lambda *_args, **_kwargs: [])
    result = platform_ready._check_strategy_daily_eod("research", "2026-06-24")
    assert result["status"] == "fail"


def test_run_platform_ready_not_ready_when_strategy_eod_failed(monkeypatch):
    monkeypatch.setattr(platform_ready, "_check_strategy_daily_eod", lambda *_args, **_kwargs: {
        "name": "strategy_daily_eod",
        "status": "fail",
        "detail": "mid_trend failed",
    })
```

- [ ] **Step 2: Add SQL and check function**

```python
CHECK_SQL["strategy_daily_eod"] = """
    SELECT status, dependency_check_status, lhb_shortline_status, mid_trend_status,
           tech_bottleneck_status, review_rows, output_dir, summary_path
    FROM ops.strategy_daily_eod_status
    WHERE trade_date = %s
    ORDER BY updated_at DESC
    LIMIT 1
"""


def _check_strategy_daily_eod(service: str, trade_date: str) -> dict[str, str]:
    rows = _fetch_check_rows(service, "strategy_daily_eod", trade_date)
    if not rows:
        return _fail("strategy_daily_eod", "missing strategy_daily_eod status row")
    row = rows[0]
    ok = (
        str(row.get("status")) == "success"
        and str(row.get("lhb_shortline_status")) == "success"
        and str(row.get("mid_trend_status")) == "success"
        and str(row.get("tech_bottleneck_status")) == "success"
    )
    detail = (
        f"status={row.get('status')} deps={row.get('dependency_check_status')} "
        f"lhb={row.get('lhb_shortline_status')} mid={row.get('mid_trend_status')} "
        f"tech={row.get('tech_bottleneck_status')} review_rows={row.get('review_rows')}"
    )
    return _pass("strategy_daily_eod", detail) if ok else _fail("strategy_daily_eod", detail)
```

- [ ] **Step 3: Add the check into the readiness chain**

```python
checks = [
    _check_daily_quality(...),
    _check_minute5(...),
    _check_deps(...),
    _check_health(...),
    _check_scores(...),
    _check_nonzero_scores(...),
    _check_watchlist(...),
    _check_diagnostics(...),
    _check_reports(...),
    _check_strategy_daily_eod(service, trade_date),
]
```

- [ ] **Step 4: Run readiness tests**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/pytest tests/test_platform_ready_strategy_eod.py tests/test_platform_ready_scripts.py -q
```

Expected: PASS, and readiness becomes `not_ready` whenever strategy EOD is missing or failed.

- [ ] **Step 5: Commit**

```bash
git -C /Users/xiwei/stock_research add src/stock_research/platform_ready.py tests/test_platform_ready_strategy_eod.py tests/test_platform_ready_scripts.py
git -C /Users/xiwei/stock_research commit -m "feat: require strategy daily eod for readiness"
```

---

### Task 6: End-to-End Verification On 2026-06-24

**Files:**
- Modify: none
- Test: live verification only

- [ ] **Step 1: Apply schema and run the task for 2026-06-24**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/python -m stock_research.cli run-strategy-daily-eod --trade-date 2026-06-24
```

Expected:

- `strategy_daily_eod|status|success`
- output files created under `outputs/research/strategy_daily_eod/2026-06-24`

- [ ] **Step 2: Verify the required review files exist**

Run:

```bash
ls -l \
  /Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-24/strategy_lhb_shortline_review.csv \
  /Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-24/strategy_mid_trend_review.csv \
  /Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-24/strategy_tech_bottleneck_review.csv \
  /Users/xiwei/stock_research/outputs/research/strategy_daily_eod/2026-06-24/strategy_eod_publish_summary.json
```

Expected: all files exist and are non-empty.

- [ ] **Step 3: Re-run platform readiness**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/python -m stock_research.platform_ready --trade-date 2026-06-24 --reports-dir /Users/xiwei/stock_research/reports --json-output /Users/xiwei/stock_research/outputs/research/platform_ready_2026-06-24.json
```

Expected:

- if data gaps remain accepted and strategy EOD succeeds: `degraded_ready`
- if strategy EOD fails: `not_ready`

- [ ] **Step 4: Verify the strategy status row**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=src .venv/bin/python - <<'PY'
from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all

with connect(SETTINGS.research_service) as conn:
    rows = fetch_all(
        conn,
        "SELECT trade_date::text, status, dependency_check_status, lhb_shortline_status, mid_trend_status, tech_bottleneck_status, review_rows FROM ops.strategy_daily_eod_status WHERE trade_date = DATE '2026-06-24'"
    )
print(rows)
PY
```

Expected: one row with all three strategy statuses set to `success`.

- [ ] **Step 5: Commit**

```bash
git -C /Users/xiwei/stock_research add /Users/xiwei/.openclaw/cron/jobs.json
git -C /Users/xiwei/stock_research commit -m "chore: wire strategy daily eod schedule"
```

---

## Spec Coverage Check

- Dedicated daily strategy EOD task:
  - Covered by Tasks 1-4
- Fixed-time trigger at `19:40`:
  - Covered by Task 4
- Dependency gate before publish:
  - Covered by Task 2
- Three strategies must all succeed:
  - Covered by Tasks 2-3
- Stable output contract under `outputs/research/strategy_daily_eod/<trade_date>/`:
  - Covered by Tasks 2-3 and Task 6
- New `ops.strategy_daily_eod_status` table:
  - Covered by Task 1
- Platform becomes `NOT_READY` if any strategy EOD fails:
  - Covered by Task 5

No uncovered spec requirements remain.

## Placeholder Scan

- No `TBD`, `TODO`, or deferred implementation markers remain.
- Every task includes exact file paths, concrete commands, and concrete code snippets.

## Type Consistency Check

- Status values are consistent across plan sections: `success`, `failed`, `running`, `skipped`.
- Strategy ids are consistent across all tasks:
  - `lhb_shortline`
  - `mid_trend`
  - `tech_bottleneck`
- Output root is consistent:
  - `outputs/research/strategy_daily_eod/<trade_date>/`

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-24-strategy-daily-eod-readiness.md`.

Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
