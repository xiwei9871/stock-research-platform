# Sector-First 302-Concept Oversold Repair v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a database-only, point-in-time, full-302-concept sector-first oversold-repair workflow that scores every sector independently, ranks stocks inside each sector, validates 1–5 forward sessions, and completes one frozen-date run within 3600 seconds.

**Architecture:** Preserve the existing immutable rolling snapshot pipeline, add explicit sector-repair features and a separate research-eligibility status, then batch-load and vectorize all 302 sectors before grouping stock candidates by sector. Publish sector-level and sector-stock artifacts separately; use the existing outcome evaluator for strict future-session validation and add sector/stock aggregation.

**Tech Stack:** Python 3.11+, pandas, NumPy, PostgreSQL/psycopg, existing `stock_research.rolling_oversold` modules, pytest, CLI artifacts.

---

### Task 1: Extend the frozen sector contracts and output schema

**Files:**
- Modify: `src/stock_research/rolling_oversold/contracts.py`
- Modify: `src/stock_research/rolling_oversold/snapshots.py`
- Modify: `src/stock_research/rolling_oversold/reporting.py`
- Create: `tests/test_rolling_oversold_sector_contracts.py`

- [ ] **Step 1: Write the failing contract tests**

Add tests that require these sector fields in every non-blocked sector row:

```python
def test_sector_repair_columns_are_required():
    required = {
        "sector_low_date_20d",
        "sector_low_close_20d",
        "sector_recovery_from_low_20d",
        "sector_days_since_low_20d",
        "sector_volume_ratio_5_20",
        "sector_ma5_slope_5d",
        "sector_ma10_slope_10d",
        "sector_research_eligibility",
    }
    assert required.issubset(set(REQUIRED_SECTOR_COLUMNS))
```

- [ ] **Step 2: Run the focused test and confirm it fails**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_contracts.py
```

Expected: FAIL because the new columns and eligibility field do not exist.

- [ ] **Step 3: Add explicit enums and column contracts**

Add `SectorResearchEligibility` with values `eligible`, `watch`, and `blocked_data`. Add the new numeric/date columns to the sector output schema and add `sector_research_eligibility` without removing `sector_gate_status`.

Keep `sector_gate_status` for backward compatibility. Snapshot validation must reject missing required columns and must allow a blocked-data sector row with null feature values plus a structured gap.

- [ ] **Step 4: Make snapshot normalization and reporting preserve the fields**

Update snapshot normalization, artifact ordering, and report loaders so the fields round-trip through CSV and manifest publication without changing historical artifact hashes.

- [ ] **Step 5: Run the focused tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_contracts.py tests/test_rolling_oversold_snapshots.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit the contract change**

```bash
rtk git add src/stock_research/rolling_oversold/contracts.py src/stock_research/rolling_oversold/snapshots.py src/stock_research/rolling_oversold/reporting.py tests/test_rolling_oversold_sector_contracts.py tests/test_rolling_oversold_snapshots.py
rtk git commit -m "feat: add sector repair contract fields"
```

### Task 2: Implement explicit sector low-point, recovery, trend, and volume features

**Files:**
- Modify: `src/stock_research/rolling_oversold/sector_scoring.py`
- Create: `tests/test_rolling_oversold_sector_features.py`

- [ ] **Step 1: Write deterministic feature tests**

Use a synthetic sector index with a known low on the third-last session and a two-session rebound. Test exact values:

Define the test-only helper in `tests/test_rolling_oversold_sector_features.py` so it calls the public scorer and returns the single `ths:300238` row:

```python
def membership_for_one_sector():
    return pd.DataFrame(
        {
            "asset_id": ["CN:SH:000001"],
            "concept_system": ["ths"],
            "concept_code": ["300238"],
            "concept_name": ["核电"],
            "start_date": [date(2020, 1, 1)],
            "end_date": [pd.NaT],
        }
    )

def make_scored_sector_row(bars, *, anchor_date):
    result = score_sector_states(
        sector_bars=bars,
        membership=membership_for_one_sector(),
        market_regime={"market_regime": "risk_off"},
        anchor_date=anchor_date,
    )
    return result.loc[result["sector_code"].eq("300238")].iloc[0]
