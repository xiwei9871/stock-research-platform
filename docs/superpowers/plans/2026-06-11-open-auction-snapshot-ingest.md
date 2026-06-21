# Open Auction Snapshot Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a production-safe full-market opening auction process snapshot collector using AKShare `stock_zh_a_spot_em` at 09:15/09:17/09:19/09:21/09:23/09:25, while keeping Tushare or another paid source authoritative for final 09:25 auction results.

**Architecture:** Store `spot_em` snapshots in new snapshot tables instead of reusing minute-bar tables, because `spot_em` is an instantaneous full-market quote surface rather than a historical 1-minute bar source. Reuse existing DB helpers, payload hashing, reporting style, and CLI patterns from `stock_research.auction_data`, but keep the old `hist_pre_min_em` collector scoped to small-pool diagnostics.

**Tech Stack:** Python, pandas, AKShare `stock_zh_a_spot_em`, PostgreSQL via existing `stock_research.db`, existing `stock_research.schema`, argparse CLI, bash wrapper, pytest.

---

## File Structure

- Modify: `src/stock_research/schema.py`
  - Add `staging.eastmoney_stock_spot_snapshot`.
  - Add `market.stock_open_auction_snapshot`.
  - Add indexes for date/target-time and asset/time lookup.

- Modify: `src/stock_research/auction_data.py`
  - Add `ts_code_from_spot_symbol`.
  - Add `open_auction_spot_snapshot_market_row`.
  - Add `open_auction_spot_snapshot_staging_row`.
  - Add `query_eastmoney_spot_snapshot_rows`.
  - Add `upsert_stock_open_auction_spot_snapshots`.
  - Add `collect_open_auction_spot_snapshot`.
  - Add report writer and cron entry builder.

- Modify: `src/stock_research/cli.py`
  - Add parser and handler for `collect-open-auction-spot-snapshot-v1`.
  - Add parser and handler for `open-auction-spot-snapshot-cron-entry`.

- Create: `scripts/run_open_auction_spot_snapshot.sh`
  - Shell wrapper for cron and manual runs.

- Modify: `docs/open-auction-minute-collect-runbook.md`
  - Document that `hist_pre_min_em` is small-pool diagnostic only.
  - Add link or section for the new `spot_em` snapshot collector.

- Test: `tests/test_auction_data.py`
  - Unit tests for row normalization, upsert SQL, collection, reports, and cron entries.

- Test: `tests/test_schema.py`
  - Schema and CLI parser assertions.

## Task 1: Add Snapshot Tables To Schema

**Files:**
- Modify: `src/stock_research/schema.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Write failing schema test**

Add these assertions to `tests/test_schema.py::test_schema_creates_stock_auction_tables`:

```python
    assert "CREATE TABLE IF NOT EXISTS staging.eastmoney_stock_spot_snapshot" in sql
    assert "CREATE TABLE IF NOT EXISTS market.stock_open_auction_snapshot" in sql
    assert "source text NOT NULL CHECK (source IN ('eastmoney_spot_snapshot'))" in sql
    assert "PRIMARY KEY (trade_date, asset_id, target_time, source)" in sql
    assert "idx_market_stock_open_auction_snapshot_date_target" in sql
    assert "idx_market_stock_open_auction_snapshot_asset_time" in sql
```

- [ ] **Step 2: Run failing schema test**

Run:

```bash
cd /Users/xiwei/stock_research
.venv/bin/pytest tests/test_schema.py::test_schema_creates_stock_auction_tables -q
```

Expected:

```text
FAILED ... AssertionError
```

- [ ] **Step 3: Add schema SQL**

In `src/stock_research/schema.py`, add this SQL near the existing auction tables:

```sql
CREATE TABLE IF NOT EXISTS staging.eastmoney_stock_spot_snapshot (
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    raw_symbol text NOT NULL,
    ts_code text NOT NULL,
    trade_date date NOT NULL,
    snapshot_time timestamp NOT NULL,
    target_time time NOT NULL,
    latest numeric,
    open numeric,
    prev_close numeric,
    high numeric,
    low numeric,
    volume numeric,
    amount numeric,
    volume_ratio numeric,
    turnover_rate numeric,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source_endpoint, ts_code, trade_date, target_time)
);

