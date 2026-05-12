# Full-History Phase 3 Daily Bars Raw Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve full-history Baostock daily bar source rows before normalization, so later backfills from 1990 onward are replayable and auditable.

**Architecture:** Add a `raw_baostock.daily_bar_payload` table keyed by source service, source table, adjustment type, trade date, and asset. Extend the existing `load-bars` path with an opt-in raw archive switch; normalization continues to write `market_daily_bar` exactly as before.

**Tech Stack:** Python, PostgreSQL, psycopg, pytest, existing `stock-research` CLI.

---

## Scope

In scope:

- raw Baostock daily bar payload schema;
- deterministic payload hashing;
- idempotent raw payload upsert;
- opt-in `stock-research load-bars --archive-raw`;
- audit coverage for `raw_baostock.daily_bar_payload`;
- runbook command examples for small smoke loads and long full-history loads.

Out of scope:

- executing 1990-current production backfill;
- replacing the existing `market_daily_bar` table;
- corporate action adjustment validation;
- factor recomputation.

## Files

- Modify: `src/stock_research/schema.py`
- Modify: `src/stock_research/market_data.py`
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/data_audit.py`
- Modify: `tests/test_schema.py`
- Modify: `tests/test_market_data.py`
- Modify: `tests/test_factor_cli.py`
- Modify: `tests/test_data_audit.py`
- Modify: `docs/daily-factor-pipeline-runbook.md`

## Task 1: Raw Daily Bar Schema

- [ ] **Step 1: Write failing schema test**

Add to `tests/test_schema.py`:

```python
def test_research_extension_includes_raw_daily_bar_payload_table():
    sql = CREATE_RESEARCH_EXTENSION_SQL
    assert "CREATE TABLE IF NOT EXISTS raw_baostock.daily_bar_payload" in sql
    assert "payload_hash text NOT NULL" in sql
    assert "idx_raw_baostock_daily_bar_payload_lookup" in sql
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_raw_daily_bar_payload_table -q
```

Expected: FAIL because the table is not defined.

- [ ] **Step 3: Implement schema**

Add inside `CREATE_RESEARCH_EXTENSION_SQL`:

```sql
CREATE TABLE IF NOT EXISTS raw_baostock.daily_bar_payload (
    source_service text NOT NULL,
    source_table text NOT NULL,
    adjust_type text NOT NULL,
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_service, source_table, adjust_type, trade_date, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_raw_baostock_daily_bar_payload_lookup
    ON raw_baostock.daily_bar_payload (adjust_type, trade_date, asset_id);
```

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_schema.py::test_research_extension_includes_raw_daily_bar_payload_table -q
```

Expected: PASS.

## Task 2: Raw Payload Helpers

- [ ] **Step 1: Write failing market data tests**

Add to `tests/test_market_data.py`:

```python
from stock_research.market_data import raw_payload_hash, raw_daily_bar_payload_row


def test_raw_payload_hash_is_stable_for_key_order():
    assert raw_payload_hash({"b": "2", "a": "1"}) == raw_payload_hash({"a": "1", "b": "2"})


def test_raw_daily_bar_payload_row_preserves_source_payload():
    row = {"trade_date": "2026-05-06", "stock_code": "sh600000", "close_price": "10.30"}
    payload = raw_daily_bar_payload_row("stock_hfq", "sh600000", "hfq", row)
    assert payload["source_service"] == "stock_hfq"
    assert payload["source_table"] == "sh600000"
    assert payload["adjust_type"] == "hfq"
    assert payload["trade_date"] == "2026-05-06"
    assert payload["asset_id"] == "CN:SH:600000"
    assert payload["payload"] == row
    assert len(payload["payload_hash"]) == 64
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_market_data.py::test_raw_payload_hash_is_stable_for_key_order tests/test_market_data.py::test_raw_daily_bar_payload_row_preserves_source_payload -q
```

Expected: FAIL because the helpers do not exist.

- [ ] **Step 3: Implement helpers**

Add to `src/stock_research/market_data.py`:

```python
def jsonable_payload(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): jsonable_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable_payload(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def raw_payload_hash(payload: dict) -> str:
    body = json.dumps(jsonable_payload(payload), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
```

Then add `raw_daily_bar_payload_row(...)` using `asset_id_from_baostock_code(row["stock_code"])`.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_market_data.py -q
```

Expected: PASS.

## Task 3: Raw Upsert And Loader Switch

- [ ] **Step 1: Write failing tests**

Add tests that monkeypatch `market_data.connect`, `market_data.execute_many`, `market_data.fetch_source_rows`, and `market_data.upsert_market_rows` to prove:

- `upsert_raw_daily_bar_payloads` emits `INSERT INTO raw_baostock.daily_bar_payload`;
- `load_market_daily_bars(..., archive_raw=True)` archives raw rows before normalized rows;
- `load_market_daily_bars(..., archive_raw=False)` keeps old behavior.

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_market_data.py -q
```

Expected: FAIL because upsert and `archive_raw` are not implemented.

- [ ] **Step 3: Implement upsert and loader switch**

Update `load_market_daily_bars` signature to:

```python
def load_market_daily_bars(
    source_service: str,
    adjust_type: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit_tables: int | None = None,
    archive_raw: bool = False,
) -> int:
```

When `archive_raw` is true, call:

```python
upsert_raw_daily_bar_payloads(
    [
        raw_daily_bar_payload_row(source_service, table_name, adjust_type, row)
        for row in source_rows
    ]
)
```

Then keep the existing normalized upsert.

- [ ] **Step 4: Verify green**

Run:

```bash
.venv/bin/python -m pytest tests/test_market_data.py -q
```

Expected: PASS.

## Task 4: CLI, Audit, And Runbook

- [ ] **Step 1: Write failing CLI and audit tests**

Add to `tests/test_schema.py` or `tests/test_factor_cli.py`:

```python
args = build_parser().parse_args(["load-bars", "--archive-raw"])
assert args.archive_raw is True
```

Update `tests/test_data_audit.py`:

```python
assert "raw_baostock.daily_bar_payload" in dataset_names
```

- [ ] **Step 2: Verify red**

Run:

```bash
.venv/bin/python -m pytest tests/test_factor_cli.py tests/test_data_audit.py -q
```

Expected: FAIL because the parser and audit dataset are missing.

- [ ] **Step 3: Implement CLI and audit**

Add `load_bars.add_argument("--archive-raw", action="store_true")`.
Pass `archive_raw=args.archive_raw` into both `load_market_daily_bars` calls.
Add `AuditDataset("raw_baostock.daily_bar_payload", "raw_baostock.daily_bar_payload", "trade_date")`.

- [ ] **Step 4: Update runbook**

Add commands:

```bash
stock-research load-bars --start-date 1990-12-19 --end-date YYYY-MM-DD --archive-raw
stock-research data-audit --expected-start-date 1990-12-01
```

- [ ] **Step 5: Final verification**

Run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/stock-research apply-research-schema
.venv/bin/stock-research load-bars --start-date 2024-05-27 --end-date 2024-05-27 --limit-tables 1 --archive-raw
.venv/bin/stock-research data-audit --expected-start-date 1990-12-01
git status --short --branch
```

