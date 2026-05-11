# Full-History Phase 8 Features, Labels, And Candidate Factors Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the model-ready research layer over full history with dynamic date windows, resumable backfills, and completeness checks that do not rely on the old 2024 smoke-test slice.

**Architecture:** Keep the existing normalized bar and factor store paths, but add a thin coverage layer that computes the real usable historical window from market data and factor lookback requirements. Then wire labels and factor backfills to those derived boundaries so every task can be restarted, skipped when already complete, and audited by date coverage rather than by rough row counts.

**Tech Stack:** Python, pandas, PostgreSQL, psycopg, pytest, existing `stock-research` CLI, existing `factor`, `feature_snapshot`, `label_snapshot`, and `market_daily_bar` tables.

---

## Current Starting Point

- `label_snapshot` currently uses `compute_and_store_labels(end_date)` with a hard-coded label horizon set and no explicit market-window helper.
- `feature_snapshot` currently uses `compute_and_store_p0_features(trade_date)` with a fixed lookback and no derived coverage start date.
- `factor.factor_daily` already has `build_and_store_factor_daily` for a single trade date, but backfill orchestration still needs a broader completeness model for long history.
- `research_preflight` still defaults to `2024-01-01` and should be moved to derived coverage for full-history work.

## Task 1: Derive Real Coverage Windows

**Files:**
- Create: `src/stock_research/research_windows.py`
- Modify: `src/stock_research/factor_config.py`
- Test: `tests/test_research_windows.py`

- [ ] **Step 1: Write the failing tests**

```python
def test_market_date_bounds_reads_hfq_bar_range(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params):
        calls.append((sql, params))
        return [{"min_date": "1990-12-19", "max_date": "2026-05-08", "date_count": 8200}]

    monkeypatch.setattr(research_windows, "connect", lambda service: _context(object()))
    monkeypatch.setattr(research_windows, "fetch_all", fake_fetch_all)

    bounds = research_windows.load_market_date_bounds(adjust_type="hfq")

    assert bounds == {
        "start_date": "1990-12-19",
        "end_date": "2026-05-08",
        "date_count": 8200,
    }
    assert calls[0][1] == ["hfq"]


def test_feature_window_uses_lookback_and_market_start(monkeypatch):
    monkeypatch.setattr(
        research_windows,
        "load_trade_dates",
        lambda start_date, end_date, adjust_type="hfq", service=None: [
            "1990-12-19",
            "1990-12-20",
            "1990-12-21",
            "1990-12-24",
        ],
    )

    window = research_windows.derive_feature_window(
        start_date="1990-12-19",
        end_date="1990-12-24",
        lookback_bars=3,
    )

    assert window == {"start_date": "1990-12-24", "end_date": "1990-12-24"}
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```bash
.venv/bin/pytest tests/test_research_windows.py -q
```

- [ ] **Step 3: Implement the coverage helpers**

Add helpers that query `market_daily_bar` for:
- earliest available `trade_date` by `adjust_type`
- latest available `trade_date`
- earliest usable feature date after lookback
- latest usable label date before the farthest forward horizon

- [ ] **Step 4: Run the tests and confirm they pass**

Run:

```bash
.venv/bin/pytest tests/test_research_windows.py -q
```

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/research_windows.py src/stock_research/factor_config.py tests/test_research_windows.py
git commit -m "Add derived research coverage windows"
```

## Task 2: Parameterize Label Backfill Window

**Files:**
- Modify: `src/stock_research/labels.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_labels.py`
- Test: `tests/test_schema.py`

- [ ] Add a helper that derives the earliest valid label date from `market_daily_bar` and label horizon.
- [ ] Keep `compute_and_store_labels(end_date)` as the write path, but add a new CLI path for full-history label backfill that accepts derived start/end dates.
- [ ] Make label tests assert that the SQL window still upserts the same horizons, but the caller now chooses dates from the derived window.

## Task 3: Make Factor Backfill Fully Resumable

**Files:**
- Modify: `src/stock_research/factor_backfill.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_factor_backfill.py`

- [ ] Keep `skip_complete` and worker support.
- [ ] Add a derived completeness query that can be used by CLI to backfill only incomplete factor dates.
- [ ] Add tests for empty windows, complete windows, and mixed windows under both sequential and worker execution.

## Task 4: Tighten Preflight And Completeness Rules

**Files:**
- Modify: `src/stock_research/research_preflight.py`
- Modify: `src/stock_research/data_audit.py`
- Test: `tests/test_research_preflight.py`
- Test: `tests/test_data_audit.py`

- [ ] Replace the hard-coded `2024-01-01` default in preflight with a derived default from the market coverage helper.
- [ ] Make factor completeness checks require every configured candidate factor unless explicitly marked unavailable for the date range.
- [ ] Add a coverage line for feature and label snapshots so Phase 8 can be audited before factor evaluation starts.

## Task 5: Phase 8 End-to-End Validation

**Files:**
- Modify: `docs/daily-factor-pipeline-runbook.md`
- Modify: `tests/test_factor_cli.py`

- [ ] Add runbook commands for full-history label backfill, feature backfill, and factor backfill.
- [ ] Verify `research-preflight` reports derived windows rather than the smoke-test default.
- [ ] Run the focused test set and the full suite before closing the slice.
