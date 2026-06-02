# Factor Store Fundamentals Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the first `quality + value` point-in-time fundamentals into the main `factor.factor_daily` pipeline, register them as valid candidate factors, and keep current `manual_v1` scoring behavior unchanged.

**Architecture:** Extend `factor_registry.py` with fundamentals metadata first, then add a small point-in-time fundamentals adapter inside `factor_pipeline.py` that builds a daily snapshot from market bars plus finance services, converts `quality` and `value` outputs into long factor rows, and appends them to the existing technical/sector rows before write-time validation. Preserve score stability by leaving `manual_v1_config()["weights"]` untouched and verifying the scoring path only uses weighted factors already present in the config.

**Tech Stack:** Python 3, pandas, existing point-in-time finance services, existing factor pipeline/store modules, pytest, monkeypatch-based unit tests

---

## File Structure

- Modify: `src/stock_research/factor_registry.py`
  - Add metadata for the first 9 fundamentals factors.
- Modify: `src/stock_research/factor_pipeline.py`
  - Add a point-in-time fundamentals snapshot adapter.
  - Add long-row builders for `quality` and `value`.
  - Extend `build_and_store_factor_daily()` to append fundamentals rows and validate the merged output.
- Reuse as-is if possible: `src/stock_research/factors/quality.py`
- Reuse as-is if possible: `src/stock_research/factors/value.py`
- Reuse as-is if possible: `src/stock_research/services/point_in_time_finance.py`
- Modify: `tests/test_factor_registry.py`
  - Lock registry metadata and candidate-list inclusion for the new factors.
- Modify: `tests/test_factor_config.py`
  - Lock candidate list expansion while keeping `manual_v1` weights stable.
- Modify: `tests/test_factor_pipeline.py`
  - Add snapshot adapter, long-row conversion, missing-finance tolerance, and pipeline integration tests.

Avoid touching `factor_store.py` unless a concrete registry/shape check cannot be expressed in `factor_pipeline.py`.

### Task 1: Register Fundamentals Metadata

**Files:**
- Modify: `src/stock_research/factor_registry.py`
- Modify: `tests/test_factor_registry.py`
- Modify: `tests/test_factor_config.py`

- [ ] **Step 1: Write the failing registry/config tests**

Add these tests before changing the registry:

```python
def test_factor_registry_returns_metadata_for_fundamental_factor():
    meta = factor_registry.get_factor_metadata("roe")

    assert meta.factor_name == "roe"
    assert meta.factor_group == "quality"
    assert meta.direction == "higher"
    assert meta.source == "fundamental"
    assert meta.status == "validated"
```

```python
def test_factor_registry_includes_first_fundamental_factor_set():
    names = factor_registry.list_factor_names()

    assert "roe" in names
    assert "debt_ratio" in names
    assert "pe_ttm" in names
    assert "pb" in names
```

```python
def test_candidate_factor_names_include_fundamental_factors_without_changing_manual_weights():
    names = factor_config.candidate_factor_names()
    config = factor_config.manual_v1_config()

    assert "roe" in names
    assert "ps_ttm" in names
    assert "pb" in names
    assert "roe_score" not in config["weights"]
    assert "pb_score" not in config["weights"]
```

