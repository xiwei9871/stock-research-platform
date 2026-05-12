# Full-History Phase 7 Finance PIT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete point-in-time financial statement infrastructure so value, quality, and cash-flow factors can use full financial statements without future leakage.

**Architecture:** Keep Baostock finance ingestion for the data it already covers well: quarterly indicators, income statement fields, and share-capital events. Add an AKShare/Eastmoney statement loader for full-history balance sheet and cash-flow statement absolute amounts, archive raw payloads, and expose point-in-time and TTM helpers that filter strictly by `announcement_date <= trade_date`.

**Tech Stack:** Python, pandas, PostgreSQL, psycopg, AKShare, Baostock, pytest, existing `stock-research` CLI and `ingest.batch_job` control plane.

---

## Current Findings

- Phase 6 industry-history raw monthly snapshots are complete from `1990-12-31` through `2026-05-08`.
- Baostock `query_stock_industry` returns empty snapshots before `2006-01-31`; this is recorded as raw empty payloads, not skipped work.
- Current finance table coverage:
  - `finance.indicator_quarter`: populated from `2007-03-31` through `2025-12-31`.
  - `finance.income_statement`: populated from `2007-03-31` through `2025-12-31`.
  - `finance.share_capital_event`: populated from `2007-03-31` through `2025-12-31`.
  - `finance.balance_sheet`: empty.
  - `finance.cash_flow`: empty.
- Local probe showed Baostock `query_balance_data` and `query_cash_flow_data` return ratio fields, not the absolute statement fields required by current schema.
- Local AKShare probe showed `stock_balance_sheet_by_report_em("SH600000")` returns absolute fields such as `TOTAL_ASSETS`, `TOTAL_LIABILITIES`, `TOTAL_EQUITY`, `MONETARYFUNDS`, `ACCOUNTS_RECE`, `INVENTORY`, and `GOODWILL`.
- Local AKShare probe showed `stock_cash_flow_sheet_by_report_em("SH600000")` returns absolute fields such as `NETCASH_OPERATE`, `NETCASH_INVEST`, `NETCASH_FINANCE`, and `CONSTRUCT_LONG_ASSET`.
- The worktree currently contains unrelated/uncommitted changes in `src/stock_research/cli.py`, `src/stock_research/ingest_jobs.py`, `src/stock_research/loaders/baostock_finance_ingestion.py`, and multiple tests. Execution must not revert them. Stage only Phase 7 hunks.

## Scope

In scope:

- AKShare/Eastmoney balance-sheet and cash-flow statement normalization;
- raw AKShare payload archival into `raw_akshare.finance_payload`;
- upserts into `finance.balance_sheet` and `finance.cash_flow`;
- one-asset smoke sync before long backfill;
- resumable `ingest.batch_job` integration for AKShare finance statements;
- point-in-time loaders for latest balance sheet and cash flow by trade date;
- TTM helpers that use only rows announced by the trade date;
- audit checks for missing balance/cash-flow rows and invalid announcement dates;
- runbook commands.

Out of scope:

- Replacing the existing Baostock indicator/income/share-capital ingestion;
- adding every AKShare statement column to normalized finance tables;
- using financial factors in scoring before Phase 8 factor backfill and gates.

## Files

- Create: `src/stock_research/loaders/akshare_finance_statements.py`
- Create: `tests/test_akshare_finance_statements.py`
- Create: `src/stock_research/finance_audit.py`
- Create: `tests/test_finance_audit.py`
- Create: `src/stock_research/services/finance_ttm.py`
- Create: `tests/test_finance_ttm.py`
- Modify: `src/stock_research/loaders/akshare_finance_loader.py`
- Modify: `src/stock_research/ingest_jobs.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/data_audit.py`
- Modify: `tests/test_ingest_jobs.py`
- Modify: `tests/test_schema.py` or current CLI parser tests
- Modify: `tests/test_data_audit.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: AKShare Statement Normalizers And Upserts

**Files:**

- Create: `src/stock_research/loaders/akshare_finance_statements.py`
- Create: `tests/test_akshare_finance_statements.py`

- [ ] **Step 1: Write failing normalizer tests**

Add:

```python
from stock_research.loaders import akshare_finance_statements


