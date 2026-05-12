# Historical Approved Factor Store Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make historical research use a durable two-stage flow: compute all candidate factors into `factor.factor_daily`, then evaluate and score only approved factors over a meaningful range starting at `2024-01-01`.

**Architecture:** Keep existing tables and pipeline stages. Add explicit candidate-factor defaults, label-coverage preflight, stricter coverage blocking, and approved-only range scoring over actual trading dates. The main CLI gets small operational entry points, but implementation must preserve unrelated local `cli.py` and ingest worktree changes by staging only task-specific hunks.

**Tech Stack:** Python, pandas, PostgreSQL through `stock_research.db`, pytest, existing factor evaluation/scoring/backtest modules.

---

## Current Context

Relevant existing modules:

- `src/stock_research/factor_pipeline.py`: computes and upserts candidate factor rows into `factor.factor_daily`.
- `src/stock_research/factor_backfill.py`: runs `build_and_store_factor_daily` over a date range, already supports trading-day lookup and progress callbacks.
- `src/stock_research/research_preflight.py`: currently checks factor/label coverage but does not find latest common label date and does not block missing horizons.
- `src/stock_research/factor_eval_batch.py`: evaluates a supplied factor list and stores `factor.factor_eval_run` plus `factor.factor_approval`.
- `src/stock_research/factor_store.py`: supports `approved_only=True` in `load_factor_daily` and `score_stored_factor_daily`.
- `src/stock_research/approved_scoring_workflow.py`: scores approved factors over a calendar date range.
- `src/stock_research/research_workflow_cli.py`: runs TopN research workflow from `factor.stock_score_daily`.

Current dirty worktree caveat:

- At plan creation, `src/stock_research/cli.py`, `src/stock_research/ingest_jobs.py`, `src/stock_research/loaders/baostock_finance_ingestion.py`, `tests/test_baostock_finance_ingestion.py`, `tests/test_ingest_jobs.py`, and `tests/test_schema.py` had unrelated uncommitted changes.
- Do not revert or overwrite those changes.
- When committing any task that touches `src/stock_research/cli.py`, inspect `git diff src/stock_research/cli.py` and stage only the hunks introduced by that task.

## File Structure

- Modify `src/stock_research/factor_config.py`  
  Add historical research defaults: start date, horizons, and candidate factor names.
- Modify `tests/test_factor_pipeline.py` or create `tests/test_factor_config.py`  
  Test default candidate names and horizons.
- Modify `src/stock_research/research_preflight.py`  
  Add latest common label-date discovery and stricter coverage status.
- Modify `tests/test_research_preflight.py`  
  Test latest common label date, missing horizons, and blocked coverage.
- Modify `src/stock_research/cli.py`  
  Add `research-preflight` command and allow batch gate to use default candidates when `--factor-names` is omitted.
- Modify `tests/test_factor_cli.py`  
  Test parser and stable command output.
- Modify `src/stock_research/factor_eval_batch.py`  
  Let batch gate use configured candidate factors by default.
- Modify `tests/test_factor_eval_batch.py`  
  Test default candidate factor behavior.
- Modify `src/stock_research/approved_scoring_workflow.py`  
  Score approved factors over actual trading dates by default.
- Modify `tests/test_approved_scoring_workflow.py`  
  Test trading-day scoring and approved-only passthrough.
- Modify `docs/daily-factor-pipeline-runbook.md`  
  Document the new historical approved-factor flow.
- Modify `docs/real-data-flow-smoke-2026-05-10.md`  
  Mark the 3-day January run as a pipeline smoke only, not a factor-validity test.

---

### Task 1: Add Historical Research Defaults

**Files:**

- Modify: `src/stock_research/factor_config.py`
- Create: `tests/test_factor_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_factor_config.py`:

