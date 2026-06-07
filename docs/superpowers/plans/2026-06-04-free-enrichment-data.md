# Free Enrichment Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the free AkShare-backed enrichment pipeline for LHB, holders, repurchase, survey, earnings forecast/express, and main business composition from `2025-01-01` onward.

**Architecture:** Add normalized tables plus `raw_akshare.enrichment_payload`, then create `free_enrichment_data.py` as the single ingestion boundary for fetch, normalize, upsert, run summary, and coverage artifacts. Reuse existing LHB tables and import logic where possible, and add one CLI command that can run all datasets or a selected subset.

**Tech Stack:** Python 3.11, pandas, AkShare, psycopg, pytest, PostgreSQL.

---

## File Structure

- Modify: `src/stock_research/schema.py`
  - Add `fundamental` and `event` schemas.
  - Add raw AkShare enrichment payload and normalized enrichment tables.
  - Add lookup indexes for date, asset, and source.
- Create: `src/stock_research/free_enrichment_data.py`
  - Own all free-source enrichment dataset contracts.
  - Implement code normalization, payload hashing, normalizers, upserts, batch runners, coverage artifacts, and run summary.
- Modify: `src/stock_research/cli.py`
  - Add parser and dispatch for `free-enrichment-backfill`.
- Modify: `tests/test_schema.py`
  - Add schema assertions for new schemas and tables.
- Create: `tests/test_free_enrichment_data.py`
  - Add TDD coverage for utilities, normalizers, upsert SQL behavior, run summary, and dry-run orchestration.
- Modify: `tests/test_factor_cli.py`
  - Add CLI parser/dispatch tests for `free-enrichment-backfill`.

---

## Task 1: Schema For Free Enrichment Storage

**Files:**
- Modify: `src/stock_research/schema.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write the failing schema test**

Add this test to `tests/test_schema.py`:

```python
def test_research_extension_includes_free_enrichment_tables():
    sql = CREATE_RESEARCH_EXTENSION_SQL

    assert "CREATE SCHEMA IF NOT EXISTS fundamental;" in sql
    assert "CREATE SCHEMA IF NOT EXISTS event;" in sql
    assert "CREATE TABLE IF NOT EXISTS raw_akshare.enrichment_payload" in sql
    assert "CREATE TABLE IF NOT EXISTS fundamental.shareholder_count" in sql
    assert "CREATE TABLE IF NOT EXISTS fundamental.top10_holder" in sql
    assert "CREATE TABLE IF NOT EXISTS fundamental.top10_float_holder" in sql
    assert "CREATE TABLE IF NOT EXISTS event.shareholder_trade" in sql
    assert "CREATE TABLE IF NOT EXISTS event.stock_repurchase" in sql
    assert "CREATE TABLE IF NOT EXISTS event.institution_survey" in sql
    assert "CREATE TABLE IF NOT EXISTS event.earnings_forecast" in sql
    assert "CREATE TABLE IF NOT EXISTS event.earnings_express" in sql
    assert "CREATE TABLE IF NOT EXISTS finance.main_business_composition" in sql
    assert "payload_hash text NOT NULL" in sql
    assert "idx_raw_akshare_enrichment_payload_endpoint" in sql
    assert "idx_event_stock_repurchase_asset_date" in sql
    assert "idx_finance_main_business_composition_asset_period" in sql
```

- [ ] **Step 2: Run the schema test and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_schema.py::test_research_extension_includes_free_enrichment_tables
```

Expected: FAIL because the new schemas and tables are not in `CREATE_RESEARCH_EXTENSION_SQL`.

- [ ] **Step 3: Add schemas and tables**

Modify `CREATE_RESEARCH_SCHEMAS_SQL` and the repeated schema block inside `CREATE_RESEARCH_EXTENSION_SQL` source area in `src/stock_research/schema.py` to include:

```sql
CREATE SCHEMA IF NOT EXISTS fundamental;
CREATE SCHEMA IF NOT EXISTS event;
```

Add table DDL to `CREATE_RESEARCH_EXTENSION_SQL` near the existing `raw_akshare.finance_payload` and finance/event-adjacent tables:

```sql
CREATE TABLE IF NOT EXISTS raw_akshare.enrichment_payload (
    id bigserial PRIMARY KEY,
    source_endpoint text NOT NULL,
    request_params jsonb NOT NULL,
    asset_id text,
    ts_code text,
    payload jsonb NOT NULL,
    payload_hash text NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (source_endpoint, payload_hash)
);

CREATE TABLE IF NOT EXISTS fundamental.shareholder_count (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_date date NOT NULL,
    announcement_date date,
    shareholder_count numeric,
    shareholder_count_change numeric,
    shareholder_count_change_pct numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_date, source)
);

CREATE TABLE IF NOT EXISTS fundamental.top10_holder (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_period date NOT NULL,
    holder_name text NOT NULL,
    holder_type text,
    hold_amount numeric,
    hold_ratio numeric,
    hold_change numeric,
    rank integer,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, holder_name, source)
);

CREATE TABLE IF NOT EXISTS fundamental.top10_float_holder (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_period date NOT NULL,
    holder_name text NOT NULL,
    holder_type text,
    hold_amount numeric,
    hold_ratio numeric,
    hold_change numeric,
    rank integer,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, holder_name, source)
);

CREATE TABLE IF NOT EXISTS event.shareholder_trade (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    trade_date date,
    announcement_date date,
    holder_name text,
    trade_type text,
    trade_amount numeric,
    trade_ratio numeric,
    trade_price numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.stock_repurchase (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    announcement_date date,
    progress_date date,
    progress text,
    repurchase_amount numeric,
    repurchase_amount_min numeric,
    repurchase_amount_max numeric,
    repurchase_price_min numeric,
    repurchase_price_max numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.institution_survey (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    survey_date date,
    announcement_date date,
    institution_count numeric,
    institution_names text,
    survey_type text,
    summary text,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.earnings_forecast (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    announcement_date date NOT NULL,
    report_period date,
    forecast_type text,
    forecast_np_min numeric,
    forecast_np_max numeric,
    forecast_np_change_min numeric,
    forecast_np_change_max numeric,
    summary text,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS event.earnings_express (
    event_id text PRIMARY KEY,
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    announcement_date date NOT NULL,
    report_period date,
    revenue numeric,
    revenue_yoy numeric,
    np_parent numeric,
    np_parent_yoy numeric,
    eps_basic numeric,
    roe_weighted numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS finance.main_business_composition (
    asset_id text NOT NULL,
    ts_code text NOT NULL,
    report_period date NOT NULL,
    classify_type text NOT NULL,
    item_name text NOT NULL,
    revenue numeric,
    revenue_ratio numeric,
    cost numeric,
    gross_profit numeric,
    gross_margin numeric,
    source text NOT NULL,
    source_endpoint text NOT NULL,
    payload_hash text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (asset_id, report_period, classify_type, item_name, source)
);
```

