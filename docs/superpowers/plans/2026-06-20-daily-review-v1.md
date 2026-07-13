# Daily Review v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `daily_review_v1` as a report-first, read-only CLI that generates Markdown, JSON, manifest, evidence payloads, and `report.report_run` registration without adding dashboard pages or any execution/broker state.

**Architecture:** Keep the implementation thin and testable. Add one pure workflow module that assembles a stable review contract from source payloads, one CLI module that loads payloads and writes artifacts, and one small contract/constants module that owns enums and normalization rules. Use golden fixtures to lock the JSON and Markdown surface before wiring the main CLI alias.

**Tech Stack:** Python 3.11+, argparse, json, pathlib, pandas where already used, pytest, existing `report_run_store`, existing `stock-research` CLI.

---

## File Structure

Create and modify only the files needed for the first phase:

```text
src/stock_research/reports/
├── daily_review_contract.py
├── daily_review_report_workflow.py
└── daily_review_report_cli.py

tests/
├── fixtures/daily_review_v1/
│   ├── source_payloads/
│   │   ├── data_readiness.json
│   │   ├── market_review.json
│   │   ├── lhb_review.json
│   │   ├── mid_trend_review.json
│   │   ├── technical_bottleneck_review.json
│   │   └── holding_reviews.json
│   ├── expected_daily_review.json
│   └── expected_daily_review.md
├── test_daily_review_report_workflow.py
├── test_daily_review_report_cli.py
└── test_factor_cli.py
```

Responsibilities:

- `daily_review_contract.py`: controlled enums, allowed actions, review priorities, helper normalization.
- `daily_review_report_workflow.py`: pure assembly, Markdown rendering, artifact writing, manifest creation, and optional report-run registration.
- `daily_review_report_cli.py`: module CLI parser plus runner integration against workflow.
- `tests/test_daily_review_report_workflow.py`: golden fixture coverage, multi-strategy holdings, partial readiness, and manual-only operator plan checks.
- `tests/test_daily_review_report_cli.py`: module CLI parser/runner tests and report-run registration.
- `tests/test_factor_cli.py`: main `stock-research run-daily-review-v1` parser acceptance and dispatch coverage.

---

### Task 1: Lock The Contract With Fixtures And Golden Tests

**Files:**
- Create: `tests/fixtures/daily_review_v1/source_payloads/data_readiness.json`
- Create: `tests/fixtures/daily_review_v1/source_payloads/market_review.json`
- Create: `tests/fixtures/daily_review_v1/source_payloads/lhb_review.json`
- Create: `tests/fixtures/daily_review_v1/source_payloads/mid_trend_review.json`
- Create: `tests/fixtures/daily_review_v1/source_payloads/technical_bottleneck_review.json`
- Create: `tests/fixtures/daily_review_v1/source_payloads/holding_reviews.json`
- Create: `tests/fixtures/daily_review_v1/expected_daily_review.json`
- Create: `tests/fixtures/daily_review_v1/expected_daily_review.md`
- Create: `tests/test_daily_review_report_workflow.py`

- [ ] **Step 1: Write source payload fixtures**

Create `tests/fixtures/daily_review_v1/source_payloads/data_readiness.json`:

```json
{
  "daily_bars": {
    "status": "ready",
    "required": true,
    "summary": "market_daily_bar ready for 2026-06-20",
    "freshness": {
      "latest_available_date": "2026-06-20",
      "expected_date": "2026-06-20",
      "is_fresh": true,
      "max_allowed_lag_days": 0
    },
    "confidence_impact": "none",
    "blocking_modules": [],
    "source_refs": ["ops.daily_pipeline_status"]
  },
  "lhb_feed": {
    "status": "missing",
    "required": false,
    "summary": "lhb payload missing for trade date",
    "freshness": {
      "latest_available_date": "2026-06-19",
      "expected_date": "2026-06-20",
      "is_fresh": false,
      "max_allowed_lag_days": 0
    },
    "confidence_impact": "LHB conclusion confidence reduced",
    "blocking_modules": ["lhb_review"],
    "source_refs": ["raw_lhb_payload"]
  }
}
```

