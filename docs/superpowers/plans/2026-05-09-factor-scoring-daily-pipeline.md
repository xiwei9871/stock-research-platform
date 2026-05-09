# Factor Scoring Daily Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the end-to-end daily factor pipeline from PostgreSQL market data to `factor.factor_daily`, `factor.stock_score_daily`, factor evaluation reports, and daily TopN output.

**Architecture:** Keep the system modular: factor calculation lives in `factors/`, persistence in `factor_store.py`, scoring in `scoring/`, evaluation in `factor_eval/`, orchestration in a small pipeline module, and CLI in `cli.py`. The first working slice uses existing technical factors and market data; later slices add point-in-time finance factors and reporting without changing V3 strategy logic.

**Tech Stack:** Python 3.11+, pandas, psycopg, PostgreSQL schemas `market`, `core`, `finance`, `factor`, existing `stock-research` CLI, pytest, Git.

---

## Current Baseline

Already implemented and tested:

- `schema.py`: research schemas plus `factor.factor_daily` and `factor.stock_score_daily`.
- `factor_store.py`: factor upsert, score upsert, TopN read, long-factor-to-score storage wrapper.
- `factors/`: trend, momentum, volume-price, risk, sector technical factor modules.
- `factor_eval/`: IC, RankIC, quantile return, Top-Bottom spread, turnover, report wrapper.
- `scoring/`: winsorize, z-score, rank score, composite score, long factor scoring pipeline.
- CLI: existing commands for schema, core data, industry bars, V3.1 cache, backtests, and old P0 features.
- Test baseline at plan creation: `199 passed`.

Main missing pieces:

- CLI commands for factor storage, scoring, TopN display, factor evaluation, and daily pipeline.
- Real DB application of new `factor.*` tables.
- Factor generation service that reads `market_daily_bar` / `market.industry_daily_bar` and writes `factor.factor_daily`.
- TopN scoring pipeline that writes `factor.stock_score_daily`.
- Point-in-time value/growth/quality factors from finance tables.
- Factor evaluation CLI and report files.
- Daily orchestration command and Markdown/CSV/Excel reports.

## File Map

Create:

- `src/stock_research/factor_pipeline.py`: read market data, compute technical factors, normalize long-form factor rows.
- `src/stock_research/factor_config.py`: factor directions, groups, weights, versions.
- `src/stock_research/factor_eval_store.py`: load factor values and forward returns from DB for evaluation.
- `src/stock_research/reports/daily_topn_report.py`: write daily TopN Markdown and CSV.
- `tests/test_factor_pipeline.py`: factor pipeline service tests.
- `tests/test_factor_cli.py`: CLI parsing and command output tests for factor/scoring commands.
- `tests/test_factor_eval_cli.py`: CLI parsing and evaluation command tests.
- `tests/test_daily_pipeline.py`: daily pipeline orchestration tests.

Modify:

- `src/stock_research/cli.py`: add CLI commands and dispatch.
- `src/stock_research/schema.py`: add optional factor evaluation run/report tables only if needed by Task 8.
- `src/stock_research/factors/value.py`: point-in-time value factors.
- `src/stock_research/factors/growth.py`: point-in-time growth factors.
- `src/stock_research/factors/quality.py`: point-in-time quality factors.
- `src/stock_research/reporting.py`: reuse existing report formatting patterns for Markdown line structure and daily output naming.
- `docs/astock-research-platform-v1.md`: update current progress after each milestone.

Do not modify:

- V3.1 strategy thresholds.
- V3.1 backtest entry/exit logic.
- Existing cache file format unless a later task explicitly adds a backward-compatible reader.

---

## Milestone 1: Apply Factor Schema And Add CLI Surface

### Task 1: Add CLI Commands For Factor Workflow

**Files:**

- Modify: `src/stock_research/cli.py`
- Test: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI parser tests**

Add `tests/test_factor_cli.py`:

```python
from stock_research.cli import build_parser


def test_cli_accepts_build_factor_daily_command():
    args = build_parser().parse_args(
        [
            "build-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--lookback-bars",
            "130",
            "--industry-system",
            "csrc",
        ]
    )

    assert args.command == "build-factor-daily"
    assert args.trade_date == "2026-05-08"
    assert args.lookback_bars == 130
    assert args.industry_system == "csrc"


def test_cli_accepts_score-factor-daily_command():
    args = build_parser().parse_args(
        [
            "score-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
        ]
    )

    assert args.command == "score-factor-daily"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"


def test_cli_accepts_show_top_scores_command():
    args = build_parser().parse_args(
        [
            "show-top-scores",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "30",
        ]
    )

    assert args.command == "show-top-scores"
    assert args.trade_date == "2026-05-08"
    assert args.score_version == "manual_v1"
    assert args.top_n == 30
```

- [ ] **Step 2: Run parser tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_cli.py -q
```

Expected: FAIL because `build-factor-daily`, `score-factor-daily`, and `show-top-scores` are unknown commands.

- [ ] **Step 3: Add parser commands**

In `src/stock_research/cli.py`, inside `build_parser()` before `return parser`, add:

```python
    build_factor_daily = subparsers.add_parser("build-factor-daily")
    build_factor_daily.add_argument("--trade-date", required=True)
    build_factor_daily.add_argument("--lookback-bars", type=int, default=130)
    build_factor_daily.add_argument("--industry-system", default="csrc")

    score_factor_daily = subparsers.add_parser("score-factor-daily")
    score_factor_daily.add_argument("--trade-date", required=True)
    score_factor_daily.add_argument("--score-version", default="manual_v1")

    show_top_scores = subparsers.add_parser("show-top-scores")
    show_top_scores.add_argument("--trade-date", required=True)
    show_top_scores.add_argument("--score-version", default="manual_v1")
    show_top_scores.add_argument("--top-n", type=int, default=30)
```

- [ ] **Step 4: Run parser tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_cli.py -q
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "Add factor workflow CLI surface"
```

### Task 2: Apply New Factor Tables To PostgreSQL

**Files:**

- No source change required if `schema.py` already includes `factor.factor_daily` and `factor.stock_score_daily`.
- Verification command against local DB.

- [ ] **Step 1: Run full tests before DB mutation**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Apply schema**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Expected output:

```text
research_schema_applied
```

- [ ] **Step 3: Verify tables exist**

Run:

```bash
PGPASSWORD='mqkj1234' /opt/homebrew/opt/libpq/bin/psql -h 192.168.3.187 -p 5432 -U postgres -d postgres -Atc "SELECT table_schema || '.' || table_name FROM information_schema.tables WHERE table_schema = 'factor' ORDER BY table_name;"
```

Expected output includes:

```text
factor.factor_daily
factor.stock_score_daily
```

- [ ] **Step 4: Verify indexes exist**

Run:

```bash
PGPASSWORD='mqkj1234' /opt/homebrew/opt/libpq/bin/psql -h 192.168.3.187 -p 5432 -U postgres -d postgres -Atc "SELECT indexname FROM pg_indexes WHERE schemaname = 'factor' ORDER BY indexname;"
```

Expected output includes:

```text
factor_daily_pkey
idx_factor_daily_lookup
idx_stock_score_daily_rank
stock_score_daily_pkey
```