```

```python
def test_recovery_from_recent_low_and_days_since_low():
    bars = make_sector_bars(
        closes=[100, 95, 90, 88, 92, 94],
        volumes=[100, 100, 120, 140, 180, 220],
        amounts=[1000, 1000, 1200, 1400, 1800, 2200],
    )
    row = make_scored_sector_row(bars, anchor_date=date(2026, 7, 31))
    assert row["sector_low_close_20d"] == 88
    assert row["sector_recovery_from_low_20d"] == pytest.approx(94 / 88 - 1)
    assert row["sector_days_since_low_20d"] == 2
    assert row["sector_volume_ratio_5_20"] > 1
```

Also test that a missing volume column produces a null volume ratio with a data-status reason, not an amount-ratio substitute.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_features.py
```

Expected: FAIL because the feature helpers and output fields are absent.

- [ ] **Step 3: Implement pure, point-in-time helpers**

Add pure helpers in `sector_scoring.py`:

- `_low_point_features(closes, dates, windows=(20, 30, 60))`
- `_trend_features(closes, dates)`
- `_volume_features(volume, amount)`
- `_breadth_features(sector_frame)`

Each helper must consume rows at or before `anchor_date`, return nulls for insufficient history, and never infer a missing volume ratio from amount.

Use the formulas:

```text
recovery_from_low = close_t / recent_low_close - 1
days_since_low = trading_index_t - trading_index_low
volume_ratio_5_20 = mean(volume[-5:]) / mean(volume[-20:])
amount_ratio_5_20 = mean(amount[-5:]) / mean(amount[-20:])
```

Add 1/3/5-day returns, MA5/MA10/MA20 levels and slopes, MA cross state, close-above-MA breadth, and leader/breadth fields to the sector row.

- [ ] **Step 4: Integrate helpers into `score_sector_states`**

Keep the existing 60/120/252 drawdown fields. Add the new fields to the finalized sector frame and ensure the date used for every feature is the actual latest usable bar at or before the anchor.

- [ ] **Step 5: Run focused and regression tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_features.py tests/test_rolling_oversold_pipeline.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit sector feature changes**

```bash
rtk git add src/stock_research/rolling_oversold/sector_scoring.py tests/test_rolling_oversold_sector_features.py
rtk git commit -m "feat: add explicit sector repair and volume features"
```

### Task 3: Decouple sector research visibility from stock selection gates

**Files:**
- Modify: `src/stock_research/rolling_oversold/sector_scoring.py`
- Modify: `src/stock_research/rolling_oversold/stock_scoring.py`
- Modify: `src/stock_research/rolling_oversold/pipeline.py`
- Create: `tests/test_rolling_oversold_sector_visibility.py`

- [ ] **Step 1: Write the nuclear regression test**

Construct a `ths:300238` sector with a >2% anchor-day rebound, a prior drawdown, and 25 active members. Assert that the sector row is still published even if the legacy gate is blocked:

```python
def test_blocked_legacy_gate_does_not_drop_sector_research_row():
    result = score_sector_states(sector_bars=bars, membership=membership, market_regime=regime, anchor_date=date(2026, 7, 31))
    nuclear = result.loc[result["sector_code"].eq("300238")].iloc[0]
    assert nuclear["sector_research_eligibility"] in {"eligible", "watch"}
    assert nuclear["sector_recovery_state"] in {"repairing", "confirmed_repair"}
```

- [ ] **Step 2: Run the test and confirm the old behavior fails**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_visibility.py
```

Expected: FAIL because stock scoring currently drops every sector with `sector_gate_status=blocked`.

- [ ] **Step 3: Implement separate research eligibility**

Add a sector-level function that returns:

- `blocked_data` only for insufficient/missing data;
- `eligible` for fresh oversold, repairing, or confirmed repairing sectors with valid data;
- `watch` for repaired, weak, or technically unconfirmed sectors.

Keep legacy gate status in the artifact, but use `sector_research_eligibility` to decide whether a sector receives an independent report.

- [ ] **Step 4: Make stock scoring sector-scoped**

Change `score_rolling_stock_candidates` so it accepts an explicit sector selection and emits `sector_stock_rank`. It must not discard a valid sector solely because the legacy gate is blocked; it may mark the stock `sector_watch` when the sector is watch-only.

- [ ] **Step 5: Run regression tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_visibility.py tests/test_rolling_oversold_stock_scoring.py tests/test_rolling_oversold_snapshots.py
```

