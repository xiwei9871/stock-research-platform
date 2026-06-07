# Intraday Risk Filter Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-only backtest that compares baseline TopN selection against intraday risk exclude and penalty variants.

**Architecture:** Create a focused `intraday_risk_filter_backtest` module that loads existing scores, prices, and intraday features, builds risk flags, transforms scores into baseline/exclude/penalty variants, and reuses `run_vectorized_topn_backtest`. Add a CLI command that writes CSV and Markdown artifacts; do not write production score tables or cron config.

**Tech Stack:** Python, pandas, PostgreSQL through existing `db` helpers, existing `vectorized_topn_backtest`, argparse CLI, pytest.

---

### Task 1: Risk Flag Construction

**Files:**
- Create: `src/stock_research/intraday_risk_filter_backtest.py`
- Create: `tests/test_intraday_risk_filter_backtest.py`

- [ ] **Step 1: Write the failing test**

Add this to `tests/test_intraday_risk_filter_backtest.py`:

```python
import pandas as pd

from stock_research.intraday_risk_filter_backtest import build_intraday_risk_flags


def test_build_intraday_risk_flags_uses_cross_sectional_quantiles():
    features = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "feature_name": "intraday_volatility_5min", "feature_value": 0.01},
            {"trade_date": "2026-01-02", "asset_id": "B", "feature_name": "intraday_volatility_5min", "feature_value": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "C", "feature_name": "intraday_volatility_5min", "feature_value": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "D", "feature_name": "intraday_volatility_5min", "feature_value": 0.04},
            {"trade_date": "2026-01-02", "asset_id": "E", "feature_name": "intraday_volatility_5min", "feature_value": 0.05},
            {"trade_date": "2026-01-02", "asset_id": "E", "feature_name": "last_30m_return", "feature_value": -0.05},
            {"trade_date": "2026-01-02", "asset_id": "A", "feature_name": "last_30m_return", "feature_value": 0.03},
            {"trade_date": "2026-01-02", "asset_id": "B", "feature_name": "last_30m_return", "feature_value": 0.02},
            {"trade_date": "2026-01-02", "asset_id": "C", "feature_name": "last_30m_return", "feature_value": 0.01},
            {"trade_date": "2026-01-02", "asset_id": "D", "feature_name": "last_30m_return", "feature_value": 0.00},
        ]
    )

    flags = build_intraday_risk_flags(features, quantile=0.2)

    row_e = flags.loc[flags["asset_id"].eq("E")].iloc[0]
    assert bool(row_e["high_intraday_volatility"]) is True
    assert bool(row_e["weak_last_30m"]) is True
    assert int(row_e["intraday_risk_flag_count"]) == 2
    assert row_e["intraday_risk_level"] == "high"
    row_a = flags.loc[flags["asset_id"].eq("A")].iloc[0]
    assert row_a["intraday_risk_level"] == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_filter_backtest.py::test_build_intraday_risk_flags_uses_cross_sectional_quantiles
```

Expected: FAIL with `ModuleNotFoundError` or missing `build_intraday_risk_flags`.

- [ ] **Step 3: Implement minimal risk flag construction**

Create `src/stock_research/intraday_risk_filter_backtest.py` with:

```python
from __future__ import annotations

import pandas as pd

RISK_FEATURES = [
    "intraday_volatility_5min",
    "amount_front_1h_ratio",
    "last_30m_return",
    "afternoon_return",
    "close_to_vwap",
]

RISK_FLAG_MAP = {
    "intraday_volatility_5min": ("high_intraday_volatility", "high"),
    "amount_front_1h_ratio": ("high_front_loaded_amount", "high"),
    "last_30m_return": ("weak_last_30m", "low"),
    "afternoon_return": ("weak_afternoon", "low"),
    "close_to_vwap": ("weak_close_to_vwap", "low"),
}


def build_intraday_risk_flags(features: pd.DataFrame, quantile: float = 0.2) -> pd.DataFrame:
    columns = [
        "trade_date",
        "asset_id",
        "high_intraday_volatility",
        "high_front_loaded_amount",
        "weak_last_30m",
        "weak_afternoon",
        "weak_close_to_vwap",
        "intraday_risk_flag_count",
        "intraday_risk_level",
    ]
    if features.empty:
        return pd.DataFrame(columns=columns)

    frame = features.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["feature_value"] = pd.to_numeric(frame["feature_value"], errors="coerce")
    wide = (
        frame.pivot_table(
            index=["trade_date", "asset_id"],
            columns="feature_name",
            values="feature_value",
            aggfunc="last",
        )
        .reset_index()
        .rename_axis(None, axis=1)
    )
    for flag_name, _direction in RISK_FLAG_MAP.values():
        wide[flag_name] = False
    for feature_name, (flag_name, direction) in RISK_FLAG_MAP.items():
        if feature_name not in wide.columns:
            continue
        if direction == "high":
            thresholds = wide.groupby("trade_date")[feature_name].transform(lambda s: s.quantile(1.0 - quantile))
            wide[flag_name] = wide[feature_name] >= thresholds
        else:
            thresholds = wide.groupby("trade_date")[feature_name].transform(lambda s: s.quantile(quantile))
            wide[flag_name] = wide[feature_name] <= thresholds
        wide[flag_name] = wide[flag_name].fillna(False)
    flag_cols = [item[0] for item in RISK_FLAG_MAP.values()]
    wide["intraday_risk_flag_count"] = wide[flag_cols].sum(axis=1).astype(int)
    wide["intraday_risk_level"] = "none"
    wide.loc[wide["intraday_risk_flag_count"].eq(1), "intraday_risk_level"] = "watch"
    wide.loc[wide["intraday_risk_flag_count"].ge(2), "intraday_risk_level"] = "high"
    return wide[columns].sort_values(["trade_date", "asset_id"]).reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_filter_backtest.py::test_build_intraday_risk_flags_uses_cross_sectional_quantiles
```

Expected: PASS.

### Task 2: Score Variants

**Files:**
- Modify: `src/stock_research/intraday_risk_filter_backtest.py`
- Modify: `tests/test_intraday_risk_filter_backtest.py`

- [ ] **Step 1: Write the failing tests**

Append:

```python
from stock_research.intraday_risk_filter_backtest import build_score_variants


def _score_rows():
    return pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "rank": 1, "score_total": 100.0},
            {"trade_date": "2026-01-02", "asset_id": "B", "rank": 2, "score_total": 95.0},
            {"trade_date": "2026-01-02", "asset_id": "C", "rank": 3, "score_total": 90.0},
            {"trade_date": "2026-01-02", "asset_id": "D", "rank": 4, "score_total": 85.0},
        ]
    )


def test_build_score_variants_excludes_high_risk_assets():
    flags = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "intraday_risk_level": "high", "intraday_risk_flag_count": 2},
            {"trade_date": "2026-01-02", "asset_id": "B", "intraday_risk_level": "none", "intraday_risk_flag_count": 0},
            {"trade_date": "2026-01-02", "asset_id": "C", "intraday_risk_level": "none", "intraday_risk_flag_count": 0},
            {"trade_date": "2026-01-02", "asset_id": "D", "intraday_risk_level": "none", "intraday_risk_flag_count": 0},
        ]
    )

    variants = build_score_variants(_score_rows(), flags)
    exclude = variants["exclude_high_risk"]

    assert exclude["asset_id"].tolist() == ["B", "C", "D"]
    assert exclude["rank"].tolist() == [1, 2, 3]
    assert exclude["score_total"].tolist() == [95.0, 90.0, 85.0]


def test_build_score_variants_penalizes_and_reranks_risk_assets():
    flags = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "asset_id": "A", "intraday_risk_level": "high", "intraday_risk_flag_count": 2},
            {"trade_date": "2026-01-02", "asset_id": "B", "intraday_risk_level": "watch", "intraday_risk_flag_count": 1},
            {"trade_date": "2026-01-02", "asset_id": "C", "intraday_risk_level": "none", "intraday_risk_flag_count": 0},
            {"trade_date": "2026-01-02", "asset_id": "D", "intraday_risk_level": "none", "intraday_risk_flag_count": 0},
        ]
    )

    variants = build_score_variants(_score_rows(), flags, watch_penalty=5.0, high_penalty=15.0)
    penalty = variants["penalty_high_risk"]

    assert penalty["asset_id"].tolist() == ["B", "A", "C", "D"]
    assert penalty["score_total"].tolist() == [90.0, 85.0, 90.0, 85.0]
    assert penalty["rank"].tolist() == [1, 2, 3, 4]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_filter_backtest.py::test_build_score_variants_excludes_high_risk_assets tests/test_intraday_risk_filter_backtest.py::test_build_score_variants_penalizes_and_reranks_risk_assets
```

Expected: FAIL with missing `build_score_variants`.

- [ ] **Step 3: Implement score variant construction**

Append to `src/stock_research/intraday_risk_filter_backtest.py`:

```python
def build_score_variants(
    scores: pd.DataFrame,
    flags: pd.DataFrame,
    *,
    watch_penalty: float = 5.0,
    high_penalty: float = 15.0,
) -> dict[str, pd.DataFrame]:
    baseline = _normalize_scores(scores)
    flagged = _attach_flags(baseline, flags)
    exclude = flagged[~flagged["intraday_risk_level"].eq("high")].copy()
    exclude = _rerank_scores(exclude)
    penalty = flagged.copy()
    penalty["score_total"] = penalty["score_total"] - penalty["intraday_risk_level"].map(
        {"none": 0.0, "watch": watch_penalty, "high": high_penalty}
    ).fillna(0.0)
    penalty = _rerank_scores(penalty)
    return {
        "baseline_topn": baseline,
        "exclude_high_risk": exclude[["trade_date", "asset_id", "rank", "score_total"]],
        "penalty_high_risk": penalty[["trade_date", "asset_id", "rank", "score_total"]],
    }


def _normalize_scores(scores: pd.DataFrame) -> pd.DataFrame:
    frame = scores.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["asset_id"] = frame["asset_id"].astype(str)
    frame["rank"] = pd.to_numeric(frame["rank"], errors="coerce")
    frame["score_total"] = pd.to_numeric(frame["score_total"], errors="coerce")
    return frame[["trade_date", "asset_id", "rank", "score_total"]].dropna(subset=["trade_date", "asset_id", "score_total"])


def _attach_flags(scores: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    if flags.empty:
        result = scores.copy()
        result["intraday_risk_level"] = "none"
        result["intraday_risk_flag_count"] = 0
        return result
    flag_cols = ["trade_date", "asset_id", "intraday_risk_level", "intraday_risk_flag_count"]
    normalized_flags = flags[flag_cols].copy()
    normalized_flags["trade_date"] = normalized_flags["trade_date"].astype(str).str[:10]
    normalized_flags["asset_id"] = normalized_flags["asset_id"].astype(str)
    result = scores.merge(normalized_flags, on=["trade_date", "asset_id"], how="left")
    result["intraday_risk_level"] = result["intraday_risk_level"].fillna("none")
    result["intraday_risk_flag_count"] = pd.to_numeric(result["intraday_risk_flag_count"], errors="coerce").fillna(0).astype(int)
    return result


def _rerank_scores(scores: pd.DataFrame) -> pd.DataFrame:
    ranked = scores.sort_values(["trade_date", "score_total", "asset_id"], ascending=[True, False, True]).copy()
    ranked["rank"] = ranked.groupby("trade_date").cumcount() + 1
    return ranked.reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_filter_backtest.py
```

Expected: PASS.

### Task 3: Backtest Runner And Report

**Files:**
- Modify: `src/stock_research/intraday_risk_filter_backtest.py`
- Modify: `tests/test_intraday_risk_filter_backtest.py`

- [ ] **Step 1: Write failing tests** for:
  - `classify_variant_recommendation`
  - `summarize_variant_backtests`
  - `write_intraday_risk_filter_report`

Use small in-memory equity curves and positions. Expected recommendation examples:

```python
assert classify_variant_recommendation(
    baseline_total_return=0.10,
    variant_total_return=0.09,
    baseline_max_drawdown=-0.12,
    variant_max_drawdown=-0.10,
) == "promote_for_shadow_review"

assert classify_variant_recommendation(
    baseline_total_return=0.10,
    variant_total_return=0.05,
    baseline_max_drawdown=-0.12,
    variant_max_drawdown=-0.10,
) == "watch_only"

assert classify_variant_recommendation(
    baseline_total_return=0.10,
    variant_total_return=0.12,
    baseline_max_drawdown=-0.12,
    variant_max_drawdown=-0.13,
) == "reject"
```

- [ ] **Step 2: Run tests and confirm missing functions**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_filter_backtest.py
```

Expected: FAIL on missing report/backtest functions.

- [ ] **Step 3: Implement runner and report**

Implement:

- `classify_variant_recommendation(...) -> str`
- `summarize_variant_backtests(backtests, flags, top_n_values) -> pd.DataFrame`
- `format_intraday_risk_filter_report(summary) -> str`
- `write_intraday_risk_filter_report(result, output_dir) -> dict[str, str]`
- `run_intraday_risk_filter_backtest_from_frames(scores, prices, features, start_date, end_date, top_n_values, ...) -> dict`

The runner must:

1. call `build_intraday_risk_flags`
2. call `build_score_variants`
3. for each `top_n` and variant, call `run_vectorized_topn_backtest`
4. concatenate positions/trades with `top_n` and `variant_name`
5. produce summary and report artifacts

- [ ] **Step 4: Run tests until green**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_filter_backtest.py
```