- [ ] **Step 5: Commit only if schema source changed**

If no source files changed, do not commit. If `schema.py` required a fix, run:

```bash
git add src/stock_research/schema.py tests/test_schema.py
git commit -m "Fix factor schema DDL"
```

---

## Milestone 2: Technical Factor Generation Into `factor.factor_daily`

### Task 3: Add Factor Pipeline Config

**Files:**

- Create: `src/stock_research/factor_config.py`
- Test: `tests/test_factor_pipeline.py`

- [ ] **Step 1: Write failing config test**

Create `tests/test_factor_pipeline.py` with:

```python
from stock_research import factor_config


def test_manual_v1_config_contains_directions_weights_and_groups():
    config = factor_config.manual_v1_config()

    assert config["score_version"] == "manual_v1"
    assert config["calc_version"] == "v1"
    assert config["source_data_version"] == "market_daily_bar:hfq"
    assert config["factor_groups"]["ret_20"] == "momentum"
    assert config["factor_directions"]["ret_20"] == "higher"
    assert config["factor_directions"]["volatility_20"] == "lower"
    assert config["weights"]["ret_20_score"] > 0
    assert config["weights"]["volatility_20_score"] > 0
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_manual_v1_config_contains_directions_weights_and_groups -q
```

Expected: FAIL because `factor_config` does not exist.

- [ ] **Step 3: Implement config**

Create `src/stock_research/factor_config.py`:

```python
def manual_v1_config() -> dict:
    factor_groups = {
        "ret_5": "momentum",
        "ret_20": "momentum",
        "ret_60": "momentum",
        "momentum_20_5": "momentum",
        "close_above_ma20": "trend",
        "close_above_ma60": "trend",
        "ma20_slope": "trend",
        "ma60_slope": "trend",
        "trend_r2_20": "trend",
        "amount_ratio_5_20": "volume_price",
        "volume_ratio_5_20": "volume_price",
        "turnover_ratio_5_20": "volume_price",
        "price_volume_corr_10": "volume_price",
        "volatility_20": "risk",
        "max_drawdown_20": "risk",
        "atr_pct": "risk",
        "distance_ma20": "risk",
        "distance_ma60": "risk",
        "sector_ret_20": "sector",
        "stock_excess_ret_20": "sector",
        "sector_up_ratio": "sector",
    }
    factor_directions = {
        "ret_5": "higher",
        "ret_20": "higher",
        "ret_60": "higher",
        "momentum_20_5": "higher",
        "close_above_ma20": "higher",
        "close_above_ma60": "higher",
        "ma20_slope": "higher",
        "ma60_slope": "higher",
        "trend_r2_20": "higher",
        "amount_ratio_5_20": "higher",
        "volume_ratio_5_20": "higher",
        "turnover_ratio_5_20": "higher",
        "price_volume_corr_10": "higher",
        "volatility_20": "lower",
        "max_drawdown_20": "higher",
        "atr_pct": "lower",
        "distance_ma20": "lower",
        "distance_ma60": "lower",
        "sector_ret_20": "higher",
        "stock_excess_ret_20": "higher",
        "sector_up_ratio": "higher",
    }
    weights = {
        "ret_20_score": 0.15,
        "ret_60_score": 0.10,
        "momentum_20_5_score": 0.10,
        "ma20_slope_score": 0.10,
        "ma60_slope_score": 0.05,
        "trend_r2_20_score": 0.05,
        "amount_ratio_5_20_score": 0.08,
        "volume_ratio_5_20_score": 0.05,
        "volatility_20_score": 0.10,
        "max_drawdown_20_score": 0.07,
        "atr_pct_score": 0.05,
        "sector_ret_20_score": 0.05,
        "stock_excess_ret_20_score": 0.05,
    }
    return {
        "score_version": "manual_v1",
        "calc_version": "v1",
        "source_data_version": "market_daily_bar:hfq",
        "factor_groups": factor_groups,
        "factor_directions": factor_directions,
        "weights": weights,
    }
```

- [ ] **Step 4: Run config test**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_manual_v1_config_contains_directions_weights_and_groups -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_config.py tests/test_factor_pipeline.py
git commit -m "Add manual factor scoring config"
```

### Task 4: Load Market Bars For Factor Calculation

**Files:**

- Create: `src/stock_research/factor_pipeline.py`
- Modify: `tests/test_factor_pipeline.py`

- [ ] **Step 1: Write failing loader test**

Append to `tests/test_factor_pipeline.py`:

```python
import pandas as pd

from stock_research import factor_pipeline