Add indexes in the existing index section:

```sql
CREATE INDEX IF NOT EXISTS idx_raw_akshare_enrichment_payload_endpoint
    ON raw_akshare.enrichment_payload (source_endpoint, fetched_at DESC);

CREATE INDEX IF NOT EXISTS idx_fundamental_shareholder_count_asset_date
    ON fundamental.shareholder_count (asset_id, report_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_stock_repurchase_asset_date
    ON event.stock_repurchase (asset_id, announcement_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_institution_survey_asset_date
    ON event.institution_survey (asset_id, survey_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_earnings_forecast_asset_date
    ON event.earnings_forecast (asset_id, announcement_date DESC);

CREATE INDEX IF NOT EXISTS idx_event_earnings_express_asset_date
    ON event.earnings_express (asset_id, announcement_date DESC);

CREATE INDEX IF NOT EXISTS idx_finance_main_business_composition_asset_period
    ON finance.main_business_composition (asset_id, report_period DESC);
```

- [ ] **Step 4: Run the schema test and verify GREEN**

Run:

```bash
./.venv/bin/pytest -q tests/test_schema.py::test_research_extension_includes_free_enrichment_tables
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/schema.py tests/test_schema.py
git commit -m "feat: add free enrichment storage schema"
```

---

## Task 2: Core Utilities And Normalization Contracts

**Files:**
- Create: `src/stock_research/free_enrichment_data.py`
- Create: `tests/test_free_enrichment_data.py`

- [ ] **Step 1: Write failing tests for identity and hashing**

Create `tests/test_free_enrichment_data.py`:

```python
import pandas as pd

from stock_research.free_enrichment_data import (
    DatasetRunResult,
    build_event_id,
    normalize_ts_code,
    payload_hash,
    ts_code_to_asset_id,
)


def test_normalize_ts_code_and_asset_id():
    assert normalize_ts_code("600000") == "600000.SH"
    assert normalize_ts_code("000001") == "000001.SZ"
    assert ts_code_to_asset_id("600000.SH") == "CN:SH:600000"
    assert ts_code_to_asset_id("000001.SZ") == "CN:SZ:000001"


def test_payload_hash_is_stable_for_dict_key_order():
    left = payload_hash({"b": 2, "a": 1})
    right = payload_hash({"a": 1, "b": 2})
    assert left == right
    assert len(left) == 64


def test_build_event_id_is_deterministic():
    assert build_event_id("repurchase", ["600000.SH", "2025-01-02", "plan"]) == build_event_id(
        "repurchase", ["600000.SH", "2025-01-02", "plan"]
    )


def test_dataset_run_result_to_dict():
    result = DatasetRunResult(
        dataset="repurchase",
        fetched_rows=3,
        normalized_rows=2,
        upserted_rows=2,
        empty_results=1,
        failed_requests=0,
    )
    assert result.to_dict()["dataset"] == "repurchase"
    assert result.to_dict()["upserted_rows"] == 2
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py
```

Expected: FAIL because `stock_research.free_enrichment_data` does not exist.

- [ ] **Step 3: Implement minimal utilities**

Create `src/stock_research/free_enrichment_data.py`:

```python
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, execute_many, fetch_all


SOURCE = "akshare"


@dataclass(frozen=True)
class DatasetRunResult:
    dataset: str
    fetched_rows: int = 0
    normalized_rows: int = 0
    upserted_rows: int = 0
    empty_results: int = 0
    failed_requests: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "fetched_rows": self.fetched_rows,
            "normalized_rows": self.normalized_rows,
            "upserted_rows": self.upserted_rows,
            "empty_results": self.empty_results,
            "failed_requests": self.failed_requests,
        }


def normalize_ts_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if not text:
        return ""
    if text.endswith((".SH", ".SZ", ".BJ")):
        return text
    code = text.zfill(6)
    if code.startswith(("60", "68", "90")):
        return f"{code}.SH"
    if code.startswith(("00", "30", "20")):
        return f"{code}.SZ"
    if code.startswith(("43", "83", "87", "92")):
        return f"{code}.BJ"
    return code


def ts_code_to_asset_id(ts_code: str) -> str:
    code = normalize_ts_code(ts_code)
    if not code or "." not in code:
        return ""
    symbol, exchange = code.split(".", 1)
    return f"CN:{exchange}:{symbol}"


def payload_hash(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_event_id(prefix: str, parts: list[Any]) -> str:
    normalized = [str(part or "").strip() for part in parts]
    digest = payload_hash({"prefix": prefix, "parts": normalized})[:24]
    return f"{prefix}:{digest}"
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/free_enrichment_data.py tests/test_free_enrichment_data.py
git commit -m "feat: add free enrichment utility contracts"
```

---

## Task 3: LHB Backfill Adapter And Raw Payload Support

**Files:**
- Modify: `src/stock_research/free_enrichment_data.py`
- Modify: `tests/test_free_enrichment_data.py`

- [ ] **Step 1: Write failing LHB runner test**

Add to `tests/test_free_enrichment_data.py`:

```python
from stock_research.free_enrichment_data import run_lhb_backfill


def test_run_lhb_backfill_uses_existing_lhb_import(monkeypatch, tmp_path):
    calls = []

    def fake_lhb_import(**kwargs):
        calls.append(kwargs)
        return {
            "top_list": pd.DataFrame([{"ts_code": "600000.SH"}]),
            "top_inst": pd.DataFrame(),
            "paths": {"top_list": str(tmp_path / "list.csv"), "top_inst": str(tmp_path / "inst.csv")},
        }

    monkeypatch.setattr("stock_research.free_enrichment_data.run_lhb_sample_import", fake_lhb_import)

    result = run_lhb_backfill(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        dry_run=False,
        service="test",
    )

    assert calls[0]["provider"] == "akshare"
    assert calls[0]["ts_codes"] is None
    assert result.dataset == "lhb"
    assert result.normalized_rows == 1
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py::test_run_lhb_backfill_uses_existing_lhb_import
```

Expected: FAIL because `run_lhb_backfill` is not implemented.

- [ ] **Step 3: Implement LHB runner wrapper**

Update `src/stock_research/free_enrichment_data.py`:

```python
from stock_research.lhb_data import run_lhb_sample_import


def run_lhb_backfill(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
) -> DatasetRunResult:
    if dry_run:
        return DatasetRunResult(dataset="lhb")
    result = run_lhb_sample_import(
        start_date=start_date,
        end_date=end_date,
        ts_codes=None,
        provider="akshare",
        output_dir=output_dir,
        service=service,
    )
    top_list = result.get("top_list", pd.DataFrame())
    top_inst = result.get("top_inst", pd.DataFrame())
    normalized_rows = len(top_list) + len(top_inst)
    return DatasetRunResult(
        dataset="lhb",
        fetched_rows=normalized_rows,
        normalized_rows=normalized_rows,
        upserted_rows=normalized_rows,
        empty_results=1 if normalized_rows == 0 else 0,
    )
```