Expected: all tests pass, including existing backward-compatibility assertions.

- [ ] **Step 6: Commit the gate separation**

```bash
rtk git add src/stock_research/rolling_oversold/sector_scoring.py src/stock_research/rolling_oversold/stock_scoring.py src/stock_research/rolling_oversold/pipeline.py tests/test_rolling_oversold_sector_visibility.py
rtk git commit -m "feat: preserve sector research beyond legacy gates"
```

### Task 4: Add full-302 batch loading and per-sector Top10 publication

**Files:**
- Modify: `src/stock_research/rolling_oversold/contracts.py`
- Modify: `src/stock_research/rolling_oversold/loaders.py`
- Modify: `src/stock_research/rolling_oversold/pipeline.py`
- Modify: `src/stock_research/rolling_oversold/snapshots.py`
- Create: `tests/test_rolling_oversold_full_sector_batch.py`

- [ ] **Step 1: Write batch and coverage tests**

Test that one anchor loads all eligible concept bars and memberships with a single database input load, that all 302 sectors receive rows, and that each sector's stock ranks restart at 1.

```python
def test_full_sector_batch_has_independent_ranks_and_one_load(monkeypatch):
    result = run_sector_batch(...)
    assert result["sector_count"] == 302
    assert result["stock_candidates"]["sector_stock_rank"].groupby(
        ["sector_system", "sector_code"]
    ).min().eq(1).all()
    assert load_calls == 1
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_full_sector_batch.py
```

Expected: FAIL because the batch API and sector-scoped rank do not exist.

- [ ] **Step 3: Add a batch API**

Add `run_sector_batch` to `pipeline.py`. It must:

1. call `load_rolling_inputs` exactly once;
2. compute market regime once;
3. compute all sector rows in one `score_sector_states` call;
4. compute all stock features once;
5. group candidates by sector without reloading data;
6. publish one immutable batch manifest.

Add a config field `sector_output_top_n=10` while keeping `stock_top_n` for compatibility.

- [ ] **Step 4: Add batch artifact schemas**

Add `sector_daily_board.csv` and `sector_stock_candidates.csv` to the snapshot artifact contract. The stock artifact must contain `sector_stock_rank`, `sector_recovery_state`, `sector_research_eligibility`, and the frozen anchor close.

- [ ] **Step 5: Run focused and pipeline tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_full_sector_batch.py tests/test_rolling_oversold_pipeline.py tests/test_rolling_oversold_acceptance.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit the batch API**

```bash
rtk git add src/stock_research/rolling_oversold/contracts.py src/stock_research/rolling_oversold/loaders.py src/stock_research/rolling_oversold/pipeline.py src/stock_research/rolling_oversold/snapshots.py tests/test_rolling_oversold_full_sector_batch.py
rtk git commit -m "feat: batch all concept sectors with independent stock ranks"
```

### Task 5: Add sector and sector-stock rolling outcome aggregation

**Files:**
- Modify: `src/stock_research/rolling_oversold/outcomes.py`
- Modify: `src/stock_research/rolling_oversold/pipeline.py`
- Create: `tests/test_rolling_oversold_sector_outcomes.py`

- [ ] **Step 1: Write outcome tests**

Test strict-future behavior and separate aggregates:

```python
def test_sector_outcomes_use_only_sessions_after_anchor():
    detail = evaluate_sector_snapshot(snapshot, bars=bars, evaluation_cutoff=date(2026, 8, 3))
    assert (pd.to_datetime(detail["target_trade_date"]) > pd.to_datetime(detail["anchor_date"])).all()
    assert detail.loc[detail["target_trade_date"].eq("2026-08-03"), "status"].eq("pending").all()
```