```python
from stock_research import factor_config


def test_historical_research_defaults_define_window_and_horizons():
    assert factor_config.historical_research_start_date() == "2024-01-01"
    assert factor_config.default_research_horizons() == [5, 10, 20, 60]


def test_candidate_factor_names_include_current_pipeline_outputs():
    names = factor_config.candidate_factor_names()

    assert "ret_20" in names
    assert "volatility_20" in names
    assert "alpha101_delta_close_1_rank" in names
    assert "gtja191_amount_momentum_5_10" in names
    assert "qlib_ret_5" in names
    assert len(names) == len(set(names))
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_config.py -q
```

Expected: FAIL because `historical_research_start_date`, `default_research_horizons`, and `candidate_factor_names` do not exist.

- [ ] **Step 3: Implement defaults**

Append to `src/stock_research/factor_config.py` after `manual_v1_config()`:

```python
def historical_research_start_date() -> str:
    return "2024-01-01"


def default_research_horizons() -> list[int]:
    return [5, 10, 20, 60]


def candidate_factor_names() -> list[str]:
    return sorted(manual_v1_config()["factor_groups"].keys())
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_config.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_config.py tests/test_factor_config.py
git commit -m "Add historical factor research defaults"
```

---

### Task 2: Discover Latest Common Label Date

**Files:**

- Modify: `src/stock_research/research_preflight.py`
- Modify: `tests/test_research_preflight.py`

- [ ] **Step 1: Write failing latest-label-date test**

Append to `tests/test_research_preflight.py`:

```python
def test_find_latest_common_label_date_requires_all_horizons(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [{"latest_common_date": "2026-01-30", "date_count": 122}]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.find_latest_common_label_date(
        start_date="2024-01-01",
        horizons=[5, 10, 20, 60],
    )

    assert result == {
        "latest_common_date": "2026-01-30",
        "date_count": 122,
        "horizons": [5, 10, 20, 60],
    }
    assert "HAVING count(DISTINCT horizon) = %s" in calls[0][0]
    assert calls[0][1] == [
        "forward_return",
        "v1",
        [5, 10, 20, 60],
        "2024-01-01",
        4,
    ]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_preflight.py::test_find_latest_common_label_date_requires_all_horizons -q
```

Expected: FAIL because `find_latest_common_label_date` does not exist.

- [ ] **Step 3: Implement latest common date helper**

Add to `src/stock_research/research_preflight.py`:

```python
def find_latest_common_label_date(
    start_date: str,
    horizons: list[int],
    label_set: str = "forward_return",
    label_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> dict:
    if not horizons:
        raise ValueError("horizons must not be empty")

    sql = """
    SELECT max(trade_date) AS latest_common_date,
           count(*) AS date_count
    FROM (
        SELECT trade_date
        FROM label_snapshot
        WHERE label_set = %s
          AND label_version = %s
          AND horizon = ANY(%s)
          AND trade_date >= %s
          AND label_name IN ('forward_return', 'future_return')
        GROUP BY trade_date
        HAVING count(DISTINCT horizon) = %s
    ) covered_dates
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [label_set, label_version, horizons, start_date, len(horizons)])
    row = rows[0] if rows else {}
    latest = row.get("latest_common_date")
    return {
        "latest_common_date": str(latest)[:10] if latest is not None else None,
        "date_count": int(row.get("date_count") or 0),
        "horizons": list(horizons),
    }
```

- [ ] **Step 4: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_preflight.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/research_preflight.py tests/test_research_preflight.py
git commit -m "Find latest common label date"
```

---

### Task 3: Make Coverage Preflight Block Missing Horizons

**Files:**

- Modify: `src/stock_research/research_preflight.py`
- Modify: `tests/test_research_preflight.py`

- [ ] **Step 1: Write failing missing-horizon test**

Append to `tests/test_research_preflight.py`:

```python
def test_check_factor_label_coverage_blocks_missing_horizons(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        if "factor.factor_daily" in sql:
            return [
                {
                    "min_date": "2024-01-02",
                    "max_date": "2026-01-30",
                    "date_count": 300,
                }
            ]
        return [
            {"horizon": 5, "min_date": "2024-01-02", "max_date": "2026-01-30", "date_count": 300},
            {"horizon": 10, "min_date": "2024-01-02", "max_date": "2026-01-30", "date_count": 300},
        ]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.check_factor_label_coverage(
        factor_names=["ret_20", "qlib_ret_5"],
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10, 20, 60],
        min_label_dates=20,
    )

    assert result["status"] == "blocked"
    assert result["missing_horizons"] == [20, 60]
    assert "missing_label_horizons" in result["reasons"]