Expected: PASS.

### Task 4: Database Loaders And CLI

**Files:**
- Modify: `src/stock_research/intraday_risk_filter_backtest.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_factor_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Add parser and dispatch tests for:

```bash
stock-research intraday-risk-filter-backtest \
  --start-date 2025-01-02 \
  --end-date 2026-06-05 \
  --score-version manual_v1 \
  --top-n-values 10,20 \
  --output-dir outputs/research/intraday_risk_filter/2026-06-06_full
```

Expected dispatch call:

```python
run_intraday_risk_filter_backtest(
    start_date="2025-01-02",
    end_date="2026-06-05",
    score_version="manual_v1",
    top_n_values=[10, 20],
    output_dir="outputs/research/intraday_risk_filter/2026-06-06_full",
    rebalance_frequency="daily",
    transaction_cost_bps=20.0,
    score_adjust_type="hfq",
    intraday_freq="5min",
    intraday_adjust_type="raw",
)
```

- [ ] **Step 2: Run CLI tests and confirm failure**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_intraday_risk_filter_backtest_command tests/test_factor_cli.py::test_intraday_risk_filter_backtest_cli_dispatches
```

Expected: FAIL due missing parser/import.

- [ ] **Step 3: Implement database loaders and CLI**

Add to module:

- `load_intraday_risk_filter_inputs(...) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]`
- `run_intraday_risk_filter_backtest(...) -> dict`

Use SQL:

- scores from `factor.stock_score_daily`
- prices from `market_daily_bar`
- intraday features from `factor.stock_intraday_features_daily` filtered to `RISK_FEATURES`

In `src/stock_research/cli.py`:

- import `run_intraday_risk_filter_backtest`
- add parser `intraday-risk-filter-backtest`
- dispatch and print:
  - `intraday_risk_filter_backtest|summary|...`
  - `intraday_risk_filter_backtest|report|...`
  - `intraday_risk_filter_backtest|rows|...`

- [ ] **Step 4: Run CLI tests until green**

Run:

```bash
./.venv/bin/pytest -q tests/test_factor_cli.py::test_cli_accepts_intraday_risk_filter_backtest_command tests/test_factor_cli.py::test_intraday_risk_filter_backtest_cli_dispatches
```

Expected: PASS.

### Task 5: Real Data Verification

**Files:**
- Output only under `outputs/research/intraday_risk_filter/`

- [ ] **Step 1: Run focused tests**

Run:

```bash
./.venv/bin/pytest -q tests/test_intraday_risk_filter_backtest.py tests/test_factor_cli.py tests/test_intraday_factor_eval.py tests/test_intraday_features.py
```

Expected: PASS.

- [ ] **Step 2: Run real backtest**

Run:

```bash
./.venv/bin/python -m stock_research.cli intraday-risk-filter-backtest \
  --start-date 2025-01-02 \
  --end-date 2026-06-05 \
  --score-version manual_v1 \
  --top-n-values 10,20 \
  --rebalance-frequency daily \
  --transaction-cost-bps 20 \
  --score-adjust-type hfq \
  --intraday-freq 5min \
  --intraday-adjust-type raw \
  --output-dir outputs/research/intraday_risk_filter/2026-06-06_full
```

Expected:

- command exits 0
- summary/report paths print
- summary has 6 rows: 2 TopN values × 3 variants

- [ ] **Step 3: Inspect results**

Run:

```bash
./.venv/bin/python - <<'PY'
import pandas as pd
path = "outputs/research/intraday_risk_filter/2026-06-06_full/intraday_risk_filter_variant_summary.csv"
df = pd.read_csv(path)
print(df[[
    "top_n",
    "variant_name",
    "recommendation",
    "total_return",
    "max_drawdown",
    "sharpe_ratio",
    "total_return_delta_vs_baseline",
    "max_drawdown_delta_vs_baseline",
]].to_string(index=False))
PY
```

Report whether each variant is `promote_for_shadow_review`, `watch_only`, or `reject`.

### Self-Review

- Spec coverage: risk flags, exclude/penalty variants, vectorized backtest reuse, artifacts, recommendations, and real range verification are covered.
- Placeholder scan: no `TBD`, `TODO`, or vague implementation instructions are present.
- Type consistency: `trade_date`, `asset_id`, `rank`, `score_total`, `variant_name`, and `top_n` are used consistently across tests, implementation, and outputs.