- [ ] **Step 2: Run the targeted registry/config tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_factor_registry.py tests/test_factor_config.py -q -k "fundamental or candidate_factor_names_include_fundamental"
```

Expected:

```text
FAILED ... unknown factor metadata: roe
FAILED ... assert 'roe' in names
```

- [ ] **Step 3: Add the minimal fundamentals metadata**

Extend `_REGISTRY` in `src/stock_research/factor_registry.py` with these `FactorMetadata` entries:

```python
"roe": FactorMetadata("roe", "quality", "higher", "Return on equity", "fundamental"),
"roa": FactorMetadata("roa", "quality", "higher", "Return on assets", "fundamental"),
"gross_margin": FactorMetadata("gross_margin", "quality", "higher", "Gross margin", "fundamental"),
"net_margin": FactorMetadata("net_margin", "quality", "higher", "Net margin", "fundamental"),
"debt_ratio": FactorMetadata("debt_ratio", "quality", "lower", "Debt ratio", "fundamental"),
"ocf_to_np": FactorMetadata("ocf_to_np", "quality", "higher", "Operating cash flow to net profit", "fundamental"),
"pe_ttm": FactorMetadata("pe_ttm", "value", "lower", "Price to earnings TTM", "fundamental"),
"ps_ttm": FactorMetadata("ps_ttm", "value", "lower", "Price to sales TTM", "fundamental"),
"pb": FactorMetadata("pb", "value", "lower", "Price to book", "fundamental"),
```

Do not edit `manual_v1_config()["weights"]`.

- [ ] **Step 4: Re-run the targeted registry/config tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_factor_registry.py tests/test_factor_config.py -q -k "fundamental or candidate_factor_names_include_fundamental"
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 5: Commit the registry slice**

Run:

```bash
git add src/stock_research/factor_registry.py tests/test_factor_registry.py tests/test_factor_config.py
git commit -m "feat: register quality and value factors"
```

### Task 2: Add The PIT Fundamentals Snapshot Adapter

**Files:**
- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `tests/test_factor_pipeline.py`
- Reference: `src/stock_research/services/point_in_time_finance.py`
- Reference: `src/stock_research/factors/quality.py`
- Reference: `src/stock_research/factors/value.py`

- [ ] **Step 1: Write the failing fundamentals snapshot tests**

Add focused tests for the adapter and long-row conversion:

```python
def test_load_point_in_time_fundamentals_snapshot_uses_market_assets_and_pit_rows(monkeypatch):
    class _Conn:
        pass

    monkeypatch.setattr(factor_pipeline, "connect", lambda service: _context(_Conn()))
    monkeypatch.setattr(
        factor_pipeline.point_in_time_finance,
        "get_latest_indicator",
        lambda conn, asset_id, trade_date: {"roe": 0.15, "roa": 0.08},
    )
    monkeypatch.setattr(
        factor_pipeline.point_in_time_finance,
        "get_latest_income_statement",
        lambda conn, asset_id, trade_date: {
            "gross_margin": 0.4,
            "net_margin": 0.1,
            "np_parent_ttm": 100.0,
            "revenue_ttm": 1000.0,
        },
    )
    monkeypatch.setattr(
        factor_pipeline.point_in_time_finance,
        "get_latest_balance_sheet",
        lambda conn, asset_id, trade_date: {
            "debt_ratio": 0.35,
            "equity_parent": 500.0,
            "total_share": 100.0,
            "float_share": 80.0,
        },
    )
    monkeypatch.setattr(
        factor_pipeline.point_in_time_finance,
        "get_latest_cash_flow",
        lambda conn, asset_id, trade_date: {"ocf_to_np": 1.2},
    )

    bars = pd.DataFrame(
        [
            {"trade_date": "2026-05-08", "asset_id": "A", "close": 10.0},
            {"trade_date": "2026-05-08", "asset_id": "B", "close": 20.0},
        ]
    )

    snapshot = factor_pipeline.load_point_in_time_fundamentals_snapshot(
        bars,
        trade_date="2026-05-08",
    )

    assert set(snapshot["asset_id"]) == {"A", "B"}
    assert set(snapshot.columns) >= {
        "asset_id",
        "close",
        "roe",
        "roa",
        "gross_margin",
        "net_margin",
        "debt_ratio",
        "ocf_to_np",
        "np_parent_ttm",
        "revenue_ttm",
        "equity_parent",
        "total_share",
        "float_share",
    }