Test summary columns for complete count, pending count, up ratio, mean/median return, and 3/5/7% hit rates by sector state and sector rank bucket.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_outcomes.py
```

Expected: FAIL because only stock snapshot aggregation exists.

- [ ] **Step 3: Implement sector-level detail and summary**

Extend the existing outcome evaluator to preserve:

- `sector_system`, `sector_code`, `sector_name`;
- `sector_recovery_state`;
- `sector_stock_rank`;
- target session date and endpoint close;
- pending/complete state.

Add summary groups for sector, recovery state, sector rank bucket, and sector-stock rank bucket.

- [ ] **Step 4: Add immutable rolling calibration inputs**

Expose a function that returns only completed outcomes strictly before the next anchor. It must reject rows whose evaluation cutoff is after the next anchor or whose target date is not complete.

- [ ] **Step 5: Run outcome regressions**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_sector_outcomes.py tests/test_rolling_oversold_outcomes.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit outcome aggregation**

```bash
rtk git add src/stock_research/rolling_oversold/outcomes.py src/stock_research/rolling_oversold/pipeline.py tests/test_rolling_oversold_sector_outcomes.py
rtk git commit -m "feat: add sector-level rolling outcome summaries"
```

### Task 6: Add CLI reports for full sector research

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `src/stock_research/rolling_oversold/reporting.py`
- Modify: `tests/test_rolling_oversold_cli.py`
- Create: `tests/test_rolling_oversold_sector_reporting.py`

- [ ] **Step 1: Write CLI and report tests**

Test parsing and output paths for:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/stock-research rolling-sector-oversold-batch \
  --anchor-date 2026-07-31 \
  --output-dir artifacts/rolling_sector_oversold/full_2026-07-31 \
  --service stock_research
```

The report test must assert that the markdown contains the nuclear sector row and the labels `confirmed_repair` and `expected_repair`.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_cli.py tests/test_rolling_oversold_sector_reporting.py
```

Expected: FAIL because the command and report writer do not exist.

- [ ] **Step 3: Add the batch CLI command**

Add `rolling-sector-oversold-batch` with:

- `--anchor-date`;
- `--output-dir`;
- `--service`;
- `--sector-stock-top-n` default 10;
- `--runtime-budget-seconds` default 3600.

Keep existing replay/daily/report commands unchanged.

- [ ] **Step 4: Render sector reports**

Write:

- full `sector_daily_board.csv`;
- full `sector_stock_candidates.csv`;
- compact `sector_repair_summary.md` sorted by repair state, drawdown, and repair strength;
- structured backfill request output for missing fields.

Do not make the markdown the source of truth; all numeric fields must come from the CSV artifact.

- [ ] **Step 5: Run CLI/report tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q tests/test_rolling_oversold_cli.py tests/test_rolling_oversold_sector_reporting.py
```

Expected: all tests pass.

- [ ] **Step 6: Commit CLI/reporting**

```bash
rtk git add src/stock_research/cli.py src/stock_research/rolling_oversold/reporting.py tests/test_rolling_oversold_cli.py tests/test_rolling_oversold_sector_reporting.py
rtk git commit -m "feat: publish full sector repair reports"
```

### Task 7: Optimize the full-302 runtime

**Files:**
- Modify: `src/stock_research/rolling_oversold/loaders.py`
- Modify: `src/stock_research/rolling_oversold/pipeline.py`
- Modify: `src/stock_research/rolling_oversold/sector_scoring.py`
- Create: `tests/test_rolling_oversold_performance.py`

- [ ] **Step 1: Add a performance acceptance test**

Use a representative database run or a deterministic 302-sector fixture. Assert the result includes stage timings and a hard timeout:

```python
def test_full_sector_batch_reports_runtime_under_budget():
    result = run_sector_batch(...)
    assert result["runtime_seconds"] <= 3600
    assert set(["load", "sector", "stock", "publication"]).issubset(
        result["runtime_metadata"]["stage_timings_seconds"]
    )
```

