# Top10 Historical News Backfill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill historical public-news enrichment for `mid_trend_shadow_top10` from `2025-01-02` through `2026-05-19`, producing replay-only file artifacts that can be audited before any database write is considered.

**Architecture:** Add one dedicated historical CLI that reads the existing `mid_trend_shadow_top10.csv`, slices it by trade date, reuses the current TopN source/feature/enrichment helpers per day, then concatenates artifacts into one historical output bundle plus a small summary/report. Keep everything file-based in v1 and preserve the existing single-day `topn-news-source-backfill` workflow untouched.

**Tech Stack:** Python, pandas, pytest

---

### Task 1: Add a historical candidate slicer for Top10 windows

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Test: `tests/test_public_news_fallback_adapter.py`

- [ ] **Step 1: Write failing tests for historical Top10 candidate slicing**

Add focused tests in `tests/test_public_news_fallback_adapter.py` for a helper that:
- reads a Top10 CSV
- filters to `start_date..end_date`
- preserves `trade_date / asset_id / ts_code / stock_name`
- supports optional `sample_trade_dates`

Example test shape:

```python
def test_load_historical_top10_candidates_filters_window_and_sample_days(tmp_path) -> None:
    path = tmp_path / "top10.csv"
    pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"},
            {"trade_date": "2025-01-03", "asset_id": "CN:SZ:300201", "ts_code": "300201.SZ", "stock_name": "海伦哲"},
            {"trade_date": "2025-01-06", "asset_id": "CN:SZ:300408", "ts_code": "300408.SZ", "stock_name": "三环集团"},
        ]
    ).to_csv(path, index=False)

    result = _load_historical_top10_candidates(
        top10_path=path,
        start_date="2025-01-03",
        end_date="2025-01-06",
        sample_trade_dates=1,
    )

    assert result["trade_date"].nunique() == 1
    assert result["trade_date"].min().isoformat() == "2025-01-03"
```

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- FAIL because the historical helper does not exist yet.

- [ ] **Step 3: Implement the historical candidate loader**

In `src/stock_research/news_source_backfill.py` add a focused helper:

```python
def _load_historical_top10_candidates(
    *,
    top10_path: str | Path,
    start_date: str,
    end_date: str,
    sample_trade_dates: int | None = None,
) -> pd.DataFrame:
    ...
```

Behavior:
- read CSV
- parse `trade_date`
- filter inclusive date window
- keep rows with valid `ts_code`
- if `sample_trade_dates` is set, keep the first N distinct trade dates in ascending order
- return normalized frame

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- PASS

### Task 2: Build the historical Top10 news backfill runner

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_public_news_fallback_adapter.py`

- [ ] **Step 1: Write failing tests for historical backfill runner**

Add tests for a new runner:

```python
def test_run_historical_top10_news_backfill_writes_combined_artifacts(tmp_path, monkeypatch) -> None:
    ...
```

Mock per-day source calls and assert:
- combined candidate file written
- combined source events file written
- one row per candidate-day in enrichment-ready output
- summary contains trade_date_count / candidate_rows / source_event_rows

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- FAIL because the historical runner does not exist yet.

- [ ] **Step 3: Implement `run_historical_top10_news_backfill(...)`**

In `src/stock_research/news_source_backfill.py` add:

```python
def run_historical_top10_news_backfill(
    *,
    top10_path: str | Path,
    start_date: str,
    end_date: str,
    provider: str,
    output_dir: str | Path | None = None,
    sample_trade_dates: int | None = None,
) -> dict[str, object]:
    ...
```

Behavior:
- call `_load_historical_top10_candidates(...)`
- group by `trade_date`
- for each day, reuse the existing TopN-source logic rather than rewriting fetch loops
- concatenate day-level source events
- write:
  - `historical_top10_candidates.csv`
  - `historical_news_source_events.csv`

Keep this runner source-layer only; do not mix in features/enrichment yet.

- [ ] **Step 4: Add CLI surface**

In `src/stock_research/cli.py` add:

```bash
stock-research historical-top10-news-backfill \
  --top10-path ... \
  --start-date ... \
  --end-date ... \
  --provider akshare_stock_news_em \
  --sample-trade-dates 20 \
  --output-dir ...