```

```python
def test_build_quality_and_value_factor_rows_drop_missing_values():
    snapshot = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "close": 10.0,
                "roe": 0.15,
                "roa": 0.08,
                "gross_margin": 0.4,
                "net_margin": 0.1,
                "debt_ratio": 0.35,
                "ocf_to_np": 1.2,
                "np_parent_ttm": 100.0,
                "revenue_ttm": 1000.0,
                "equity_parent": 500.0,
                "total_share": 100.0,
                "float_share": 80.0,
            },
            {
                "asset_id": "B",
                "close": 20.0,
                "roe": None,
                "roa": None,
                "gross_margin": None,
                "net_margin": None,
                "debt_ratio": None,
                "ocf_to_np": None,
                "np_parent_ttm": None,
                "revenue_ttm": None,
                "equity_parent": None,
                "total_share": None,
                "float_share": None,
            },
        ]
    )

    quality_rows = factor_pipeline.build_quality_factor_rows(
        snapshot,
        trade_date="2026-05-08",
        calc_version="v1",
        source_data_version="pit_finance_v1",
    )
    value_rows = factor_pipeline.build_value_factor_rows(
        snapshot,
        trade_date="2026-05-08",
        calc_version="v1",
        source_data_version="pit_finance_v1",
    )

    assert set(quality_rows["factor_name"]) == {
        "roe",
        "roa",
        "gross_margin",
        "net_margin",
        "debt_ratio",
        "ocf_to_np",
    }
    assert set(value_rows["factor_name"]) == {"pe_ttm", "ps_ttm", "pb"}
    assert set(quality_rows["asset_id"]) == {"A"}
    assert set(value_rows["asset_id"]) == {"A"}
    assert set(quality_rows["source"]) == {"fundamental"}
    assert set(value_rows["source_data_version"]) == {"pit_finance_v1"}
```

- [ ] **Step 2: Run the focused pipeline tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_factor_pipeline.py -q -k "point_in_time_fundamentals or quality_and_value_factor_rows"
```

Expected:

```text
FAILED ... AttributeError: module 'stock_research.factor_pipeline' has no attribute 'load_point_in_time_fundamentals_snapshot'
```

- [ ] **Step 3: Implement the minimal adapter and row builders**

In `src/stock_research/factor_pipeline.py`:

1. Add imports:

```python
from stock_research.factors import quality, value
from stock_research.services import point_in_time_finance
```

2. Add:

- `load_point_in_time_fundamentals_snapshot(bars, trade_date, service=...)`
- `build_quality_factor_rows(snapshot, trade_date, calc_version, source_data_version)`
- `build_value_factor_rows(snapshot, trade_date, calc_version, source_data_version)`
- a small `_melt_factor_frame(...)` helper

Recommended long-row shape:

```python
{
    "trade_date": "2026-05-08",
    "asset_id": "A",
    "factor_name": "roe",
    "factor_group": "quality",
    "factor_value": 0.15,
    "calc_version": "v1",
    "source": "fundamental",
    "source_data_version": "pit_finance_v1",
}
```

Use `bars[["asset_id", "close"]]` as the base asset universe, drop duplicate `asset_id`, and merge PIT fields onto that frame.