- [ ] **Step 4: Run LHB test and full utility tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/free_enrichment_data.py tests/test_free_enrichment_data.py
git commit -m "feat: add free enrichment lhb runner"
```

---

## Task 4: Holder Dataset Normalizers And Upserts

**Files:**
- Modify: `src/stock_research/free_enrichment_data.py`
- Modify: `tests/test_free_enrichment_data.py`

- [ ] **Step 1: Write failing holder normalizer tests**

Add to `tests/test_free_enrichment_data.py`:

```python
from stock_research.free_enrichment_data import (
    normalize_shareholder_count_rows,
    normalize_top_holder_rows,
)


def test_normalize_shareholder_count_rows_maps_chinese_columns():
    raw = pd.DataFrame(
        [
            {
                "代码": "600000",
                "截止日期": "2025-03-31",
                "公告日期": "2025-04-20",
                "股东户数": 100000,
                "股东户数增减": -1000,
                "股东户数较上期变化百分比": -1.0,
            }
        ]
    )

    frame = normalize_shareholder_count_rows(raw, endpoint="stock_zh_a_gdhs_detail_em")

    assert frame.iloc[0]["ts_code"] == "600000.SH"
    assert frame.iloc[0]["asset_id"] == "CN:SH:600000"
    assert frame.iloc[0]["report_date"] == "2025-03-31"
    assert frame.iloc[0]["shareholder_count"] == 100000


def test_normalize_top_holder_rows_supports_float_holder_flag():
    raw = pd.DataFrame(
        [
            {
                "代码": "000001",
                "报告期": "2025-03-31",
                "股东名称": "中央汇金资产管理有限责任公司",
                "股东类型": "其它",
                "持股数": 123,
                "占总股本持股比例": 1.2,
                "增减": 3,
                "名次": 1,
            }
        ]
    )

    frame = normalize_top_holder_rows(raw, endpoint="stock_gdfx_top_10_em")

    assert frame.iloc[0]["ts_code"] == "000001.SZ"
    assert frame.iloc[0]["report_period"] == "2025-03-31"
    assert frame.iloc[0]["holder_name"] == "中央汇金资产管理有限责任公司"
```

- [ ] **Step 2: Run holder tests and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py -k "holder or shareholder_count"
```

Expected: FAIL because holder normalizers are not implemented.

- [ ] **Step 3: Implement holder normalizers**

Add helpers to `free_enrichment_data.py`:

```python
def _date_text(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def _first_existing(frame: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series([None] * len(frame))


def normalize_shareholder_count_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    data = pd.DataFrame()
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["report_date"] = _date_text(_first_existing(frame, ["截止日期", "报告期", "END_DATE"]))
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "DECLAREDATE", "公告日"]))
    data["shareholder_count"] = pd.to_numeric(_first_existing(frame, ["股东户数", "HOLDER_NUM"]), errors="coerce")
    data["shareholder_count_change"] = pd.to_numeric(_first_existing(frame, ["股东户数增减", "较上期变化", "HOLDER_NUM_CHANGE"]), errors="coerce")
    data["shareholder_count_change_pct"] = pd.to_numeric(_first_existing(frame, ["股东户数较上期变化百分比", "较上期变化百分比"]), errors="coerce")
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    return data[data["asset_id"].ne("") & data["report_date"].notna()].reset_index(drop=True)


def normalize_top_holder_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    data = pd.DataFrame()
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "截止日期", "END_DATE"]))
    data["holder_name"] = _first_existing(frame, ["股东名称", "HOLDER_NAME"]).fillna("").astype(str)
    data["holder_type"] = _first_existing(frame, ["股东类型", "HOLDER_TYPE"])
    data["hold_amount"] = pd.to_numeric(_first_existing(frame, ["持股数", "持股数量", "HOLD_NUM"]), errors="coerce")
    data["hold_ratio"] = pd.to_numeric(_first_existing(frame, ["占总股本持股比例", "持股比例", "HOLD_RATIO"]), errors="coerce")
    data["hold_change"] = pd.to_numeric(_first_existing(frame, ["增减", "持股变动", "HOLD_CHANGE"]), errors="coerce")
    data["rank"] = pd.to_numeric(_first_existing(frame, ["名次", "排名", "RANK"]), errors="coerce")
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    return data[data["asset_id"].ne("") & data["report_period"].notna() & data["holder_name"].ne("")].reset_index(drop=True)
```

- [ ] **Step 4: Run holder normalizer tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py -k "holder or shareholder_count"
```

Expected: PASS.

- [ ] **Step 5: Add upsert tests and implementation**

Add tests that monkeypatch `execute_many` and assert the target table names:

```python
from stock_research.free_enrichment_data import upsert_shareholder_count_rows, upsert_top_holder_rows


def test_holder_upserts_use_expected_tables(monkeypatch):
    calls = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("stock_research.free_enrichment_data.connect", lambda service: Conn())
    monkeypatch.setattr("stock_research.free_enrichment_data.execute_many", lambda conn, sql, rows: calls.append((sql, list(rows))))

    shareholder = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "report_date": "2025-03-31",
                "announcement_date": "2025-04-20",
                "shareholder_count": 100000,
                "shareholder_count_change": -1000,
                "shareholder_count_change_pct": -1,
                "source": "akshare",
                "source_endpoint": "stock_zh_a_gdhs_detail_em",
                "payload_hash": "h1",
            }
        ]
    )
    holders = pd.DataFrame(
        [
            {
                "asset_id": "CN:SH:600000",
                "ts_code": "600000.SH",
                "report_period": "2025-03-31",
                "holder_name": "holder",
                "holder_type": "fund",
                "hold_amount": 1,
                "hold_ratio": 1,
                "hold_change": 0,
                "rank": 1,
                "source": "akshare",
                "source_endpoint": "stock_gdfx_top_10_em",
                "payload_hash": "h2",
            }
        ]
    )

    upsert_shareholder_count_rows(shareholder, service="test")
    upsert_top_holder_rows(holders, table="fundamental.top10_holder", service="test")

    assert "INSERT INTO fundamental.shareholder_count" in calls[0][0]
    assert "INSERT INTO fundamental.top10_holder" in calls[1][0]
```

Implement `upsert_shareholder_count_rows` and `upsert_top_holder_rows` with `ON CONFLICT` keys from the schema.

- [ ] **Step 6: Run tests and commit**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/free_enrichment_data.py tests/test_free_enrichment_data.py
git commit -m "feat: add holder enrichment normalizers"
```

