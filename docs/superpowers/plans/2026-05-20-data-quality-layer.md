# Data Quality Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-pass unified Data Quality Layer that aggregates existing `data_audit`, `finance_audit`, and `research_preflight` checks behind one stable contract and one new CLI entrypoint.

**Architecture:** Add a new `data_quality.py` orchestration module that calls the existing leaf checks, normalizes their status/shape into one report object, and formats both summary and per-check output. Wire that module into `cli.py` as a new `data-quality` command while keeping the existing leaf commands unchanged.

**Tech Stack:** Python 3, `argparse`, existing `stock_research` modules, `pytest`, monkeypatch-based unit tests

---

## File Structure

- Create: `src/stock_research/data_quality.py`
  - Own the unified report contract, status normalization, summary calculation, and stable text formatting.
- Modify: `src/stock_research/cli.py`
  - Add the `data-quality` parser entry near the existing `data-audit` / `finance-audit` / `research-preflight` commands.
  - Add the runtime dispatch branch near the existing audit/preflight branches.
- Create: `tests/test_data_quality.py`
  - Cover report shape, status normalization, preflight aggregation, optional industry-membership inclusion, and line formatting.
- Modify: `tests/test_factor_cli.py`
  - Add parser acceptance coverage and CLI output / exit-code coverage for `data-quality`.

The plan keeps `src/stock_research/data_audit.py`, `src/stock_research/finance_audit.py`, and `src/stock_research/research_preflight.py` as unchanged leaf-check modules unless a tiny compatibility helper becomes unavoidable during implementation.

### Task 1: Add The Unified Data Quality Module

**Files:**
- Create: `src/stock_research/data_quality.py`
- Create: `tests/test_data_quality.py`
- Reference: `src/stock_research/data_audit.py`
- Reference: `src/stock_research/finance_audit.py`
- Reference: `src/stock_research/research_preflight.py`

- [ ] **Step 1: Write the failing module tests**

Add `tests/test_data_quality.py` with focused tests that lock the unified contract before any implementation:

```python
import stock_research.data_quality as data_quality


def test_run_data_quality_normalizes_leaf_checks(monkeypatch):
    monkeypatch.setattr(
        data_quality,
        "run_data_audit",
        lambda **kwargs: [
            {
                "dataset": "market_daily_bar",
                "status": "short_history",
                "rows": 10,
                "date_count": 2,
                "min_date": "2024-01-01",
                "max_date": "2024-01-02",
            },
            {
                "dataset": "factor.factor_approval",
                "status": "empty",
                "rows": 0,
                "date_count": 0,
                "min_date": None,
                "max_date": None,
            },
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "summarize_finance_coverage",
        lambda **kwargs: [
            {"check": "missing_balance_sheet", "status": "blocked", "rows": 2},
            {"check": "announcement_before_report_period", "status": "warning", "rows": 1},
        ],
    )
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 122,
            "horizons": [5, 10],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: {
            "status": "ok",
            "factor_date_count": 122,
            "factor_complete_date_count": 122,
            "missing_horizons": [],
            "short_label_horizons": [],
            "required_factor_names": ["ret_20"],
            "unavailable_factor_names": [],
            "reasons": [],
        },
    )

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10],
        factor_names=["ret_20"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=False,
    )

    assert report["overall_status"] == "blocked"
    assert report["blocked_checks"] == ["factor.factor_approval", "missing_balance_sheet"]
    assert report["warning_checks"] == ["market_daily_bar", "announcement_before_report_period"]
    assert report["checks"][0]["kind"] == "data_audit"
    assert report["checks"][0]["status"] == "warning"
    assert report["checks"][0]["metrics"]["rows"] == 10
```

```python
def test_run_data_quality_adds_preflight_and_optional_membership(monkeypatch):
    monkeypatch.setattr(data_quality, "run_data_audit", lambda **kwargs: [])
    monkeypatch.setattr(data_quality, "summarize_finance_coverage", lambda **kwargs: [])
    monkeypatch.setattr(
        data_quality,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 80,
            "horizons": [5, 10, 20, 60],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_factor_label_coverage",
        lambda **kwargs: {
            "status": "blocked",
            "factor_date_count": 50,
            "factor_complete_date_count": 10,
            "missing_horizons": [20, 60],
            "short_label_horizons": [5],
            "required_factor_names": ["ret_20"],
            "unavailable_factor_names": ["late_factor"],
            "reasons": ["missing_label_horizons"],
        },
    )
    monkeypatch.setattr(
        data_quality,
        "check_industry_membership_coverage",
        lambda **kwargs: {
            "status": "blocked",
            "market_rows": 100,
            "covered_rows": 70,
            "missing_rows": 30,
            "date_count": 2,
        },
    )

    report = data_quality.run_data_quality(
        expected_start_date="1990-12-01",
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10, 20, 60],
        factor_names=["ret_20", "late_factor"],
        calc_version="v1",
        min_label_dates=20,
        require_industry_membership=True,
    )

    check_names = [item["check_name"] for item in report["checks"]]
    assert "latest_common_label_date" in check_names
    assert "factor_label_coverage" in check_names
    assert "industry_membership_coverage" in check_names
```