```

- [ ] **Step 2: Write failing insufficient-label-count test**

Append to `tests/test_research_preflight.py`:

```python
def test_check_factor_label_coverage_blocks_small_label_samples(monkeypatch):
    def fake_fetch_all(conn, sql, params):
        if "factor.factor_daily" in sql:
            return [
                {
                    "min_date": "2026-01-28",
                    "max_date": "2026-01-30",
                    "date_count": 3,
                }
            ]
        return [
            {"horizon": 5, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
            {"horizon": 10, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
            {"horizon": 20, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
            {"horizon": 60, "min_date": "2026-01-28", "max_date": "2026-01-30", "date_count": 3},
        ]

    monkeypatch.setattr(research_preflight, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_preflight, "fetch_all", fake_fetch_all)

    result = research_preflight.check_factor_label_coverage(
        factor_names=["ret_20"],
        start_date="2026-01-28",
        end_date="2026-01-30",
        horizons=[5, 10, 20, 60],
        min_label_dates=20,
    )

    assert result["status"] == "blocked"
    assert result["short_label_horizons"] == [5, 10, 20, 60]
    assert "insufficient_label_dates" in result["reasons"]
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_preflight.py::test_check_factor_label_coverage_blocks_missing_horizons tests/test_research_preflight.py::test_check_factor_label_coverage_blocks_small_label_samples -q
```

Expected: FAIL because `check_factor_label_coverage` does not return missing/short horizon diagnostics and does not accept `min_label_dates`.

- [ ] **Step 4: Implement stricter coverage result**

Replace the body and signature of `check_factor_label_coverage` in `src/stock_research/research_preflight.py` with:

```python
def check_factor_label_coverage(
    factor_names: list[str],
    start_date: str,
    end_date: str,
    horizons: list[int],
    calc_version: str = "v1",
    min_label_dates: int = 20,
    service: str = SETTINGS.research_service,
) -> dict:
    if not factor_names:
        raise ValueError("factor_names must not be empty")
    if not horizons:
        raise ValueError("horizons must not be empty")

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
          AND label_name IN ('forward_return', 'future_return')
          AND trade_date BETWEEN %s AND %s
        GROUP BY horizon
        ORDER BY horizon
    """
    with connect(service) as conn:
        factor_rows = fetch_all(conn, factor_sql, [factor_names, calc_version, start_date, end_date])
        label_rows = fetch_all(conn, label_sql, [horizons, start_date, end_date])

    factor = factor_rows[0] if factor_rows else {}
    factor_date_count = int(factor.get("date_count") or 0)
    label_horizons = {int(row["horizon"]): row for row in label_rows}
    missing_horizons = [horizon for horizon in horizons if horizon not in label_horizons]
    short_label_horizons = [
        horizon
        for horizon in horizons
        if horizon in label_horizons and int(label_horizons[horizon].get("date_count") or 0) < min_label_dates
    ]

    reasons = []
    if factor_date_count <= 0:
        reasons.append("missing_factor_rows")
    if missing_horizons:
        reasons.append("missing_label_horizons")
    if short_label_horizons:
        reasons.append("insufficient_label_dates")

    return {
        "status": "ok" if not reasons else "blocked",
        "reasons": reasons,
        "factor_min_date": factor.get("min_date"),
        "factor_max_date": factor.get("max_date"),
        "factor_date_count": factor_date_count,
        "label_horizons": label_horizons,
        "missing_horizons": missing_horizons,
        "short_label_horizons": short_label_horizons,
        "min_label_dates": min_label_dates,
    }
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_preflight.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/research_preflight.py tests/test_research_preflight.py
git commit -m "Block historical research on weak coverage"
```

---

### Task 4: Add Research Preflight CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing parser test**

Append to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_research_preflight_command():
    args = build_parser().parse_args(
        [
            "research-preflight",
            "--start-date",
            "2024-01-01",
            "--horizons",
            "5,10,20,60",
            "--factor-names",
            "ret_20,qlib_ret_5",
            "--min-label-dates",
            "20",
        ]
    )

    assert args.command == "research-preflight"
    assert args.start_date == "2024-01-01"
    assert args.horizons == "5,10,20,60"
    assert args.factor_names == "ret_20,qlib_ret_5"
    assert args.min_label_dates == 20
```

- [ ] **Step 2: Write failing output test**

Append to `tests/test_factor_cli.py`:

```python
def test_research_preflight_cli_prints_latest_date_and_coverage(monkeypatch, capsys):
    import sys

    import stock_research.cli as cli

    monkeypatch.setattr(cli, "candidate_factor_names", lambda: ["ret_20", "qlib_ret_5"])
    monkeypatch.setattr(
        cli,
        "find_latest_common_label_date",
        lambda **kwargs: {
            "latest_common_date": "2026-01-30",
            "date_count": 122,
            "horizons": [5, 10, 20, 60],
        },
    )
    monkeypatch.setattr(
        cli,
        "check_factor_label_coverage",
        lambda **kwargs: {
            "status": "ok",
            "reasons": [],
            "factor_date_count": 122,
            "missing_horizons": [],
            "short_label_horizons": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "research-preflight", "--start-date", "2024-01-01"],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "research_preflight|latest_common_label_date|2026-01-30|122",
        "research_preflight|coverage|ok|factor_dates|122",
        "research_preflight|missing_horizons|",
        "research_preflight|short_label_horizons|",
    ]
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_cli.py::test_cli_accepts_research_preflight_command tests/test_factor_cli.py::test_research_preflight_cli_prints_latest_date_and_coverage -q
```

Expected: FAIL because CLI does not expose `research-preflight`.

- [ ] **Step 4: Add CLI imports**

In `src/stock_research/cli.py`, add imports near the factor imports:

```python
from stock_research.factor_config import candidate_factor_names
from stock_research.research_preflight import (
    check_factor_label_coverage,
    find_latest_common_label_date,
)
```

- [ ] **Step 5: Add parser command**

Inside `build_parser()`, near factor workflow commands, add:

```python
    research_preflight = subparsers.add_parser("research-preflight")
    research_preflight.add_argument("--start-date", default="2024-01-01")
    research_preflight.add_argument("--end-date")
    research_preflight.add_argument("--horizons", default="5,10,20,60")
    research_preflight.add_argument("--factor-names")
    research_preflight.add_argument("--calc-version", default="v1")
    research_preflight.add_argument("--min-label-dates", type=int, default=20)
```

- [ ] **Step 6: Add dispatch branch**

Inside `main()`, before `backfill-factor-daily`, add:

```python
    elif args.command == "research-preflight":
        horizons = [int(value.strip()) for value in args.horizons.split(",") if value.strip()]
        factors = (
            [value.strip() for value in args.factor_names.split(",") if value.strip()]
            if args.factor_names
            else candidate_factor_names()
        )
        latest = find_latest_common_label_date(
            start_date=args.start_date,
            horizons=horizons,
        )
        end_date = args.end_date or latest["latest_common_date"]
        coverage = check_factor_label_coverage(
            factor_names=factors,
            start_date=args.start_date,
            end_date=end_date,
            horizons=horizons,
            calc_version=args.calc_version,
            min_label_dates=args.min_label_dates,
        )
        print(
            "research_preflight|latest_common_label_date|"
            f"{latest['latest_common_date']}|{latest['date_count']}"
        )
        print(
            "research_preflight|coverage|"
            f"{coverage['status']}|factor_dates|{coverage['factor_date_count']}"
        )
        print(
            "research_preflight|missing_horizons|"
            + ",".join(str(value) for value in coverage["missing_horizons"])
        )
        print(
            "research_preflight|short_label_horizons|"
            + ",".join(str(value) for value in coverage["short_label_horizons"])
        )
```

- [ ] **Step 7: Run CLI tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_cli.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit task-specific hunks**

Because `src/stock_research/cli.py` had unrelated local changes at plan creation, use interactive staging or patch staging carefully:

```bash
git diff src/stock_research/cli.py
git add -p src/stock_research/cli.py
git add tests/test_factor_cli.py
git commit -m "Add research preflight CLI"
```

Expected: commit includes only `research-preflight` imports, parser branch, dispatch branch, and tests.

---

### Task 5: Let Batch Evaluation Use Default Candidate Factors

**Files:**

- Modify: `src/stock_research/factor_eval_batch.py`
- Modify: `tests/test_factor_eval_batch.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing batch default test**

Append to `tests/test_factor_eval_batch.py`:

```python
def test_run_factor_gate_batch_uses_default_candidates_when_factor_names_omitted(monkeypatch):
    loaded = []

    monkeypatch.setattr(
        factor_eval_batch,
        "candidate_factor_names",
        lambda: ["ret_20", "qlib_ret_5"],
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "load_multi_horizon_factor_eval_inputs",
        lambda **kwargs: loaded.append(kwargs["factor_name"]) or (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.02]}),
        ),
    )
    monkeypatch.setattr(
        factor_eval_batch,
        "generate_multi_horizon_report",
        lambda **kwargs: {
            "factor_name": kwargs["factor_name"],
            "horizons": kwargs["horizons"],
            "reports": {5: {"ic_summary": {"mean_ic": 0.04, "icir": 0.6, "ic_count": 30}}},
        },
    )
    monkeypatch.setattr(factor_eval_batch, "store_factor_eval_run", lambda **kwargs: None)
    monkeypatch.setattr(factor_eval_batch, "store_factor_approval", lambda **kwargs: None)
    monkeypatch.setattr(factor_eval_batch, "_new_run_id", lambda factor_name: f"run-{factor_name}")

    result = factor_eval_batch.run_factor_gate_batch(
        factor_names=None,
        start_date="2024-01-01",
        end_date="2026-01-30",
        horizons=[5, 10, 20, 60],
    )

    assert loaded == ["ret_20", "qlib_ret_5"]
    assert list(result["factor_name"]) == ["ret_20", "qlib_ret_5"]
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_batch.py::test_run_factor_gate_batch_uses_default_candidates_when_factor_names_omitted -q
```

Expected: FAIL because `factor_names` does not accept `None` and `candidate_factor_names` is not imported.

- [ ] **Step 3: Implement default candidates**

Modify imports in `src/stock_research/factor_eval_batch.py`:

```python
from stock_research.factor_config import candidate_factor_names
```

Replace `run_factor_gate_batch` with this implementation:

```python
def run_factor_gate_batch(
    factor_names: list[str] | None,
    start_date: str,
    end_date: str,
    horizons: list[int],
    primary_horizon: int = 5,
    calc_version: str = "v1",
    score_version: str = "manual_v1",
    quantiles: int = 5,
    top_n: int = 30,
) -> pd.DataFrame:
    selected_factor_names = factor_names or candidate_factor_names()
    rows = []
    for factor_name in selected_factor_names:
        factors, returns = load_multi_horizon_factor_eval_inputs(
            factor_name=factor_name,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            calc_version=calc_version,
        )
        multi_horizon_report = generate_multi_horizon_report(
            factors=factors,
            returns=returns,
            factor_name=factor_name,
            horizons=horizons,
            quantiles=quantiles,
            top_n=top_n,
        )
        decision = decide_factor_gate(
            factor_name=factor_name,
            multi_horizon_report=multi_horizon_report,
            primary_horizon=primary_horizon,
        )
        run_id = _new_run_id(factor_name)
        store_factor_eval_run(
            run_id=run_id,
            factor_name=factor_name,
            calc_version=calc_version,
            start_date=start_date,
            end_date=end_date,
            horizons=horizons,
            primary_horizon=primary_horizon,
            status=decision["status"],
            reason=decision["reason"],
            metrics={
                "decision": decision,
                "multi_horizon": _summarize_multi_horizon_report(multi_horizon_report),
            },
        )
        store_factor_approval(
            factor_name=factor_name,
            calc_version=calc_version,
            score_version=score_version,
            status=decision["status"],
            reason=decision["reason"],
            eval_run_id=run_id,
        )
        rows.append(
            {
                "factor_name": factor_name,
                "status": decision["status"],
                "reason": decision["reason"],
                "primary_horizon": primary_horizon,
                "mean_ic": decision.get("mean_ic"),
                "icir": decision.get("icir"),
                "ic_count": decision.get("ic_count"),
                "eval_run_id": run_id,
            }
        )
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Update CLI parser test for optional factor names**

Modify `test_cli_accepts_evaluate_factor_gate_batch_command` in `tests/test_factor_cli.py` so `--factor-names` is no longer required:

```python
def test_cli_accepts_evaluate_factor_gate_batch_command_without_factor_names():
    args = build_parser().parse_args(
        [
            "evaluate-factor-gate-batch",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2026-01-30",
        ]
    )

    assert args.command == "evaluate-factor-gate-batch"
    assert args.factor_names is None
    assert args.horizons == "5,10,20,60"
```

- [ ] **Step 5: Update CLI parser**

In `src/stock_research/cli.py`, change:

```python
evaluate_factor_gate_batch.add_argument("--factor-names", required=True)
```

to:

```python
evaluate_factor_gate_batch.add_argument("--factor-names")
```

- [ ] **Step 6: Update CLI dispatch**

In the `evaluate-factor-gate-batch` branch, change the `factor_names` argument:

```python
factor_names=(
    [value.strip() for value in args.factor_names.split(",") if value.strip()]
    if args.factor_names
    else None
),
```

- [ ] **Step 7: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_batch.py tests/test_factor_cli.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit task-specific hunks**

```bash
git diff src/stock_research/cli.py
git add src/stock_research/factor_eval_batch.py tests/test_factor_eval_batch.py tests/test_factor_cli.py
git add -p src/stock_research/cli.py
git commit -m "Use default candidates for batch factor gate"
```

Expected: commit includes batch default behavior and optional CLI factor list only.

---

### Task 6: Score Approved Factors Over Trading Dates

**Files:**

- Modify: `src/stock_research/approved_scoring_workflow.py`
- Modify: `tests/test_approved_scoring_workflow.py`

- [ ] **Step 1: Write failing trading-day scoring test**

Append to `tests/test_approved_scoring_workflow.py`:

```python
def test_score_approved_factors_range_uses_trading_dates_by_default(monkeypatch):
    calls = []

    monkeypatch.setattr(
        approved_scoring_workflow,
        "load_trade_dates_for_backfill",
        lambda **kwargs: ["2024-01-02", "2024-01-03"],
    )
    monkeypatch.setattr(
        approved_scoring_workflow,
        "score_stored_factor_daily",
        lambda **kwargs: calls.append(kwargs) or 8,
    )

    result = approved_scoring_workflow.score_approved_factors_range(
        start_date="2024-01-01",
        end_date="2024-01-05",
        score_version="manual_v1",
    )

    assert list(result["trade_date"]) == ["2024-01-02", "2024-01-03"]
    assert list(result["score_rows"]) == [8, 8]
    assert calls[0]["trade_date"] == "2024-01-02"
    assert calls[0]["approved_only"] is True
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_approved_scoring_workflow.py::test_score_approved_factors_range_uses_trading_dates_by_default -q
```

Expected: FAIL because approved scoring uses calendar dates and does not import `load_trade_dates_for_backfill`.

- [ ] **Step 3: Implement trading-day scoring**

Replace `src/stock_research/approved_scoring_workflow.py` with:

```python
import pandas as pd

from stock_research.factor_backfill import build_trade_date_range, load_trade_dates_for_backfill
from stock_research.factor_store import score_stored_factor_daily


def score_approved_factors_range(
    start_date: str,
    end_date: str,
    score_version: str = "manual_v1",
    calc_version: str = "v1",
    trading_days_only: bool = True,
    adjust_type: str = "hfq",
) -> pd.DataFrame:
    trade_dates = (
        load_trade_dates_for_backfill(
            start_date=start_date,
            end_date=end_date,
            adjust_type=adjust_type,
        )
        if trading_days_only
        else build_trade_date_range(start_date, end_date)
    )
    rows = []
    for trade_date in trade_dates:
        count = score_stored_factor_daily(
            trade_date=trade_date,
            score_version=score_version,
            calc_version=calc_version,
            approved_only=True,
        )
        rows.append({"trade_date": trade_date, "score_rows": count})
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run approved scoring tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_approved_scoring_workflow.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/approved_scoring_workflow.py tests/test_approved_scoring_workflow.py
git commit -m "Score approved factors on trading dates"
```

---

### Task 7: Document Operator Flow And Real-Data Verification

**Files:**

- Modify: `docs/daily-factor-pipeline-runbook.md`
- Modify: `docs/real-data-flow-smoke-2026-05-10.md`
- Test: documentation plus command verification

- [ ] **Step 1: Update runbook historical flow**

In `docs/daily-factor-pipeline-runbook.md`, replace the current "Historical Research Loop" section with:

````markdown
## Historical Approved-Factor Research Loop

Use this flow when testing factor effectiveness. `factor.factor_daily` stores candidate factors. A stored factor is not effective until `factor.factor_approval` records `status='approved'` for the target score version.

1. Refresh forward-return labels:

```bash
MARKET_END_DATE=$(date +%F)
/Users/xiwei/stock_research/.venv/bin/stock-research labels --end-date "$MARKET_END_DATE"
```

2. Find the latest label-covered end date and check coverage:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 2024-01-01 --horizons 5,10,20,60 --min-label-dates 20
```

3. Capture the label-covered end date and backfill all current candidate factors:

```bash
END_DATE=$(/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 2024-01-01 --horizons 5,10,20,60 --min-label-dates 20 | awk -F'|' '/latest_common_label_date/ {print $3}')
/Users/xiwei/stock_research/.venv/bin/stock-research backfill-factor-daily --start-date 2024-01-01 --end-date "$END_DATE" --lookback-bars 130 --industry-system csrc
```

4. Re-run preflight with the same end date:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 2024-01-01 --end-date "$END_DATE" --horizons 5,10,20,60 --min-label-dates 20
```

5. Batch evaluate default candidate factors:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research evaluate-factor-gate-batch --start-date 2024-01-01 --end-date "$END_DATE" --horizons 5,10,20,60 --primary-horizon 5 --score-version manual_v1
```

6. Score the historical range with approved factors only from Python until a dedicated CLI command is added:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -c "from stock_research.approved_scoring_workflow import score_approved_factors_range; result = score_approved_factors_range('2024-01-01', '$END_DATE', score_version='manual_v1'); print(result.to_string(index=False)); print('approved_score_rows|' + str(int(result['score_rows'].sum()) if not result.empty else 0))"
```

7. Run TopN research workflow on approved-only scores:

```bash
cd /Users/xiwei/stock_research
.venv/bin/python -m stock_research.research_workflow_cli --start-date 2024-01-01 --end-date "$END_DATE" --score-version manual_v1 --top-n 20 --rebalance-frequency weekly --transaction-cost-bps 10 --max-positions 20 --strategy-id approved_topn_weekly_v1
```
````

- [ ] **Step 2: Update 3-day smoke document**

Append this section to `docs/real-data-flow-smoke-2026-05-10.md`:

```markdown
## Interpretation

The `2026-01-28` to `2026-01-30` run was a pipeline smoke test only. It proved that factor backfill, label coverage checks, batch gate persistence, approved-only scoring, and TopN workflow wiring can execute on real PostgreSQL data.

It was not a factor-validity test. A 3-day window is too small for IC, RankIC, quantile return, turnover, or TopN performance conclusions. The historical approved-factor research flow now starts at `2024-01-01` and ends at the latest date covered by all required forward-return horizons.
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_research_preflight.py tests/test_factor_config.py tests/test_factor_eval_batch.py tests/test_approved_scoring_workflow.py tests/test_factor_cli.py -q
```

Expected: PASS.

- [ ] **Step 4: Run full tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Run real-data preflight smoke**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research research-preflight --start-date 2024-01-01 --horizons 5,10,20,60 --min-label-dates 20
```

Expected: command exits 0 and prints four machine-readable lines with these prefixes:

```text
research_preflight|latest_common_label_date|
research_preflight|coverage|
research_preflight|missing_horizons|
research_preflight|short_label_horizons|
```

`coverage|blocked` is acceptable before the historical backfill has been run. After backfill, rerun the same command with the discovered end date and expect a line containing `research_preflight|coverage|ok|`.

- [ ] **Step 6: Commit docs and final verification**

```bash
git add docs/daily-factor-pipeline-runbook.md docs/real-data-flow-smoke-2026-05-10.md
git commit -m "Document historical approved factor flow"
```

---

## Recommended Execution Order

1. Task 1: Add defaults.
2. Task 2: Find latest common label date.
3. Task 3: Strengthen coverage blocking.
4. Task 4: Add preflight CLI.
5. Task 5: Default batch gate to configured candidates.
6. Task 6: Score approved factors over trading dates.
7. Task 7: Document and verify the operator flow.

## Acceptance Criteria

- `candidate_factor_names()` returns all current pipeline factor names without duplicates.
- `find_latest_common_label_date()` returns the latest date covered by every required horizon.
- `check_factor_label_coverage()` blocks missing factor rows, missing horizons, and too-small label samples.
- `stock-research research-preflight --start-date 2024-01-01` prints stable machine-readable preflight lines.
- `stock-research evaluate-factor-gate-batch` can run without `--factor-names` and then uses default candidates.
- Approved-only historical scoring runs over trading dates, not calendar dates.
- Runbook states that `factor.factor_daily` stores candidates, while `factor.factor_approval` determines effective factors.
- Full test suite passes.

## Commit Policy

- Commit after each task.
- Do not commit generated `reports/`, `cache/`, `logs/`, `.pytest_cache/`, `.venv/`, `.DS_Store`, or `__pycache__/`.
- Do not revert unrelated local changes in `cli.py` or ingest modules.
- When a task touches a dirty file, stage only the hunks introduced by the task.
- Push only after full verification passes.

## Self-Review

Spec coverage:

- Historical `2024-01-01` start date: Task 1 and Task 7.
- Latest label-covered end date: Task 2 and Task 4.
- Candidate factor storage before evaluation: Task 1 and Task 7 document and configure it; existing `factor_backfill.py` provides execution.
- Coverage blocking before evaluation: Task 3 and Task 4.
- Batch evaluation of candidate factors: Task 5.
- Approved-only scoring: Task 6.
- TopN research workflow use: Task 7 documents the existing workflow command.
- 3-day smoke interpretation: Task 7.

Placeholder scan:

- No unresolved placeholders or unspecified code steps remain.
- Each code-changing step includes exact code or exact replacement instructions.

Type consistency:

- Public defaults are `historical_research_start_date()`, `default_research_horizons()`, and `candidate_factor_names()`.
- Preflight helper names are `find_latest_common_label_date()` and `check_factor_label_coverage()`.
- Approved-only range scoring remains `score_approved_factors_range()`.