- [ ] **Step 4: Re-run the focused pipeline tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_factor_pipeline.py -q -k "point_in_time_fundamentals or quality_and_value_factor_rows"
```

Expected:

```text
all selected tests passed
```

- [ ] **Step 5: Commit the fundamentals adapter slice**

Run:

```bash
git add src/stock_research/factor_pipeline.py tests/test_factor_pipeline.py
git commit -m "feat: add point-in-time fundamentals factor builders"
```

### Task 3: Wire Fundamentals Into The Main Factor Pipeline

**Files:**
- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `tests/test_factor_pipeline.py`

- [ ] **Step 1: Write the failing main-pipeline integration tests**

Extend `tests/test_factor_pipeline.py` with integration-style pipeline checks:

```python
def test_build_and_store_factor_daily_appends_quality_and_value_rows(monkeypatch):
    bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-08",
                "asset_id": "A",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "preclose": 10.0,
                "volume": 1000.0,
                "amount": 1000000.0,
                "turnover_rate": 1.0,
                "trade_status": "1",
                "is_st": False,
            }
        ]
    )
    stored = []
    monkeypatch.setattr(factor_pipeline, "load_market_bars_for_factor_date", lambda *args, **kwargs: bars)
    monkeypatch.setattr(
        factor_pipeline,
        "enrich_bars_with_industry",
        lambda bars, **kwargs: bars.assign(industry_code="T", industry_name="Tech"),
    )
    monkeypatch.setattr(
        factor_pipeline,
        "load_industry_bars_for_factor_date",
        lambda *args, **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr(
        factor_pipeline,
        "load_point_in_time_fundamentals_snapshot",
        lambda bars, trade_date, service="stock_research": pd.DataFrame(
            [
                {
                    "asset_id": "A",
                    "close": 10.5,
                    "roe": 0.15,
                    "roa": 0.08,
                    "gross_margin": 0.4,
                    "net_margin": 0.1,
                    "debt_ratio": 0.35,
                    "ocf_to_np": 1.2,
                    "np_parent_ttm": 100.0,
                    "revenue_ttm": 1000.0,
                    "equity_parent": 500.0,
                    "total_share": 100.0,
                    "float_share": 80.0,
                }
            ]
        ),
    )
    monkeypatch.setattr(factor_pipeline, "upsert_factor_daily", lambda rows: stored.append(rows) or len(rows))

    count = factor_pipeline.build_and_store_factor_daily("2026-05-08")

    names = set(stored[0]["factor_name"])
    assert "ret_20" in names
    assert "roe" in names
    assert "pb" in names
    assert count == len(stored[0])
```

```python
def test_build_and_store_factor_daily_keeps_running_when_fundamentals_are_missing(monkeypatch):
    bars = pd.DataFrame(
        [
            {
                "trade_date": "2026-05-08",
                "asset_id": "A",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "preclose": 10.0,
                "volume": 1000.0,
                "amount": 1000000.0,
                "turnover_rate": 1.0,
                "trade_status": "1",
                "is_st": False,
            }
        ]
    )
    stored = []
    monkeypatch.setattr(factor_pipeline, "load_market_bars_for_factor_date", lambda *args, **kwargs: bars)
    monkeypatch.setattr(
        factor_pipeline,
        "enrich_bars_with_industry",
        lambda bars, **kwargs: bars.assign(industry_code="T", industry_name="Tech"),
    )
    monkeypatch.setattr(
        factor_pipeline,
        "load_industry_bars_for_factor_date",
        lambda *args, **kwargs: pd.DataFrame(),
    )
    monkeypatch.setattr(
        factor_pipeline,
        "load_point_in_time_fundamentals_snapshot",
        lambda bars, trade_date, service="stock_research": pd.DataFrame([{"asset_id": "A", "close": 10.5}]),
    )
    monkeypatch.setattr(factor_pipeline, "upsert_factor_daily", lambda rows: stored.append(rows) or len(rows))

    count = factor_pipeline.build_and_store_factor_daily("2026-05-08")

    assert count > 0
    assert "ret_20" in set(stored[0]["factor_name"])
    assert "roe" not in set(stored[0]["factor_name"])
```

- [ ] **Step 2: Run the targeted main-pipeline tests and verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_factor_pipeline.py -q -k "appends_quality_and_value_rows or keeps_running_when_fundamentals_are_missing"
```

Expected:

```text
FAILED ... assert 'roe' in names
```

- [ ] **Step 3: Extend the main builder with fundamentals rows**

In `build_and_store_factor_daily()`:

- keep the existing technical/sector generation
- call `load_point_in_time_fundamentals_snapshot(...)`
- build `quality_rows`
- build `value_rows`
- concat them with the existing rows
- keep registry validation before write

Use:

```python
fundamentals = load_point_in_time_fundamentals_snapshot(...)
quality_rows = build_quality_factor_rows(...)
value_rows = build_value_factor_rows(...)
all_rows = pd.concat([technical_rows, sector_rows, quality_rows, value_rows], ignore_index=True)
```

Do not modify `manual_v1_config()["weights"]`.

- [ ] **Step 4: Re-run the targeted main-pipeline tests and make them pass**

Run:

```bash
.venv/bin/pytest tests/test_factor_pipeline.py -q -k "appends_quality_and_value_rows or keeps_running_when_fundamentals_are_missing"
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit the pipeline integration slice**

Run:

```bash
git add src/stock_research/factor_pipeline.py tests/test_factor_pipeline.py
git commit -m "feat: wire fundamentals into factor daily pipeline"
```

### Task 4: Regression And Score-Stability Hardening

**Files:**
- Modify: `tests/test_factor_pipeline.py`
- Modify: `tests/test_factor_registry.py`
- Modify: `tests/test_factor_config.py`
- Optional Modify: `tests/test_daily_pipeline.py`

- [ ] **Step 1: Add the final score-stability and registry-shape regressions**

Add one or two final tests that lock the intended non-scoring behavior:

```python
def test_manual_v1_config_weights_remain_unchanged_for_new_fundamentals():
    config = factor_config.manual_v1_config()

    assert "roe_score" not in config["weights"]
    assert "pe_ttm_score" not in config["weights"]
    assert "pb_score" not in config["weights"]
    assert config["weights"]["ret_20_score"] > 0
```

```python
def test_build_quality_and_value_rows_match_factor_daily_shape():
    snapshot = pd.DataFrame(
        [
            {
                "asset_id": "A",
                "close": 10.0,
                "roe": 0.15,
                "roa": 0.08,
                "gross_margin": 0.4,
                "net_margin": 0.1,
                "debt_ratio": 0.35,
                "ocf_to_np": 1.2,
                "np_parent_ttm": 100.0,
                "revenue_ttm": 1000.0,
                "equity_parent": 500.0,
                "total_share": 100.0,
                "float_share": 80.0,
            }
        ]
    )

    rows = pd.concat(
        [
            factor_pipeline.build_quality_factor_rows(snapshot, "2026-05-08", "v1", "pit_finance_v1"),
            factor_pipeline.build_value_factor_rows(snapshot, "2026-05-08", "v1", "pit_finance_v1"),
        ],
        ignore_index=True,
    )

    assert list(rows.columns) == factor_pipeline.FACTOR_DAILY_COLUMNS
    assert not rows["factor_value"].isna().any()
```

- [ ] **Step 2: Run the focused fundamentals regression slice**

Run:

```bash
.venv/bin/pytest tests/test_factor_pipeline.py tests/test_factor_registry.py tests/test_factor_config.py tests/test_factor_value.py tests/test_factor_fundamental.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 3: Run the full direct regression set**

Run:

```bash
.venv/bin/pytest tests/test_factor_pipeline.py tests/test_factor_registry.py tests/test_factor_config.py tests/test_factor_value.py tests/test_factor_fundamental.py tests/test_daily_pipeline.py tests/test_factor_backfill.py tests/test_factor_cli.py -q
```

Expected:

```text
all tests passed
```

- [ ] **Step 4: Review the final diff**

Run:

```bash
git diff -- src/stock_research/factor_registry.py src/stock_research/factor_pipeline.py tests/test_factor_registry.py tests/test_factor_config.py tests/test_factor_pipeline.py
```

Verify:

- only `quality + value` factors were added
- no `growth` factor was introduced
- `manual_v1` weights did not change
- fundamentals use `source = "fundamental"` and `source_data_version = "pit_finance_v1"`

- [ ] **Step 5: Commit the regression hardening**

Run:

```bash
git add src/stock_research/factor_registry.py src/stock_research/factor_pipeline.py tests/test_factor_registry.py tests/test_factor_config.py tests/test_factor_pipeline.py
git commit -m "test: harden fundamentals factor pipeline coverage"
```

## Self-Review

### Spec coverage

- Registry metadata for 9 fundamentals factors: Task 1
- PIT-safe fundamentals adapter: Task 2
- Main `build_and_store_factor_daily()` integration: Task 3
- Candidate-list inclusion without score-weight changes: Tasks 1 and 4
- Missing-fundamentals non-blocking behavior: Tasks 2 and 3
- Long-row/store shape guarantees: Tasks 2 and 4

### Placeholder scan

- No `TBD`, `TODO`, or deferred implementation placeholders remain
- Every task includes exact files, concrete test code, commands, and expected outcomes
- All referenced helpers are either existing code or introduced in earlier steps

### Type consistency

- Snapshot adapter: `load_point_in_time_fundamentals_snapshot`
- Long-row builders: `build_quality_factor_rows`, `build_value_factor_rows`
- Unified write shape uses existing `FACTOR_DAILY_COLUMNS`
- Fundamentals lineage is consistently `source="fundamental"` and `source_data_version="pit_finance_v1"`