---

## Task 5: Event Dataset Normalizers And Upserts

**Files:**
- Modify: `src/stock_research/free_enrichment_data.py`
- Modify: `tests/test_free_enrichment_data.py`

- [ ] **Step 1: Write failing event normalizer tests**

Add tests for repurchase, survey, and shareholder trade:

```python
from stock_research.free_enrichment_data import (
    normalize_institution_survey_rows,
    normalize_repurchase_rows,
    normalize_shareholder_trade_rows,
)


def test_normalize_repurchase_rows_builds_event_id():
    raw = pd.DataFrame([{"代码": "600000", "公告日期": "2025-02-01", "进度": "实施", "已回购金额": 1000}])
    frame = normalize_repurchase_rows(raw, endpoint="stock_repurchase_em")
    assert frame.iloc[0]["event_id"].startswith("repurchase:")
    assert frame.iloc[0]["asset_id"] == "CN:SH:600000"
    assert frame.iloc[0]["announcement_date"] == "2025-02-01"


def test_normalize_institution_survey_rows_keeps_summary():
    raw = pd.DataFrame([{"代码": "000001", "调研日期": "2025-05-01", "机构数量": 12, "调研内容": "核心问题"}])
    frame = normalize_institution_survey_rows(raw, endpoint="stock_jgdy_detail_em")
    assert frame.iloc[0]["event_id"].startswith("survey:")
    assert frame.iloc[0]["institution_count"] == 12
    assert frame.iloc[0]["summary"] == "核心问题"


def test_normalize_shareholder_trade_rows_keeps_trade_type():
    raw = pd.DataFrame([{"代码": "000001", "变动日期": "2025-04-01", "股东名称": "holder", "变动方向": "减持", "变动数量": 10}])
    frame = normalize_shareholder_trade_rows(raw, endpoint="stock_ggcg_em")
    assert frame.iloc[0]["event_id"].startswith("shareholder_trade:")
    assert frame.iloc[0]["trade_type"] == "减持"
```

- [ ] **Step 2: Run event normalizer tests and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py -k "repurchase or survey or shareholder_trade"
```

Expected: FAIL because event normalizers are missing.

- [ ] **Step 3: Implement event normalizers**

Add functions with flexible Chinese/English column aliases:

```python
def normalize_repurchase_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["progress_date"] = _date_text(_first_existing(frame, ["进度日期", "更新日期", "UPDATE_DATE"]))
    data["progress"] = _first_existing(frame, ["进度", "回购进度", "PROGRESS"])
    data["repurchase_amount"] = pd.to_numeric(_first_existing(frame, ["已回购金额", "回购金额", "REPURCHASE_AMOUNT"]), errors="coerce")
    data["repurchase_amount_min"] = pd.to_numeric(_first_existing(frame, ["拟回购金额下限", "金额下限"]), errors="coerce")
    data["repurchase_amount_max"] = pd.to_numeric(_first_existing(frame, ["拟回购金额上限", "金额上限"]), errors="coerce")
    data["repurchase_price_min"] = pd.to_numeric(_first_existing(frame, ["回购价格下限", "价格下限"]), errors="coerce")
    data["repurchase_price_max"] = pd.to_numeric(_first_existing(frame, ["回购价格上限", "价格上限"]), errors="coerce")
    data["event_id"] = data.apply(lambda row: build_event_id("repurchase", [row["ts_code"], row["announcement_date"], row["progress"]]), axis=1)
    return data[data["asset_id"].ne("")].reset_index(drop=True)


def normalize_institution_survey_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data
    data["survey_date"] = _date_text(_first_existing(frame, ["调研日期", "接待日期", "SURVEY_DATE"]))
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["institution_count"] = pd.to_numeric(_first_existing(frame, ["机构数量", "调研机构数量"]), errors="coerce")
    data["institution_names"] = _first_existing(frame, ["调研机构", "机构名称", "ORG_NAMES"])
    data["survey_type"] = _first_existing(frame, ["调研类型", "接待方式", "SURVEY_TYPE"])
    data["summary"] = _first_existing(frame, ["调研内容", "主要内容", "SUMMARY"])
    data["event_id"] = data.apply(lambda row: build_event_id("survey", [row["ts_code"], row["survey_date"], row["summary"]]), axis=1)
    return data[data["asset_id"].ne("")].reset_index(drop=True)


def normalize_shareholder_trade_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data
    data["trade_date"] = _date_text(_first_existing(frame, ["变动日期", "交易日期", "TRADE_DATE"]))
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["holder_name"] = _first_existing(frame, ["股东名称", "变动人", "HOLDER_NAME"])
    data["trade_type"] = _first_existing(frame, ["变动方向", "变动类型", "TRADE_TYPE"])
    data["trade_amount"] = pd.to_numeric(_first_existing(frame, ["变动数量", "成交股数", "TRADE_AMOUNT"]), errors="coerce")
    data["trade_ratio"] = pd.to_numeric(_first_existing(frame, ["变动比例", "TRADE_RATIO"]), errors="coerce")
    data["trade_price"] = pd.to_numeric(_first_existing(frame, ["成交均价", "TRADE_PRICE"]), errors="coerce")
    data["event_id"] = data.apply(lambda row: build_event_id("shareholder_trade", [row["ts_code"], row["trade_date"], row["holder_name"], row["trade_type"]]), axis=1)
    return data[data["asset_id"].ne("")].reset_index(drop=True)
