# LHB Auction Result Backfill 20250101 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill Tushare opening and closing auction result bars for the LHB research universe from `2025-01-01` onward, with dry-run planning, missing-coverage checks, daily call limits, checkpoint/resume, and database upsert reuse.

**Architecture:** Keep the first phase scoped to auction result bars, not 9:15-9:25 per-minute auction detail. Build an explicit backfill plan from selected LHB universe files and A-share trade dates, compare it with existing `market.stock_auction_bar` coverage, then execute only missing `trade_date + auction_phase` calls. Reuse `sync_tushare_stock_auction_bars` and `upsert_stock_auction_bars`, but add a safer orchestration layer for ordered backfill.

**Tech Stack:** Python, pandas, Tushare `stk_auction_o` / `stk_auction_c`, PostgreSQL via existing `stock_research.db`, pytest, existing `stock_research` CLI.

---

## Scope

This plan backfills:

- `open_call`: opening auction result bar.
- `close_call`: closing auction result bar.
- LHB candidate stocks only.
- Date range starting at `2025-01-01`.
- Cached storage in `staging.tushare_stock_auction_bar` and `market.stock_auction_bar`.

This plan does not backfill:

- 9:15-9:25 per-minute virtual auction quotes.
- Tick-level order book or Level2 auction detail.
- Full-market auction data unless explicitly enabled later.

## Current Implementation Context

Existing files:

- `src/stock_research/auction_data.py`
  - Has `sync_tushare_stock_auction_bars`.
  - Has `query_tushare_auction_rows_for_trade_date`.
  - Has `upsert_stock_auction_bars`.
  - Existing sync can accept `trade_dates`, but does not yet build a missing-only backfill plan.

- `src/stock_research/schema.py`
  - Has `staging.tushare_stock_auction_bar`.
  - Has `market.stock_auction_bar`.

- `src/stock_research/cli.py`
  - Has `sync-tushare-auction-bars`.
  - Needs a safer LHB-specific backfill planning/execution command.

- `tests/test_auction_data.py`
  - Already covers row conversion, upsert, and scoped sync behavior.
  - Add tests for plan building and daily call limiting.

## Backfill Policy

Use this policy for the first production run:

- Universe: LHB candidate `ts_code` values from supplied CSV artifacts.
- Start date: `2025-01-01`.
- End date: caller supplied; default should be today only at CLI layer if needed.
- Phases: `open_call,close_call`.
- Query unit: one Tushare call per `trade_date + phase`.
- Local filtering: after each full-market date response, keep only selected `ts_code` rows before upsert.
- Resume behavior: skip `trade_date + phase` where every selected `ts_code` already exists in `market.stock_auction_bar`.
- Daily cap: default `500` calls per run.
- Sleep: default `1.3` seconds to stay below 50 calls/minute.
- Output: CSV plan, CSV executed log, markdown report.

With roughly 350 trading days from `2025-01-01` to mid-2026:

- Open only: about 350 calls.
- Open + close: about 700 calls.
- This is below the 8000/day Tushare cap, but use `--max-calls` to avoid accidental overuse.

## File Structure

- Modify: `src/stock_research/auction_data.py`
  - Add universe loading from candidate CSV files.
  - Add existing coverage loading.
  - Add missing-only backfill plan builder.
  - Add safe ordered executor.
  - Add report writer.

- Modify: `src/stock_research/cli.py`
  - Add `lhb-auction-backfill-plan-v1`.
  - Add `lhb-auction-backfill-run-v1`.

- Modify: `tests/test_auction_data.py`
  - Add unit tests for universe loading, plan building, missing coverage, daily limit, and report output.

- Modify: `tests/test_schema.py`
  - Add parser tests for the two new CLI commands.

- Create output directory at runtime:
  - `outputs/research/lhb_auction_backfill_20250101/`

## Task 1: Add LHB Auction Universe Loader

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] **Step 1: Write failing test for loading unique LHB ts_codes**

Add this test to `tests/test_auction_data.py`:

```python
def test_load_lhb_auction_backfill_universe_reads_unique_ts_codes(tmp_path):
    path = tmp_path / "lhb_candidates.csv"
    pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "ts_code": "600023.SH"},
            {"trade_date": "2025-01-03", "ts_code": "600023.SH"},
            {"trade_date": "2025-01-03", "ts_code": "000001.SZ"},
            {"trade_date": "2024-12-31", "ts_code": "300001.SZ"},
            {"trade_date": "2025-01-04", "ts_code": ""},
        ]
    ).to_csv(path, index=False)

    universe = load_lhb_auction_backfill_universe(
        candidate_paths=[path],
        start_date="2025-01-01",
        end_date="2025-01-31",
    )

    assert universe == ["000001.SZ", "600023.SH"]
```

- [ ] **Step 2: Run the failing test**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/pytest tests/test_auction_data.py::test_load_lhb_auction_backfill_universe_reads_unique_ts_codes -q
```

Expected:

```text
FAILED ... NameError: name 'load_lhb_auction_backfill_universe' is not defined
```

- [ ] **Step 3: Implement the loader**

Add this function to `src/stock_research/auction_data.py`:

```python
def load_lhb_auction_backfill_universe(
    *,
    candidate_paths: list[str | Path],
    start_date: str,
    end_date: str,
) -> list[str]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    values: set[str] = set()
    for path_value in candidate_paths:
        path = Path(path_value)
        frame = pd.read_csv(path, low_memory=False)
        if frame.empty or "ts_code" not in frame.columns:
            continue
        data = frame.copy()
        if "trade_date" in data.columns:
            dates = pd.to_datetime(data["trade_date"], errors="coerce")
            data = data[dates.between(start, end)]
        codes = data["ts_code"].astype(str).str.strip().str.upper()
        values.update(code for code in codes if code and code != "NAN")
    return sorted(values)
```

- [ ] **Step 4: Run test to verify pass**

Run:

```bash
.venv/bin/pytest tests/test_auction_data.py::test_load_lhb_auction_backfill_universe_reads_unique_ts_codes -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/auction_data.py tests/test_auction_data.py
git commit -m "feat: load lhb auction backfill universe"
```

## Task 2: Build Missing-Only Auction Backfill Plan

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] **Step 1: Write failing test for missing coverage plan**

Add this test:

```python
def test_build_lhb_auction_backfill_plan_skips_complete_date_phase():
    trade_dates = ["2025-01-02", "2025-01-03"]
    ts_codes = ["000001.SZ", "600023.SH"]
    existing = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "ts_code": "000001.SZ", "auction_phase": "open_call"},
            {"trade_date": "2025-01-02", "ts_code": "600023.SH", "auction_phase": "open_call"},
            {"trade_date": "2025-01-02", "ts_code": "000001.SZ", "auction_phase": "close_call"},
        ]
    )

    plan = build_lhb_auction_backfill_plan(
        trade_dates=trade_dates,
        ts_codes=ts_codes,
        auction_phases=["open_call", "close_call"],
        existing_coverage=existing,
    )

    assert plan.to_dict("records") == [
        {
            "trade_date": "2025-01-02",
            "auction_phase": "close_call",
            "selected_ts_codes": 2,
            "existing_rows": 1,
            "missing_rows": 1,
            "should_query": True,
        },
        {
            "trade_date": "2025-01-03",
            "auction_phase": "open_call",
            "selected_ts_codes": 2,
            "existing_rows": 0,
            "missing_rows": 2,
            "should_query": True,
        },
        {
            "trade_date": "2025-01-03",
            "auction_phase": "close_call",
            "selected_ts_codes": 2,
            "existing_rows": 0,
            "missing_rows": 2,
            "should_query": True,
        },
    ]