Create `tests/fixtures/daily_review_v1/source_payloads/holding_reviews.json`:

```json
[
  {
    "trade_date": "2026-06-20",
    "strategy_id": "lhb",
    "asset_id": "CN:SH:600000",
    "entry_reason": "lhb_follow",
    "holding_logic": "shortline_event",
    "current_state": "watch",
    "risk_status": "elevated",
    "action": "manual_review",
    "exit_condition": "break_open_low",
    "evidence": {"bucket": "trial_list"}
  },
  {
    "trade_date": "2026-06-20",
    "strategy_id": "mid_trend",
    "asset_id": "CN:SH:600000",
    "entry_reason": "trend_hold",
    "holding_logic": "ma20_intact",
    "current_state": "healthy",
    "risk_status": "normal",
    "action": "hold",
    "exit_condition": "break_ma20",
    "evidence": {"bucket": "healthy"}
  }
]
```

Create `tests/fixtures/daily_review_v1/expected_daily_review.json`:

```json
{
  "trade_date": "2026-06-20",
  "report_type": "daily_review_v1",
  "schema_version": "daily_review_v1",
  "status": "partial",
  "warnings": ["source_missing:lhb_feed"]
}
```

Create `tests/fixtures/daily_review_v1/expected_daily_review.md`:

```md
# 2026-06-20 Daily Review

## Executive Summary

- Data status: partial
- Market status: defensive
- LHB conclusion: trial
- Mid Trend conclusion: hold core names
- Technical Bottleneck conclusion: monitor upgrades only
- P0 must-review: CN:SH:600000
- Forbidden actions: chase stale LHB names
```

- [ ] **Step 2: Write failing workflow tests**

Create `tests/test_daily_review_report_workflow.py`:

```python
import json
from pathlib import Path

from stock_research.reports.daily_review_report_workflow import (
    ACTION_VALUES,
    REVIEW_PRIORITY_VALUES,
    build_daily_review,
    write_daily_review_package,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "daily_review_v1"


def _read_json(name: str):
    return json.loads((FIXTURE_ROOT / "source_payloads" / name).read_text(encoding="utf-8"))


def test_build_daily_review_matches_golden_fixture():
    result = build_daily_review(
        trade_date="2026-06-20",
        run_id="daily_review_v1_20260620_2200",
        data_readiness=_read_json("data_readiness.json"),
        market_review=_read_json("market_review.json"),
        lhb_review=_read_json("lhb_review.json"),
        mid_trend_review=_read_json("mid_trend_review.json"),
        technical_bottleneck_review=_read_json("technical_bottleneck_review.json"),
        holding_reviews=_read_json("holding_reviews.json"),
    )

    expected = json.loads((FIXTURE_ROOT / "expected_daily_review.json").read_text(encoding="utf-8"))

    assert result["trade_date"] == expected["trade_date"]
    assert result["report_type"] == expected["report_type"]
    assert result["schema_version"] == expected["schema_version"]
    assert result["status"] == expected["status"]
    assert result["warnings"] == expected["warnings"]


def test_build_daily_review_keeps_same_asset_under_multiple_strategies():
    result = build_daily_review(
        trade_date="2026-06-20",
        run_id="daily_review_v1_20260620_2200",
        data_readiness=_read_json("data_readiness.json"),
        market_review=_read_json("market_review.json"),
        lhb_review=_read_json("lhb_review.json"),
        mid_trend_review=_read_json("mid_trend_review.json"),
        technical_bottleneck_review=_read_json("technical_bottleneck_review.json"),
        holding_reviews=_read_json("holding_reviews.json"),
    )

    matching = [row for row in result["holding_reviews"] if row["asset_id"] == "CN:SH:600000"]
    assert len(matching) == 2
    assert {row["strategy_id"] for row in matching} == {"lhb", "mid_trend"}


def test_write_daily_review_package_writes_golden_markdown(tmp_path):
    result = build_daily_review(
        trade_date="2026-06-20",
        run_id="daily_review_v1_20260620_2200",
        data_readiness=_read_json("data_readiness.json"),
        market_review=_read_json("market_review.json"),
        lhb_review=_read_json("lhb_review.json"),
        mid_trend_review=_read_json("mid_trend_review.json"),
        technical_bottleneck_review=_read_json("technical_bottleneck_review.json"),
        holding_reviews=_read_json("holding_reviews.json"),
    )

    paths = write_daily_review_package(result, output_root=tmp_path)
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    expected_prefix = (FIXTURE_ROOT / "expected_daily_review.md").read_text(encoding="utf-8").strip()

    assert markdown.startswith(expected_prefix)


def test_action_and_priority_sets_are_stable():
    assert ACTION_VALUES == {
        "no_action",
        "manual_review",
        "watch",
        "add_candidate",
        "hold",
        "warning",
        "reduce_review",
        "exit_review",
        "forbidden",
        "research_required",
    }
    assert REVIEW_PRIORITY_VALUES == {"P0", "P1", "P2", "P3"}
```

