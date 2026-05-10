# Historical Factor Research Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the missing research loop from historical factor backfill to label coverage checks, batch factor approval, approved-only scoring, TopN backtest, and daily automation readiness.

**Architecture:** Keep each stage independently runnable and testable. Add range/backfill helpers and preflight checks as separate modules, then wire them into existing CLIs without changing automatic trading boundaries. Do not overwrite existing local ingest/finance changes; stage only task-specific hunks.

**Tech Stack:** Python, pandas, PostgreSQL via existing `stock_research.db`, pytest, existing factor/scoring/backtest/report modules.

---

## File Structure

- `src/stock_research/factor_backfill.py`  
  New range runner for `build_and_store_factor_daily`.
- `tests/test_factor_backfill.py`  
  Tests range planning and per-date execution behavior.
- `src/stock_research/research_preflight.py`  
  New read-only coverage checks for factor dates, label dates, score rows, industry/index/feature inputs.
- `tests/test_research_preflight.py`  
  Tests SQL shape and actionable status output.
- `src/stock_research/factor_eval_batch.py`  
  Extend current batch gate with candidate defaults and no-overlap diagnostics.
- `tests/test_factor_eval_batch.py`  
  Extend existing tests for empty/insufficient coverage behavior.
- `src/stock_research/approved_scoring_workflow.py`  
  New workflow: score approved factors for a date range, then optionally run TopN research workflow.
- `tests/test_approved_scoring_workflow.py`  
  Tests approved-only scoring over a range and workflow handoff.
- `src/stock_research/cron_install_plan.py`  
  New helper that renders manual cron/OpenClaw install commands without mutating the system.
- `tests/test_cron_install_plan.py`  
  Tests generated command text.
- `src/stock_research/cli.py`  
  Add commands only after focused tests; preserve unrelated local ingest-loop hunks.
- `docs/daily-factor-pipeline-runbook.md`  
  Document operational sequence.
- `docs/astock-research-platform-v1.md`  
  Update completed/remaining status.

---

### Task 1: Historical Factor Backfill Module

**Files:**
- Create: `src/stock_research/factor_backfill.py`
- Create: `tests/test_factor_backfill.py`

- [ ] **Step 1: Write failing range date test**

```python
from stock_research.factor_backfill import build_trade_date_range


def test_build_trade_date_range_returns_inclusive_daily_strings():
    assert build_trade_date_range("2026-05-01", "2026-05-03") == [
        "2026-05-01",
        "2026-05-02",
        "2026-05-03",
    ]
```

- [ ] **Step 2: Run failing test**

Run: `.venv/bin/pytest tests/test_factor_backfill.py -q`  
Expected: FAIL because `stock_research.factor_backfill` does not exist.

- [ ] **Step 3: Implement date range helper**

```python
import pandas as pd


def build_trade_date_range(start_date: str, end_date: str) -> list[str]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if end < start:
        raise ValueError("end_date must be >= start_date")
    return [value.date().isoformat() for value in pd.date_range(start, end, freq="D")]
```

- [ ] **Step 4: Run passing test**

Run: `.venv/bin/pytest tests/test_factor_backfill.py -q`  
Expected: PASS.

- [ ] **Step 5: Write failing backfill execution test**

```python
from stock_research import factor_backfill


def test_backfill_factor_daily_range_runs_each_date(monkeypatch):
    calls = []

    monkeypatch.setattr(
        factor_backfill,
        "build_and_store_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 10,
    )

    result = factor_backfill.backfill_factor_daily_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        lookback_bars=130,
        industry_system="csrc",
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert list(result["factor_rows"]) == [10, 10]
    assert calls[0]["trade_date"] == "2026-05-01"
    assert calls[1]["trade_date"] == "2026-05-02"
```

- [ ] **Step 6: Implement range runner**

Add to `src/stock_research/factor_backfill.py`:

```python
from stock_research.factor_pipeline import build_and_store_factor_daily


def backfill_factor_daily_range(
    start_date: str,
    end_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
) -> pd.DataFrame:
    rows = []
    for trade_date in build_trade_date_range(start_date, end_date):
        count = build_and_store_factor_daily(
            trade_date=trade_date,
            lookback_bars=lookback_bars,
            industry_system=industry_system,
        )
        rows.append({"trade_date": trade_date, "factor_rows": count})
    return pd.DataFrame(rows)
```

- [ ] **Step 7: Verify task**

Run: `.venv/bin/pytest tests/test_factor_backfill.py -q`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/stock_research/factor_backfill.py tests/test_factor_backfill.py
git commit -m "Add historical factor backfill"
```

---

### Task 2: Research Coverage Preflight

**Files:**
- Create: `src/stock_research/research_preflight.py`
- Create: `tests/test_research_preflight.py`

- [ ] **Step 1: Write failing coverage check test**

```python
import stock_research.research_preflight as research_preflight