```

- [ ] **Step 2: Implement the plan builder**

Add this function:

```python
def build_lhb_auction_backfill_plan(
    *,
    trade_dates: list[str],
    ts_codes: list[str],
    auction_phases: list[str],
    existing_coverage: pd.DataFrame,
) -> pd.DataFrame:
    selected_codes = sorted({str(code).strip().upper() for code in ts_codes if str(code).strip()})
    coverage = existing_coverage.copy()
    if coverage.empty:
        coverage = pd.DataFrame(columns=["trade_date", "ts_code", "auction_phase"])
    coverage["trade_date"] = pd.to_datetime(coverage["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    coverage["ts_code"] = coverage["ts_code"].astype(str).str.strip().str.upper()
    coverage["auction_phase"] = coverage["auction_phase"].astype(str).str.strip()

    rows: list[dict[str, object]] = []
    for trade_date in sorted(set(trade_dates)):
        normalized_date = pd.Timestamp(trade_date).strftime("%Y-%m-%d")
        for phase in auction_phases:
            existing_rows = coverage[
                coverage["trade_date"].eq(normalized_date)
                & coverage["auction_phase"].eq(phase)
                & coverage["ts_code"].isin(selected_codes)
            ]["ts_code"].nunique()
            missing_rows = max(len(selected_codes) - int(existing_rows), 0)
            if missing_rows <= 0:
                continue
            rows.append(
                {
                    "trade_date": normalized_date,
                    "auction_phase": phase,
                    "selected_ts_codes": len(selected_codes),
                    "existing_rows": int(existing_rows),
                    "missing_rows": missing_rows,
                    "should_query": True,
                }
            )
    return pd.DataFrame(
        rows,
        columns=[
            "trade_date",
            "auction_phase",
            "selected_ts_codes",
            "existing_rows",
            "missing_rows",
            "should_query",
        ],
    )
```

- [ ] **Step 3: Run focused test**

Run:

```bash
.venv/bin/pytest tests/test_auction_data.py::test_build_lhb_auction_backfill_plan_skips_complete_date_phase -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/auction_data.py tests/test_auction_data.py
git commit -m "feat: build lhb auction backfill plan"
```

## Task 3: Add Existing Coverage Loader

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] **Step 1: Write failing test for coverage SQL**

Add this test:

```python
def test_load_existing_lhb_auction_coverage_queries_selected_scope(monkeypatch):
    recorded = {}

    class Context:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_fetch_all(conn, sql, params):
        recorded["sql"] = sql
        recorded["params"] = params
        return [
            {"trade_date": "2025-01-02", "ts_code": "600023.SH", "auction_phase": "open_call"},
        ]

    monkeypatch.setattr("stock_research.auction_data.connect", lambda service: Context())
    monkeypatch.setattr("stock_research.auction_data.fetch_all", fake_fetch_all)

    coverage = load_existing_lhb_auction_coverage(
        start_date="2025-01-01",
        end_date="2025-01-31",
        ts_codes=["600023.SH"],
        auction_phases=["open_call"],
    )

    assert "FROM market.stock_auction_bar" in recorded["sql"]
    assert recorded["params"] == ["2025-01-01", "2025-01-31", ["600023.SH"], ["open_call"]]
    assert coverage.to_dict("records") == [
        {"trade_date": "2025-01-02", "ts_code": "600023.SH", "auction_phase": "open_call"}
    ]
```

- [ ] **Step 2: Implement coverage loader**

Add:

```python
def load_existing_lhb_auction_coverage(
    *,
    start_date: str,
    end_date: str,
    ts_codes: list[str],
    auction_phases: list[str],
    research_service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT trade_date::text AS trade_date, ts_code, auction_phase
    FROM market.stock_auction_bar
    WHERE trade_date BETWEEN %s AND %s
      AND ts_code = ANY(%s)
      AND auction_phase = ANY(%s)
      AND source = 'tushare'
    ORDER BY trade_date, auction_phase, ts_code
    """
    with connect(research_service) as conn:
        rows = fetch_all(conn, sql, [start_date, end_date, ts_codes, auction_phases])
    return pd.DataFrame(rows, columns=["trade_date", "ts_code", "auction_phase"])
```

- [ ] **Step 3: Run focused test**

Run:

```bash
.venv/bin/pytest tests/test_auction_data.py::test_load_existing_lhb_auction_coverage_queries_selected_scope -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/auction_data.py tests/test_auction_data.py
git commit -m "feat: load lhb auction coverage"
```

## Task 4: Add Dry-Run Report Builder

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] **Step 1: Write failing test for report outputs**

Add:

```python
def test_write_lhb_auction_backfill_plan_report_writes_csv_and_markdown(tmp_path):
    plan = pd.DataFrame(
        [
            {
                "trade_date": "2025-01-02",
                "auction_phase": "open_call",
                "selected_ts_codes": 2,
                "existing_rows": 0,
                "missing_rows": 2,
                "should_query": True,
            },
            {
                "trade_date": "2025-01-02",
                "auction_phase": "close_call",
                "selected_ts_codes": 2,
                "existing_rows": 1,
                "missing_rows": 1,
                "should_query": True,
            },
        ]
    )

    result = write_lhb_auction_backfill_plan_report(
        plan=plan,
        output_dir=tmp_path,
        start_date="2025-01-01",
        end_date="2025-01-31",
        ts_code_count=2,
    )

    assert Path(result["paths"]["plan"]).exists()
    assert Path(result["paths"]["markdown_report"]).exists()
    assert result["summary"]["planned_calls"] == 2
    assert result["summary"]["planned_missing_rows"] == 3
```

- [ ] **Step 2: Implement report writer**

Add:

```python
def write_lhb_auction_backfill_plan_report(
    *,
    plan: pd.DataFrame,
    output_dir: str | Path,
    start_date: str,
    end_date: str,
    ts_code_count: int,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    suffix = f"{start_date.replace('-', '')}_{end_date.replace('-', '')}"
    plan_path = output / f"lhb_auction_backfill_plan_{suffix}.csv"
    report_path = output / f"lhb_auction_backfill_plan_{suffix}.md"
    plan.to_csv(plan_path, index=False)

    planned_calls = int(len(plan))
    planned_missing_rows = int(pd.to_numeric(plan.get("missing_rows", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
    phase_counts = plan["auction_phase"].value_counts().to_dict() if "auction_phase" in plan.columns else {}
    lines = [
        "# LHB Auction Backfill Plan",
        "",
        f"- Window: `{start_date}` to `{end_date}`",
        f"- Universe size: `{ts_code_count}`",
        f"- Planned calls: `{planned_calls}`",
        f"- Planned missing rows: `{planned_missing_rows}`",
        f"- Phase counts: `{phase_counts}`",
        "",
        "This is a dry-run plan. It does not call Tushare.",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "plan": plan,
        "summary": {
            "planned_calls": planned_calls,
            "planned_missing_rows": planned_missing_rows,
            "phase_counts": phase_counts,
        },
        "paths": {
            "plan": str(plan_path),
            "markdown_report": str(report_path),
        },
    }
```

- [ ] **Step 3: Run focused test**

Run:

```bash
.venv/bin/pytest tests/test_auction_data.py::test_write_lhb_auction_backfill_plan_report_writes_csv_and_markdown -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/auction_data.py tests/test_auction_data.py
git commit -m "feat: report lhb auction backfill plan"
```

## Task 5: Add Ordered Executor With Max Calls

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] **Step 1: Write failing test for max-call execution limit**

Add:

```python
def test_run_lhb_auction_backfill_plan_respects_max_calls(monkeypatch):
    calls = []
    plan = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "auction_phase": "open_call"},
            {"trade_date": "2025-01-02", "auction_phase": "close_call"},
            {"trade_date": "2025-01-03", "auction_phase": "open_call"},
        ]
    )

    def fake_query(client, trade_date, auction_phase):
        calls.append((trade_date.strftime("%Y-%m-%d"), auction_phase))
        return [
            {
                "ts_code": "600023.SH",
                "trade_date": trade_date.strftime("%Y%m%d"),
                "open": 10,
                "high": 10,
                "low": 10,
                "close": 10,
                "vol": 100,
                "amount": 1000,
                "vwap": 10,
            }
        ]

    monkeypatch.setattr("stock_research.auction_data.tushare_client", lambda token=None: "client")
    monkeypatch.setattr("stock_research.auction_data.query_tushare_auction_rows_for_trade_date", fake_query)
    monkeypatch.setattr(
        "stock_research.auction_data.upsert_stock_auction_bars",
        lambda rows, auction_phase, source_endpoint, params: len(rows),
    )

    executed = run_lhb_auction_backfill_plan(
        plan=plan,
        ts_codes=["600023.SH"],
        max_calls=2,
        sleep_seconds=0,
    )

    assert calls == [("2025-01-02", "open_call"), ("2025-01-02", "close_call")]
    assert executed["summary"]["executed_calls"] == 2
    assert executed["summary"]["remaining_calls"] == 1
```

- [ ] **Step 2: Implement executor**

Add:

```python
def run_lhb_auction_backfill_plan(
    *,
    plan: pd.DataFrame,
    ts_codes: list[str],
    max_calls: int,
    token: str | None = None,
    sleep_seconds: float = 1.3,
) -> dict[str, Any]:
    selected_ts_codes = {str(code).strip().upper() for code in ts_codes if str(code).strip()}
    client = tushare_client(token=token)
    rows: list[dict[str, Any]] = []
    executed_calls = 0
    total_plan_calls = len(plan)
    for _, task in plan.sort_values(["trade_date", "auction_phase"]).head(max_calls).iterrows():
        phase = str(task["auction_phase"])
        trade_date = dt.date.fromisoformat(str(task["trade_date"]))
        endpoint = auction_endpoint_for_phase(phase)
        raw_rows = query_tushare_auction_rows_for_trade_date(
            client,
            trade_date=trade_date,
            auction_phase=phase,
        )
        selected_rows = [row for row in raw_rows if str(row.get("ts_code")).strip().upper() in selected_ts_codes]
        params = {
            "trade_date": trade_date.strftime("%Y%m%d"),
            "auction_phase": phase,
            "ts_codes": sorted(selected_ts_codes),
            "executor": "lhb_auction_backfill_plan_v1",
        }
        upserted = upsert_stock_auction_bars(
            selected_rows,
            auction_phase=phase,
            source_endpoint=endpoint,
            params=params,
        )
        rows.append(
            {
                "trade_date": trade_date.strftime("%Y-%m-%d"),
                "auction_phase": phase,
                "queried_rows": len(raw_rows),
                "selected_rows": len(selected_rows),
                "upserted_rows": upserted,
            }
        )
        executed_calls += 1
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return {
        "executed": pd.DataFrame(rows),
        "summary": {
            "executed_calls": executed_calls,
            "remaining_calls": max(total_plan_calls - executed_calls, 0),
            "upserted_rows": int(sum(row["upserted_rows"] for row in rows)),
        },
    }
```

- [ ] **Step 3: Run focused test**

Run:

```bash
.venv/bin/pytest tests/test_auction_data.py::test_run_lhb_auction_backfill_plan_respects_max_calls -q
```

Expected:

```text
1 passed
```

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/auction_data.py tests/test_auction_data.py
git commit -m "feat: run lhb auction backfill plan"
```

## Task 6: Add CLI Commands

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write parser test**

Add to `tests/test_schema.py`:

```python
def test_cli_accepts_lhb_auction_backfill_commands():
    plan_args = build_parser().parse_args(
        [
            "lhb-auction-backfill-plan-v1",
            "--candidate-paths",
            "selected.csv,phase18.csv",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2026-06-09",
            "--auction-phases",
            "open_call,close_call",
            "--output-dir",
            "outputs/research/lhb_auction_backfill_20250101",
        ]
    )
    assert plan_args.command == "lhb-auction-backfill-plan-v1"
    assert plan_args.candidate_paths == ["selected.csv", "phase18.csv"]
    assert plan_args.auction_phases == ["open_call", "close_call"]

    run_args = build_parser().parse_args(
        [
            "lhb-auction-backfill-run-v1",
            "--plan-path",
            "plan.csv",
            "--ts-codes-path",
            "universe.csv",
            "--max-calls",
            "500",
            "--sleep-seconds",
            "1.3",
            "--output-dir",
            "outputs/research/lhb_auction_backfill_20250101",
        ]
    )
    assert run_args.command == "lhb-auction-backfill-run-v1"
    assert run_args.max_calls == 500
```

- [ ] **Step 2: Add parser arguments**

In `src/stock_research/cli.py`, add:

```python
lhb_auction_backfill_plan = subparsers.add_parser("lhb-auction-backfill-plan-v1")
lhb_auction_backfill_plan.add_argument("--candidate-paths", type=parse_str_list, required=True)
lhb_auction_backfill_plan.add_argument("--start-date", required=True)
lhb_auction_backfill_plan.add_argument("--end-date", required=True)
lhb_auction_backfill_plan.add_argument(
    "--auction-phases",
    type=parse_auction_phases,
    default=["open_call", "close_call"],
)
lhb_auction_backfill_plan.add_argument(
    "--trade-dates",
    type=parse_trade_dates,
    help="Optional explicit A-share trade dates. Use this to avoid natural-day calls.",
)
lhb_auction_backfill_plan.add_argument("--output-dir", required=True)

lhb_auction_backfill_run = subparsers.add_parser("lhb-auction-backfill-run-v1")
lhb_auction_backfill_run.add_argument("--plan-path", required=True)
lhb_auction_backfill_run.add_argument("--ts-codes-path", required=True)
lhb_auction_backfill_run.add_argument("--max-calls", type=int, default=500)
lhb_auction_backfill_run.add_argument("--sleep-seconds", type=float, default=1.3)
lhb_auction_backfill_run.add_argument("--token")
lhb_auction_backfill_run.add_argument("--output-dir", required=True)
```

- [ ] **Step 3: Add dispatch**

In `main`, add:

```python
elif args.command == "lhb-auction-backfill-plan-v1":
    ts_codes = load_lhb_auction_backfill_universe(
        candidate_paths=args.candidate_paths,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    trade_dates = args.trade_dates or []
    coverage = load_existing_lhb_auction_coverage(
        start_date=args.start_date,
        end_date=args.end_date,
        ts_codes=ts_codes,
        auction_phases=args.auction_phases,
    )
    plan = build_lhb_auction_backfill_plan(
        trade_dates=trade_dates,
        ts_codes=ts_codes,
        auction_phases=args.auction_phases,
        existing_coverage=coverage,
    )
    result = write_lhb_auction_backfill_plan_report(
        plan=plan,
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        ts_code_count=len(ts_codes),
    )
    print(f"lhb_auction_backfill_plan_v1|plan|{result['paths']['plan']}")
    print(f"lhb_auction_backfill_plan_v1|report|{result['paths']['markdown_report']}")
    print(f"lhb_auction_backfill_plan_v1|planned_calls|{result['summary']['planned_calls']}")
    return 0
elif args.command == "lhb-auction-backfill-run-v1":
    plan = pd.read_csv(args.plan_path, low_memory=False)
    universe = pd.read_csv(args.ts_codes_path, low_memory=False)
    ts_codes = sorted(universe["ts_code"].astype(str).str.strip().str.upper().unique())
    result = run_lhb_auction_backfill_plan(
        plan=plan,
        ts_codes=ts_codes,
        max_calls=args.max_calls,
        token=args.token,
        sleep_seconds=args.sleep_seconds,
    )
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    executed_path = output / "lhb_auction_backfill_executed_latest.csv"
    result["executed"].to_csv(executed_path, index=False)
    print(f"lhb_auction_backfill_run_v1|executed|{executed_path}")
    print(f"lhb_auction_backfill_run_v1|executed_calls|{result['summary']['executed_calls']}")
    print(f"lhb_auction_backfill_run_v1|remaining_calls|{result['summary']['remaining_calls']}")
    return 0
```

- [ ] **Step 4: Run parser test**

Run:

```bash
.venv/bin/pytest tests/test_schema.py::test_cli_accepts_lhb_auction_backfill_commands -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py tests/test_schema.py
git commit -m "feat: add lhb auction backfill cli"
```

## Task 7: First Dry Run

**Files:**
- Runtime output only

- [ ] **Step 1: Prepare candidate paths**

Use the most recent LHB candidate artifacts that contain `ts_code` and `trade_date`.

Preferred first inputs:

```text
outputs/research/lhb_phase18c_auction_cash_account_*/lhb_phase18c_selected_trades_*.csv
outputs/research/lhb_phase18b_auction_topn_rerank_*/lhb_phase18b_scored_candidates_*.csv
```

If multiple files exist, pass them as a comma-separated list.

- [ ] **Step 2: Generate explicit trade dates**

Use an existing trading calendar artifact or database query to produce only A-share open dates from `2025-01-01` to the selected end date. Save them as comma-separated CLI input or an operator note.

Do not run the backfill command over natural calendar dates.

- [ ] **Step 3: Run dry-run plan**

Example:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research lhb-auction-backfill-plan-v1 \
  --candidate-paths outputs/research/lhb_phase18c_auction_cash_account_20250101_20260605/lhb_phase18c_selected_trades_v1.csv \
  --start-date 2025-01-01 \
  --end-date 2026-06-09 \
  --auction-phases open_call,close_call \
  --trade-dates 2025-01-02,2025-01-03 \
  --output-dir outputs/research/lhb_auction_backfill_20250101
```

Expected:

```text
lhb_auction_backfill_plan_v1|plan|outputs/research/lhb_auction_backfill_20250101/lhb_auction_backfill_plan_20250101_20260609.csv
lhb_auction_backfill_plan_v1|report|outputs/research/lhb_auction_backfill_20250101/lhb_auction_backfill_plan_20250101_20260609.md
lhb_auction_backfill_plan_v1|planned_calls|...
```

- [ ] **Step 4: Review plan before spending calls**

Open the markdown report and verify:

- Planned calls are below the intended cap.
- Phase counts include both `open_call` and `close_call`.
- Universe size matches the expected LHB candidate count.
- Missing rows are plausible.

## Task 8: First Controlled Backfill Run

**Files:**
- Runtime output only

- [ ] **Step 1: Run small execution**

Start with `--max-calls 20`:

```bash
cd /Users/xiwei/stock_research
.venv/bin/stock-research lhb-auction-backfill-run-v1 \
  --plan-path outputs/research/lhb_auction_backfill_20250101/lhb_auction_backfill_plan_20250101_20260609.csv \
  --ts-codes-path outputs/research/lhb_auction_backfill_20250101/lhb_auction_backfill_universe_20250101_20260609.csv \
  --max-calls 20 \
  --sleep-seconds 1.3 \
  --output-dir outputs/research/lhb_auction_backfill_20250101
```

Expected:

```text
lhb_auction_backfill_run_v1|executed|...
lhb_auction_backfill_run_v1|executed_calls|20
lhb_auction_backfill_run_v1|remaining_calls|...
```

- [ ] **Step 2: Regenerate plan**

Run the dry-run command again. Expected:

- Missing calls decrease by 20 if those trade dates/phases returned usable rows.
- Already upserted rows are skipped.

- [ ] **Step 3: Scale to daily cap**

If the first run is healthy:

```bash
.venv/bin/stock-research lhb-auction-backfill-run-v1 \
  --plan-path outputs/research/lhb_auction_backfill_20250101/lhb_auction_backfill_plan_20250101_20260609.csv \
  --ts-codes-path outputs/research/lhb_auction_backfill_20250101/lhb_auction_backfill_universe_20250101_20260609.csv \
  --max-calls 500 \
  --sleep-seconds 1.3 \
  --output-dir outputs/research/lhb_auction_backfill_20250101
```

## Task 9: Verification After Backfill

**Files:**
- Runtime output only

- [ ] **Step 1: Run unit tests**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/pytest tests/test_auction_data.py tests/test_schema.py::test_cli_accepts_lhb_auction_backfill_commands -q
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Run coverage audit**

Regenerate dry-run plan after each batch. Completion target:

```text
planned_calls = 0
```

If planned calls remain positive:

- Check if Tushare returned no rows for suspended or non-trading stocks.
- Check if the trade date is a holiday accidentally included in `--trade-dates`.
- Check if `ts_code` format differs from Tushare format.

- [ ] **Step 3: Re-run Phase18 diagnostics**

After coverage is complete enough:

- Re-run Phase18C auction cash account.
- Re-run Phase18D close auction lifecycle.
- Re-run Phase18E joint exit diagnostics.
- Re-run Phase18F tradable joint exit replay.

Compare these metrics against the last saved reports:

- Top3/Top5/Top10 win rate.
- Average return.
- Final equity.
- Max drawdown.
- Number of adjusted exits.
- Sell-flying risk after new exit rules.

## Risk Controls

- Never run without `--max-calls`.
- Never pass a Tushare token in shell history if the environment variable `TUSHARE_TOKEN` is available.
- Prefer explicit `--trade-dates`; do not query natural days.
- Keep `--sleep-seconds >= 1.3` unless Tushare limits are rechecked.
- Do not include `data/manual/` or large PDF artifacts in this feature branch.

## Acceptance Criteria

- Dry-run command produces a CSV plan and markdown report without calling Tushare.
- Execution command respects `--max-calls`.
- Re-running dry-run after execution skips already stored rows.
- Open and close auction result bars are stored in `market.stock_auction_bar`.
- Existing Phase18 reports can read the completed auction data without code changes.
- Focused tests pass.

## Self-Review

- Requirement coverage:
  - Starts from `2025-01-01`: covered by CLI and plan examples.
  - Sequential backfill: covered by sorted plan execution.
  - Avoid daily call cap: covered by `--max-calls` and `--sleep-seconds`.
  - Avoid repeated downloads: covered by existing coverage loader and missing-only plan.
  - First phase only auction results: stated in scope and non-goals.

- Placeholder scan:
  - No placeholder implementation steps are left.
  - Runtime paths are examples and should be replaced with the actual latest LHB artifacts during execution.

- Type consistency:
  - `candidate_paths` is parsed as `list[str]`.
  - `auction_phases` uses existing `parse_auction_phases`.
  - `trade_dates` uses existing `parse_trade_dates`.
  - Plan DataFrame columns are reused by the executor.