```

Print:
- candidates path
- source events path
- source rows

- [ ] **Step 5: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- PASS

### Task 3: Chain historical features and enrichment

**Files:**
- Modify: `src/stock_research/news_features.py`
- Modify: `src/stock_research/topn_news_enrichment.py`
- Modify: `src/stock_research/news_source_backfill.py`
- Test: `tests/test_news_features.py`
- Test: `tests/test_topn_news_enrichment.py`

- [ ] **Step 1: Write failing tests for historical chain outputs**

Add focused tests that the historical runner can continue from candidates/events into:
- `historical_news_feature_mentions.csv`
- `historical_news_feature_daily.csv`
- `historical_top10_news_enrichment.csv`

The tests should mock tiny 2-day inputs and assert the row counts and key columns exist.

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py \
  /Users/xiwei/stock_research/tests/test_news_features.py \
  /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- FAIL because the historical runner does not yet write feature/enrichment artifacts.

- [ ] **Step 3: Extend the historical runner through feature + enrichment**

Reuse existing helpers:
- `map_news_mentions(...)`
- `build_news_feature_daily(...)`
- `build_topn_news_enrichment(...)`

Concatenate across trade dates and write:
- `historical_news_feature_mentions.csv`
- `historical_news_feature_daily.csv`
- `historical_top10_news_enrichment.csv`

Important:
- mode stays `replay`
- no DB writes
- preserve the current news-compact-summary behavior

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py \
  /Users/xiwei/stock_research/tests/test_news_features.py \
  /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py -q
```

Expected:
- PASS

### Task 4: Add summary/report artifacts

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Test: `tests/test_public_news_fallback_adapter.py`

- [ ] **Step 1: Write failing tests for summary/report generation**

Add tests asserting the historical runner writes:
- `historical_top10_news_backfill_summary.csv`
- `historical_top10_news_backfill_report.md`

And summary contains at least:
- `trade_date_count`
- `candidate_rows`
- `source_event_rows`
- `mention_rows`
- `feature_rows`
- `enrichment_rows`
- `coverage_rows`
- `coverage_rate`
- `compact_summary_nonempty_rows`
- `capital_broker_resonance_rows`
- `risk_without_catalyst_rows`

- [ ] **Step 2: Verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- FAIL because the summary/report do not exist yet.

- [ ] **Step 3: Implement summary + report**

In `src/stock_research/news_source_backfill.py`:
- derive summary metrics from the concatenated artifacts
- write one-row CSV summary
- write markdown report answering:
  - coverage rate
  - compact summary non-empty ratio
  - resonance count
  - risk-without-catalyst count

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- PASS

### Task 5: Focused verification and historical smoke run

**Files:**
- Inspect: `outputs/research/top10_historical_news_backfill_20250102_20260519/...`

- [ ] **Step 1: Run focused verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest \
  /Users/xiwei/stock_research/tests/test_news_source_backfill.py \
  /Users/xiwei/stock_research/tests/test_news_features.py \
  /Users/xiwei/stock_research/tests/test_topn_news_enrichment.py \
  /Users/xiwei/stock_research/tests/test_mid_trend_position_dossier.py \
  /Users/xiwei/stock_research/tests/test_public_news_fallback_adapter.py -q
```

Expected:
- PASS

- [ ] **Step 2: Run a small historical smoke**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  historical-top10-news-backfill \
  --top10-path /Users/xiwei/stock_research/outputs/research/mid_trend_shadow_top10.csv \
  --start-date 2025-01-02 \
  --end-date 2025-01-31 \
  --provider akshare_stock_news_em \
  --sample-trade-dates 10 \
  --output-dir /Users/xiwei/stock_research/outputs/research/top10_historical_news_backfill_smoke_202501
```

Expected:
- combined candidate/source/feature/enrichment artifacts written
- summary/report written

- [ ] **Step 3: Inspect smoke report**

Confirm:
- coverage rate is reported
- compact summary non-empty count is reported
- resonance / risk-without-catalyst counts are reported