- [ ] **Step 3: Run the workflow tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_review_report_workflow.py -q
```

Expected: FAIL with `ModuleNotFoundError` or missing symbol errors because `daily_review_report_workflow.py` does not exist yet.

- [ ] **Step 4: Commit the fixture-first test scaffold**

```bash
git add tests/fixtures/daily_review_v1 tests/test_daily_review_report_workflow.py
git commit -m "test: add daily review v1 golden fixtures"
```

---

### Task 2: Implement The Daily Review Contract And Pure Workflow

**Files:**
- Create: `src/stock_research/reports/daily_review_contract.py`
- Create: `src/stock_research/reports/daily_review_report_workflow.py`
- Test: `tests/test_daily_review_report_workflow.py`

- [ ] **Step 1: Implement the contract module**

Create `src/stock_research/reports/daily_review_contract.py`:

```python
ACTION_VALUES = {
    "no_action",
    "manual_review",
    "watch",
    "add_candidate",
    "hold",
    "warning",
    "reduce_review",
    "exit_review",
    "forbidden",
    "research_required",
}

REVIEW_PRIORITY_VALUES = {"P0", "P1", "P2", "P3"}


def normalize_action(value: object, default: str = "manual_review") -> str:
    text = str(value or "").strip()
    return text if text in ACTION_VALUES else default


def normalize_review_priority(value: object, default: str = "P2") -> str:
    text = str(value or "").strip().upper()
    return text if text in REVIEW_PRIORITY_VALUES else default
```

- [ ] **Step 2: Implement pure review assembly**

Create `src/stock_research/reports/daily_review_report_workflow.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from stock_research.report_run_store import record_report_run
from stock_research.reports.daily_review_contract import (
    ACTION_VALUES,
    REVIEW_PRIORITY_VALUES,
    normalize_action,
    normalize_review_priority,
)


def build_daily_review(
    *,
    trade_date: str,
    run_id: str,
    data_readiness: dict[str, Any],
    market_review: dict[str, Any],
    lhb_review: dict[str, Any],
    mid_trend_review: dict[str, Any],
    technical_bottleneck_review: dict[str, Any],
    holding_reviews: list[dict[str, Any]],
) -> dict[str, Any]:
    warnings = _collect_readiness_warnings(data_readiness)
    status = "partial" if warnings else "success"
    holdings = [_normalize_holding_review(row) for row in holding_reviews]
    strategy_items = _build_strategy_items(lhb_review, mid_trend_review, technical_bottleneck_review, trade_date)
    return {
        "trade_date": trade_date,
        "run_id": run_id,
        "report_type": "daily_review_v1",
        "schema_version": "daily_review_v1",
        "status": status,
        "data_readiness": data_readiness,
        "market_review": market_review,
        "strategy_summaries": {
            "lhb": lhb_review,
            "mid_trend": mid_trend_review,
            "technical_bottleneck": technical_bottleneck_review,
        },
        "strategy_items": strategy_items,
        "holding_reviews": holdings,
        "operator_plan": {
            "mode": "manual_review_only",
            "overall_position_bias": market_review.get("target_exposure", ""),
            "must_check_before_open": [],
            "forbidden_actions": list(lhb_review.get("forbidden_actions", [])),
            "manual_decisions": [],
        },
        "next_day_plan": _build_next_day_plan(market_review, lhb_review, mid_trend_review, technical_bottleneck_review),
        "report_paths": {},
        "warnings": warnings,
    }