def test_normalize_em_balance_sheet_row_maps_absolute_fields():
    row = {
        "SECUCODE": "600000.SH",
        "REPORT_DATE": "2025-12-31 00:00:00",
        "REPORT_TYPE": "年报",
        "NOTICE_DATE": "2026-03-31 00:00:00",
        "TOTAL_ASSETS": 100.0,
        "TOTAL_LIABILITIES": 60.0,
        "TOTAL_EQUITY": 40.0,
        "MONETARYFUNDS": 10.0,
        "ACCOUNTS_RECE": 2.0,
        "INVENTORY": 3.0,
        "GOODWILL": 4.0,
    }

    normalized = akshare_finance_statements.normalize_em_balance_sheet_row(row)

    assert normalized == {
        "asset_id": "CN:SH:600000",
        "report_period": "2025-12-31",
        "report_type": "FY",
        "announcement_date": "2026-03-31",
        "total_assets": 100.0,
        "total_liabilities": 60.0,
        "total_equity": 40.0,
        "monetary_funds": 10.0,
        "accounts_receivable": 2.0,
        "inventory": 3.0,
        "goodwill": 4.0,
        "source": "akshare_em",
    }


def test_normalize_em_cash_flow_row_maps_absolute_fields():
    row = {
        "SECUCODE": "600000.SH",
        "REPORT_DATE": "2025-12-31 00:00:00",
        "REPORT_TYPE": "年报",
        "NOTICE_DATE": "2026-03-31 00:00:00",
        "NETCASH_OPERATE": 20.0,
        "NETCASH_INVEST": -5.0,
        "NETCASH_FINANCE": -3.0,
        "CONSTRUCT_LONG_ASSET": 2.0,
    }

    normalized = akshare_finance_statements.normalize_em_cash_flow_row(row)

    assert normalized["asset_id"] == "CN:SH:600000"
    assert normalized["report_period"] == "2025-12-31"
    assert normalized["report_type"] == "FY"
    assert normalized["announcement_date"] == "2026-03-31"
    assert normalized["net_operate_cash_flow"] == 20.0
    assert normalized["net_invest_cash_flow"] == -5.0
    assert normalized["net_finance_cash_flow"] == -3.0
    assert normalized["capex"] == 2.0
    assert normalized["free_cash_flow"] == 18.0
    assert normalized["source"] == "akshare_em"
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_akshare_finance_statements.py::test_normalize_em_balance_sheet_row_maps_absolute_fields tests/test_akshare_finance_statements.py::test_normalize_em_cash_flow_row_maps_absolute_fields -q
```

Expected: fails because `stock_research.loaders.akshare_finance_statements` does not exist.

- [ ] **Step 3: Implement normalizers**

Create `src/stock_research/loaders/akshare_finance_statements.py` with:

```python
from typing import Any

import pandas as pd

from stock_research.assets import asset_id_from_baostock_code


def _date(value: Any) -> str:
    return str(value)[:10]


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    if text == "":
        return None
    return float(value)


def _asset_id_from_secucode(value: str) -> str:
    code, exchange = str(value).split(".", 1)
    return asset_id_from_baostock_code(f"{exchange.lower()}.{code}")


def _report_type(value: Any) -> str:
    text = str(value)
    return "FY" if "年报" in text else "Q"


def normalize_em_balance_sheet_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": _asset_id_from_secucode(str(row["SECUCODE"])),
        "report_period": _date(row["REPORT_DATE"]),
        "report_type": _report_type(row.get("REPORT_TYPE")),
        "announcement_date": _date(row["NOTICE_DATE"]),
        "total_assets": _number(row.get("TOTAL_ASSETS")),
        "total_liabilities": _number(row.get("TOTAL_LIABILITIES")),
        "total_equity": _number(row.get("TOTAL_EQUITY")),
        "monetary_funds": _number(row.get("MONETARYFUNDS")),
        "accounts_receivable": _number(row.get("ACCOUNTS_RECE")),
        "inventory": _number(row.get("INVENTORY")),
        "goodwill": _number(row.get("GOODWILL")),
        "source": "akshare_em",
    }