```

Add `_base_event_frame`:

```python
def _base_event_frame(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    data = pd.DataFrame()
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    return data
```

- [ ] **Step 4: Add event upsert test and implementation**

Add a test that calls:

```python
from stock_research.free_enrichment_data import upsert_event_rows


def test_upsert_event_rows_uses_requested_event_table(monkeypatch):
    calls = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("stock_research.free_enrichment_data.connect", lambda service: Conn())
    monkeypatch.setattr("stock_research.free_enrichment_data.execute_many", lambda conn, sql, rows: calls.append((sql, list(rows))))

    frame = pd.DataFrame([{"event_id": "repurchase:1", "asset_id": "CN:SH:600000", "ts_code": "600000.SH"}])
    upsert_event_rows(frame, table="event.stock_repurchase", service="test")

    assert "INSERT INTO event.stock_repurchase" in calls[0][0]
    assert "ON CONFLICT (event_id)" in calls[0][0]
```

Implement `upsert_event_rows` with table-specific column lists from schema. Reject unknown table names with `ValueError`.

- [ ] **Step 5: Run event tests and commit**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py -k "repurchase or survey or shareholder_trade or upsert_event"
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/free_enrichment_data.py tests/test_free_enrichment_data.py
git commit -m "feat: add free enrichment event normalizers"
```

---

## Task 6: Earnings And Main Business Datasets

**Files:**
- Modify: `src/stock_research/free_enrichment_data.py`
- Modify: `tests/test_free_enrichment_data.py`

- [ ] **Step 1: Write failing tests for earnings and main business**

Add:

```python
from stock_research.free_enrichment_data import (
    normalize_earnings_express_rows,
    normalize_earnings_forecast_rows,
    normalize_main_business_rows,
)


def test_normalize_earnings_forecast_rows():
    raw = pd.DataFrame([{"代码": "600000", "公告日期": "2025-04-10", "报告期": "2025-03-31", "预告类型": "预增", "净利润下限": 10}])
    frame = normalize_earnings_forecast_rows(raw, endpoint="stock_yjyg_em")
    assert frame.iloc[0]["event_id"].startswith("earnings_forecast:")
    assert frame.iloc[0]["forecast_type"] == "预增"
    assert frame.iloc[0]["report_period"] == "2025-03-31"


def test_normalize_earnings_express_rows():
    raw = pd.DataFrame([{"代码": "000001", "公告日期": "2025-04-15", "报告期": "2025-03-31", "营业收入": 100, "净利润": 20}])
    frame = normalize_earnings_express_rows(raw, endpoint="stock_yjkb_em")
    assert frame.iloc[0]["event_id"].startswith("earnings_express:")
    assert frame.iloc[0]["revenue"] == 100
    assert frame.iloc[0]["np_parent"] == 20


def test_normalize_main_business_rows():
    raw = pd.DataFrame([{"代码": "600000", "报告期": "2025-06-30", "分类方向": "按产品", "主营构成": "贷款", "主营收入": 1000, "毛利率": 40}])
    frame = normalize_main_business_rows(raw, endpoint="stock_zygc_em")
    assert frame.iloc[0]["classify_type"] == "按产品"
    assert frame.iloc[0]["item_name"] == "贷款"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py -k "earnings or main_business"
```

Expected: FAIL because normalizers are missing.

- [ ] **Step 3: Implement earnings and main business normalizers**

Add these functions to `src/stock_research/free_enrichment_data.py`:

```python
def normalize_earnings_forecast_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "预测报告期", "REPORT_PERIOD"]))
    data["forecast_type"] = _first_existing(frame, ["预告类型", "业绩变动类型", "FORECAST_TYPE"])
    data["forecast_np_min"] = pd.to_numeric(_first_existing(frame, ["净利润下限", "FORECAST_NP_MIN"]), errors="coerce")
    data["forecast_np_max"] = pd.to_numeric(_first_existing(frame, ["净利润上限", "FORECAST_NP_MAX"]), errors="coerce")
    data["forecast_np_change_min"] = pd.to_numeric(_first_existing(frame, ["净利润变动幅度下限", "预增幅下限"]), errors="coerce")
    data["forecast_np_change_max"] = pd.to_numeric(_first_existing(frame, ["净利润变动幅度上限", "预增幅上限"]), errors="coerce")
    data["summary"] = _first_existing(frame, ["业绩预告摘要", "变动原因", "SUMMARY"])
    data["event_id"] = data.apply(
        lambda row: build_event_id("earnings_forecast", [row["ts_code"], row["announcement_date"], row["report_period"], row["forecast_type"]]),
        axis=1,
    )
    return data[data["asset_id"].ne("") & data["announcement_date"].notna()].reset_index(drop=True)


def normalize_earnings_express_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    data = _base_event_frame(frame, endpoint=endpoint)
    if data.empty:
        return data
    data["announcement_date"] = _date_text(_first_existing(frame, ["公告日期", "ANN_DATE"]))
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "REPORT_PERIOD"]))
    data["revenue"] = pd.to_numeric(_first_existing(frame, ["营业收入", "REVENUE"]), errors="coerce")
    data["revenue_yoy"] = pd.to_numeric(_first_existing(frame, ["营业收入同比", "REVENUE_YOY"]), errors="coerce")
    data["np_parent"] = pd.to_numeric(_first_existing(frame, ["归母净利润", "净利润", "NP_PARENT"]), errors="coerce")
    data["np_parent_yoy"] = pd.to_numeric(_first_existing(frame, ["归母净利润同比", "净利润同比", "NP_PARENT_YOY"]), errors="coerce")
    data["eps_basic"] = pd.to_numeric(_first_existing(frame, ["基本每股收益", "EPS_BASIC"]), errors="coerce")
    data["roe_weighted"] = pd.to_numeric(_first_existing(frame, ["加权净资产收益率", "ROE_WEIGHTED"]), errors="coerce")
    data["event_id"] = data.apply(
        lambda row: build_event_id("earnings_express", [row["ts_code"], row["announcement_date"], row["report_period"]]),
        axis=1,
    )
    return data[data["asset_id"].ne("") & data["announcement_date"].notna()].reset_index(drop=True)


def normalize_main_business_rows(frame: pd.DataFrame, *, endpoint: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    data = pd.DataFrame()
    data["ts_code"] = _first_existing(frame, ["代码", "股票代码", "SECURITY_CODE"]).map(normalize_ts_code)
    data["asset_id"] = data["ts_code"].map(ts_code_to_asset_id)
    data["report_period"] = _date_text(_first_existing(frame, ["报告期", "截止日期", "REPORT_PERIOD"]))
    data["classify_type"] = _first_existing(frame, ["分类方向", "分类类型", "CLASSIFY_TYPE"]).fillna("").astype(str)
    data["item_name"] = _first_existing(frame, ["主营构成", "项目名称", "ITEM_NAME"]).fillna("").astype(str)
    data["revenue"] = pd.to_numeric(_first_existing(frame, ["主营收入", "营业收入", "REVENUE"]), errors="coerce")
    data["revenue_ratio"] = pd.to_numeric(_first_existing(frame, ["收入比例", "主营收入占比", "REVENUE_RATIO"]), errors="coerce")
    data["cost"] = pd.to_numeric(_first_existing(frame, ["主营成本", "营业成本", "COST"]), errors="coerce")
    data["gross_profit"] = pd.to_numeric(_first_existing(frame, ["主营利润", "毛利", "GROSS_PROFIT"]), errors="coerce")
    data["gross_margin"] = pd.to_numeric(_first_existing(frame, ["毛利率", "GROSS_MARGIN"]), errors="coerce")
    data["source"] = SOURCE
    data["source_endpoint"] = endpoint
    data["payload_hash"] = frame.apply(lambda row: payload_hash(row.to_dict()), axis=1)
    return data[
        data["asset_id"].ne("")
        & data["report_period"].notna()
        & data["classify_type"].ne("")
        & data["item_name"].ne("")
    ].reset_index(drop=True)
```

`normalize_main_business_rows` returns these columns:

```python
[
    "asset_id",
    "ts_code",
    "report_period",
    "classify_type",
    "item_name",
    "revenue",
    "revenue_ratio",
    "cost",
    "gross_profit",
    "gross_margin",
    "source",
    "source_endpoint",
    "payload_hash",
]
```

- [ ] **Step 4: Add upsert for main business**

Add `upsert_main_business_rows(frame, service=...)` using:

```sql
INSERT INTO finance.main_business_composition (
    asset_id, ts_code, report_period, classify_type, item_name,
    revenue, revenue_ratio, cost, gross_profit, gross_margin,
    source, source_endpoint, payload_hash
) VALUES (...)
ON CONFLICT (asset_id, report_period, classify_type, item_name, source) DO UPDATE SET
    revenue = EXCLUDED.revenue,
    revenue_ratio = EXCLUDED.revenue_ratio,
    cost = EXCLUDED.cost,
    gross_profit = EXCLUDED.gross_profit,
    gross_margin = EXCLUDED.gross_margin,
    source_endpoint = EXCLUDED.source_endpoint,
    payload_hash = EXCLUDED.payload_hash,
    updated_at = now()
```

- [ ] **Step 5: Run tests and commit**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/free_enrichment_data.py tests/test_free_enrichment_data.py
git commit -m "feat: add earnings and main business enrichment"
```

---

## Task 7: Dataset Orchestrator, Coverage Artifacts, And Progress Logs

**Files:**
- Modify: `src/stock_research/free_enrichment_data.py`
- Modify: `tests/test_free_enrichment_data.py`

- [ ] **Step 1: Write failing orchestration test**

Add:

```python
from stock_research.free_enrichment_data import run_free_enrichment_backfill


def test_run_free_enrichment_backfill_writes_summary_and_coverage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "stock_research.free_enrichment_data.run_lhb_backfill",
        lambda **kwargs: DatasetRunResult(dataset="lhb", fetched_rows=2, normalized_rows=2, upserted_rows=2),
    )

    result = run_free_enrichment_backfill(
        dataset="lhb",
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
        batch_size=100,
        sleep_seconds=0,
        limit=None,
        dry_run=False,
        service="test",
    )

    assert result["summary_path"].endswith("run_summary.json")
    assert result["coverage_path"].endswith("dataset_coverage.csv")
    assert (tmp_path / "run_summary.json").exists()
    assert (tmp_path / "dataset_coverage.csv").exists()