```python
def test_formatters_emit_stable_summary_and_check_lines():
    summary = data_quality.format_data_quality_summary_line(
        {
            "overall_status": "warning",
            "checks": [{}, {}, {}],
            "blocked_checks": [],
            "warning_checks": ["market_daily_bar"],
        }
    )
    check_line = data_quality.format_data_quality_check_line(
        {
            "check_name": "factor_label_coverage",
            "status": "blocked",
            "kind": "research_preflight",
            "metrics": {"factor_date_count": 0},
        }
    )

    assert summary == "data_quality|summary|warning|checks|3|blocked|0|warning|1"
    assert check_line == (
        "data_quality|factor_label_coverage|blocked|kind|research_preflight|"
        "factor_date_count|0"
    )
```

- [ ] **Step 2: Run the new module test file and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_data_quality.py -q
```

Expected:

```text
ERROR tests/test_data_quality.py
E   ModuleNotFoundError: No module named 'stock_research.data_quality'
```

- [ ] **Step 3: Write the minimal unified implementation**

Create `src/stock_research/data_quality.py` with a stable public surface and explicit normalization helpers:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from stock_research.data_audit import run_data_audit
from stock_research.finance_audit import summarize_finance_coverage
from stock_research.factor_config import candidate_factor_names
from stock_research.research_preflight import (
    check_factor_label_coverage,
    check_industry_membership_coverage,
    find_latest_common_label_date,
)


def normalize_data_audit_status(status: str) -> str:
    mapping = {
        "ok": "ok",
        "short_history": "warning",
        "empty": "blocked",
    }
    return mapping[status]


def normalize_leaf_check(check_name: str, kind: str, status: str, metrics: dict[str, Any], details: dict[str, Any]) -> dict[str, Any]:
    return {
        "check_name": check_name,
        "status": status,
        "kind": kind,
        "source": kind,
        "metrics": metrics,
        "details": details,
    }


def run_data_quality(
    expected_start_date: str,
    start_date: str,
    end_date: str,
    horizons: list[int],
    factor_names: list[str] | None,
    calc_version: str,
    min_label_dates: int,
    require_industry_membership: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    factors = factor_names or candidate_factor_names()
    checks.extend(_build_data_audit_checks(expected_start_date=expected_start_date))
    checks.extend(_build_finance_audit_checks())
    checks.extend(
        _build_research_preflight_checks(
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            factor_names=factors,
            calc_version=calc_version,
            min_label_dates=min_label_dates,
            require_industry_membership=require_industry_membership,
        )
    )
    blocked_checks = [item["check_name"] for item in checks if item["status"] == "blocked"]
    warning_checks = [item["check_name"] for item in checks if item["status"] == "warning"]
    overall_status = "blocked" if blocked_checks else "warning" if warning_checks else "ok"
    return {
        "overall_status": overall_status,
        "generated_at": datetime.now().astimezone().isoformat(),
        "checks": checks,
        "blocked_checks": blocked_checks,
        "warning_checks": warning_checks,
    }
```

Also implement:

- `_build_data_audit_checks(...)`
- `_build_finance_audit_checks()`
- `_build_research_preflight_checks(...)`
- `format_data_quality_summary_line(report)`
- `format_data_quality_check_line(check)`
- `iter_data_quality_lines(report)`

The preflight builder must always emit:

- `latest_common_label_date`
- `factor_label_coverage`

and only emit:

- `industry_membership_coverage`

when `require_industry_membership` is `True`.

For the `latest_common_label_date` check, treat:

- `date_count > 0` and non-null date as `ok`
- null latest date as `blocked`

For the text formatter, keep the first four stable fields exactly:

```python
f"data_quality|{check['check_name']}|{check['status']}|kind|{check['kind']}"
```