def normalize_em_cash_flow_row(row: dict[str, Any]) -> dict[str, Any]:
    net_operate = _number(row.get("NETCASH_OPERATE"))
    capex = _number(row.get("CONSTRUCT_LONG_ASSET"))
    free_cash_flow = None if net_operate is None else net_operate - (capex or 0.0)
    return {
        "asset_id": _asset_id_from_secucode(str(row["SECUCODE"])),
        "report_period": _date(row["REPORT_DATE"]),
        "report_type": _report_type(row.get("REPORT_TYPE")),
        "announcement_date": _date(row["NOTICE_DATE"]),
        "net_operate_cash_flow": net_operate,
        "net_invest_cash_flow": _number(row.get("NETCASH_INVEST")),
        "net_finance_cash_flow": _number(row.get("NETCASH_FINANCE")),
        "capex": capex,
        "free_cash_flow": free_cash_flow,
        "source": "akshare_em",
    }
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_akshare_finance_statements.py -q
```

Expected: normalizer tests pass.

- [ ] **Step 5: Add failing upsert tests**

Add tests asserting `upsert_balance_sheets` inserts into `finance.balance_sheet`, `upsert_cash_flows` inserts into `finance.cash_flow`, and empty inputs return zero.

- [ ] **Step 6: Implement upserts**

Add `upsert_balance_sheets(conn, rows)` and `upsert_cash_flows(conn, rows)` using `execute_many`. Use the existing primary keys:

```sql
ON CONFLICT (asset_id, report_period, report_type, announcement_date, source)
DO UPDATE SET
    total_assets = EXCLUDED.total_assets,
    total_liabilities = EXCLUDED.total_liabilities,
    total_equity = EXCLUDED.total_equity,
    monetary_funds = EXCLUDED.monetary_funds,
    accounts_receivable = EXCLUDED.accounts_receivable,
    inventory = EXCLUDED.inventory,
    goodwill = EXCLUDED.goodwill,
    updated_at = now()
```

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/loaders/akshare_finance_statements.py tests/test_akshare_finance_statements.py
git commit -m "Add AKShare finance statement normalizers"
```

## Task 2: AKShare Raw Archive And One-Asset Sync

**Files:**

- Modify: `src/stock_research/loaders/akshare_finance_statements.py`
- Modify: `src/stock_research/loaders/akshare_finance_loader.py`
- Modify: `tests/test_akshare_finance_statements.py`

- [ ] **Step 1: Write failing sync tests**

Test `sync_finance_statements_for_asset("CN:SH:600000", "SH600000")` with monkeypatched AKShare functions returning two small DataFrames. Assert:

- `store_finance_payload` is called for `stock_balance_sheet_by_report_em`;
- `store_finance_payload` is called for `stock_cash_flow_sheet_by_report_em`;
- balance and cash rows are upserted;
- returned counts include `balance_sheet`, `cash_flow`, and `raw_payload`.

- [ ] **Step 2: Implement fetch and sync**

Add:

```python
import akshare as ak
from stock_research.config import SETTINGS
from stock_research.db import connect
from stock_research.loaders.akshare_finance_loader import store_finance_payload


def sync_finance_statements_for_asset(
    asset_id: str,
    akshare_symbol: str,
    *,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    balance_df = ak.stock_balance_sheet_by_report_em(symbol=akshare_symbol)
    cash_df = ak.stock_cash_flow_sheet_by_report_em(symbol=akshare_symbol)
    balance_payload = balance_df.to_dict("records")
    cash_payload = cash_df.to_dict("records")
    balance_rows = [normalize_em_balance_sheet_row(row) for row in balance_payload if row.get("NOTICE_DATE")]
    cash_rows = [normalize_em_cash_flow_row(row) for row in cash_payload if row.get("NOTICE_DATE")]
    with connect(service) as conn:
        store_finance_payload(
            conn,
            "stock_balance_sheet_by_report_em",
            {"symbol": akshare_symbol},
            balance_payload,
            asset_id=asset_id,
        )
        store_finance_payload(
            conn,
            "stock_cash_flow_sheet_by_report_em",
            {"symbol": akshare_symbol},
            cash_payload,
            asset_id=asset_id,
        )
        balance_count = upsert_balance_sheets(conn, balance_rows)
        cash_count = upsert_cash_flows(conn, cash_rows)
    return {"balance_sheet": balance_count, "cash_flow": cash_count, "raw_payload": 2}
```

- [ ] **Step 3: Run a real one-asset smoke sync**

Run:

```bash
.venv/bin/python - <<'PY'
from stock_research.loaders.akshare_finance_statements import sync_finance_statements_for_asset
print(sync_finance_statements_for_asset("CN:SH:600000", "SH600000"))
PY
```

Expected: non-zero `balance_sheet` and `cash_flow`; `raw_payload` equals `2`.

- [ ] **Step 4: Verify database rows**

Run:

```bash
.venv/bin/python - <<'PY'
from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all
with connect(SETTINGS.research_service) as conn:
    for table in ["finance.balance_sheet", "finance.cash_flow"]:
        rows = fetch_all(conn, f"SELECT count(*) AS rows, min(report_period)::text AS min_period, max(report_period)::text AS max_period FROM {table} WHERE asset_id = %s", ["CN:SH:600000"])
        print(table, rows[0])
PY
```

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/loaders/akshare_finance_statements.py src/stock_research/loaders/akshare_finance_loader.py tests/test_akshare_finance_statements.py
git commit -m "Sync AKShare finance statements for one asset"
```

## Task 3: Resumable AKShare Statement Backfill Jobs

**Files:**

- Modify: `src/stock_research/ingest_jobs.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_ingest_jobs.py`
- Modify: parser tests currently located in `tests/test_schema.py`

- [ ] **Step 1: Write failing job-builder tests**

Add tests for:

- `build_akshare_finance_statement_jobs(asset_count=3, batch_size=2)` returns two jobs;
- job ids are `akshare-finance-statements:offset0:limit2` and `akshare-finance-statements:offset2:limit2`;
- `dataset` is `akshare-finance-statements`;
- `source` is `akshare_em`.

- [ ] **Step 2: Implement job builder and creator**

Add:

```python
def akshare_finance_statement_job_id(offset: int, limit: int) -> str:
    return f"akshare-finance-statements:offset{offset}:limit{limit}"


def build_akshare_finance_statement_jobs(*, asset_count: int, batch_size: int) -> list[dict[str, Any]]:
    jobs = []
    for offset in range(0, asset_count, batch_size):
        jobs.append({
            "job_id": akshare_finance_statement_job_id(offset, batch_size),
            "dataset": "akshare-finance-statements",
            "source": "akshare_em",
            "year": None,
            "quarter": None,
            "offset_value": offset,
            "limit_value": batch_size,
            "params": {"offset": offset, "limit": batch_size},
        })
    return jobs
```

Extend `create_ingest_jobs_for_service` so `dataset == "akshare-finance-statements"` creates these jobs from `core.asset_master` assets with `akshare_code IS NOT NULL`.

- [ ] **Step 3: Write failing runner tests**

Test that `run_ingest_jobs` dispatches `akshare-finance-statements` jobs to `sync_finance_statements_for_assets(limit, offset)` and counts `balance_sheet + cash_flow` as `rows_written`.

- [ ] **Step 4: Implement batch sync dispatch**

Add a helper in `akshare_finance_statements.py`:

```python
def sync_finance_statements_for_assets(
    *,
    limit: int,
    offset: int,
    service: str = SETTINGS.research_service,
) -> dict[str, int]:
    with connect(service) as conn:
        rows = fetch_all(
            conn,
            """
            SELECT asset_id
            FROM core.asset_master
            WHERE akshare_code IS NOT NULL
              AND exchange IN ('SH', 'SZ')
            ORDER BY asset_id
            OFFSET %s
            LIMIT %s
            """,
            [offset, limit],
        )
    totals = {"queried_assets": 0, "balance_sheet": 0, "cash_flow": 0, "raw_payload": 0}
    for row in rows:
        asset_id = row["asset_id"]
        exchange = asset_id.split(":")[1]
        symbol = asset_id.split(":")[2]
        counts = sync_finance_statements_for_asset(asset_id, f"{exchange}{symbol}", service=service)
        totals["queried_assets"] += 1
        totals["balance_sheet"] += int(counts.get("balance_sheet", 0))
        totals["cash_flow"] += int(counts.get("cash_flow", 0))
        totals["raw_payload"] += int(counts.get("raw_payload", 0))
    return totals