- [ ] **Step 2: Benchmark the current implementation**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli rolling-sector-oversold-batch \
  --anchor-date 2026-07-31 \
  --output-dir artifacts/rolling_sector_oversold/perf_baseline_2026-07-31 \
  --service stock_research
```

Record load, sector, stock, publication timings before optimization.

- [ ] **Step 3: Remove repeated work**

Ensure:

- one SQL load per dataset per anchor;
- concept/industry memberships are canonicalized once;
- sector bars are grouped once;
- stock features are computed once and reused by all sector groups;
- report formatting never recomputes features.

- [ ] **Step 4: Run the performance benchmark**

Run the same command with an output directory ending in `_optimized`. Verify:

- exit code 0;
- no blocked data caused by timeout;
- full sector row count;
- runtime <=3600 seconds;
- no stage exceeds the budget because of an accidental repeated load.

- [ ] **Step 5: Commit the optimization**

```bash
rtk git add src/stock_research/rolling_oversold/loaders.py src/stock_research/rolling_oversold/pipeline.py src/stock_research/rolling_oversold/sector_scoring.py tests/test_rolling_oversold_performance.py
rtk git commit -m "perf: batch full concept sector analysis"
```

### Task 8: Run the 7/27–7/31 walk-forward acceptance

**Files:**
- Create: `docs/superpowers/verification/2026-08-03-sector-first-302-oversold-repair-v2-validation.md`
- Modify: `tests/test_rolling_oversold_acceptance.py`

- [ ] **Step 1: Add acceptance assertions**

Require:

- five frozen anchors processed;
- all sector rows present for each anchor;
- 302-sector coverage or an explicit structured data gap;
- no target-date leakage;
- nuclear sector present at 2026-07-31;
- sector and stock outcomes contain complete/pending states;
- historical snapshots remain immutable.

- [ ] **Step 2: Run the full focused test suite**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q \
  tests/test_rolling_oversold_sector_contracts.py \
  tests/test_rolling_oversold_sector_features.py \
  tests/test_rolling_oversold_sector_visibility.py \
  tests/test_rolling_oversold_full_sector_batch.py \
  tests/test_rolling_oversold_sector_outcomes.py \
  tests/test_rolling_oversold_sector_reporting.py \
  tests/test_rolling_oversold_performance.py \
  tests/test_rolling_oversold_acceptance.py
```

Expected: all tests pass.

- [ ] **Step 3: Run the frozen replay**

Run:

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli rolling-sector-oversold-replay \
  --anchor-start-date 2026-07-27 \
  --anchor-end-date 2026-07-31 \
  --output-dir artifacts/rolling_sector_oversold/full_replay_2026-07-27_2026-07-31 \
  --sector-top-n 302 \
  --stock-top-n 10 \
  --score-version rolling_oversold_sector_v2 \
  --service stock_research
```

- [ ] **Step 4: Verify the artifacts**

Check that:

- every anchor has a manifest and preflight;
- the 7/31 sector board contains `ths,300238,核电`;
- 8/3–8/7 outcomes are pending when those bars are absent;
- no candidate target date is on or before its anchor;
- runtime metadata is present.

- [ ] **Step 5: Write the acceptance record**

Record the exact commands, database service, row counts, runtime stage timings, blocked gaps, complete/pending outcome counts, nuclear regression result, and v1/v2 paired performance comparison in `docs/superpowers/verification/2026-08-03-sector-first-302-oversold-repair-v2-validation.md`.

- [ ] **Step 6: Run compile and full regression tests**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m compileall -q src/stock_research/rolling_oversold
rtk /Users/xiwei/stock_research/.venv/bin/pytest -q
```

Expected: compile succeeds and the complete test suite reports zero failures.

- [ ] **Step 7: Commit the acceptance record**

```bash
rtk git add tests/test_rolling_oversold_acceptance.py docs/superpowers/verification/2026-08-03-sector-first-302-oversold-repair-v2-validation.md
rtk git commit -m "test: accept full sector oversold repair v2"
```