then append scalar metrics in insertion order.

- [ ] **Step 4: Run the module tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_data_quality.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit the module slice**

Run:

```bash
git add tests/test_data_quality.py src/stock_research/data_quality.py
git commit -m "feat: add unified data quality layer"
```

### Task 2: Wire The New CLI Command

**Files:**
- Modify: `src/stock_research/cli.py:26-31`
- Modify: `src/stock_research/cli.py:574-577`
- Modify: `src/stock_research/cli.py:892-903`
- Modify: `src/stock_research/cli.py:1674-1842`
- Modify: `tests/test_factor_cli.py:2127-2287`
- Modify: `tests/test_factor_cli.py:2600-2630`

- [ ] **Step 1: Write the failing CLI parser and runtime tests**

Add these tests to `tests/test_factor_cli.py` near the existing audit/preflight coverage:

```python
def test_cli_accepts_data_quality_command():
    args = build_parser().parse_args(
        [
            "data-quality",
            "--expected-start-date",
            "1990-12-01",
            "--start-date",
            "2024-01-01",
            "--horizons",
            "5,10,20,60",
            "--factor-names",
            "ret_20,qlib_ret_5",
            "--min-label-dates",
            "20",
            "--require-industry-membership",
            "--json",
        ]
    )

    assert args.command == "data-quality"
    assert args.expected_start_date == "1990-12-01"
    assert args.start_date == "2024-01-01"
    assert args.horizons == [5, 10, 20, 60]
    assert args.factor_names == ["ret_20", "qlib_ret_5"]
    assert args.min_label_dates == 20
    assert args.require_industry_membership is True
    assert args.json is True
```

```python
def test_data_quality_cli_prints_summary_and_check_lines(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_data_quality",
        lambda **kwargs: {
            "overall_status": "warning",
            "checks": [
                {
                    "check_name": "market_daily_bar",
                    "status": "warning",
                    "kind": "data_audit",
                    "metrics": {"rows": 10},
                    "details": {},
                }
            ],
            "blocked_checks": [],
            "warning_checks": ["market_daily_bar"],
            "generated_at": "2026-05-20T12:00:00+08:00",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "data-quality", "--start-date", "2024-01-01"],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "data_quality|summary|warning|checks|1|blocked|0|warning|1",
        "data_quality|market_daily_bar|warning|kind|data_audit|rows|10",
    ]
```

```python
def test_data_quality_cli_prints_json_and_exits_nonzero_when_blocked(monkeypatch, capsys):
    import json
    import pytest
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "run_data_quality",
        lambda **kwargs: {
            "overall_status": "blocked",
            "checks": [],
            "blocked_checks": ["factor_label_coverage"],
            "warning_checks": [],
            "generated_at": "2026-05-20T12:00:00+08:00",
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "data-quality", "--start-date", "2024-01-01", "--json"],
    )

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["overall_status"] == "blocked"
    assert payload["blocked_checks"] == ["factor_label_coverage"]
```