```

It should query `core.asset_master` ordered by `asset_id`, convert `CN:SH:600000` to `SH600000` and `CN:SZ:000001` to `SZ000001`, call `sync_finance_statements_for_asset`, and return totals:

```python
{"queried_assets": n, "balance_sheet": balance_rows, "cash_flow": cash_rows, "raw_payload": raw_payloads}
```

Update `run_ingest_jobs` with a small dataset dispatch instead of a hard-coded Baostock-only branch.

- [ ] **Step 5: Add CLI acceptance**

Ensure existing commands work:

```bash
stock-research create-ingest-jobs --dataset akshare-finance-statements --start-year 1990 --end-year 2026 --batch-size 20
stock-research run-ingest-loop --dataset akshare-finance-statements --jobs-per-round 5 --sleep-seconds 10 --report-target phase7-akshare-finance
```

For this dataset, `start-year` and `end-year` are accepted for CLI compatibility but ignored by the asset-based job builder.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/ingest_jobs.py src/stock_research/cli.py src/stock_research/loaders/akshare_finance_statements.py tests/test_ingest_jobs.py tests/test_schema.py
git commit -m "Add AKShare finance statement backfill jobs"
```

## Task 4: Point-In-Time TTM Helpers

**Files:**

- Create: `src/stock_research/services/finance_ttm.py`
- Create: `tests/test_finance_ttm.py`

- [ ] **Step 1: Write failing TTM tests**

Use synthetic rows where a later report exists but `announcement_date > trade_date`. Assert the later row is excluded.

```python
def test_calc_ttm_uses_only_announced_rows():
    rows = [
        {"report_period": "2024-12-31", "announcement_date": "2025-03-30", "np_parent": 100.0},
        {"report_period": "2025-03-31", "announcement_date": "2025-04-30", "np_parent": 30.0},
        {"report_period": "2025-06-30", "announcement_date": "2025-08-30", "np_parent": 80.0},
        {"report_period": "2024-06-30", "announcement_date": "2024-08-30", "np_parent": 60.0},
    ]

    value = finance_ttm.calc_ttm_from_cumulative_rows(
        rows,
        value_column="np_parent",
        trade_date="2025-07-31",
    )

    assert value == 100.0
```

- [ ] **Step 2: Implement TTM calculation**

Implement:

```python
def calc_ttm_from_cumulative_rows(rows: list[dict], *, value_column: str, trade_date: str) -> float | None:
    available = [
        row for row in rows
        if str(row["announcement_date"])[:10] <= trade_date and row.get(value_column) is not None
    ]
    by_period = {str(row["report_period"])[:10]: float(row[value_column]) for row in available}
    if not by_period:
        return None
    latest_period = max(by_period)
    latest_value = by_period[latest_period]
    if latest_period.endswith("-12-31"):
        return latest_value
    year = int(latest_period[:4])
    suffix = latest_period[4:]
    previous_fy = f"{year - 1}-12-31"
    prior_same_period = f"{year - 1}{suffix}"
    if previous_fy not in by_period or prior_same_period not in by_period:
        return None
    return latest_value + by_period[previous_fy] - by_period[prior_same_period]
```

Rule:

- Filter `announcement_date <= trade_date`.
- Pick newest `report_period`.
- If newest report is `12-31`, return its value.
- Otherwise return `latest_value + previous_fy_value - same_period_prior_year_value` when all three are available.
- Return `None` if required components are missing.

- [ ] **Step 3: Add DB loader tests**

Test `load_income_ttm(conn, asset_id, trade_date)` queries `finance.income_statement` with `announcement_date <= %s` and orders by `report_period DESC, announcement_date DESC`.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/services/finance_ttm.py tests/test_finance_ttm.py
git commit -m "Add point-in-time finance TTM helpers"
```

## Task 5: Finance Coverage Audit

**Files:**

- Create: `src/stock_research/finance_audit.py`
- Create: `tests/test_finance_audit.py`
- Modify: `src/stock_research/cli.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

- [ ] **Step 1: Write failing audit tests**

Test `find_finance_statement_gaps(conn)` returns:

- income periods that have no balance sheet;
- income periods that have no cash flow;
- rows with `announcement_date IS NULL`;
- rows where `announcement_date < report_period` only as warnings, not hard blockers, because some statement sources can publish special period corrections.

- [ ] **Step 2: Implement audit queries**

Create functions:

```python
def summarize_finance_coverage(service: str = SETTINGS.research_service) -> list[dict]:
    checks = [
        (
            "missing_balance_sheet",
            """
            SELECT count(*) AS rows
            FROM finance.income_statement i
            LEFT JOIN finance.balance_sheet b
              USING (asset_id, report_period, report_type, announcement_date, source)
            WHERE b.asset_id IS NULL
            """,
        ),
        (
            "missing_cash_flow",
            """
            SELECT count(*) AS rows
            FROM finance.income_statement i
            LEFT JOIN finance.cash_flow c
              USING (asset_id, report_period, report_type, announcement_date, source)
            WHERE c.asset_id IS NULL
            """,
        ),
    ]
    results = []
    with connect(service) as conn:
        for check, sql in checks:
            row = fetch_all(conn, sql)[0]
            rows = int(row["rows"] or 0)
            results.append({"check": check, "status": "ok" if rows == 0 else "blocked", "rows": rows})
    return results


def format_finance_audit_line(row: dict) -> str:
    return f"finance_audit|{row['check']}|{row['status']}|rows|{row['rows']}"
```

Core checks:

```sql
SELECT count(*) FROM finance.income_statement i
LEFT JOIN finance.balance_sheet b
  USING (asset_id, report_period, report_type, announcement_date, source)
WHERE b.asset_id IS NULL;
```

Use a similar query for `finance.cash_flow`.

- [ ] **Step 3: Add CLI command**

Add:

```bash
stock-research finance-audit
```

It should print stable lines such as `finance_audit|missing_balance_sheet|ok|rows|0`.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/finance_audit.py tests/test_finance_audit.py src/stock_research/cli.py docs/daily-factor-pipeline-runbook.md
git commit -m "Add finance statement coverage audit"
```

## Task 6: Small Batch, Then Full Backfill

**Files:**

- Modify: `docs/daily-factor-pipeline-runbook.md`

- [ ] **Step 1: Apply schema**

Run:

```bash
.venv/bin/stock-research apply-research-schema
```

- [ ] **Step 2: One-asset smoke**

Run:

```bash
.venv/bin/python - <<'PY'
from stock_research.loaders.akshare_finance_statements import sync_finance_statements_for_asset
print(sync_finance_statements_for_asset("CN:SH:600000", "SH600000"))
PY
```

Expected: non-zero `balance_sheet` and `cash_flow`.

- [ ] **Step 3: Small batch jobs**

Run:

```bash
.venv/bin/stock-research create-ingest-jobs --dataset akshare-finance-statements --start-year 1990 --end-year 2026 --batch-size 5
.venv/bin/stock-research run-ingest-loop --dataset akshare-finance-statements --jobs-per-round 1 --sleep-seconds 0 --max-rounds 1 --report-dry-run --report-target phase7-smoke
```

Expected:

- one job succeeds or produces an actionable source error;
- `finance.balance_sheet` row count increases;
- `finance.cash_flow` row count increases.

- [ ] **Step 4: Full backfill**

Run conservatively first:

```bash
.venv/bin/stock-research run-ingest-loop --dataset akshare-finance-statements --jobs-per-round 5 --sleep-seconds 10 --report-target phase7-akshare-finance
```

Do not enable parallelism until single-worker throughput and source reliability are measured.

- [ ] **Step 5: Final verification**

Run:

```bash
.venv/bin/stock-research finance-audit
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
.venv/bin/python -m pytest -q
```

Expected:

- `finance.balance_sheet` and `finance.cash_flow` are non-empty;
- `finance-audit` shows no missing balance/cash-flow rows for the AKShare-covered statement periods;
- all tests pass.

- [ ] **Step 6: Commit runbook**

```bash
git add docs/daily-factor-pipeline-runbook.md
git commit -m "Document phase 7 finance statement backfill"
```

## Self-Review

- Phase 7 master requirements are covered:
  - balance sheet persistence: Tasks 1-3 and 6;
  - cash flow persistence: Tasks 1-3 and 6;
  - report period and announcement date validation: Tasks 1, 2, and 5;
  - point-in-time latest loaders: existing `point_in_time_finance.py`, extended by Task 4;
  - TTM with strict announcement-date filtering: Task 4;
  - audit checks: Task 5.
- No plan step requires replacing existing Baostock finance ingestion.
- No step assumes Baostock has absolute balance-sheet or cash-flow statement fields.
- Long backfill is gated by one-asset and one-job smoke tests.