```

- [ ] **Step 2: Run orchestration test and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py::test_run_free_enrichment_backfill_writes_summary_and_coverage
```

Expected: FAIL because the orchestrator is missing.

- [ ] **Step 3: Implement orchestrator and artifact writers**

Add:

```python
DATASETS = ("lhb", "holder", "repurchase", "survey", "forecast", "express", "mainbiz")


def run_free_enrichment_backfill(
    *,
    dataset: str,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    batch_size: int = 100,
    sleep_seconds: float = 1.0,
    limit: int | None = None,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    requested = list(DATASETS) if dataset == "all" else [dataset]
    results: list[DatasetRunResult] = []
    failures: list[dict[str, Any]] = []

    for name in requested:
        if name == "lhb":
            result = run_lhb_backfill(start_date=start_date, end_date=end_date, output_dir=out, dry_run=dry_run, service=service)
        else:
            result = DatasetRunResult(dataset=name)
        results.append(result)
        print(
            "free_enrichment_batch|"
            f"dataset={result.dataset}|fetched={result.fetched_rows}|"
            f"normalized={result.normalized_rows}|upserted={result.upserted_rows}|"
            f"empty={result.empty_results}|failed={result.failed_requests}"
        )

    summary_path = out / "run_summary.json"
    coverage_path = out / "dataset_coverage.csv"
    failures_path = out / "dataset_failures.csv"

    summary_path.write_text(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2), encoding="utf-8")
    pd.DataFrame([coverage_row(item, start_date=start_date, end_date=end_date) for item in results]).to_csv(coverage_path, index=False)
    pd.DataFrame(failures).to_csv(failures_path, index=False)
    return {"results": results, "summary_path": str(summary_path), "coverage_path": str(coverage_path), "failures_path": str(failures_path)}


def coverage_row(result: DatasetRunResult, *, start_date: str, end_date: str) -> dict[str, Any]:
    return {
        "dataset": result.dataset,
        "start_date": start_date,
        "end_date": end_date,
        "asset_count_total": 0,
        "asset_count_covered": 0,
        "coverage_ratio": 0.0,
        "row_count": result.upserted_rows,
        "empty_result_count": result.empty_results,
        "failed_request_count": result.failed_requests,
        "source": SOURCE,
    }
```

- [ ] **Step 4: Run orchestration test**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py::test_run_free_enrichment_backfill_writes_summary_and_coverage
```

Expected: PASS.

- [ ] **Step 5: Extend non-LHB runners**

Add `build_akshare_client()` and dataset runners to `free_enrichment_data.py`. Start with this concrete dispatch table and one runner pattern:

```python
def build_akshare_client():
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("akshare package is required for free enrichment backfill") from exc
    return ak


def run_repurchase_backfill(
    *,
    start_date: str,
    end_date: str,
    output_dir: str | Path,
    dry_run: bool = False,
    service: str = SETTINGS.research_service,
    client: Any = None,
) -> DatasetRunResult:
    endpoint = "stock_repurchase_em"
    ak = client or build_akshare_client()
    try:
        raw = pd.DataFrame(ak.stock_repurchase_em())
    except Exception:
        return DatasetRunResult(dataset="repurchase", failed_requests=1)
    frame = normalize_repurchase_rows(raw, endpoint=endpoint)
    if not frame.empty:
        mask = frame["announcement_date"].between(start_date, end_date)
        frame = frame.loc[mask].reset_index(drop=True)
    if not dry_run and not frame.empty:
        upsert_event_rows(frame, table="event.stock_repurchase", service=service)
    return DatasetRunResult(
        dataset="repurchase",
        fetched_rows=len(raw),
        normalized_rows=len(frame),
        upserted_rows=0 if dry_run else len(frame),
        empty_results=1 if frame.empty else 0,
    )
```

Add the remaining runners with the same signature and explicit endpoint names:

```python
def run_holder_backfill(*, start_date: str, end_date: str, output_dir: str | Path, dry_run: bool = False, service: str = SETTINGS.research_service, client: Any = None) -> DatasetRunResult:
    endpoint = "stock_zh_a_gdhs_detail_em"
    ak = client or build_akshare_client()
    try:
        raw = pd.DataFrame(ak.stock_zh_a_gdhs_detail_em())
    except Exception:
        return DatasetRunResult(dataset="holder", failed_requests=1)
    shareholder = normalize_shareholder_count_rows(raw, endpoint=endpoint)
    if not shareholder.empty:
        shareholder = shareholder.loc[shareholder["report_date"].between(start_date, end_date)].reset_index(drop=True)
    if not dry_run and not shareholder.empty:
        upsert_shareholder_count_rows(shareholder, service=service)
    return DatasetRunResult(dataset="holder", fetched_rows=len(raw), normalized_rows=len(shareholder), upserted_rows=0 if dry_run else len(shareholder), empty_results=1 if shareholder.empty else 0)