```

- [ ] **Step 3: Implement Markdown, manifest, evidence, and package writing**

Add to `src/stock_research/reports/daily_review_report_workflow.py`:

```python
def write_daily_review_package(
    review: dict[str, Any],
    *,
    output_root: str | Path,
    record_run: bool = False,
) -> dict[str, str]:
    output_dir = Path(output_root) / review["trade_date"]
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    review_path = output_dir / "daily_review.json"
    markdown_path = output_dir / "daily_review.md"
    manifest_path = output_dir / "manifest.json"
    operator_plan_path = output_dir / "operator_plan_template.json"

    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(render_daily_review_markdown(review), encoding="utf-8")
    operator_plan_path.write_text(
        json.dumps(build_operator_plan_template(review), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_evidence_files(review, evidence_dir)
    manifest = build_manifest(review, review_path, markdown_path, manifest_path, operator_plan_path, evidence_dir)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if record_run:
        record_report_run(
            trade_date=review["trade_date"],
            report_type="daily_review_v1",
            report_paths=manifest["report_paths"],
            status=review["status"],
            metadata={"schema_version": review["schema_version"], "warnings": review["warnings"]},
        )

    return manifest["report_paths"]
```

- [ ] **Step 4: Run workflow tests to verify they pass**

Run:

```bash
.venv/bin/pytest tests/test_daily_review_report_workflow.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the workflow implementation**

```bash
git add src/stock_research/reports/daily_review_contract.py src/stock_research/reports/daily_review_report_workflow.py tests/test_daily_review_report_workflow.py
git commit -m "feat: add daily review v1 workflow"
```

---

### Task 3: Add The Module CLI And Report-Run Integration Tests

**Files:**
- Create: `src/stock_research/reports/daily_review_report_cli.py`
- Create: `tests/test_daily_review_report_cli.py`
- Test: `tests/test_daily_review_report_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_daily_review_report_cli.py`:

```python
from pathlib import Path

from stock_research.reports.daily_review_report_cli import build_parser, run_daily_review_report


def test_build_parser_accepts_record_run_flags():
    args = build_parser().parse_args(
        [
            "--trade-date",
            "2026-06-20",
            "--output-root",
            "/tmp/reports",
            "--apply-report-run-schema",
            "--record-run",
        ]
    )

    assert args.trade_date == "2026-06-20"
    assert args.output_root == "/tmp/reports"
    assert args.apply_report_run_schema is True
    assert args.record_run is True


def test_run_daily_review_report_writes_expected_files(tmp_path, monkeypatch):
    payload = {
        "data_readiness": {},
        "market_review": {"target_exposure": "defensive"},
        "lhb_review": {"forbidden_actions": ["chase stale LHB names"]},
        "mid_trend_review": {},
        "technical_bottleneck_review": {},
        "holding_reviews": [],
    }

    monkeypatch.setattr(
        "stock_research.reports.daily_review_report_cli.load_daily_review_inputs",
        lambda trade_date: payload,
    )

    result = run_daily_review_report(
        trade_date="2026-06-20",
        output_root=tmp_path,
        apply_report_run_schema_first=False,
        record_run=False,
    )

    assert Path(result["report_paths"]["json_path"]).exists()
    assert Path(result["report_paths"]["markdown_path"]).exists()
    assert Path(result["report_paths"]["manifest_path"]).exists()
```

- [ ] **Step 2: Run CLI tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_daily_review_report_cli.py -q
```

Expected: FAIL because `daily_review_report_cli.py` does not exist yet.

- [ ] **Step 3: Implement the module CLI**

Create `src/stock_research/reports/daily_review_report_cli.py`:

```python
import argparse
from pathlib import Path
from typing import Any

from stock_research.report_run_store import apply_report_run_schema
from stock_research.reports.daily_review_report_workflow import build_daily_review, write_daily_review_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stock_research.reports.daily_review_report_cli")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--output-root", default="/Users/xiwei/stock_research/reports/daily_review")
    parser.add_argument("--apply-report-run-schema", action="store_true")
    parser.add_argument("--record-run", action="store_true")
    return parser


def load_daily_review_inputs(trade_date: str) -> dict[str, Any]:
    return {
        "data_readiness": {},
        "market_review": {},
        "lhb_review": {},
        "mid_trend_review": {},
        "technical_bottleneck_review": {},
        "holding_reviews": [],
    }
```

- [ ] **Step 4: Finish the runner and main entrypoint**

Add to `src/stock_research/reports/daily_review_report_cli.py`:

```python
def run_daily_review_report(
    *,
    trade_date: str,
    output_root: str | Path,
    apply_report_run_schema_first: bool = False,
    record_run: bool = False,
) -> dict[str, Any]:
    if apply_report_run_schema_first:
        apply_report_run_schema()

    payload = load_daily_review_inputs(trade_date)
    review = build_daily_review(
        trade_date=trade_date,
        run_id=f"daily_review_v1_{trade_date.replace('-', '')}_2200",
        data_readiness=payload["data_readiness"],
        market_review=payload["market_review"],
        lhb_review=payload["lhb_review"],
        mid_trend_review=payload["mid_trend_review"],
        technical_bottleneck_review=payload["technical_bottleneck_review"],
        holding_reviews=payload["holding_reviews"],
    )
    report_paths = write_daily_review_package(review, output_root=output_root, record_run=record_run)
    return {"review": review, "report_paths": report_paths}


def main(runner=run_daily_review_report) -> None:
    args = build_parser().parse_args()
    result = runner(
        trade_date=args.trade_date,
        output_root=Path(args.output_root),
        apply_report_run_schema_first=args.apply_report_run_schema,
        record_run=args.record_run,
    )
    for key, value in result["report_paths"].items():
        print(f"daily_review_v1|{key}|{value}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run CLI tests to verify they pass**

Run:

```bash
.venv/bin/pytest tests/test_daily_review_report_cli.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit the module CLI**

```bash
git add src/stock_research/reports/daily_review_report_cli.py tests/test_daily_review_report_cli.py
git commit -m "feat: add daily review v1 module cli"
```

---

### Task 4: Wire The Main `stock-research` CLI Alias

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Add a failing parser test for the new command**

Add to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_run_daily_review_v1_command():
    args = build_parser().parse_args(
        [
            "run-daily-review-v1",
            "--trade-date",
            "2026-06-20",
            "--output-root",
            "/tmp/daily-review",
            "--apply-report-run-schema",
            "--record-run",
        ]
    )

    assert args.command == "run-daily-review-v1"
    assert args.trade_date == "2026-06-20"
    assert args.output_root == "/tmp/daily-review"
    assert args.apply_report_run_schema is True
    assert args.record_run is True
```

- [ ] **Step 2: Run the parser test to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -k run_daily_review_v1_command -q
```

Expected: FAIL because `run-daily-review-v1` is not registered.

- [ ] **Step 3: Register the parser and dispatch branch**

Modify `src/stock_research/cli.py` near the daily research report parser:

```python
daily_review_v1 = subparsers.add_parser("run-daily-review-v1")
daily_review_v1.add_argument("--trade-date", required=True)
daily_review_v1.add_argument("--output-root", default="/Users/xiwei/stock_research/reports/daily_review")
daily_review_v1.add_argument("--apply-report-run-schema", action="store_true")
daily_review_v1.add_argument("--record-run", action="store_true")
```

Modify the command dispatch branch:

```python
elif args.command == "run-daily-review-v1":
    from stock_research.reports.daily_review_report_cli import run_daily_review_report

    result = run_daily_review_report(
        trade_date=args.trade_date,
        output_root=args.output_root,
        apply_report_run_schema_first=args.apply_report_run_schema,
        record_run=args.record_run,
    )
    for key, value in result["report_paths"].items():
        print(f"daily_review_v1|{key}|{value}")
```

- [ ] **Step 4: Run the parser test to verify it passes**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -k run_daily_review_v1_command -q
```

Expected: PASS.

- [ ] **Step 5: Commit the main CLI wiring**

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add daily review v1 main cli command"
```

---

### Task 5: Add End-To-End Artifact And Drift Protection Coverage

**Files:**
- Modify: `tests/test_daily_review_report_workflow.py`
- Modify: `tests/test_daily_review_report_cli.py`

- [ ] **Step 1: Add exact JSON drift assertions**

Append to `tests/test_daily_review_report_workflow.py`:

```python
def test_build_daily_review_exact_json_golden(tmp_path):
    result = build_daily_review(
        trade_date="2026-06-20",
        run_id="daily_review_v1_20260620_2200",
        data_readiness=_read_json("data_readiness.json"),
        market_review=_read_json("market_review.json"),
        lhb_review=_read_json("lhb_review.json"),
        mid_trend_review=_read_json("mid_trend_review.json"),
        technical_bottleneck_review=_read_json("technical_bottleneck_review.json"),
        holding_reviews=_read_json("holding_reviews.json"),
    )

    actual = tmp_path / "actual_daily_review.json"
    actual.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    expected = (FIXTURE_ROOT / "expected_daily_review.json").read_text(encoding="utf-8")

    assert actual.read_text(encoding="utf-8") == expected
```

- [ ] **Step 2: Add report-run registration coverage**

Append to `tests/test_daily_review_report_cli.py`:

```python
def test_run_daily_review_report_records_report_run(tmp_path, monkeypatch):
    calls = {}

    monkeypatch.setattr(
        "stock_research.reports.daily_review_report_cli.load_daily_review_inputs",
        lambda trade_date: {
            "data_readiness": {},
            "market_review": {"target_exposure": "defensive"},
            "lhb_review": {"forbidden_actions": []},
            "mid_trend_review": {},
            "technical_bottleneck_review": {},
            "holding_reviews": [],
        },
    )
    monkeypatch.setattr(
        "stock_research.reports.daily_review_report_workflow.record_report_run",
        lambda **kwargs: calls.setdefault("record_run", kwargs) or "daily-review-run-id",
    )

    run_daily_review_report(
        trade_date="2026-06-20",
        output_root=tmp_path,
        apply_report_run_schema_first=False,
        record_run=True,
    )

    assert calls["record_run"]["report_type"] == "daily_review_v1"
    assert calls["record_run"]["trade_date"] == "2026-06-20"
```

- [ ] **Step 3: Run the focused test set**

Run:

```bash
.venv/bin/pytest tests/test_daily_review_report_workflow.py tests/test_daily_review_report_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Run the CLI parser regression check**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -k "daily_review_v1 or run_daily_review_v1_command" -q
```

Expected: PASS.

- [ ] **Step 5: Commit the final coverage pass**

```bash
git add tests/test_daily_review_report_workflow.py tests/test_daily_review_report_cli.py
git commit -m "test: add daily review v1 drift protection coverage"
```

---

## Self-Review

- Spec coverage: data readiness freshness/impact/blockers, action enum, review priority, multi-strategy holdings, manual operator template, Executive Summary, report-run registration, and golden fixtures are each mapped to at least one task.
- Placeholder scan: no `TODO`, `TBD`, or “implement later” instructions remain.
- Type consistency: `action` uses one enum set everywhere; `review_priority` uses `P0`-`P3`; `decision_status` uses `pending`/`confirmed`/`skipped`/`invalidated`; the CLI command name is consistently `run-daily-review-v1`.