CREATE TABLE IF NOT EXISTS market.stock_open_auction_snapshot (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    trade_date date NOT NULL,
    snapshot_time timestamp NOT NULL,
    target_time time NOT NULL,
    auction_phase text NOT NULL CHECK (auction_phase IN ('open_call')),
    latest numeric,
    open numeric,
    prev_close numeric,
    high numeric,
    low numeric,
    volume numeric,
    amount numeric,
    volume_ratio numeric,
    turnover_rate numeric,
    source text NOT NULL CHECK (source IN ('eastmoney_spot_snapshot')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (trade_date, asset_id, target_time, source)
);
```

Add these indexes near the existing auction indexes:

```sql
CREATE INDEX IF NOT EXISTS idx_staging_eastmoney_stock_spot_snapshot_date_target
    ON staging.eastmoney_stock_spot_snapshot (trade_date, target_time);

CREATE INDEX IF NOT EXISTS idx_market_stock_open_auction_snapshot_date_target
    ON market.stock_open_auction_snapshot (trade_date, target_time);

CREATE INDEX IF NOT EXISTS idx_market_stock_open_auction_snapshot_asset_time
    ON market.stock_open_auction_snapshot (asset_id, snapshot_time DESC);
```

- [ ] **Step 4: Run schema test**

Run:

```bash
.venv/bin/pytest tests/test_schema.py::test_schema_creates_stock_auction_tables -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit schema task**

Run:

```bash
git add src/stock_research/schema.py tests/test_schema.py
git commit -m "feat: add open auction spot snapshot tables"
```

## Task 2: Normalize AKShare Spot Snapshot Rows

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] **Step 1: Add imports to the test file**

Extend the import list from `stock_research.auction_data` in `tests/test_auction_data.py`:

```python
    open_auction_spot_snapshot_market_row,
    open_auction_spot_snapshot_staging_row,
    ts_code_from_spot_symbol,
```

- [ ] **Step 2: Add failing tests**

Add these tests to `tests/test_auction_data.py`:

```python
def raw_spot_snapshot_row() -> dict:
    return {
        "代码": "600023",
        "名称": "浙能电力",
        "最新价": 5.45,
        "今开": 5.40,
        "昨收": 5.38,
        "最高": 5.47,
        "最低": 5.39,
        "成交量": 457800,
        "成交额": 2495009.92,
        "量比": 1.23,
        "换手率": 0.56,
    }


def test_ts_code_from_spot_symbol_maps_cn_exchanges():
    assert ts_code_from_spot_symbol("600023") == "600023.SH"
    assert ts_code_from_spot_symbol("000001") == "000001.SZ"
    assert ts_code_from_spot_symbol("300001") == "300001.SZ"
    assert ts_code_from_spot_symbol("830799") == "830799.BJ"


def test_open_auction_spot_snapshot_market_row_normalizes_spot_payload():
    row = open_auction_spot_snapshot_market_row(
        raw_spot_snapshot_row(),
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
    )

    assert row["asset_id"] == "CN:SH:600023"
    assert row["ts_code"] == "600023.SH"
    assert row["trade_date"] == dt.date(2026, 6, 11)
    assert row["snapshot_time"] == dt.datetime(2026, 6, 11, 9, 17, 5)
    assert row["target_time"] == dt.time(9, 17)
    assert row["auction_phase"] == "open_call"
    assert row["latest"] == 5.45
    assert row["open"] == 5.40
    assert row["prev_close"] == 5.38
    assert row["volume"] == 457800
    assert row["amount"] == 2495009.92
    assert row["volume_ratio"] == 1.23
    assert row["turnover_rate"] == 0.56
    assert row["source"] == "eastmoney_spot_snapshot"


def test_open_auction_spot_snapshot_staging_row_preserves_payload_hash():
    row = open_auction_spot_snapshot_staging_row(
        raw_spot_snapshot_row(),
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
        source_endpoint="stock_zh_a_spot_em",
        params={"target_time": "09:17"},
    )

    assert row["source_endpoint"] == "stock_zh_a_spot_em"
    assert row["raw_symbol"] == "600023"
    assert row["ts_code"] == "600023.SH"
    assert row["target_time"] == dt.time(9, 17)
    assert row["payload"] == raw_spot_snapshot_row()
    assert len(row["payload_hash"]) == 64
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_auction_data.py::test_ts_code_from_spot_symbol_maps_cn_exchanges \
  tests/test_auction_data.py::test_open_auction_spot_snapshot_market_row_normalizes_spot_payload \
  tests/test_auction_data.py::test_open_auction_spot_snapshot_staging_row_preserves_payload_hash \
  -q
```

Expected:

```text
FAILED ... ImportError
```

- [ ] **Step 4: Implement normalization helpers**

Add these functions to `src/stock_research/auction_data.py` near the existing Eastmoney helpers:

```python
def ts_code_from_spot_symbol(symbol: Any) -> str:
    code = str(symbol).strip().zfill(6)
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"Unsupported spot symbol: {symbol}")
    if code.startswith("6"):
        return f"{code}.SH"
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8", "9")):
        return f"{code}.BJ"
    raise ValueError(f"Unsupported spot symbol: {symbol}")


def parse_target_time(value: str | dt.time) -> dt.time:
    if isinstance(value, dt.time):
        return value
    return dt.datetime.strptime(str(value), "%H:%M").time()


def open_auction_spot_snapshot_market_row(
    raw: dict[str, Any],
    *,
    trade_date: dt.date,
    snapshot_time: dt.datetime,
    target_time: str | dt.time,
    source: str = "eastmoney_spot_snapshot",
) -> dict[str, Any]:
    ts_code = ts_code_from_spot_symbol(_first_present(raw, ["代码", "symbol", "raw_symbol"]))
    return {
        "asset_id": asset_id_from_ts_code(ts_code),
        "ts_code": ts_code,
        "trade_date": trade_date,
        "snapshot_time": snapshot_time.replace(tzinfo=None),
        "target_time": parse_target_time(target_time),
        "auction_phase": "open_call",
        "latest": parse_float(_first_present(raw, ["最新价", "latest"])),
        "open": parse_float(_first_present(raw, ["今开", "open"])),
        "prev_close": parse_float(_first_present(raw, ["昨收", "prev_close"])),
        "high": parse_float(_first_present(raw, ["最高", "high"])),
        "low": parse_float(_first_present(raw, ["最低", "low"])),
        "volume": parse_float(_first_present(raw, ["成交量", "volume", "vol"])),
        "amount": parse_float(_first_present(raw, ["成交额", "amount"])),
        "volume_ratio": parse_float(_first_present(raw, ["量比", "volume_ratio"])),
        "turnover_rate": parse_float(_first_present(raw, ["换手率", "turnover_rate"])),
        "source": source,
    }


def open_auction_spot_snapshot_staging_row(
    raw: dict[str, Any],
    *,
    trade_date: dt.date,
    snapshot_time: dt.datetime,
    target_time: str | dt.time,
    source_endpoint: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {str(key): value for key, value in raw.items()}
    market_row = open_auction_spot_snapshot_market_row(
        payload,
        trade_date=trade_date,
        snapshot_time=snapshot_time,
        target_time=target_time,
    )
    return {
        "source_endpoint": source_endpoint,
        "request_params": params or {},
        "raw_symbol": str(_first_present(payload, ["代码", "symbol", "raw_symbol"])),
        "ts_code": market_row["ts_code"],
        "trade_date": trade_date,
        "snapshot_time": market_row["snapshot_time"],
        "target_time": market_row["target_time"],
        "latest": market_row["latest"],
        "open": market_row["open"],
        "prev_close": market_row["prev_close"],
        "high": market_row["high"],
        "low": market_row["low"],
        "volume": market_row["volume"],
        "amount": market_row["amount"],
        "volume_ratio": market_row["volume_ratio"],
        "turnover_rate": market_row["turnover_rate"],
        "payload": payload,
        "payload_hash": payload_hash(payload),
    }
```

- [ ] **Step 5: Run tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_auction_data.py::test_ts_code_from_spot_symbol_maps_cn_exchanges \
  tests/test_auction_data.py::test_open_auction_spot_snapshot_market_row_normalizes_spot_payload \
  tests/test_auction_data.py::test_open_auction_spot_snapshot_staging_row_preserves_payload_hash \
  -q
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Commit normalization task**

Run:

```bash
git add src/stock_research/auction_data.py tests/test_auction_data.py
git commit -m "feat: normalize open auction spot snapshots"
```

## Task 3: Add Snapshot Query, Upsert, Collector, And Report

**Files:**
- Modify: `src/stock_research/auction_data.py`
- Test: `tests/test_auction_data.py`

- [ ] **Step 1: Extend test imports**

Add these names to the import list in `tests/test_auction_data.py`:

```python
    collect_open_auction_spot_snapshot,
    query_eastmoney_spot_snapshot_rows,
    upsert_stock_open_auction_spot_snapshots,
    write_open_auction_spot_snapshot_report,
```

- [ ] **Step 2: Add failing tests**

Add these tests:

```python
def test_upsert_stock_open_auction_spot_snapshots_writes_staging_and_market(monkeypatch):
    calls = []

    def fake_execute_many(conn, sql, rows):
        calls.append((conn, sql, list(rows)))

    monkeypatch.setattr(auction_data, "connect", lambda service: _Context("conn"))
    monkeypatch.setattr(auction_data, "execute_many", fake_execute_many)

    count = upsert_stock_open_auction_spot_snapshots(
        [raw_spot_snapshot_row()],
        trade_date=dt.date(2026, 6, 11),
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
        target_time="09:17",
        params={"target_time": "09:17"},
    )

    assert count == 1
    assert len(calls) == 2
    assert "INSERT INTO staging.eastmoney_stock_spot_snapshot" in calls[0][1]
    assert "INSERT INTO market.stock_open_auction_snapshot" in calls[1][1]
    assert "ON CONFLICT (trade_date, asset_id, target_time, source)" in calls[1][1]
    assert calls[1][2][0]["target_time"] == dt.time(9, 17)


def test_collect_open_auction_spot_snapshot_queries_once_and_reports(monkeypatch):
    query_calls = []
    upsert_calls = []

    def fake_query():
        query_calls.append("called")
        return [raw_spot_snapshot_row()]

    def fake_upsert(rows, trade_date, snapshot_time, target_time, source_endpoint="stock_zh_a_spot_em", params=None):
        upsert_calls.append((rows, trade_date, snapshot_time, target_time, source_endpoint, params))
        return len(rows)

    monkeypatch.setattr(auction_data, "query_eastmoney_spot_snapshot_rows", fake_query)
    monkeypatch.setattr(auction_data, "upsert_stock_open_auction_spot_snapshots", fake_upsert)

    result = collect_open_auction_spot_snapshot(
        trade_date="2026-06-11",
        target_time="09:17",
        snapshot_time=dt.datetime(2026, 6, 11, 9, 17, 5),
    )

    assert query_calls == ["called"]
    assert upsert_calls[0][0] == [raw_spot_snapshot_row()]
    assert upsert_calls[0][1] == dt.date(2026, 6, 11)
    assert upsert_calls[0][3] == "09:17"
    assert result["summary"]["queried_rows"] == 1
    assert result["summary"]["upserted_rows"] == 1
    assert result["summary"]["skipped_rows"] == 0


def test_write_open_auction_spot_snapshot_report(tmp_path):
    result = {
        "detail": pd.DataFrame(
            [
                {
                    "trade_date": "2026-06-11",
                    "target_time": "09:17",
                    "snapshot_time": "2026-06-11T09:17:05",
                    "queried_rows": 1,
                    "upserted_rows": 1,
                    "skipped_rows": 0,
                    "error": "",
                }
            ]
        ),
        "summary": {
            "trade_date": "2026-06-11",
            "target_time": "09:17",
            "snapshot_time": "2026-06-11T09:17:05",
            "queried_rows": 1,
            "upserted_rows": 1,
            "skipped_rows": 0,
            "error": "",
        },
    }

    report = write_open_auction_spot_snapshot_report(
        result=result,
        output_dir=tmp_path,
        trade_date="2026-06-11",
        target_time="09:17",
    )

    text = Path(report["paths"]["markdown_report"]).read_text(encoding="utf-8")
    assert "- target_time: 09:17" in text
    assert "- upserted_rows: 1" in text
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_auction_data.py::test_upsert_stock_open_auction_spot_snapshots_writes_staging_and_market \
  tests/test_auction_data.py::test_collect_open_auction_spot_snapshot_queries_once_and_reports \
  tests/test_auction_data.py::test_write_open_auction_spot_snapshot_report \
  -q
```

Expected:

```text
FAILED ... ImportError
```

- [ ] **Step 4: Implement query wrapper**

Add this function:

```python
def query_eastmoney_spot_snapshot_rows() -> list[dict[str, Any]]:
    import akshare as ak

    frame = ak.stock_zh_a_spot_em()
    return list(frame.to_dict("records"))
```

- [ ] **Step 5: Implement upsert**

Add this function:

```python
def upsert_stock_open_auction_spot_snapshots(
    rows: list[dict[str, Any]],
    *,
    trade_date: dt.date,
    snapshot_time: dt.datetime,
    target_time: str | dt.time,
    source_endpoint: str = "stock_zh_a_spot_em",
    research_service: str = SETTINGS.research_service,
    params: dict[str, Any] | None = None,
) -> int:
    if not rows:
        return 0

    staging_rows = [
        open_auction_spot_snapshot_staging_row(
            row,
            trade_date=trade_date,
            snapshot_time=snapshot_time,
            target_time=target_time,
            source_endpoint=source_endpoint,
            params=params,
        )
        for row in rows
    ]
    market_rows = [
        open_auction_spot_snapshot_market_row(
            row,
            trade_date=trade_date,
            snapshot_time=snapshot_time,
            target_time=target_time,
        )
        for row in rows
    ]

    staging_sql = """
    INSERT INTO staging.eastmoney_stock_spot_snapshot (
        source_endpoint, request_params, raw_symbol, ts_code, trade_date, snapshot_time,
        target_time, latest, open, prev_close, high, low, volume, amount,
        volume_ratio, turnover_rate, payload, payload_hash
    )
    VALUES (
        %(source_endpoint)s, %(request_params)s::jsonb, %(raw_symbol)s, %(ts_code)s,
        %(trade_date)s, %(snapshot_time)s, %(target_time)s, %(latest)s, %(open)s,
        %(prev_close)s, %(high)s, %(low)s, %(volume)s, %(amount)s,
        %(volume_ratio)s, %(turnover_rate)s, %(payload)s::jsonb, %(payload_hash)s
    )
    ON CONFLICT (source_endpoint, ts_code, trade_date, target_time)
    DO UPDATE SET
        request_params = EXCLUDED.request_params,
        snapshot_time = EXCLUDED.snapshot_time,
        latest = EXCLUDED.latest,
        open = EXCLUDED.open,
        prev_close = EXCLUDED.prev_close,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        volume_ratio = EXCLUDED.volume_ratio,
        turnover_rate = EXCLUDED.turnover_rate,
        payload = EXCLUDED.payload,
        payload_hash = EXCLUDED.payload_hash,
        fetched_at = now()
    """
    market_sql = """
    INSERT INTO market.stock_open_auction_snapshot (
        asset_id, ts_code, trade_date, snapshot_time, target_time, auction_phase,
        latest, open, prev_close, high, low, volume, amount, volume_ratio,
        turnover_rate, source
    )
    VALUES (
        %(asset_id)s, %(ts_code)s, %(trade_date)s, %(snapshot_time)s, %(target_time)s,
        %(auction_phase)s, %(latest)s, %(open)s, %(prev_close)s, %(high)s, %(low)s,
        %(volume)s, %(amount)s, %(volume_ratio)s, %(turnover_rate)s, %(source)s
    )
    ON CONFLICT (trade_date, asset_id, target_time, source)
    DO UPDATE SET
        ts_code = EXCLUDED.ts_code,
        snapshot_time = EXCLUDED.snapshot_time,
        latest = EXCLUDED.latest,
        open = EXCLUDED.open,
        prev_close = EXCLUDED.prev_close,
        high = EXCLUDED.high,
        low = EXCLUDED.low,
        volume = EXCLUDED.volume,
        amount = EXCLUDED.amount,
        volume_ratio = EXCLUDED.volume_ratio,
        turnover_rate = EXCLUDED.turnover_rate,
        updated_at = now()
    """
    staging_params = [
        {
            **row,
            "request_params": canonical_json(row["request_params"]),
            "payload": canonical_json(row["payload"]),
        }
        for row in staging_rows
    ]
    with connect(research_service) as conn:
        execute_many(conn, staging_sql, staging_params)
        execute_many(conn, market_sql, market_rows)
    return len(market_rows)
```

- [ ] **Step 6: Implement collector and report writer**

Add these functions:

```python
def collect_open_auction_spot_snapshot(
    *,
    trade_date: str | dt.date,
    target_time: str,
    snapshot_time: dt.datetime | None = None,
) -> dict[str, Any]:
    target_date = dt.date.fromisoformat(str(trade_date)) if not isinstance(trade_date, dt.date) else trade_date
    captured_at = (snapshot_time or dt.datetime.now()).replace(tzinfo=None)
    rows: list[dict[str, Any]] = []
    upserted = 0
    skipped = 0
    error = ""
    try:
        rows = query_eastmoney_spot_snapshot_rows()
        valid_rows = []
        for row in rows:
            try:
                ts_code_from_spot_symbol(_first_present(row, ["代码", "symbol", "raw_symbol"]))
                valid_rows.append(row)
            except ValueError:
                skipped += 1
        params = {
            "trade_date": target_date.isoformat(),
            "target_time": target_time,
            "snapshot_time": captured_at.isoformat(timespec="seconds"),
        }
        upserted = upsert_stock_open_auction_spot_snapshots(
            valid_rows,
            trade_date=target_date,
            snapshot_time=captured_at,
            target_time=target_time,
            params=params,
        )
    except Exception as exc:  # pragma: no cover - integration safety path.
        error = str(exc)

    detail = pd.DataFrame(
        [
            {
                "trade_date": target_date.isoformat(),
                "target_time": target_time,
                "snapshot_time": captured_at.isoformat(timespec="seconds"),
                "queried_rows": len(rows),
                "upserted_rows": upserted,
                "skipped_rows": skipped,
                "error": error,
            }
        ]
    )
    return {
        "detail": detail,
        "summary": detail.iloc[0].to_dict(),
    }


def write_open_auction_spot_snapshot_report(
    *,
    result: dict[str, Any],
    output_dir: str | Path,
    trade_date: str | dt.date,
    target_time: str,
) -> dict[str, Any]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    date_text = str(trade_date)
    safe_target = str(target_time).replace(":", "")
    detail_path = output / f"open_auction_spot_snapshot_{date_text}_{safe_target}.csv"
    latest_path = output / "open_auction_spot_snapshot_latest.csv"
    report_path = output / f"open_auction_spot_snapshot_{date_text}_{safe_target}.md"
    result["detail"].to_csv(detail_path, index=False)
    result["detail"].to_csv(latest_path, index=False)
    summary = result["summary"]
    lines = [
        f"# Open Auction Spot Snapshot {date_text} {target_time}",
        "",
        f"- trade_date: {summary['trade_date']}",
        f"- target_time: {summary['target_time']}",
        f"- snapshot_time: {summary['snapshot_time']}",
        f"- queried_rows: {summary['queried_rows']}",
        f"- upserted_rows: {summary['upserted_rows']}",
        f"- skipped_rows: {summary['skipped_rows']}",
        f"- error: {summary['error']}",
        "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return {
        "paths": {
            "detail": detail_path,
            "latest": latest_path,
            "markdown_report": report_path,
        },
        "summary": summary,
    }
```

- [ ] **Step 7: Run tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_auction_data.py::test_upsert_stock_open_auction_spot_snapshots_writes_staging_and_market \
  tests/test_auction_data.py::test_collect_open_auction_spot_snapshot_queries_once_and_reports \
  tests/test_auction_data.py::test_write_open_auction_spot_snapshot_report \
  -q
```

Expected:

```text
3 passed
```

- [ ] **Step 8: Commit collector task**

Run:

```bash
git add src/stock_research/auction_data.py tests/test_auction_data.py
git commit -m "feat: collect open auction spot snapshots"
```

## Task 4: Add CLI, Wrapper Script, And Cron Entries

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/auction_data.py`
- Create: `scripts/run_open_auction_spot_snapshot.sh`
- Test: `tests/test_auction_data.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Add failing cron-entry test**

Add this test to `tests/test_auction_data.py`:

```python
def test_build_open_auction_spot_snapshot_cron_entries_uses_requested_slots():
    entries = auction_data.build_open_auction_spot_snapshot_cron_entries(
        project_dir="/Users/xiwei/stock_research",
        output_dir="outputs/research/open_auction_spot_snapshot",
        log_path="logs/open_auction_spot_snapshot.log",
    )

    assert len(entries) == 6
    assert entries[0].startswith("15 9 * * 1-5 ")
    assert "scripts/run_open_auction_spot_snapshot.sh 09:15" in entries[0]
    assert entries[1].startswith("17 9 * * 1-5 ")
    assert "scripts/run_open_auction_spot_snapshot.sh 09:17" in entries[1]
    assert entries[-1].startswith("25 9 * * 1-5 ")
    assert "scripts/run_open_auction_spot_snapshot.sh 09:25" in entries[-1]
```

- [ ] **Step 2: Add failing CLI parser assertions**

Add these assertions to `tests/test_schema.py::test_schema_creates_stock_auction_tables` or a parser-focused test:

```python
    parser = build_parser()
    args = parser.parse_args(
        [
            "collect-open-auction-spot-snapshot-v1",
            "--trade-date",
            "2026-06-11",
            "--target-time",
            "09:17",
        ]
    )
    assert args.command == "collect-open-auction-spot-snapshot-v1"
    assert args.target_time == "09:17"

    cron_args = parser.parse_args(["open-auction-spot-snapshot-cron-entry"])
    assert cron_args.command == "open-auction-spot-snapshot-cron-entry"
```

- [ ] **Step 3: Run failing tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_auction_data.py::test_build_open_auction_spot_snapshot_cron_entries_uses_requested_slots \
  tests/test_schema.py::test_schema_creates_stock_auction_tables \
  -q
```

Expected:

```text
FAILED ... AttributeError
```

- [ ] **Step 4: Implement cron entry builder**

Add this constant and function to `src/stock_research/auction_data.py`:

```python
OPEN_AUCTION_SPOT_SNAPSHOT_TARGETS = [
    ("09:15", 15),
    ("09:17", 17),
    ("09:19", 19),
    ("09:21", 21),
    ("09:23", 23),
    ("09:25", 25),
]


def build_open_auction_spot_snapshot_cron_entries(
    *,
    project_dir: str = "/Users/xiwei/stock_research",
    output_dir: str = "outputs/research/open_auction_spot_snapshot",
    log_path: str = "logs/open_auction_spot_snapshot.log",
) -> list[str]:
    entries = []
    for target_time, minute in OPEN_AUCTION_SPOT_SNAPSHOT_TARGETS:
        entries.append(
            " ".join(
                [
                    str(minute),
                    "9",
                    "*",
                    "*",
                    "1-5",
                    f"cd {project_dir} &&",
                    f"OPEN_AUCTION_SPOT_OUTPUT_DIR={output_dir}",
                    f"scripts/run_open_auction_spot_snapshot.sh {target_time} $(date +\\%F)",
                    f">> {log_path} 2>&1",
                ]
            )
        )
    return entries
```

- [ ] **Step 5: Add CLI parser entries**

In `src/stock_research/cli.py`, add parser setup near the existing auction commands:

```python
    open_auction_spot_snapshot = subparsers.add_parser("collect-open-auction-spot-snapshot-v1")
    open_auction_spot_snapshot.add_argument("--trade-date", default="auto")
    open_auction_spot_snapshot.add_argument("--target-time", required=True)
    open_auction_spot_snapshot.add_argument(
        "--output-dir",
        default="/Users/xiwei/stock_research/outputs/research/open_auction_spot_snapshot",
    )

    open_auction_spot_snapshot_cron = subparsers.add_parser("open-auction-spot-snapshot-cron-entry")
    open_auction_spot_snapshot_cron.add_argument("--project-dir", default="/Users/xiwei/stock_research")
    open_auction_spot_snapshot_cron.add_argument(
        "--output-dir",
        default="outputs/research/open_auction_spot_snapshot",
    )
    open_auction_spot_snapshot_cron.add_argument("--log-path", default="logs/open_auction_spot_snapshot.log")
```

Add handler code near the existing auction handlers:

```python
    elif args.command == "collect-open-auction-spot-snapshot-v1":
        trade_date = dt.date.today().isoformat() if args.trade_date == "auto" else args.trade_date
        result = collect_open_auction_spot_snapshot(
            trade_date=trade_date,
            target_time=args.target_time,
        )
        report = write_open_auction_spot_snapshot_report(
            result=result,
            output_dir=args.output_dir,
            trade_date=trade_date,
            target_time=args.target_time,
        )
        print(f"open_auction_spot_snapshot_v1|detail|{report['paths']['detail']}")
        print(f"open_auction_spot_snapshot_v1|latest|{report['paths']['latest']}")
        print(f"open_auction_spot_snapshot_v1|report|{report['paths']['markdown_report']}")
        print(f"open_auction_spot_snapshot_v1|queried_rows|{report['summary']['queried_rows']}")
        print(f"open_auction_spot_snapshot_v1|upserted_rows|{report['summary']['upserted_rows']}")
        print(f"open_auction_spot_snapshot_v1|skipped_rows|{report['summary']['skipped_rows']}")
        return 0
    elif args.command == "open-auction-spot-snapshot-cron-entry":
        for entry in build_open_auction_spot_snapshot_cron_entries(
            project_dir=args.project_dir,
            output_dir=args.output_dir,
            log_path=args.log_path,
        ):
            print(entry)
        return 0
```

Update the imports at the top of `src/stock_research/cli.py` to include:

```python
    build_open_auction_spot_snapshot_cron_entries,
    collect_open_auction_spot_snapshot,
    write_open_auction_spot_snapshot_report,
```

- [ ] **Step 6: Create wrapper script**

Create `scripts/run_open_auction_spot_snapshot.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="${OPEN_AUCTION_SPOT_ROOT:-/Users/xiwei/stock_research}"
PYTHON="${OPEN_AUCTION_SPOT_PYTHON:-$ROOT/.venv/bin/python}"
TARGET_TIME="${1:?target time is required, for example 09:17}"
TRADE_DATE="${2:-$(date +%F)}"
OUTPUT_DIR="${OPEN_AUCTION_SPOT_OUTPUT_DIR:-$ROOT/outputs/research/open_auction_spot_snapshot}"

mkdir -p "$ROOT/logs"
cd "$ROOT"

"$PYTHON" -m stock_research.cli collect-open-auction-spot-snapshot-v1 \
  --trade-date "$TRADE_DATE" \
  --target-time "$TARGET_TIME" \
  --output-dir "$OUTPUT_DIR"
```