def run_survey_backfill(*, start_date: str, end_date: str, output_dir: str | Path, dry_run: bool = False, service: str = SETTINGS.research_service, client: Any = None) -> DatasetRunResult:
    endpoint = "stock_jgdy_detail_em"
    ak = client or build_akshare_client()
    try:
        raw = pd.DataFrame(ak.stock_jgdy_detail_em())
    except Exception:
        return DatasetRunResult(dataset="survey", failed_requests=1)
    frame = normalize_institution_survey_rows(raw, endpoint=endpoint)
    if not frame.empty:
        frame = frame.loc[frame["survey_date"].between(start_date, end_date)].reset_index(drop=True)
    if not dry_run and not frame.empty:
        upsert_event_rows(frame, table="event.institution_survey", service=service)
    return DatasetRunResult(dataset="survey", fetched_rows=len(raw), normalized_rows=len(frame), upserted_rows=0 if dry_run else len(frame), empty_results=1 if frame.empty else 0)


def run_forecast_backfill(*, start_date: str, end_date: str, output_dir: str | Path, dry_run: bool = False, service: str = SETTINGS.research_service, client: Any = None) -> DatasetRunResult:
    endpoint = "stock_yjyg_em"
    ak = client or build_akshare_client()
    try:
        raw = pd.DataFrame(ak.stock_yjyg_em(date=start_date[:4]))
    except Exception:
        return DatasetRunResult(dataset="forecast", failed_requests=1)
    frame = normalize_earnings_forecast_rows(raw, endpoint=endpoint)
    if not frame.empty:
        frame = frame.loc[frame["announcement_date"].between(start_date, end_date)].reset_index(drop=True)
    if not dry_run and not frame.empty:
        upsert_event_rows(frame, table="event.earnings_forecast", service=service)
    return DatasetRunResult(dataset="forecast", fetched_rows=len(raw), normalized_rows=len(frame), upserted_rows=0 if dry_run else len(frame), empty_results=1 if frame.empty else 0)


def run_express_backfill(*, start_date: str, end_date: str, output_dir: str | Path, dry_run: bool = False, service: str = SETTINGS.research_service, client: Any = None) -> DatasetRunResult:
    endpoint = "stock_yjkb_em"
    ak = client or build_akshare_client()
    try:
        raw = pd.DataFrame(ak.stock_yjkb_em(date=start_date[:4]))
    except Exception:
        return DatasetRunResult(dataset="express", failed_requests=1)
    frame = normalize_earnings_express_rows(raw, endpoint=endpoint)
    if not frame.empty:
        frame = frame.loc[frame["announcement_date"].between(start_date, end_date)].reset_index(drop=True)
    if not dry_run and not frame.empty:
        upsert_event_rows(frame, table="event.earnings_express", service=service)
    return DatasetRunResult(dataset="express", fetched_rows=len(raw), normalized_rows=len(frame), upserted_rows=0 if dry_run else len(frame), empty_results=1 if frame.empty else 0)


def run_mainbiz_backfill(*, start_date: str, end_date: str, output_dir: str | Path, dry_run: bool = False, service: str = SETTINGS.research_service, client: Any = None) -> DatasetRunResult:
    endpoint = "stock_zygc_em"
    ak = client or build_akshare_client()
    try:
        raw = pd.DataFrame(ak.stock_zygc_em())
    except Exception:
        return DatasetRunResult(dataset="mainbiz", failed_requests=1)
    frame = normalize_main_business_rows(raw, endpoint=endpoint)
    if not frame.empty:
        frame = frame.loc[frame["report_period"].between(start_date, end_date)].reset_index(drop=True)
    if not dry_run and not frame.empty:
        upsert_main_business_rows(frame, service=service)
    return DatasetRunResult(dataset="mainbiz", fetched_rows=len(raw), normalized_rows=len(frame), upserted_rows=0 if dry_run else len(frame), empty_results=1 if frame.empty else 0)
```

- [ ] **Step 6: Run tests and commit**

Run:

```bash
./.venv/bin/pytest -q tests/test_free_enrichment_data.py
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/free_enrichment_data.py tests/test_free_enrichment_data.py
git commit -m "feat: orchestrate free enrichment backfills"
```

---

## Task 8: CLI Wiring

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing parser test**

Add to `tests/test_factor_cli.py`:

```python
def test_cli_accepts_free_enrichment_backfill_command():
    parser = build_parser()

    args = parser.parse_args(
        [
            "free-enrichment-backfill",
            "--dataset",
            "all",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "today",
            "--batch-size",
            "50",
            "--sleep-seconds",
            "0.5",
            "--limit",
            "10",
            "--dry-run",
        ]
    )

    assert args.command == "free-enrichment-backfill"
    assert args.dataset == "all"
    assert args.batch_size == 50
    assert args.sleep_seconds == 0.5
    assert args.limit == 10
    assert args.dry_run is True
```

- [ ] **Step 2: Run parser test and verify RED**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_free_enrichment_backfill_command
```

Expected: FAIL because the parser does not know `free-enrichment-backfill`.

- [ ] **Step 3: Add parser and import**

Modify imports in `src/stock_research/cli.py`:

```python
from stock_research.free_enrichment_data import run_free_enrichment_backfill
```

Add parser near other research/data backfill commands:

```python
free_enrichment_backfill = subparsers.add_parser("free-enrichment-backfill")
free_enrichment_backfill.add_argument("--dataset", default="all", choices=["all", "lhb", "holder", "repurchase", "survey", "forecast", "express", "mainbiz"])
free_enrichment_backfill.add_argument("--start-date", default="2025-01-01")
free_enrichment_backfill.add_argument("--end-date", default="today")
free_enrichment_backfill.add_argument("--batch-size", type=int, default=100)
free_enrichment_backfill.add_argument("--sleep-seconds", type=float, default=1.0)
free_enrichment_backfill.add_argument("--limit", type=int)
free_enrichment_backfill.add_argument("--dry-run", action="store_true")
free_enrichment_backfill.add_argument("--service", default=SETTINGS.research_service)
free_enrichment_backfill.add_argument(
    "--output-dir",
    default="/Users/xiwei/stock_research/outputs/research/free_enrichment",
)
```

- [ ] **Step 4: Add dispatch test**