- [ ] **Step 2: Run the targeted CLI tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "data_quality"
```

Expected:

```text
FAILED tests/test_factor_cli.py::test_cli_accepts_data_quality_command
FAILED tests/test_factor_cli.py::test_data_quality_cli_prints_summary_and_check_lines
FAILED tests/test_factor_cli.py::test_data_quality_cli_prints_json_and_exits_nonzero_when_blocked
```

- [ ] **Step 3: Implement the new parser and dispatch branch**

Update `src/stock_research/cli.py` in three places:

1. Import the new functions near the existing audit imports:

```python
from stock_research.data_quality import (
    format_data_quality_check_line,
    format_data_quality_summary_line,
    run_data_quality,
)
```

2. Add a new parser next to `data-audit` and `finance-audit`, reusing the existing preflight options:

```python
data_quality = subparsers.add_parser("data-quality")
data_quality.add_argument("--expected-start-date", default="1990-12-01")
data_quality.add_argument("--start-date")
data_quality.add_argument("--end-date")
data_quality.add_argument("--horizons", type=parse_research_horizons, default=[5, 10, 20, 60])
data_quality.add_argument("--factor-names", type=parse_factor_names)
data_quality.add_argument("--calc-version", default="v1")
data_quality.add_argument("--min-label-dates", type=int, default=20)
data_quality.add_argument("--require-industry-membership", action="store_true")
data_quality.add_argument("--json", action="store_true")
```

3. Add a runtime branch before or after `research-preflight` that:

- derives `start_date` from `load_market_date_bounds()` when missing
- calls `run_data_quality(...)`
- prints JSON with `json.dumps(report, ensure_ascii=False)`
- otherwise prints one summary line followed by each check line
- raises `SystemExit(1)` when `report["overall_status"] == "blocked"`

Use this shape:

```python
elif args.command == "data-quality":
    start_date = args.start_date
    if start_date is None:
        bounds = load_market_date_bounds()
        start_date = bounds["start_date"]
    report = run_data_quality(
        expected_start_date=args.expected_start_date,
        start_date=start_date,
        end_date=args.end_date,
        horizons=args.horizons,
        factor_names=args.factor_names,
        calc_version=args.calc_version,
        min_label_dates=args.min_label_dates,
        require_industry_membership=args.require_industry_membership,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(format_data_quality_summary_line(report))
        for check in report["checks"]:
            print(format_data_quality_check_line(check))
    if report["overall_status"] == "blocked":
        raise SystemExit(1)
```

- [ ] **Step 4: Run the targeted CLI tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_factor_cli.py -q -k "data_quality"
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit the CLI slice**

Run:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add data quality CLI aggregation"
```

### Task 3: Regression And Exit-Code Verification

**Files:**
- Modify: `tests/test_factor_cli.py` if any assertion text needs small stabilization after full-suite runs
- No new production files expected

- [ ] **Step 1: Add one integration-style regression test for market-start fallback**

Extend `tests/test_factor_cli.py` with one more focused test to keep the new command aligned with existing `research-preflight` behavior:

```python
def test_data_quality_cli_uses_market_start_when_start_omitted(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    calls = []
    monkeypatch.setattr(
        cli,
        "load_market_date_bounds",
        lambda: {"start_date": "1990-12-19", "end_date": "2026-05-08", "date_count": 8200},
    )
    monkeypatch.setattr(
        cli,
        "run_data_quality",
        lambda **kwargs: calls.append(kwargs)
        or {
            "overall_status": "ok",
            "checks": [],
            "blocked_checks": [],
            "warning_checks": [],
            "generated_at": "2026-05-20T12:00:00+08:00",
        },
    )
    monkeypatch.setattr(sys, "argv", ["stock-research", "data-quality"])

    cli.main()

    assert calls[0]["start_date"] == "1990-12-19"
    assert capsys.readouterr().out.strip() == "data_quality|summary|ok|checks|0|blocked|0|warning|0"
```

- [ ] **Step 2: Run the focused data-quality test slice**

Run:

```bash
.venv/bin/pytest tests/test_data_quality.py tests/test_factor_cli.py -q -k "data_quality or research_preflight or data_audit"
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 3: Run the full direct regression set**

Run:

```bash
.venv/bin/pytest tests/test_data_quality.py tests/test_data_audit.py tests/test_finance_audit.py tests/test_research_preflight.py tests/test_factor_cli.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 4: Review the final diff before commit**

Run:

```bash
git diff -- src/stock_research/data_quality.py src/stock_research/cli.py tests/test_data_quality.py tests/test_factor_cli.py
```

Verify:

- old commands are unchanged
- new command only adds behavior, not refactors unrelated branches
- summary line and per-check line shapes match the spec
- no database writes were introduced

- [ ] **Step 5: Commit the regression hardening**

Run:

```bash
git add tests/test_factor_cli.py tests/test_data_quality.py src/stock_research/data_quality.py src/stock_research/cli.py
git commit -m "test: harden data quality aggregation coverage"
```

## Self-Review

### Spec coverage

- Unified module and report contract: Task 1
- Status normalization and `overall_status`: Task 1
- New `data-quality` CLI entrypoint: Task 2
- JSON/text output and exit codes: Task 2
- Market-start fallback and regression protection: Task 3
- Preserve old commands and avoid new checks: enforced by Task 3 diff review and limited file list

### Placeholder scan

- No `TBD`, `TODO`, or “implement later” placeholders remain
- Every task includes exact files, commands, and concrete code snippets
- Later tasks only reference functions introduced in earlier tasks

### Type consistency

- Unified public function name: `run_data_quality`
- Stable formatter names: `format_data_quality_summary_line`, `format_data_quality_check_line`
- Unified report keys: `overall_status`, `checks`, `blocked_checks`, `warning_checks`, `generated_at`
- Unified check keys: `check_name`, `status`, `kind`, `source`, `metrics`, `details`