Then run:

```bash
chmod +x scripts/run_open_auction_spot_snapshot.sh
```

- [ ] **Step 7: Run tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_auction_data.py::test_build_open_auction_spot_snapshot_cron_entries_uses_requested_slots \
  tests/test_schema.py::test_schema_creates_stock_auction_tables \
  -q
```

Expected:

```text
2 passed
```

- [ ] **Step 8: Commit CLI and wrapper task**

Run:

```bash
git add src/stock_research/auction_data.py src/stock_research/cli.py tests/test_auction_data.py tests/test_schema.py scripts/run_open_auction_spot_snapshot.sh
git commit -m "feat: add open auction spot snapshot cli"
```

## Task 5: Update Runbook And Run Full Verification

**Files:**
- Modify: `docs/open-auction-minute-collect-runbook.md`
- Test: `tests/test_auction_data.py`
- Test: `tests/test_schema.py`

- [ ] **Step 1: Update runbook**

Add this section to `docs/open-auction-minute-collect-runbook.md` after the purpose section:

```markdown
## Production Source Policy

For full-market opening auction process data, use `collect-open-auction-spot-snapshot-v1`, backed by AKShare `stock_zh_a_spot_em`.

The production snapshot schedule is:

- `09:15`
- `09:17`
- `09:19`
- `09:21`
- `09:23`
- `09:25`

Cron entries trigger on those minute marks; the wrapper captures the actual `snapshot_time` when the command runs. The 09:25 snapshot is a process snapshot and should not overwrite final auction result rows in `market.stock_auction_bar`.

The existing `collect-open-auction-minute-v1` command uses AKShare `stock_zh_a_hist_pre_min_em`. Keep it for small watchlists and diagnostics only. It is not a stable full-market historical or production backfill source.
```

- [ ] **Step 2: Run focused test suite**

Run:

```bash
.venv/bin/pytest tests/test_auction_data.py tests/test_schema.py -q
```

Expected:

```text
... passed
```

- [ ] **Step 3: Smoke CLI parser**

Run:

```bash
.venv/bin/python -m stock_research.cli open-auction-spot-snapshot-cron-entry
```

Expected output includes these six lines:

```text
15 9 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_SPOT_OUTPUT_DIR=outputs/research/open_auction_spot_snapshot scripts/run_open_auction_spot_snapshot.sh 09:15 $(date +\%F) >> logs/open_auction_spot_snapshot.log 2>&1
17 9 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_SPOT_OUTPUT_DIR=outputs/research/open_auction_spot_snapshot scripts/run_open_auction_spot_snapshot.sh 09:17 $(date +\%F) >> logs/open_auction_spot_snapshot.log 2>&1
19 9 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_SPOT_OUTPUT_DIR=outputs/research/open_auction_spot_snapshot scripts/run_open_auction_spot_snapshot.sh 09:19 $(date +\%F) >> logs/open_auction_spot_snapshot.log 2>&1
21 9 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_SPOT_OUTPUT_DIR=outputs/research/open_auction_spot_snapshot scripts/run_open_auction_spot_snapshot.sh 09:21 $(date +\%F) >> logs/open_auction_spot_snapshot.log 2>&1
23 9 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_SPOT_OUTPUT_DIR=outputs/research/open_auction_spot_snapshot scripts/run_open_auction_spot_snapshot.sh 09:23 $(date +\%F) >> logs/open_auction_spot_snapshot.log 2>&1
25 9 * * 1-5 cd /Users/xiwei/stock_research && OPEN_AUCTION_SPOT_OUTPUT_DIR=outputs/research/open_auction_spot_snapshot scripts/run_open_auction_spot_snapshot.sh 09:25 $(date +\%F) >> logs/open_auction_spot_snapshot.log 2>&1
```

- [ ] **Step 4: Commit runbook and verification task**

Run:

```bash
git add docs/open-auction-minute-collect-runbook.md
git commit -m "docs: document open auction snapshot source policy"
```

## Self-Review

- Spec coverage: Tasks 1-4 cover new data model, row normalization, collector, report, CLI, wrapper, and cron schedule. Task 5 covers runbook update and verification.
- Source separation: The plan keeps `market.stock_auction_bar` as final-result storage and creates separate snapshot tables for `spot_em`.
- Schedule coverage: The cron task emits exactly `09:15`, `09:17`, `09:19`, `09:21`, `09:23`, and `09:25`.
- Test coverage: Unit tests cover schema, normalization, SQL upsert, collector behavior, report output, and cron generation.