Add:

```python
def test_cli_dispatches_free_enrichment_backfill(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        "stock_research.cli.run_free_enrichment_backfill",
        lambda **kwargs: calls.append(kwargs)
        or {
            "summary_path": "/tmp/run_summary.json",
            "coverage_path": "/tmp/dataset_coverage.csv",
            "failures_path": "/tmp/dataset_failures.csv",
            "results": [],
        },
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "stock-research",
            "free-enrichment-backfill",
            "--dataset",
            "lhb",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-31",
        ],
    )

    cli.main()

    out = capsys.readouterr().out
    assert calls[0]["dataset"] == "lhb"
    assert "free_enrichment|summary|/tmp/run_summary.json" in out
    assert "free_enrichment|coverage|/tmp/dataset_coverage.csv" in out
```

- [ ] **Step 5: Add dispatch implementation**

Add dispatch in `main` before the final legacy command section:

```python
elif args.command == "free-enrichment-backfill":
    result = run_free_enrichment_backfill(
        dataset=args.dataset,
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep_seconds,
        limit=args.limit,
        dry_run=args.dry_run,
        service=args.service,
    )
    print(f"free_enrichment|summary|{result['summary_path']}")
    print(f"free_enrichment|coverage|{result['coverage_path']}")
    print(f"free_enrichment|failures|{result['failures_path']}")
```

- [ ] **Step 6: Run CLI tests and commit**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_free_enrichment_backfill_command tests/test_factor_cli.py::test_cli_dispatches_free_enrichment_backfill
```

Expected: PASS.

Commit:

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "feat: add free enrichment backfill cli"
```

---

## Task 9: Verification And First Dry Run

**Files:**
- No planned source edits unless verification exposes a defect.

- [ ] **Step 1: Run targeted test suite**

Run:

```bash
./.venv/bin/pytest -q tests/test_schema.py tests/test_free_enrichment_data.py tests/test_factor_cli.py -k "free_enrichment or enrichment or lhb or schema"
```

Expected: PASS.

- [ ] **Step 2: Run full related tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_lhb_data.py tests/test_free_enrichment_data.py tests/test_schema.py
```

Expected: PASS.

- [ ] **Step 3: Apply schema to local database**

Run:

```bash
./.venv/bin/stock-research apply-schema
```

Expected: command completes without database errors.

- [ ] **Step 4: Run dry-run command**

Run:

```bash
./.venv/bin/stock-research free-enrichment-backfill \
  --dataset all \
  --start-date 2025-01-01 \
  --end-date today \
  --batch-size 20 \
  --sleep-seconds 0 \
  --limit 5 \
  --dry-run \
  --output-dir outputs/research/free_enrichment_dry_run_20260604
```

Expected output includes:

```text
free_enrichment|summary|outputs/research/free_enrichment_dry_run_20260604/run_summary.json
free_enrichment|coverage|outputs/research/free_enrichment_dry_run_20260604/dataset_coverage.csv
free_enrichment|failures|outputs/research/free_enrichment_dry_run_20260604/dataset_failures.csv
```

- [ ] **Step 5: Run live LHB smoke**

Run:

```bash
./.venv/bin/stock-research free-enrichment-backfill \
  --dataset lhb \
  --start-date 2025-01-01 \
  --end-date today \
  --batch-size 100 \
  --sleep-seconds 1 \
  --output-dir outputs/research/free_enrichment_lhb_smoke_20260604
```

Expected: `run_summary.json`, `dataset_coverage.csv`, and LHB sample CSV files are written. The command prints at least one `free_enrichment_batch|dataset=lhb|...` progress line.

- [ ] **Step 6: Commit any verification fixes**

If verification required fixes:

```bash
git add src/stock_research tests
git commit -m "fix: stabilize free enrichment verification"
```

If no fixes were required, do not create an empty commit.

---

## Task 10: First Full Backfill Run

**Files:**
- Runtime outputs only.

- [ ] **Step 1: Start the full free-source backfill**

Run:

```bash
./.venv/bin/stock-research free-enrichment-backfill \
  --dataset all \
  --start-date 2025-01-01 \
  --end-date today \
  --batch-size 100 \
  --sleep-seconds 1 \
  --output-dir outputs/research/free_enrichment_full_20260604
```

Expected: progress logs print after each dataset batch. The command does not fail the whole run for individual request errors.

- [ ] **Step 2: Inspect coverage artifacts**

Run:

```bash
head -20 outputs/research/free_enrichment_full_20260604/dataset_coverage.csv
head -20 outputs/research/free_enrichment_full_20260604/dataset_failures.csv
```

Expected: coverage rows exist for each dataset, and failures are data rows that can be triaged.

- [ ] **Step 3: Query database row counts**

Run:

```bash
psql "$DATABASE_URL" -c "
SELECT 'market.lhb_top_list_daily' AS table_name, count(*) FROM market.lhb_top_list_daily WHERE trade_date >= DATE '2025-01-01'
UNION ALL SELECT 'fundamental.shareholder_count', count(*) FROM fundamental.shareholder_count WHERE report_date >= DATE '2025-01-01'
UNION ALL SELECT 'event.stock_repurchase', count(*) FROM event.stock_repurchase WHERE announcement_date >= DATE '2025-01-01'
UNION ALL SELECT 'event.institution_survey', count(*) FROM event.institution_survey WHERE survey_date >= DATE '2025-01-01'
UNION ALL SELECT 'event.earnings_forecast', count(*) FROM event.earnings_forecast WHERE announcement_date >= DATE '2025-01-01'
UNION ALL SELECT 'event.earnings_express', count(*) FROM event.earnings_express WHERE announcement_date >= DATE '2025-01-01'
UNION ALL SELECT 'finance.main_business_composition', count(*) FROM finance.main_business_composition WHERE report_period >= DATE '2025-01-01';
"
```

Expected: row counts reflect inserted data for datasets whose free endpoints returned records.

---

## Self-Review

Spec coverage:

- Separate normalized tables plus raw payload storage: covered by Task 1.
- Reuse existing LHB storage: covered by Task 3.
- Dataset-specific normalizers and upserts: covered by Tasks 4, 5, and 6.
- Unified CLI: covered by Task 8.
- Progress logs, run summary, coverage and failures: covered by Task 7.
- Dry run and live smoke: covered by Task 9.
- First full run: covered by Task 10.

Placeholder scan:

- No deferred implementation placeholders remain.
- No unresolved decisions remain.

Type consistency:

- `DatasetRunResult`, `run_lhb_backfill`, `run_free_enrichment_backfill`, and `coverage_row` are named consistently.
- CLI command name is consistently `free-enrichment-backfill`.
- Output artifact keys are consistently `summary_path`, `coverage_path`, and `failures_path`.