def test_check_factor_label_coverage_reports_overlap(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        if "factor.factor_daily" in sql:
            return [{"min_date": "2026-05-01", "max_date": "2026-05-10", "date_count": 10}]
        return [{"horizon": 5, "min_date": "2026-05-01", "max_date": "2026-05-08", "date_count": 8}]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.check_factor_label_coverage(
        factor_names=["alpha101_delta_close_1_rank"],
        start_date="2026-05-01",
        end_date="2026-05-10",
        horizons=[5],
    )

    assert result["status"] == "ok"
    assert result["factor_date_count"] == 10
    assert result["label_horizons"][5]["date_count"] == 8
    assert "factor.factor_daily" in calls[0][0]
```

Include `_context` helper in the test:

```python
class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 2: Run failing test**

Run: `.venv/bin/pytest tests/test_research_preflight.py -q`  
Expected: FAIL because module does not exist.

- [ ] **Step 3: Implement coverage check**

```python
from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def check_factor_label_coverage(
    factor_names: list[str],
    start_date: str,
    end_date: str,
    horizons: list[int],
    calc_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> dict:
    factor_sql = """
        SELECT min(trade_date) AS min_date, max(trade_date) AS max_date,
               count(DISTINCT trade_date) AS date_count
        FROM factor.factor_daily
        WHERE factor_name = ANY(%s)
          AND calc_version = %s
          AND trade_date BETWEEN %s AND %s
    """
    label_sql = """
        SELECT horizon, min(trade_date) AS min_date, max(trade_date) AS max_date,
               count(DISTINCT trade_date) AS date_count
        FROM label_snapshot
        WHERE label_set = 'forward_return'
          AND label_version = 'v1'
          AND horizon = ANY(%s)
          AND trade_date BETWEEN %s AND %s
        GROUP BY horizon
        ORDER BY horizon
    """
    with connect(service) as conn:
        factor_rows = fetch_all(conn, factor_sql, [factor_names, calc_version, start_date, end_date])
        label_rows = fetch_all(conn, label_sql, [horizons, start_date, end_date])
    factor = factor_rows[0] if factor_rows else {}
    label_horizons = {int(row["horizon"]): row for row in label_rows}
    status = "ok" if int(factor.get("date_count") or 0) > 0 and label_horizons else "blocked"
    return {
        "status": status,
        "factor_min_date": factor.get("min_date"),
        "factor_max_date": factor.get("max_date"),
        "factor_date_count": int(factor.get("date_count") or 0),
        "label_horizons": label_horizons,
    }
```

- [ ] **Step 4: Verify task**

Run: `.venv/bin/pytest tests/test_research_preflight.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/research_preflight.py tests/test_research_preflight.py
git commit -m "Add research coverage preflight"
```

---

### Task 3: Backfill CLI Commands

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing parser test for backfill command**

Add to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_backfill_factor_daily_command():
    args = build_parser().parse_args(
        [
            "backfill-factor-daily",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-10",
            "--lookback-bars",
            "130",
            "--industry-system",
            "csrc",
        ]
    )

    assert args.command == "backfill-factor-daily"
    assert args.start_date == "2026-05-01"
    assert args.end_date == "2026-05-10"
    assert args.lookback_bars == 130
```

- [ ] **Step 2: Run failing test**

Run: `.venv/bin/pytest tests/test_factor_cli.py::test_cli_accepts_backfill_factor_daily_command -q`  
Expected: FAIL invalid command.

- [ ] **Step 3: Add parser and handler**

Modify `src/stock_research/cli.py`:

```python
from stock_research.factor_backfill import backfill_factor_daily_range
```

Add parser:

```python
backfill_factor_daily = subparsers.add_parser("backfill-factor-daily")
backfill_factor_daily.add_argument("--start-date", required=True)
backfill_factor_daily.add_argument("--end-date", required=True)
backfill_factor_daily.add_argument("--lookback-bars", type=int, default=130)
backfill_factor_daily.add_argument("--industry-system", default="csrc")
```

Add handler:

```python
elif args.command == "backfill-factor-daily":
    result = backfill_factor_daily_range(
        start_date=args.start_date,
        end_date=args.end_date,
        lookback_bars=args.lookback_bars,
        industry_system=args.industry_system,
    )
    total = int(result["factor_rows"].sum()) if not result.empty else 0
    print(f"factor_daily_backfill|dates|{len(result)}")
    print(f"factor_daily_backfill|rows|{total}")
```

- [ ] **Step 4: Write CLI output test**

```python
def test_backfill_factor_daily_cli_prints_summary(monkeypatch, capsys):
    import sys
    import pandas as pd
    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "backfill_factor_daily_range",
        lambda **kwargs: pd.DataFrame(
            [
                {"trade_date": "2026-05-01", "factor_rows": 10},
                {"trade_date": "2026-05-02", "factor_rows": 20},
            ]
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "backfill-factor-daily",
            "--start-date",
            "2026-05-01",
            "--end-date",
            "2026-05-02",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "factor_daily_backfill|dates|2",
        "factor_daily_backfill|rows|30",
    ]
```

- [ ] **Step 5: Verify task**

Run: `.venv/bin/pytest tests/test_factor_cli.py -q`  
Expected: PASS.

- [ ] **Step 6: Commit only relevant CLI hunks**

Use `git add -p src/stock_research/cli.py` and do not stage unrelated ingest-loop hunks.

```bash
git add tests/test_factor_cli.py
git commit -m "Add factor backfill CLI"
```

---

### Task 4: Approved-Only Scoring Range Workflow

**Files:**
- Create: `src/stock_research/approved_scoring_workflow.py`
- Create: `tests/test_approved_scoring_workflow.py`

- [ ] **Step 1: Write failing scoring range test**

```python
from stock_research import approved_scoring_workflow


def test_score_approved_factors_range_scores_each_date(monkeypatch):
    calls = []
    monkeypatch.setattr(
        approved_scoring_workflow,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 5,
    )

    result = approved_scoring_workflow.score_approved_factors_range(
        start_date="2026-05-01",
        end_date="2026-05-02",
        score_version="manual_v1",
    )

    assert list(result["trade_date"]) == ["2026-05-01", "2026-05-02"]
    assert list(result["score_rows"]) == [5, 5]
    assert calls[0]["approved_only"] is True
```

- [ ] **Step 2: Run failing test**

Run: `.venv/bin/pytest tests/test_approved_scoring_workflow.py -q`  
Expected: FAIL module missing.

- [ ] **Step 3: Implement workflow**

```python
import pandas as pd

from stock_research.factor_backfill import build_trade_date_range
from stock_research.factor_store import score_stored_factor_daily


def score_approved_factors_range(
    start_date: str,
    end_date: str,
    score_version: str = "manual_v1",
    calc_version: str = "v1",
) -> pd.DataFrame:
    rows = []
    for trade_date in build_trade_date_range(start_date, end_date):
        count = score_stored_factor_daily(
            trade_date=trade_date,
            score_version=score_version,
            calc_version=calc_version,
            approved_only=True,
        )
        rows.append({"trade_date": trade_date, "score_rows": count})
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Verify task**

Run: `.venv/bin/pytest tests/test_approved_scoring_workflow.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/approved_scoring_workflow.py tests/test_approved_scoring_workflow.py
git commit -m "Add approved scoring range workflow"
```

---

### Task 5: End-to-End Research Loop Runbook

**Files:**
- Modify: `docs/daily-factor-pipeline-runbook.md`
- Modify: `docs/astock-research-platform-v1.md`

- [ ] **Step 1: Update runbook sequence**

Add this operational order to `docs/daily-factor-pipeline-runbook.md`:

```markdown
## Historical Research Loop

1. Backfill historical factor rows:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-factor-daily --start-date YYYY-MM-DD --end-date YYYY-MM-DD --lookback-bars 130 --industry-system csrc
```

2. Confirm label coverage for the same range before gate evaluation.

3. Batch evaluate candidate factors:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate-batch --factor-names alpha101_delta_close_1_rank,gtja191_amount_momentum_5_10,qlib_alpha158_ret_5 --start-date YYYY-MM-DD --end-date YYYY-MM-DD --horizons 5,10,20,60 --primary-horizon 5 --score-version manual_v1
```

4. Score with approved factors only after approvals exist.

5. Run TopN research workflow and compare the tear sheet before changing daily report usage.
```
```

- [ ] **Step 2: Update status doc**

In `docs/astock-research-platform-v1.md`, move these from “remaining” to “current progress” after tasks above are complete:

```markdown
- 已落地历史因子批量回算入口。
- 已落地 approved-only 评分区间 workflow。
```

- [ ] **Step 3: Verify docs and tests**

Run: `.venv/bin/pytest -q`  
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs/daily-factor-pipeline-runbook.md docs/astock-research-platform-v1.md
git commit -m "Document historical research loop"
```

---

## Execution Notes

- Keep existing unrelated dirty files intact:
  - `src/stock_research/ingest_jobs.py`
  - `src/stock_research/loaders/baostock_finance_ingestion.py`
  - `tests/test_baostock_finance_ingestion.py`
  - `tests/test_ingest_jobs.py`
  - `tests/test_schema.py`
- `src/stock_research/cli.py` currently also has unrelated local ingest-loop hunks. Use `git add -p` and stage only task-specific CLI hunks.
- Do not run a real historical backfill until tests pass and the date range is chosen. A full range can write many rows.
- Do not approve factors based on one-day factor data. Gate evaluation requires overlapping historical factor rows and forward return labels.

## Self-Review

- Spec coverage: historical factor backfill is Task 1 and Task 3; coverage checks are Task 2; batch approvals are already implemented and documented in Task 5; approved-only scoring is Task 4; runbook is Task 5.
- Placeholder scan: no TBD/TODO placeholders remain.
- Type consistency: date helpers return `list[str]`; range workflows return `pd.DataFrame`; CLI outputs use stable pipe-delimited lines.