def test_load_market_bars_for_factor_date_queries_lookback_window(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [
            {
                "trade_date": "2026-05-08",
                "asset_id": "CN:SH:600001",
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

    monkeypatch.setattr(factor_pipeline, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_pipeline, "fetch_all", fake_fetch_all)

    bars = factor_pipeline.load_market_bars_for_factor_date("2026-05-08", lookback_bars=130)

    assert len(bars) == 1
    assert bars.iloc[0]["asset_id"] == "CN:SH:600001"
    assert "row_number() over" in calls[0][0]
    assert calls[0][1] == ["2026-05-08", 130]


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_load_market_bars_for_factor_date_queries_lookback_window -q
```

Expected: FAIL because `factor_pipeline` or function does not exist.

- [ ] **Step 3: Implement loader**

Create or update `src/stock_research/factor_pipeline.py`:

```python
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_market_bars_for_factor_date(
    trade_date: str,
    lookback_bars: int = 130,
    adjust_type: str = "hfq",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    WITH ranked AS (
        SELECT
            trade_date,
            asset_id,
            open,
            high,
            low,
            close,
            preclose,
            volume,
            amount,
            turnover_rate,
            trade_status,
            is_st,
            row_number() over (partition by asset_id order by trade_date desc) AS row_num
        FROM market_daily_bar
        WHERE trade_date <= %s
          AND adjust_type = %s
    )
    SELECT
        trade_date,
        asset_id,
        open,
        high,
        low,
        close,
        preclose,
        volume,
        amount,
        turnover_rate,
        trade_status,
        is_st
    FROM ranked
    WHERE row_num <= %s
    ORDER BY asset_id, trade_date
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [trade_date, adjust_type, lookback_bars])
    return pd.DataFrame(rows)
```

Adjust the expected params in the test to `["2026-05-08", "hfq", 130]`.

- [ ] **Step 4: Run loader test**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_load_market_bars_for_factor_date_queries_lookback_window -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/factor_pipeline.py tests/test_factor_pipeline.py
git commit -m "Add factor market bar loader"
```

### Task 5: Compute Technical Factor Rows For One Trade Date

**Files:**

- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `tests/test_factor_pipeline.py`

- [ ] **Step 1: Write failing computation test**

Append:

```python
def test_compute_technical_factor_rows_returns_long_factor_daily_rows():
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": list(dates) * 2,
            "asset_id": ["A"] * 70 + ["B"] * 70,
            "open": list(range(1, 71)) + list(range(2, 72)),
            "high": list(range(2, 72)) + list(range(3, 73)),
            "low": list(range(1, 71)) + list(range(2, 72)),
            "close": list(range(1, 71)) + list(range(2, 72)),
            "preclose": [None] + list(range(1, 70)) + [None] + list(range(2, 71)),
            "volume": [1000.0 + index for index in range(70)] * 2,
            "amount": [1000000.0 + index * 1000 for index in range(70)] * 2,
            "turnover_rate": [1.0 + index / 100 for index in range(70)] * 2,
            "trade_status": ["1"] * 140,
            "is_st": [False] * 140,
        }
    )

    rows = factor_pipeline.compute_technical_factor_rows(
        bars,
        trade_date="2026-03-11",
        factor_groups={"ret_20": "momentum", "volatility_20": "risk"},
        calc_version="v1",
        source_data_version="market_daily_bar:hfq",
    )

    assert set(rows["factor_name"]) == {"ret_20", "volatility_20"}
    assert set(rows["asset_id"]) == {"A", "B"}
    assert set(rows["factor_group"]) == {"momentum", "risk"}
    assert set(rows["calc_version"]) == {"v1"}
    assert set(rows["source"]) == {"custom"}
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_compute_technical_factor_rows_returns_long_factor_daily_rows -q
```

Expected: FAIL because `compute_technical_factor_rows` does not exist.

- [ ] **Step 3: Implement computation**

In `factor_pipeline.py`, import factor modules and add:

```python
from typing import Any

from stock_research.factors import momentum, risk, trend, volume_price


def compute_technical_factor_rows(
    bars: pd.DataFrame,
    trade_date: str,
    factor_groups: dict[str, str],
    calc_version: str,
    source_data_version: str,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if bars.empty:
        return pd.DataFrame(columns=[
            "trade_date",
            "asset_id",
            "factor_name",
            "factor_group",
            "factor_value",
            "calc_version",
            "source",
            "source_data_version",
        ])

    for asset_id, group in bars.groupby("asset_id", sort=False):
        frame = group.sort_values("trade_date").reset_index(drop=True)
        computed = frame.copy()
        for calculator in (
            momentum.compute_momentum_factors,
            trend.compute_trend_factors,
            volume_price.compute_volume_price_factors,
            risk.compute_risk_factors,
        ):
            factor_frame = calculator(frame)
            for column in factor_frame.columns:
                computed[column] = factor_frame[column]

        latest = computed[computed["trade_date"].astype(str).str[:10] == str(trade_date)[:10]]
        if latest.empty:
            continue
        record = latest.iloc[-1]
        for factor_name, factor_group in factor_groups.items():
            if factor_name not in computed.columns:
                continue
            value = record.get(factor_name)
            if pd.isna(value):
                continue
            rows.append(
                {
                    "trade_date": str(trade_date)[:10],
                    "asset_id": str(asset_id),
                    "factor_name": factor_name,
                    "factor_group": factor_group,
                    "factor_value": float(value),
                    "calc_version": calc_version,
                    "source": "custom",
                    "source_data_version": source_data_version,
                }
            )

    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run computation test**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_compute_technical_factor_rows_returns_long_factor_daily_rows -q
```

Expected: PASS.

- [ ] **Step 5: Run focused factor pipeline tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py -q
```

Expected: all tests in `test_factor_pipeline.py` pass.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/factor_pipeline.py tests/test_factor_pipeline.py
git commit -m "Compute technical factor daily rows"
```

### Task 6: Build And Store Technical Factor Daily

**Files:**

- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `tests/test_factor_pipeline.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing service test**

Append:

```python
def test_build_and_store_factor_daily_loads_computes_and_upserts(monkeypatch):
    calls = []
    dates = pd.date_range("2026-01-01", periods=70, freq="D")
    bars = pd.DataFrame(
        {
            "trade_date": dates,
            "asset_id": ["A"] * 70,
            "open": range(1, 71),
            "high": range(2, 72),
            "low": range(1, 71),
            "close": range(1, 71),
            "preclose": [None] + list(range(1, 70)),
            "volume": [1000.0 + index for index in range(70)],
            "amount": [1000000.0 + index * 1000 for index in range(70)],
            "turnover_rate": [1.0 + index / 100 for index in range(70)],
            "trade_status": ["1"] * 70,
            "is_st": [False] * 70,
        }
    )

    monkeypatch.setattr(factor_pipeline, "load_market_bars_for_factor_date", lambda *args, **kwargs: bars)
    monkeypatch.setattr(factor_pipeline, "upsert_factor_daily", lambda rows: calls.append(rows) or len(rows))

    count = factor_pipeline.build_and_store_factor_daily("2026-03-11", lookback_bars=130)

    assert count > 0
    assert calls[0]["trade_date"].nunique() == 1
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py::test_build_and_store_factor_daily_loads_computes_and_upserts -q
```

Expected: FAIL because `build_and_store_factor_daily` does not exist.

- [ ] **Step 3: Implement service wrapper**

In `factor_pipeline.py`, import config/store and add:

```python
from stock_research.factor_config import manual_v1_config
from stock_research.factor_store import upsert_factor_daily


def build_and_store_factor_daily(
    trade_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
) -> int:
    config = manual_v1_config()
    bars = load_market_bars_for_factor_date(trade_date, lookback_bars=lookback_bars)
    factors = compute_technical_factor_rows(
        bars,
        trade_date=trade_date,
        factor_groups=config["factor_groups"],
        calc_version=config["calc_version"],
        source_data_version=config["source_data_version"],
    )
    return upsert_factor_daily(factors)
```

Keep `industry_system` in the signature now because sector enrichment in Task 9 will use it.

- [ ] **Step 4: Add CLI dispatch test**

Append to `tests/test_factor_cli.py`:

```python
def test_build_factor_daily_cli_prints_count(monkeypatch, capsys):
    import sys
    import stock_research.cli as cli

    monkeypatch.setattr(cli, "build_and_store_factor_daily", lambda **kwargs: 42)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "build-factor-daily",
            "--trade-date",
            "2026-05-08",
            "--lookback-bars",
            "130",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "factor_daily_stored|42"
```

- [ ] **Step 5: Update CLI imports and dispatch**

In `cli.py`, add import:

```python
from stock_research.factor_pipeline import build_and_store_factor_daily
```

In `main()`, add branch before `build-v31-cache`:

```python
    elif args.command == "build-factor-daily":
        count = build_and_store_factor_daily(
            trade_date=args.trade_date,
            lookback_bars=args.lookback_bars,
            industry_system=args.industry_system,
        )
        print(f"factor_daily_stored|{count}")
```

- [ ] **Step 6: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py tests/test_factor_cli.py -q
```

Expected: all focused tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/factor_pipeline.py src/stock_research/cli.py tests/test_factor_pipeline.py tests/test_factor_cli.py
git commit -m "Add factor daily build command"
```

---

## Milestone 3: Score Factors And Read TopN

### Task 7: Score Stored Factor Daily

**Files:**

- Modify: `src/stock_research/factor_store.py`
- Modify: `tests/test_factor_store.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing DB load test**

Append to `tests/test_factor_store.py`:

```python
def test_load_factor_daily_queries_trade_date_and_calc_version(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [
            {
                "trade_date": "2026-05-08",
                "asset_id": "A",
                "factor_name": "ret_20",
                "factor_group": "momentum",
                "factor_value": 0.1,
                "calc_version": "v1",
                "source": "custom",
                "source_data_version": "market_daily_bar:hfq",
            }
        ]

    monkeypatch.setattr(factor_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_store, "fetch_all", fake_fetch_all)

    frame = factor_store.load_factor_daily("2026-05-08", calc_version="v1")

    assert frame.iloc[0]["factor_name"] == "ret_20"
    assert "FROM factor.factor_daily" in calls[0][0]
    assert calls[0][1] == ["2026-05-08", "v1"]
```

- [ ] **Step 2: Implement `load_factor_daily`**

In `factor_store.py`:

```python
def load_factor_daily(
    trade_date: object,
    calc_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT
        trade_date,
        asset_id,
        factor_name,
        factor_group,
        factor_value,
        calc_version,
        source,
        source_data_version
    FROM factor.factor_daily
    WHERE trade_date = %s
      AND calc_version = %s
    ORDER BY asset_id, factor_name
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [_date_string(trade_date), calc_version])
    return pd.DataFrame(rows)
```

- [ ] **Step 3: Add service wrapper**

In `factor_store.py`:

```python
from stock_research.factor_config import manual_v1_config


def score_stored_factor_daily(
    trade_date: object,
    score_version: str = "manual_v1",
    calc_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> int:
    config = manual_v1_config()
    factors = load_factor_daily(trade_date, calc_version=calc_version, service=service)
    return score_and_store_factor_daily(
        factors,
        factor_directions=config["factor_directions"],
        weights=config["weights"],
        score_version=score_version,
        calc_version=calc_version,
        service=service,
    )
```

- [ ] **Step 4: Add CLI dispatch tests**

Append to `tests/test_factor_cli.py`:

```python
def test_score_factor_daily_cli_prints_count(monkeypatch, capsys):
    import sys
    import stock_research.cli as cli

    monkeypatch.setattr(cli, "score_stored_factor_daily", lambda **kwargs: 12)
    monkeypatch.setattr(
        sys,
        "argv",
        ["stock-research", "score-factor-daily", "--trade-date", "2026-05-08"],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "stock_score_daily_stored|12"
```

In `cli.py`, import and dispatch:

```python
from stock_research.factor_store import load_top_scores, score_stored_factor_daily
```

```python
    elif args.command == "score-factor-daily":
        count = score_stored_factor_daily(
            trade_date=args.trade_date,
            score_version=args.score_version,
        )
        print(f"stock_score_daily_stored|{count}")
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_store.py tests/test_factor_cli.py -q
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/factor_store.py src/stock_research/cli.py tests/test_factor_store.py tests/test_factor_cli.py
git commit -m "Add stored factor scoring command"
```

### Task 8: Show Top Scores CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI output test**

Append:

```python
def test_show_top_scores_cli_prints_ranked_rows(monkeypatch, capsys):
    import sys
    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "load_top_scores",
        lambda trade_date, score_version, top_n: [
            {
                "trade_date": trade_date,
                "asset_id": "A",
                "rank": 1,
                "score_total": 88.5,
                "score_version": score_version,
            }
        ],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "show-top-scores",
            "--trade-date",
            "2026-05-08",
            "--score-version",
            "manual_v1",
            "--top-n",
            "10",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.strip() == "top_score|2026-05-08|1|A|88.5|manual_v1"
```

- [ ] **Step 2: Implement CLI dispatch**

In `cli.py`:

```python
    elif args.command == "show-top-scores":
        for row in load_top_scores(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
        ):
            print(
                f"top_score|{row['trade_date']}|{row['rank']}|"
                f"{row['asset_id']}|{row['score_total']}|{row['score_version']}"
            )
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_cli.py -q
```

Expected: all CLI factor tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/cli.py tests/test_factor_cli.py
git commit -m "Add top score display command"
```

---

## Milestone 4: Real DB Smoke Run

### Task 9: Run Factor Build And Score For One Recent Trade Date

**Files:**

- No source files expected unless smoke test exposes a bug.

- [ ] **Step 1: Apply schema**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Expected:

```text
research_schema_applied
```

- [ ] **Step 2: Build factor daily for one known loaded date**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research build-factor-daily --trade-date 2026-05-08 --lookback-bars 130
```

Expected output:

```text
factor_daily_stored|<positive integer>
```

Acceptance: integer is greater than `1000`.

- [ ] **Step 3: Score factor daily**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research score-factor-daily --trade-date 2026-05-08 --score-version manual_v1
```

Expected:

```text
stock_score_daily_stored|<positive integer>
```

Acceptance: integer is greater than `100`.

- [ ] **Step 4: Show Top30**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research show-top-scores --trade-date 2026-05-08 --score-version manual_v1 --top-n 30
```

Expected: 30 lines starting with `top_score|`.

- [ ] **Step 5: Verify DB counts**

Run:

```bash
PGPASSWORD='mqkj1234' /opt/homebrew/opt/libpq/bin/psql -h 192.168.3.187 -p 5432 -U postgres -d postgres -Atc "SELECT 'factor_daily|' || count(*) FROM factor.factor_daily WHERE trade_date = '2026-05-08' UNION ALL SELECT 'stock_score_daily|' || count(*) FROM factor.stock_score_daily WHERE trade_date = '2026-05-08';"
```

Expected:

```text
factor_daily|<positive integer>
stock_score_daily|<positive integer>
```

- [ ] **Step 6: Commit bug fixes only if source changed**

If this smoke run required source changes:

```bash
git add <changed files>
git commit -m "Fix factor scoring smoke run"
```

---

## Milestone 5: Add Sector Factors To Daily Pipeline

### Task 10: Load Industry Membership And Industry Bars For Sector Factors

**Files:**

- Modify: `src/stock_research/factor_pipeline.py`
- Modify: `tests/test_factor_pipeline.py`

- [ ] **Step 1: Write failing sector enrichment test**

Append:

```python
def test_enrich_bars_with_industry_code_uses_point_in_time_membership(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [{"asset_id": "A", "industry_code": "T", "industry_name": "Tech"}]

    monkeypatch.setattr(factor_pipeline, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_pipeline, "fetch_all", fake_fetch_all)

    bars = pd.DataFrame({"trade_date": ["2026-05-08"], "asset_id": ["A"], "close": [10.0]})
    result = factor_pipeline.enrich_bars_with_industry(bars, trade_date="2026-05-08", industry_system="csrc")

    assert result.iloc[0]["industry_code"] == "T"
    assert "core.industry_membership" in calls[0][0]
    assert calls[0][1] == ["csrc", "2026-05-08", "2026-05-08"]
```

- [ ] **Step 2: Implement enrichment**

Add:

```python
def enrich_bars_with_industry(
    bars: pd.DataFrame,
    trade_date: str,
    industry_system: str = "csrc",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT asset_id, industry_code, industry_name
    FROM core.industry_membership
    WHERE industry_system = %s
      AND start_date <= %s
      AND (end_date IS NULL OR end_date > %s)
    """
    with connect(service) as conn:
        rows = fetch_all(conn, sql, [industry_system, trade_date, trade_date])
    membership = pd.DataFrame(rows)
    if membership.empty:
        result = bars.copy()
        result["industry_code"] = None
        result["industry_name"] = None
        return result
    return bars.merge(membership, on="asset_id", how="left")
```

- [ ] **Step 3: Load industry bars**

Add test and function:

```python
def load_industry_bars_for_factor_date(
    trade_date: str,
    lookback_bars: int = 130,
    industry_system: str = "csrc",
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    WITH ranked AS (
        SELECT
            trade_date,
            industry_code,
            industry_name,
            open,
            high,
            low,
            close,
            preclose,
            volume,
            amount,
            row_number() over (partition by industry_code order by trade_date desc) AS row_num
        FROM market.industry_daily_bar
        WHERE trade_date <= %s
          AND industry_system = %s
    )
    SELECT *
    FROM ranked
    WHERE row_num <= %s
    ORDER BY industry_code, trade_date
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [trade_date, industry_system, lookback_bars]))
```

- [ ] **Step 4: Add sector factor rows into `compute_technical_factor_rows`**

After stock bars are enriched and industry bars loaded, call:

```python
from stock_research.factors.sector import compute_sector_factors
```

Use `compute_sector_factors(stock_bars, industry_bars, ret_window=20)` and include `sector_ret_20`, `stock_excess_ret_20`, `sector_up_ratio` from config.

- [ ] **Step 5: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/factor_pipeline.py tests/test_factor_pipeline.py
git commit -m "Add sector factor enrichment"
```

---

## Milestone 6: Factor Evaluation CLI

### Task 11: Load Factor Values And Forward Returns From DB

**Files:**

- Create: `src/stock_research/factor_eval_store.py`
- Create: `tests/test_factor_eval_store.py`

- [ ] **Step 1: Write failing loader test**

Create `tests/test_factor_eval_store.py`:

```python
from stock_research import factor_eval_store


def test_load_factor_eval_inputs_queries_factor_and_label_tables(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        if "factor.factor_daily" in sql:
            return [{"trade_date": "2026-01-01", "asset_id": "A", "factor_value": 1.0}]
        return [{"trade_date": "2026-01-01", "asset_id": "A", "forward_return_5d": 0.02}]

    monkeypatch.setattr(factor_eval_store, "connect", lambda service: _context(object()))
    monkeypatch.setattr(factor_eval_store, "fetch_all", fake_fetch_all)

    factors, returns = factor_eval_store.load_factor_eval_inputs(
        factor_name="ret_20",
        start_date="2026-01-01",
        end_date="2026-02-01",
        horizon=5,
    )

    assert factors.iloc[0]["factor_value"] == 1.0
    assert returns.iloc[0]["forward_return_5d"] == 0.02
    assert len(calls) == 2


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 2: Implement loader**

Create `src/stock_research/factor_eval_store.py`:

```python
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_factor_eval_inputs(
    factor_name: str,
    start_date: str,
    end_date: str,
    horizon: int,
    calc_version: str = "v1",
    label_set: str = "forward_return",
    label_version: str = "v1",
    service: str = SETTINGS.research_service,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_sql = """
    SELECT trade_date, asset_id, factor_value
    FROM factor.factor_daily
    WHERE factor_name = %s
      AND calc_version = %s
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    return_sql = """
    SELECT
        trade_date,
        asset_id,
        label_value AS forward_return_5d
    FROM label_snapshot
    WHERE label_set = %s
      AND label_version = %s
      AND horizon = %s
      AND label_name = 'forward_return'
      AND trade_date BETWEEN %s AND %s
    ORDER BY trade_date, asset_id
    """
    return_col = f"forward_return_{horizon}d"
    with connect(service) as conn:
        factor_rows = fetch_all(conn, factor_sql, [factor_name, calc_version, start_date, end_date])
        return_rows = fetch_all(conn, return_sql, [label_set, label_version, horizon, start_date, end_date])
    returns = pd.DataFrame(return_rows)
    if not returns.empty and return_col != "forward_return_5d":
        returns = returns.rename(columns={"forward_return_5d": return_col})
    return pd.DataFrame(factor_rows), returns
```

- [ ] **Step 3: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_store.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/factor_eval_store.py tests/test_factor_eval_store.py
git commit -m "Add factor evaluation DB loader"
```

### Task 12: Add `eval-factor` CLI

**Files:**

- Modify: `src/stock_research/cli.py`
- Create: `tests/test_factor_eval_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_factor_eval_cli.py`:

```python
from stock_research.cli import build_parser


def test_cli_accepts_eval_factor_command():
    args = build_parser().parse_args(
        [
            "eval-factor",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
            "--horizon",
            "5",
            "--quantiles",
            "5",
            "--top-n",
            "30",
        ]
    )

    assert args.command == "eval-factor"
    assert args.factor_name == "ret_20"
    assert args.horizon == 5
    assert args.quantiles == 5
    assert args.top_n == 30
```

- [ ] **Step 2: Add parser command**

In `cli.py`:

```python
    eval_factor = subparsers.add_parser("eval-factor")
    eval_factor.add_argument("--factor-name", required=True)
    eval_factor.add_argument("--start-date", required=True)
    eval_factor.add_argument("--end-date", required=True)
    eval_factor.add_argument("--horizon", type=int, default=5)
    eval_factor.add_argument("--quantiles", type=int, default=5)
    eval_factor.add_argument("--top-n", type=int, default=30)
```

- [ ] **Step 3: Add dispatch output test**

Append:

```python
def test_eval_factor_cli_prints_summary(monkeypatch, capsys):
    import sys
    import pandas as pd
    import stock_research.cli as cli

    monkeypatch.setattr(
        cli,
        "load_factor_eval_inputs",
        lambda **kwargs: (
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "factor_value": [1.0]}),
            pd.DataFrame({"trade_date": ["2026-01-01"], "asset_id": ["A"], "forward_return_5d": [0.01]}),
        ),
    )
    monkeypatch.setattr(
        cli,
        "generate_factor_eval_report",
        lambda *args, **kwargs: {"ic_summary": {"mean_ic": 0.1, "ic_count": 10}, "rank_ic_summary": {"mean_ic": 0.2}},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "stock-research",
            "eval-factor",
            "--factor-name",
            "ret_20",
            "--start-date",
            "2026-01-01",
            "--end-date",
            "2026-05-08",
        ],
    )

    cli.main()

    assert capsys.readouterr().out.splitlines() == [
        "factor_eval|ret_20|mean_ic|0.1",
        "factor_eval|ret_20|ic_count|10",
        "factor_eval|ret_20|mean_rank_ic|0.2",
    ]
```

- [ ] **Step 4: Implement dispatch**

In `cli.py`, import:

```python
from stock_research.factor_eval.report import generate_factor_eval_report
from stock_research.factor_eval_store import load_factor_eval_inputs
```

Add branch:

```python
    elif args.command == "eval-factor":
        factors, returns = load_factor_eval_inputs(
            factor_name=args.factor_name,
            start_date=args.start_date,
            end_date=args.end_date,
            horizon=args.horizon,
        )
        report = generate_factor_eval_report(
            factors,
            returns,
            factor_name=args.factor_name,
            return_col=f"forward_return_{args.horizon}d",
            quantiles=args.quantiles,
            top_n=args.top_n,
        )
        print(f"factor_eval|{args.factor_name}|mean_ic|{report['ic_summary']['mean_ic']}")
        print(f"factor_eval|{args.factor_name}|ic_count|{report['ic_summary']['ic_count']}")
        print(f"factor_eval|{args.factor_name}|mean_rank_ic|{report['rank_ic_summary']['mean_ic']}")
```

- [ ] **Step 5: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_eval_cli.py tests/test_factor_eval_store.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/cli.py src/stock_research/factor_eval_store.py tests/test_factor_eval_cli.py tests/test_factor_eval_store.py
git commit -m "Add factor evaluation command"
```

---

## Milestone 7: Point-In-Time Finance Factors

### Task 13: Implement Value Factors

**Files:**

- Modify: `src/stock_research/factors/value.py`
- Create: `tests/test_factor_value.py`

- [ ] **Step 1: Write failing value factor test**

Create `tests/test_factor_value.py`:

```python
import pandas as pd
import pytest

from stock_research.factors import value


def test_compute_value_factors_uses_point_in_time_finance_and_share_data():
    prices = pd.DataFrame(
        [{"trade_date": "2026-05-08", "asset_id": "A", "close": 10.0}]
    )
    finance = pd.DataFrame(
        [{"asset_id": "A", "np_parent_ttm": 100.0, "revenue_ttm": 1000.0, "equity_parent": 500.0}]
    )
    shares = pd.DataFrame(
        [{"asset_id": "A", "total_share": 100.0, "float_share": 80.0}]
    )

    result = value.compute_value_factors(prices, finance, shares)

    latest = result.iloc[0]
    assert latest["market_cap"] == pytest.approx(1000.0)
    assert latest["float_market_cap"] == pytest.approx(800.0)
    assert latest["pe_ttm"] == pytest.approx(10.0)
    assert latest["ps_ttm"] == pytest.approx(1.0)
    assert latest["pb"] == pytest.approx(2.0)
```

- [ ] **Step 2: Implement value factors**

In `value.py`, implement:

```python
import pandas as pd


def compute_value_factors(
    prices: pd.DataFrame,
    finance: pd.DataFrame,
    shares: pd.DataFrame,
) -> pd.DataFrame:
    frame = prices.merge(finance, on="asset_id", how="left").merge(shares, on="asset_id", how="left")
    frame["market_cap"] = pd.to_numeric(frame["close"], errors="coerce") * pd.to_numeric(frame["total_share"], errors="coerce")
    frame["float_market_cap"] = pd.to_numeric(frame["close"], errors="coerce") * pd.to_numeric(frame["float_share"], errors="coerce")
    frame["pe_ttm"] = frame["market_cap"] / pd.to_numeric(frame["np_parent_ttm"], errors="coerce").replace(0, pd.NA)
    frame["ps_ttm"] = frame["market_cap"] / pd.to_numeric(frame["revenue_ttm"], errors="coerce").replace(0, pd.NA)
    frame["pb"] = frame["market_cap"] / pd.to_numeric(frame["equity_parent"], errors="coerce").replace(0, pd.NA)
    return frame
```

- [ ] **Step 3: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_value.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/factors/value.py tests/test_factor_value.py
git commit -m "Add point-in-time value factors"
```

### Task 14: Implement Growth And Quality Factors

**Files:**

- Modify: `src/stock_research/factors/growth.py`
- Modify: `src/stock_research/factors/quality.py`
- Create: `tests/test_factor_fundamental.py`

- [ ] **Step 1: Write failing growth/quality tests**

Create:

```python
import pandas as pd
import pytest

from stock_research.factors import growth, quality


def test_compute_growth_factors_uses_report_metrics():
    frame = pd.DataFrame(
        [{"asset_id": "A", "revenue_yoy": 0.2, "np_yoy": 0.3, "deduct_np_yoy": 0.25}]
    )

    result = growth.compute_growth_factors(frame)

    assert result.iloc[0]["revenue_yoy"] == pytest.approx(0.2)
    assert result.iloc[0]["np_parent_yoy"] == pytest.approx(0.3)
    assert result.iloc[0]["deduct_np_yoy"] == pytest.approx(0.25)


def test_compute_quality_factors_uses_report_metrics():
    frame = pd.DataFrame(
        [{"asset_id": "A", "roe": 0.15, "roa": 0.08, "gross_margin": 0.4, "net_margin": 0.1, "debt_ratio": 0.35, "ocf_to_np": 1.2}]
    )

    result = quality.compute_quality_factors(frame)

    assert result.iloc[0]["roe"] == pytest.approx(0.15)
    assert result.iloc[0]["ocf_to_np"] == pytest.approx(1.2)
    assert result.iloc[0]["debt_ratio"] == pytest.approx(0.35)
```

- [ ] **Step 2: Implement modules**

In `growth.py`:

```python
import pandas as pd


def compute_growth_factors(indicators: pd.DataFrame) -> pd.DataFrame:
    result = indicators.copy()
    result["revenue_yoy"] = pd.to_numeric(result["revenue_yoy"], errors="coerce")
    result["np_parent_yoy"] = pd.to_numeric(result["np_yoy"], errors="coerce")
    result["deduct_np_yoy"] = pd.to_numeric(result["deduct_np_yoy"], errors="coerce")
    return result[["asset_id", "revenue_yoy", "np_parent_yoy", "deduct_np_yoy"]]
```

In `quality.py`:

```python
import pandas as pd


def compute_quality_factors(indicators: pd.DataFrame) -> pd.DataFrame:
    result = indicators.copy()
    columns = ["roe", "roa", "gross_margin", "net_margin", "debt_ratio", "ocf_to_np"]
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result[["asset_id"] + columns]
```

- [ ] **Step 3: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_factor_fundamental.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/factors/growth.py src/stock_research/factors/quality.py tests/test_factor_fundamental.py
git commit -m "Add growth and quality factors"
```

### Task 15: Load Point-In-Time Finance Inputs

**Files:**

- Create: `src/stock_research/fundamental_pipeline.py`
- Create: `tests/test_fundamental_pipeline.py`

- [ ] **Step 1: Write failing point-in-time loader test**

Create:

```python
from stock_research import fundamental_pipeline


def test_load_point_in_time_indicators_filters_by_announcement_date(monkeypatch):
    calls = []

    def fake_fetch_all(conn, sql, params=None):
        calls.append((sql, params))
        return [{"asset_id": "A", "roe": 0.15, "announcement_date": "2026-03-20"}]

    monkeypatch.setattr(fundamental_pipeline, "connect", lambda service: _context(object()))
    monkeypatch.setattr(fundamental_pipeline, "fetch_all", fake_fetch_all)

    frame = fundamental_pipeline.load_point_in_time_indicators("2026-05-08")

    assert frame.iloc[0]["asset_id"] == "A"
    assert "announcement_date <= %s" in calls[0][0]
    assert calls[0][1] == ["2026-05-08"]


class _context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 2: Implement loader**

Create `fundamental_pipeline.py`:

```python
import pandas as pd

from stock_research.config import SETTINGS
from stock_research.db import connect, fetch_all


def load_point_in_time_indicators(
    trade_date: str,
    service: str = SETTINGS.research_service,
) -> pd.DataFrame:
    sql = """
    SELECT DISTINCT ON (asset_id)
        asset_id,
        report_period,
        announcement_date,
        roe,
        roa,
        gross_margin,
        net_margin,
        debt_ratio,
        revenue_yoy,
        np_yoy,
        deduct_np_yoy,
        ocf_to_np
    FROM finance.indicator_quarter
    WHERE announcement_date <= %s
    ORDER BY asset_id, announcement_date DESC, report_period DESC
    """
    with connect(service) as conn:
        return pd.DataFrame(fetch_all(conn, sql, [trade_date]))
```

- [ ] **Step 3: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_fundamental_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/fundamental_pipeline.py tests/test_fundamental_pipeline.py
git commit -m "Add point-in-time fundamental loaders"
```

---

## Milestone 8: Daily Pipeline And Reports

### Task 16: Add Daily Factor Scoring Pipeline

**Files:**

- Create: `src/stock_research/daily_pipeline.py`
- Create: `tests/test_daily_pipeline.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing daily pipeline test**

Create `tests/test_daily_pipeline.py`:

```python
from stock_research import daily_pipeline


def test_run_daily_factor_pipeline_runs_build_score_and_topn(monkeypatch):
    calls = []

    monkeypatch.setattr(daily_pipeline, "build_and_store_factor_daily", lambda **kwargs: calls.append("build") or 100)
    monkeypatch.setattr(daily_pipeline, "score_stored_factor_daily", lambda **kwargs: calls.append("score") or 20)
    monkeypatch.setattr(daily_pipeline, "load_top_scores", lambda **kwargs: [{"asset_id": "A", "rank": 1}])

    result = daily_pipeline.run_daily_factor_pipeline("2026-05-08", top_n=10)

    assert calls == ["build", "score"]
    assert result["factor_rows"] == 100
    assert result["score_rows"] == 20
    assert result["top_scores"][0]["asset_id"] == "A"
```

- [ ] **Step 2: Implement pipeline**

Create:

```python
from typing import Any

from stock_research.factor_pipeline import build_and_store_factor_daily
from stock_research.factor_store import load_top_scores, score_stored_factor_daily


def run_daily_factor_pipeline(
    trade_date: str,
    score_version: str = "manual_v1",
    top_n: int = 30,
    lookback_bars: int = 130,
) -> dict[str, Any]:
    factor_rows = build_and_store_factor_daily(
        trade_date=trade_date,
        lookback_bars=lookback_bars,
    )
    score_rows = score_stored_factor_daily(
        trade_date=trade_date,
        score_version=score_version,
    )
    top_scores = load_top_scores(
        trade_date=trade_date,
        score_version=score_version,
        top_n=top_n,
    )
    return {
        "trade_date": trade_date,
        "score_version": score_version,
        "factor_rows": factor_rows,
        "score_rows": score_rows,
        "top_scores": top_scores,
    }
```

- [ ] **Step 3: Add CLI command**

Parser:

```python
    daily_factor_pipeline = subparsers.add_parser("run-daily-factor-pipeline")
    daily_factor_pipeline.add_argument("--trade-date", required=True)
    daily_factor_pipeline.add_argument("--score-version", default="manual_v1")
    daily_factor_pipeline.add_argument("--top-n", type=int, default=30)
    daily_factor_pipeline.add_argument("--lookback-bars", type=int, default=130)
```

Dispatch:

```python
    elif args.command == "run-daily-factor-pipeline":
        result = run_daily_factor_pipeline(
            trade_date=args.trade_date,
            score_version=args.score_version,
            top_n=args.top_n,
            lookback_bars=args.lookback_bars,
        )
        print(f"daily_factor_pipeline|factor_rows|{result['factor_rows']}")
        print(f"daily_factor_pipeline|score_rows|{result['score_rows']}")
        print(f"daily_factor_pipeline|top_scores|{len(result['top_scores'])}")
```

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_daily_pipeline.py tests/test_factor_cli.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/daily_pipeline.py src/stock_research/cli.py tests/test_daily_pipeline.py tests/test_factor_cli.py
git commit -m "Add daily factor scoring pipeline"
```

### Task 17: Generate Daily TopN Report

**Files:**

- Create: `src/stock_research/reports/__init__.py`
- Create: `src/stock_research/reports/daily_topn_report.py`
- Create: `tests/test_daily_topn_report.py`

- [ ] **Step 1: Write failing report test**

Create:

```python
from pathlib import Path

from stock_research.reports.daily_topn_report import write_daily_topn_report


def test_write_daily_topn_report_writes_markdown_and_csv(tmp_path):
    result = write_daily_topn_report(
        trade_date="2026-05-08",
        score_version="manual_v1",
        top_scores=[
            {"rank": 1, "asset_id": "A", "score_total": 88.5},
            {"rank": 2, "asset_id": "B", "score_total": 80.0},
        ],
        output_dir=tmp_path,
    )

    md_path = Path(result["markdown_path"])
    csv_path = Path(result["csv_path"])
    assert md_path.exists()
    assert csv_path.exists()
    assert "2026-05-08 TopN" in md_path.read_text(encoding="utf-8")
    assert "A" in csv_path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Implement report writer**

Create package and module:

```python
from pathlib import Path

import pandas as pd


def write_daily_topn_report(
    trade_date: str,
    score_version: str,
    top_scores: list[dict],
    output_dir: str | Path = "/Users/xiwei/stock_research/reports",
) -> dict[str, str]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    base = f"daily_topn_{trade_date}_{score_version}"
    md_path = path / f"{base}.md"
    csv_path = path / f"{base}.csv"

    frame = pd.DataFrame(top_scores)
    frame.to_csv(csv_path, index=False)

    lines = [f"# {trade_date} TopN", "", f"- Score version: `{score_version}`", ""]
    for row in top_scores:
        lines.append(f"{row['rank']}. {row['asset_id']} score={row['score_total']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"markdown_path": str(md_path), "csv_path": str(csv_path)}
```

- [ ] **Step 3: Integrate into daily pipeline**

In `daily_pipeline.py`, after loading top scores:

```python
from stock_research.reports.daily_topn_report import write_daily_topn_report
```

Add optional argument:

```python
reports_dir: str = "/Users/xiwei/stock_research/reports",
```

Call:

```python
report_paths = write_daily_topn_report(trade_date, score_version, top_scores, reports_dir)
```

Return `report_paths` in result.

- [ ] **Step 4: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_daily_topn_report.py tests/test_daily_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/reports tests/test_daily_topn_report.py src/stock_research/daily_pipeline.py tests/test_daily_pipeline.py
git commit -m "Add daily TopN report"
```

---

## Milestone 9: Real Daily Run And Validation

### Task 18: Run One Full Daily Pipeline

**Files:**

- No source files expected unless validation exposes a bug.

- [ ] **Step 1: Run full unit tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Apply schema**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Expected:

```text
research_schema_applied
```

- [ ] **Step 3: Run daily pipeline**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-factor-pipeline --trade-date 2026-05-08 --score-version manual_v1 --top-n 30 --lookback-bars 130
```

Expected:

```text
daily_factor_pipeline|factor_rows|<positive integer>
daily_factor_pipeline|score_rows|<positive integer>
daily_factor_pipeline|top_scores|30
```

- [ ] **Step 4: Inspect Top30**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research show-top-scores --trade-date 2026-05-08 --score-version manual_v1 --top-n 30
```

Expected: 30 `top_score|...` rows.

- [ ] **Step 5: Verify no generated artifacts are staged**

Run:

```bash
git status --ignored --short
```

Expected: generated files under `reports/` are ignored; source tree is clean unless a bug fix was made.

- [ ] **Step 6: Commit source fixes only if needed**

If source changed:

```bash
git add <changed source and tests>
git commit -m "Fix daily factor pipeline smoke run"
```

- [ ] **Step 7: Push**

Run:

```bash
git push
```

Expected:

```text
main -> main
```

---

## Milestone 10: Connect To V3 Research Without Changing Strategy

### Task 19: Add Stock Score Adapter For Backtest Experiments

**Files:**

- Create: `src/stock_research/score_adapter.py`
- Create: `tests/test_score_adapter.py`

- [ ] **Step 1: Write failing adapter test**

Create:

```python
import pandas as pd

from stock_research.score_adapter import stock_scores_to_retention_candidates


def test_stock_scores_to_retention_candidates_shapes_cache_like_frame():
    scores = pd.DataFrame(
        [
            {"trade_date": "2026-05-08", "asset_id": "A", "rank": 1, "score_total": 90.0},
            {"trade_date": "2026-05-08", "asset_id": "B", "rank": 2, "score_total": 80.0},
        ]
    )

    result = stock_scores_to_retention_candidates(scores)

    assert list(result.columns) == [
        "trade_date",
        "asset_id",
        "rank",
        "score",
        "hard_filter_pass",
        "board_filter_pass",
        "market_filter_pass",
    ]
    assert result.iloc[0]["score"] == 90.0
```

- [ ] **Step 2: Implement adapter**

Create:

```python
import pandas as pd


def stock_scores_to_retention_candidates(scores: pd.DataFrame) -> pd.DataFrame:
    result = scores.copy()
    result = result.rename(columns={"score_total": "score"})
    result["hard_filter_pass"] = True
    result["board_filter_pass"] = True
    result["market_filter_pass"] = True
    return result[
        [
            "trade_date",
            "asset_id",
            "rank",
            "score",
            "hard_filter_pass",
            "board_filter_pass",
            "market_filter_pass",
        ]
    ]
```

- [ ] **Step 3: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_score_adapter.py -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/score_adapter.py tests/test_score_adapter.py
git commit -m "Add stock score adapter for research backtests"
```

This adapter is for research experiments only. It must not change `retention_backtest.py` behavior until a separate strategy experiment plan is approved.

---

## Milestone 11: Final Documentation And Operating Runbook

### Task 20: Add Operator Runbook

**Files:**

- Create: `docs/daily-factor-pipeline-runbook.md`
- Modify: `README.md`

- [ ] **Step 1: Write runbook**

Create `docs/daily-factor-pipeline-runbook.md`:

```markdown
# Daily Factor Pipeline Runbook

## Purpose

Run the local A-share factor scoring pipeline after market data is updated.

## Commands

Apply schema:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research apply-research-schema
```

Build factor daily:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research build-factor-daily --trade-date YYYY-MM-DD --lookback-bars 130
```

Score factor daily:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research score-factor-daily --trade-date YYYY-MM-DD --score-version manual_v1
```

Show Top30:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research show-top-scores --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 30
```

Run full daily pipeline:

```bash
/Users/xiwei/stock_research/.venv/bin/stock-research run-daily-factor-pipeline --trade-date YYYY-MM-DD --score-version manual_v1 --top-n 30 --lookback-bars 130
```

## Expected Outputs

- `factor.factor_daily` has rows for the trade date.
- `factor.stock_score_daily` has ranked rows for the trade date.
- TopN command prints ranked candidates.
- Reports are written under `reports/`, which is ignored by Git.

## Guardrails

- Do not use finance factors unless `announcement_date <= trade_date`.
- Do not treat TopN as a buy signal.
- Do not change V3 strategy thresholds in this pipeline.
```

- [ ] **Step 2: Update README**

Add a short section to `README.md`:

```markdown
## Daily Factor Pipeline

See `docs/daily-factor-pipeline-runbook.md` for the current operator workflow.
The pipeline writes factors to `factor.factor_daily`, scores to `factor.stock_score_daily`, and reports to ignored local `reports/` files.
```

- [ ] **Step 3: Run tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit and push**

```bash
git add README.md docs/daily-factor-pipeline-runbook.md
git commit -m "Document daily factor pipeline"
git push
```

---

## Recommended Execution Order

1. Milestone 1: CLI surface and schema application.
2. Milestone 2: technical factor generation into `factor.factor_daily`.
3. Milestone 3: scoring and TopN from `factor.stock_score_daily`.
4. Milestone 4: one-date real DB smoke run.
5. Milestone 5: sector factor enrichment.
6. Milestone 6: factor evaluation CLI.
7. Milestone 7: point-in-time finance factors.
8. Milestone 8: daily pipeline and report output.
9. Milestone 9: full daily run validation.
10. Milestone 10: research adapter for V3 experiments without changing strategy.
11. Milestone 11: operator runbook.

## Acceptance Criteria

By the end of this plan:

- `stock-research apply-research-schema` creates all current research DB tables.
- `stock-research build-factor-daily --trade-date YYYY-MM-DD` writes technical factor rows to `factor.factor_daily`.
- `stock-research score-factor-daily --trade-date YYYY-MM-DD` writes ranked scores to `factor.stock_score_daily`.
- `stock-research show-top-scores --trade-date YYYY-MM-DD --top-n 30` prints ranked Top30.
- `stock-research eval-factor --factor-name ret_20 ...` prints IC and RankIC summary.
- `stock-research run-daily-factor-pipeline --trade-date YYYY-MM-DD` runs build, score, TopN, and report output.
- Finance factors use point-in-time data only.
- Generated reports and local cache remain untracked by Git.
- Full test suite passes before every commit.

## Commit Policy

- Commit after each task or milestone with a focused message.
- Push after each green milestone.
- Never commit `cache/`, `reports/`, `logs/`, `.venv/`, `.pytest_cache/`, or `.DS_Store`.
- If a real DB smoke run exposes a bug, add a unit test first, then fix.

## Self-Review

Spec coverage:

- CLI commands: Tasks 1, 6, 7, 8, 12, 16.
- Apply schema: Tasks 2 and 18.
- Factor generation: Tasks 3, 4, 5, 6, 10.
- TopN scoring: Tasks 7, 8, 9.
- Finance factors: Tasks 13, 14, 15.
- Factor evaluation CLI: Tasks 11 and 12.
- Daily pipeline and reports: Tasks 16, 17, 18, 20.
- V3 research bridge without strategy changes: Task 19.

Placeholder scan:

- The plan has no `TBD` placeholders.
- Every implementation task includes concrete files, tests, commands, and expected results.

Type consistency:

- Factor rows use `trade_date`, `asset_id`, `factor_name`, `factor_group`, `factor_value`, `calc_version`, `source`, `source_data_version`.
- Score rows use `trade_date`, `asset_id`, `rank`, `score_total`, `score_version`, `score_components`, `calc_version`, `source_data_version`.
- CLI names use kebab-case and service functions use snake_case.
