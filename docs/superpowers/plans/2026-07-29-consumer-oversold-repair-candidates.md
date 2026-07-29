# Consumer Oversold Repair Candidates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a PIT-safe weekly A-share consumer oversold research pipeline that produces separate expected-repair and early-validation candidate lists, each capped at 20 names, plus full scores, exclusions, coverage audit, and a review report.

**Architecture:** Implement a focused `stock_research.consumer_oversold` package with pure frame-based universe, feature, evidence, scoring, and reporting units. A thin loader layer reads existing market, industry, finance, event, and factor tables; a pipeline composes those frames and writes deterministic artifacts. Because the repository does not yet have a complete normalized analyst-consensus history, the first version uses a source-dated evidence CSV for forward repair claims and refuses to promote rows whose required evidence or hard-risk review is unknown.

**Tech Stack:** Python 3.12, pandas, numpy, psycopg/PostgreSQL, existing `stock_research` services, pytest, Markdown/CSV/JSON artifacts.

---

## Scope and file map

Create these focused modules:

- `src/stock_research/consumer_oversold/__init__.py`: public exports only.
- `src/stock_research/consumer_oversold/contracts.py`: constants, required columns, dataclasses, and configuration validation.
- `src/stock_research/consumer_oversold/universe.py`: broad-consumer membership and deterministic hard market-status filters.
- `src/stock_research/consumer_oversold/features.py`: 6–12 month oversold, valuation, fundamental-gap, balance-sheet, and already-priced features from frames.
- `src/stock_research/consumer_oversold/evidence.py`: source-dated repair evidence validation and repair-bucket classification inputs.
- `src/stock_research/consumer_oversold/scoring.py`: gates, component scores, bucket assignment, de-duplication, and Top 20 ranking.
- `src/stock_research/consumer_oversold/loaders.py`: database reads using existing PIT and market tables.
- `src/stock_research/consumer_oversold/reporting.py`: six required output artifacts and Markdown rendering.
- `src/stock_research/consumer_oversold/pipeline.py`: orchestration entry point.
- `config/consumer_oversold_industry_rules_v1.csv`: auditable industry pattern rules.
- `config/consumer_oversold_asset_overrides_v1.csv`: explicit include/exclude overrides for direct-to-consumer brands or false positives.
- `config/consumer_oversold_repair_evidence_template_v1.csv`: operator evidence schema with no live recommendations embedded.
- `src/stock_research/cli.py`: register and dispatch `consumer-oversold-weekly`.

Create these tests:

- `tests/test_consumer_oversold_contracts.py`
- `tests/test_consumer_oversold_universe.py`
- `tests/test_consumer_oversold_features.py`
- `tests/test_consumer_oversold_fundamentals.py`
- `tests/test_consumer_oversold_evidence.py`
- `tests/test_consumer_oversold_scoring.py`
- `tests/test_consumer_oversold_reporting.py`
- `tests/test_consumer_oversold_loaders.py`
- `tests/test_consumer_oversold_pipeline.py`
- `tests/test_consumer_oversold_cli.py`
- `tests/test_consumer_oversold_evaluation.py`

The first implementation does not add dashboard UI, automated trade advice, portfolio sizing, or a machine-learning ranker.

### Task 1: Define configuration and artifact contracts

**Files:**
- Create: `src/stock_research/consumer_oversold/__init__.py`
- Create: `src/stock_research/consumer_oversold/contracts.py`
- Create: `tests/test_consumer_oversold_contracts.py`

- [ ] **Step 1: Write the failing contract tests**

```python
from stock_research.consumer_oversold.contracts import (
    ConsumerOversoldConfig,
    EXPECTED_REPAIR,
    EARLY_VALIDATION,
    validate_trade_date,
)


def test_default_config_matches_approved_design():
    config = ConsumerOversoldConfig(trade_date="2026-07-29")
    assert config.lookback_6m_bars == 126
    assert config.lookback_12m_bars == 252
    assert config.min_6m_return == -0.20
    assert config.min_12m_drawdown == -0.30
    assert config.min_relative_return == -0.10
    assert config.min_oversold_score == 60.0
    assert config.min_base_upside == 0.25
    assert config.max_per_bucket == 20
    assert {EXPECTED_REPAIR, EARLY_VALIDATION} == {
        "expected_repair",
        "early_validation",
    }


def test_trade_date_must_be_real_iso_date():
    assert validate_trade_date("2026-07-29") == "2026-07-29"
    for invalid in ["20260729", "2026-02-30", ""]:
        try:
            validate_trade_date(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted invalid date: {invalid}")
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_contracts.py -q
```

Expected: collection fails because `stock_research.consumer_oversold` does not exist.

- [ ] **Step 3: Implement the contracts**

`contracts.py` must define immutable configuration and stable artifact names:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

EXPECTED_REPAIR = "expected_repair"
EARLY_VALIDATION = "early_validation"
REPAIR_BUCKETS = (EXPECTED_REPAIR, EARLY_VALIDATION)

OUTPUT_FILENAMES = {
    "expected": "consumer_oversold_expected_repair_top20.csv",
    "early": "consumer_oversold_early_validation_top20.csv",
    "scores": "consumer_oversold_full_scores.csv",
    "exclusions": "consumer_oversold_exclusions.csv",
    "coverage": "consumer_oversold_data_coverage_audit.json",
    "report": "consumer_oversold_weekly_report.md",
}


def validate_trade_date(value: str) -> str:
    parsed = date.fromisoformat(str(value))
    normalized = parsed.isoformat()
    if normalized != value:
        raise ValueError("trade_date must use YYYY-MM-DD")
    return normalized


@dataclass(frozen=True)
class ConsumerOversoldConfig:
    trade_date: str
    lookback_6m_bars: int = 126
    lookback_12m_bars: int = 252
    valuation_lookback_years: int = 5
    min_listed_days: int = 365
    min_avg_turnover_amount: float = 30_000_000.0
    min_6m_return: float = -0.20
    min_12m_drawdown: float = -0.30
    min_relative_return: float = -0.10
    min_oversold_score: float = 60.0
    min_base_upside: float = 0.25
    max_per_bucket: int = 20
    max_priced_in_penalty: float = 20.0

    def __post_init__(self) -> None:
        validate_trade_date(self.trade_date)
        if self.max_per_bucket < 1 or self.max_per_bucket > 20:
            raise ValueError("max_per_bucket must be between 1 and 20")
```

`__init__.py` exports `ConsumerOversoldConfig`, `EXPECTED_REPAIR`, and `EARLY_VALIDATION`.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 1 pytest command. Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
rtk git add src/stock_research/consumer_oversold tests/test_consumer_oversold_contracts.py
rtk git commit -m "feat: define consumer oversold contracts"
```

### Task 2: Build the broad-consumer universe and deterministic exclusions

**Files:**
- Create: `config/consumer_oversold_industry_rules_v1.csv`
- Create: `config/consumer_oversold_asset_overrides_v1.csv`
- Create: `src/stock_research/consumer_oversold/universe.py`
- Create: `tests/test_consumer_oversold_universe.py`

- [ ] **Step 1: Add failing universe tests**

Use frame fixtures containing China Tourism Group Duty Free, a supermarket, an auto OEM, an auto-parts company, an ST stock, and a newly listed stock. Assert:

```python
def test_universe_includes_terminal_consumer_and_excludes_auto_parts(sample_frames):
    result = build_consumer_universe_from_frames(**sample_frames)
    included = set(result.loc[result["included"], "stock_code"])
    excluded = result.set_index("stock_code")["exclude_reasons"].to_dict()
    assert {"601888", "000759", "601127", "600418"} <= included
    assert "000887" not in included
    assert "not_terminal_consumer" in excluded["000887"]


def test_universe_applies_market_status_and_override_rules(sample_frames):
    result = build_consumer_universe_from_frames(**sample_frames)
    by_code = result.set_index("stock_code")
    assert "st_or_delisting_risk" in by_code.loc["600001", "exclude_reasons"]
    assert "listed_less_than_365_days" in by_code.loc["600002", "exclude_reasons"]
    assert "low_liquidity" in by_code.loc["600003", "exclude_reasons"]
```

- [ ] **Step 2: Run the universe tests and verify RED**

Expected: import failure for `consumer_oversold.universe`.

- [ ] **Step 3: Add auditable CSV rules**

`consumer_oversold_industry_rules_v1.csv` columns:

```text
priority,industry_system,industry_name_pattern,consumer_subindustry,action,reason
```

Populate explicit include patterns for food and beverage, household appliances, retail, duty free, tourism, hotel, restaurant, textile/apparel, beauty care, home products, leisure services, and passenger-vehicle/complete-vehicle industries. Add higher-priority exclude patterns for auto parts, materials, equipment, OEM manufacturing, finance, and real estate.

Use this initial rule content, with regular-expression matching against normalized industry names:

```csv
priority,industry_system,industry_name_pattern,consumer_subindustry,action,reason
10,*,汽车零部件|零部件|汽车电子|轮胎|车用材料,,exclude,not_terminal_consumer
11,*,材料|设备|工业机械|代工|OEM,,exclude,not_terminal_consumer
12,*,银行|证券|保险|房地产,,exclude,not_terminal_consumer
100,*,白酒|啤酒|饮料|乳品|食品|调味品,food_beverage,include,terminal_consumer_industry
110,*,家用电器|白色家电|厨卫电器|小家电,home_appliance,include,terminal_consumer_industry
120,*,商超|百货|零售|免税|专业连锁,retail_duty_free,include,terminal_consumer_industry
130,*,旅游|景区|酒店|餐饮|休闲服务,tourism_hospitality,include,terminal_consumer_industry
140,*,纺织服装|服饰|鞋帽,textile_apparel,include,terminal_consumer_industry
150,*,美容护理|化妆品|个人护理,beauty_care,include,terminal_consumer_industry
160,*,家居|家具|文娱|文体用品,home_leisure,include,terminal_consumer_industry
170,*,乘用车|商用车|汽车整车|整车,auto_oem,include,terminal_consumer_industry
```

`consumer_oversold_asset_overrides_v1.csv` columns:

```text
stock_code,action,consumer_subindustry,reason,effective_from,effective_to
```

Keep the file header-only initially. Overrides are an audit mechanism, not a seed list.

- [ ] **Step 4: Implement universe classification**

Expose:

```python
def build_consumer_universe_from_frames(
    *,
    assets: pd.DataFrame,
    statuses: pd.DataFrame,
    liquidity: pd.DataFrame,
    industries: pd.DataFrame,
    industry_rules: pd.DataFrame,
    asset_overrides: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> pd.DataFrame:
    """Return one row per asset with included, subindustry, and reason lists."""
```

Rules are evaluated in ascending `priority`; an active asset override takes precedence over industry pattern matching. Market gates then add these exact exclusion codes: `st_or_delisting_risk`, `suspended`, `listed_less_than_365_days`, `low_liquidity`, `missing_industry`, and `not_terminal_consumer`.

The returned frame must retain excluded rows and serialize `include_reasons` and `exclude_reasons` as `|`-joined stable sorted strings.

- [ ] **Step 5: Run tests and commit**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_universe.py -q
rtk git diff --check
```

Expected: pass, then commit:

```bash
rtk git add config/consumer_oversold_* src/stock_research/consumer_oversold/universe.py tests/test_consumer_oversold_universe.py
rtk git commit -m "feat: build consumer oversold universe"
```

### Task 3: Compute 6–12 month oversold and already-priced features

**Files:**
- Create: `src/stock_research/consumer_oversold/features.py`
- Create: `tests/test_consumer_oversold_features.py`

- [ ] **Step 1: Write failing price-feature tests**

Construct 252 bars for two assets and their subindustry peers. Assert exact formulas:

```python
def test_price_features_use_six_and_twelve_month_history():
    result = compute_price_features(bars, membership, trade_date="2026-07-29")
    row = result.set_index("asset_id").loc["A"]
    assert row["return_6m"] == pytest.approx(60.0 / 100.0 - 1.0)
    assert row["max_drawdown_12m"] == pytest.approx(60.0 / 120.0 - 1.0)
    assert row["relative_return_6m"] == pytest.approx(row["return_6m"] - row["industry_return_6m"])
    assert row["distance_ma120"] == pytest.approx(60.0 / row["ma120"] - 1.0)
    assert row["distance_ma250"] == pytest.approx(60.0 / row["ma250"] - 1.0)


def test_already_priced_penalty_uses_rebound_relative_strength_and_valuation():
    row = compute_already_priced_features(price_row, valuation_row)
    assert row["rebound_from_low"] == pytest.approx(0.30)
    assert row["priced_in_penalty"] == 20.0
```

- [ ] **Step 2: Verify RED**

Run the feature test file. Expected: missing function failures.

- [ ] **Step 3: Implement price features and scores**

Implement:

```python
def compute_price_features(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    cutoff = pd.Timestamp(trade_date)
    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.loc[frame["trade_date"].le(cutoff)].sort_values(["asset_id", "trade_date"])
    rows = []
    for asset_id, history in frame.groupby("asset_id", sort=True):
        history = history.tail(252)
        if len(history) < 126:
            continue
        close = history["close"]
        latest = float(close.iloc[-1])
        six_month_start = float(close.iloc[-126])
        low_60 = float(close.tail(60).min())
        rows.append({
            "asset_id": str(asset_id),
            "latest_close": latest,
            "return_6m": latest / six_month_start - 1.0,
            "max_drawdown_12m": latest / float(close.max()) - 1.0,
            "rebound_from_low": latest / low_60 - 1.0,
            "ma120": float(close.tail(120).mean()),
            "ma250": float(close.tail(250).mean()),
        })
    result = pd.DataFrame(rows).merge(membership, on="asset_id", how="left")
    result["industry_return_6m"] = result.groupby("consumer_subindustry")["return_6m"].transform("mean")
    result["industry_peer_count"] = result.groupby("consumer_subindustry")["asset_id"].transform("count")
    result["relative_return_6m"] = result["return_6m"] - result["industry_return_6m"]
    result.loc[result["industry_peer_count"].lt(3), ["industry_return_6m", "relative_return_6m"]] = pd.NA
    result["distance_ma120"] = result["latest_close"] / result["ma120"] - 1.0
    result["distance_ma250"] = result["latest_close"] / result["ma250"] - 1.0
    return result


def compute_oversold_score(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["drawdown_percentile"] * 30.0
        + frame["return_6m_percentile"] * 20.0
        + frame["relative_return_percentile"] * 20.0
        + frame["valuation_depression_percentile"] * 20.0
        + frame["ma_distance_percentile"] * 10.0
    ).clip(0.0, 100.0)
```

For negative-return factors, convert the deepest decline to percentile 1.0 within the eligible consumer universe. Compute industry returns as equal-weight asset returns within `consumer_subindustry`; require at least three peers, otherwise set `industry_return_6m` and `relative_return_6m` missing and record `relative_return_coverage=false`.

Implement the priced-in penalty deterministically:

```python
penalty = (
    6.0 * (rebound_from_low >= 0.25)
    + 4.0 * (relative_return_60d >= 0.10)
    + 5.0 * (valuation_percentile >= 0.50)
    + 5.0 * (evidence_revision_state == "broadly_priced")
)
```

Cap the result at 20.

- [ ] **Step 4: Run tests and commit**

Run feature tests, then:

```bash
rtk git add src/stock_research/consumer_oversold/features.py tests/test_consumer_oversold_features.py
rtk git commit -m "feat: compute consumer oversold price features"
```

### Task 4: Add PIT fundamentals, valuation scenarios, and hard-risk features

**Files:**
- Modify: `src/stock_research/consumer_oversold/features.py`
- Create: `tests/test_consumer_oversold_fundamentals.py`

- [ ] **Step 1: Write failing PIT and valuation tests**

Tests must prove that rows announced after the trade date are ignored and that negative PE is never used:

```python
def test_fundamental_features_ignore_future_announcements():
    result = compute_fundamental_features(finance_rows, trade_date="2026-07-29")
    row = result.set_index("asset_id").loc["A"]
    assert row["latest_announcement_date"] == "2026-07-20"
    assert row["latest_net_margin"] == pytest.approx(0.03)


def test_valuation_scenarios_use_ps_for_loss_making_company():
    result = compute_valuation_features(current, history, fundamentals)
    row = result.iloc[0]
    assert row["valuation_method"] == "ps_normalized_margin"
    assert pd.isna(row["pe_ttm"])
    assert row["base_upside"] == pytest.approx(0.30)
```

Add hard-risk cases for negative parent equity, debt pressure, two-period OCF deterioration, and unknown manual audit/pledge review.

- [ ] **Step 2: Verify RED**

Run the new test file. Expected: missing function or column failures.

- [ ] **Step 3: Implement fundamental history features**

Expose:

```python
def compute_fundamental_features(
    finance_rows: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Use only announcement_date <= trade_date and return latest plus history gaps."""


def compute_valuation_features(
    current_valuation: pd.DataFrame,
    valuation_history: pd.DataFrame,
    fundamentals: pd.DataFrame,
) -> pd.DataFrame:
    """Return current percentile and pessimistic/base/optimistic upside."""
```

For each asset, use the latest eight distinct report periods available by the trade date. Calculate latest values, prior-period deltas, and median normal levels for revenue growth, net-profit growth, gross margin, net margin, ROE, OCF/net profit, debt ratio, and parent equity.

The three scenarios use 0%, 65%, and 80% closure of the gap between current operating level and the median normal level. Stable positive earners prefer PE/FCF; retail, tourism, duty free, and loss-making rows use EV/EBITDA or PS as available. A method can be selected only if its denominator is positive and present.

Apply these deterministic scenario formulas:

```python
scenario_margin = current_margin + closure * (normal_margin - current_margin)
scenario_revenue = revenue_ttm * (1.0 + closure * max(normal_revenue_growth - current_revenue_growth, 0.0))
scenario_profit = max(scenario_revenue * scenario_margin, 0.0)
reference_multiple = min(company_valid_multiple_median, industry_valid_multiple_median)
scenario_multiple = {
    "pessimistic": min(current_valid_multiple, reference_multiple * 0.80),
    "base": reference_multiple * 0.85,
    "optimistic": reference_multiple,
}[scenario]
scenario_market_cap = scenario_profit * scenario_multiple
scenario_upside = scenario_market_cap / current_market_cap - 1.0
```

For PS rows, replace `scenario_profit * scenario_multiple` with `scenario_revenue * scenario_ps_multiple`. For EV/EBITDA rows, use scenario EBITDA and subtract net debt before comparing with current market cap. Require at least 24 valid monthly company observations for a self-history median; otherwise use the subindustry median and record `valuation_self_history_insufficient=true`. Winsorize valid reference multiples at the cross-sectional 10th and 90th percentiles before calculating scenarios.

Emit these hard-risk codes:

- `negative_parent_equity`
- `debt_pressure`
- `ocf_two_period_deterioration`
- `audit_review_triggered`
- `pledge_debt_combination`
- `permanent_impairment_flag`
- `hard_risk_review_unknown`

Automated financial flags and manual evidence flags are combined; any triggered code excludes the row. `hard_risk_review_unknown` also blocks final Top 20 promotion.

- [ ] **Step 4: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_features.py tests/test_consumer_oversold_fundamentals.py -q
rtk git add src/stock_research/consumer_oversold/features.py tests/test_consumer_oversold_fundamentals.py
rtk git commit -m "feat: score PIT fundamentals and valuation repair"
```

### Task 5: Validate source-dated repair evidence

**Files:**
- Create: `config/consumer_oversold_repair_evidence_template_v1.csv`
- Create: `src/stock_research/consumer_oversold/evidence.py`
- Create: `tests/test_consumer_oversold_evidence.py`

- [ ] **Step 1: Write failing evidence tests**

Required columns are:

```text
asset_id,stock_code,evidence_as_of_date,repair_bucket,repair_thesis,leading_indicator,unrepaired_metrics,expected_validation_date,main_risks,invalidation_conditions,source_title,source_url,source_publish_date,forecast_revision_state,audit_review_status,pledge_debt_review_status,permanent_impairment_status,catalyst_verifiability_score,expected_improvement_score,operator_notes
```

Tests:

```python
def test_evidence_rejects_future_source_and_unknown_bucket():
    with pytest.raises(ValueError, match="future evidence"):
        validate_repair_evidence(future_source, trade_date="2026-07-29")
    with pytest.raises(ValueError, match="repair_bucket"):
        validate_repair_evidence(unknown_bucket, trade_date="2026-07-29")


def test_evidence_requires_traceable_source_and_hard_risk_review():
    validated = validate_repair_evidence(valid_rows, trade_date="2026-07-29")
    assert validated.iloc[0]["evidence_complete"]
    assert not validated.iloc[1]["evidence_complete"]
    assert "missing_source_url" in validated.iloc[1]["evidence_errors"]
```

- [ ] **Step 2: Verify RED**

Run evidence tests. Expected: missing module failure.

- [ ] **Step 3: Implement strict evidence validation**

`validate_repair_evidence(frame, trade_date)` must:

- reject duplicate `asset_id` rows;
- reject `evidence_as_of_date` or `source_publish_date` after the trade date;
- allow only `expected_repair` and `early_validation`;
- require non-empty thesis, leading indicator, unrepaired metrics, validation date, main risks, invalidation conditions, title, and URL;
- allow hard-risk statuses only `clear`, `triggered`, or `unknown`;
- require scores from 0 through 100;
- set `evidence_complete=false` rather than inventing values when fields are missing;
- set `hard_risk_manual_trigger=true` if any hard-risk status is `triggered`;
- set `hard_risk_review_unknown=true` if any hard-risk status is `unknown`.

The template contains only the header and one commented example in the accompanying README section of the weekly report; it must not contain preselected live stocks.

- [ ] **Step 4: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_evidence.py -q
rtk git add config/consumer_oversold_repair_evidence_template_v1.csv src/stock_research/consumer_oversold/evidence.py tests/test_consumer_oversold_evidence.py
rtk git commit -m "feat: validate consumer repair evidence"
```

### Task 6: Implement gates, component scores, bucket assignment, and Top 20 ranking

**Files:**
- Create: `src/stock_research/consumer_oversold/scoring.py`
- Create: `tests/test_consumer_oversold_scoring.py`

- [ ] **Step 1: Write failing scoring tests**

Cover the approved weighting, no forced fill, mutual exclusivity, and completed-repair exclusion:

```python
def test_composite_score_uses_approved_weights_and_penalty():
    result = score_candidates(sample_rows, config)
    row = result.set_index("asset_id").loc["A"]
    expected = 0.35 * 80 + 0.25 * 70 + 0.20 * 90 + 0.15 * 60 + 0.05 * 100 - 8
    assert row["composite_score"] == pytest.approx(expected)


def test_ranked_buckets_are_mutually_exclusive_and_not_force_filled():
    result = rank_candidate_buckets(scored_rows, config)
    assert len(result["expected"]) == 7
    assert len(result["early"]) == 5
    assert set(result["expected"]["asset_id"]).isdisjoint(result["early"]["asset_id"])


def test_completed_repair_and_unknown_risk_are_excluded():
    result = apply_candidate_gates(rows, config)
    reasons = result.set_index("asset_id")["exclusion_reasons"]
    assert "repair_already_completed" in reasons["A"]
    assert "hard_risk_review_unknown" in reasons["B"]
```

- [ ] **Step 2: Verify RED**

Run scoring tests. Expected: missing module failure.

- [ ] **Step 3: Implement exact gates and scoring**

Eligibility requires either `return_6m <= -0.20` or `max_drawdown_12m <= -0.30`, plus `relative_return_6m <= -0.10`, `oversold_score >= 60`, `base_upside >= 0.25`, complete evidence, and no hard-risk trigger/unknown status.

Compute:

```python
composite_score = (
    0.35 * repair_potential_score
    + 0.25 * valuation_repair_score
    + 0.20 * oversold_score
    + 0.15 * balance_sheet_score
    + 0.05 * catalyst_verifiability_score
    - priced_in_penalty
)
```

`repair_potential_score` combines operating gap 25%, expected improvement 25%, catalyst credibility 20%, balance-sheet runway 15%, and valuation pessimism 15%.

Build the component fields with these exact normalizations:

```python
operating_gap_score = 100.0 * mean_available([
    clip((normal_net_margin - current_net_margin) / max(abs(normal_net_margin), 0.01), 0.0, 1.0),
    clip((normal_roe - current_roe) / max(abs(normal_roe), 0.01), 0.0, 1.0),
    clip((normal_revenue_growth - current_revenue_growth) / 0.30, 0.0, 1.0),
])
expected_improvement_score = evidence_expected_improvement_score
catalyst_credibility_score = evidence_catalyst_verifiability_score
valuation_pessimism_score = 100.0 * valuation_depression_percentile
repair_potential_score = (
    0.25 * operating_gap_score
    + 0.25 * expected_improvement_score
    + 0.20 * catalyst_credibility_score
    + 0.15 * balance_sheet_score
    + 0.15 * valuation_pessimism_score
)
valuation_repair_score = 50.0 * valuation_depression_percentile + 50.0 * base_upside_percentile
```

`balance_sheet_score` is the mean of four available 0–100 subscores: positive parent equity, inverse subindustry debt-ratio percentile, OCF/net-profit quality, and cash-flow trend. Require at least three of four subscores; otherwise set it missing and exclude with `balance_sheet_coverage_insufficient`.

Set `repair_already_completed=true` when current revenue growth, profit growth, and margin have all recovered to at least 90% of their normal levels, or when the evidence row explicitly marks the thesis as completed. Exclude such rows.

Sort each bucket by `composite_score DESC`, `base_upside DESC`, `asset_id ASC`; take at most `config.max_per_bucket`. Do not backfill rejected rows.

- [ ] **Step 4: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_scoring.py -q
rtk git add src/stock_research/consumer_oversold/scoring.py tests/test_consumer_oversold_scoring.py
rtk git commit -m "feat: rank consumer repair candidates"
```

### Task 7: Add database loaders with PIT and coverage guarantees

**Files:**
- Create: `src/stock_research/consumer_oversold/loaders.py`
- Create: `tests/test_consumer_oversold_loaders.py`

- [ ] **Step 1: Write failing loader query tests**

Monkeypatch `connect` and `fetch_all` to capture SQL. Assert:

```python
def test_finance_loader_enforces_announcement_cutoff(monkeypatch):
    load_consumer_finance_history(["A"], trade_date="2026-07-29", service="test")
    assert "announcement_date <= %s" in captured_sql
    assert captured_params[-1] == "2026-07-29"


def test_market_loader_requests_at_least_252_bars(monkeypatch):
    load_consumer_market_history("2026-07-29", service="test")
    assert "LIMIT %s" in captured_sql
    assert 260 in captured_params
```

- [ ] **Step 2: Verify RED**

Run loader tests. Expected: missing loader functions.

- [ ] **Step 3: Implement loaders**

Add the exact public functions `load_consumer_universe_frames(trade_date, service)`, `load_consumer_market_history(trade_date, service)`, `load_consumer_finance_history(asset_ids, trade_date, service)`, `load_consumer_valuation_history(asset_ids, trade_date, service)`, and `load_consumer_earnings_forecasts(asset_ids, trade_date, service)`. Their return types are respectively `dict[str, pd.DataFrame]` and four `pd.DataFrame` objects.

Use existing tables:

- `core.asset_master`
- `core.asset_status_daily`
- `core.industry_membership`
- `market_daily_bar`
- `finance.indicator_quarter`
- `finance.income_statement`
- `finance.balance_sheet`
- `finance.cash_flow`
- `finance.share_capital_event`
- `factor.factor_daily`
- `event.earnings_forecast`
- `event.earnings_express`

Every event or finance query must include its announcement-date cutoff. Valuation history loads `pe_ttm`, `ps_ttm`, and `pb` for up to five years and reports the number of valid observations per asset. Market history requests 260 distinct trading dates to safely cover 252 bars.

- [ ] **Step 4: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_loaders.py -q
rtk git add src/stock_research/consumer_oversold/loaders.py tests/test_consumer_oversold_loaders.py
rtk git commit -m "feat: load consumer repair research data"
```

### Task 8: Write deterministic artifacts and coverage audit

**Files:**
- Create: `src/stock_research/consumer_oversold/reporting.py`
- Create: `tests/test_consumer_oversold_reporting.py`

- [ ] **Step 1: Write failing reporting tests**

Assert all six filenames, stable columns, Chinese report sections, and no missing risk section:

```python
def test_reporting_writes_all_approved_artifacts(tmp_path):
    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)
    assert set(result["paths"]) == {"expected", "early", "scores", "exclusions", "coverage", "report"}
    for path in result["paths"].values():
        assert Path(path).exists()
    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert "纯预期修复" in report
    assert "初步验证但尚未充分定价" in report
    assert "失效条件" in report
    assert "数据覆盖" in report
```

- [ ] **Step 2: Verify RED**

Run reporting tests. Expected: missing reporting module.

- [ ] **Step 3: Implement artifact writing**

`write_consumer_oversold_artifacts(payload, output_dir)` writes atomically through a staging directory, then renames complete files into place. The coverage JSON includes trade date, row counts at every funnel stage, data-date maxima, missing-field counts, evidence completeness, valuation-history coverage, finance-history coverage, and warnings.

The Markdown report renders for every selected stock: subindustry, category, six-month return, twelve-month drawdown, relative return, valuation method/percentile, three scenarios, repair thesis, unrepaired metrics, next validation event/date, evidence source, risks, invalidation conditions, component scores, penalty, and composite score.

- [ ] **Step 4: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_reporting.py -q
rtk git add src/stock_research/consumer_oversold/reporting.py tests/test_consumer_oversold_reporting.py
rtk git commit -m "feat: report consumer repair candidates"
```

### Task 9: Compose the weekly pipeline

**Files:**
- Create: `src/stock_research/consumer_oversold/pipeline.py`
- Create: `tests/test_consumer_oversold_pipeline.py`

- [ ] **Step 1: Write a failing end-to-end frame test**

The fixture must include at least one valid expected-repair row, one valid early-validation row, an auto-parts exclusion, an unknown hard-risk review, a future evidence row, and a completed-repair row.

```python
def test_weekly_pipeline_produces_mutually_exclusive_lists_and_audit(tmp_path):
    result = build_consumer_oversold_weekly_from_frames(
        frames=frames,
        evidence=evidence,
        config=ConsumerOversoldConfig(trade_date="2026-07-29"),
        output_dir=tmp_path,
    )
    assert list(result["expected"]["asset_id"]) == ["EXPECTED_A"]
    assert list(result["early"]["asset_id"]) == ["EARLY_A"]
    assert "hard_risk_review_unknown" in set(result["exclusions"]["exclusion_reasons"])
    assert result["coverage"]["selected_expected"] == 1
    assert result["coverage"]["selected_early"] == 1
```

- [ ] **Step 2: Verify RED**

Run pipeline tests. Expected: missing pipeline function.

- [ ] **Step 3: Implement orchestration**

Expose two entry points. `build_consumer_oversold_weekly_from_frames` takes keyword-only `frames: dict[str, pd.DataFrame]`, `evidence: pd.DataFrame`, `config: ConsumerOversoldConfig`, and optional `output_dir: str | Path | None`, returning `dict[str, Any]`. `run_consumer_oversold_weekly` takes keyword-only `trade_date`, `evidence_path`, `output_dir`, and optional `service=SETTINGS.research_service`, returning the same payload contract.

The frame-based function owns business logic. The database entry point only loads frames, reads the evidence CSV, calls the pure function, and writes artifacts. Funnel stages must be named: `raw_assets`, `consumer_universe`, `market_eligible`, `oversold_eligible`, `hard_risk_clear`, `evidence_complete`, `valuation_eligible`, `selected_expected`, and `selected_early`.

- [ ] **Step 4: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_pipeline.py -q
rtk git add src/stock_research/consumer_oversold/pipeline.py tests/test_consumer_oversold_pipeline.py
rtk git commit -m "feat: compose weekly consumer repair pipeline"
```

### Task 10: Add the CLI command

**Files:**
- Modify: `src/stock_research/cli.py`
- Create: `tests/test_consumer_oversold_cli.py`

- [ ] **Step 1: Write the failing CLI dispatch test**

```python
def test_cli_dispatches_consumer_oversold_weekly(monkeypatch, tmp_path, capsys):
    captured = {}
    monkeypatch.setattr(cli, "run_consumer_oversold_weekly", lambda **kwargs: captured.update(kwargs) or fake_result(tmp_path))
    cli.main_for_args([
        "consumer-oversold-weekly",
        "--trade-date", "2026-07-29",
        "--evidence-path", "evidence.csv",
        "--output-dir", str(tmp_path),
    ])
    assert captured["trade_date"] == "2026-07-29"
    assert captured["evidence_path"] == "evidence.csv"
    assert "consumer_oversold|expected|" in capsys.readouterr().out
```

- [ ] **Step 2: Verify RED**

Run the CLI test. Expected: argparse rejects the unknown command.

- [ ] **Step 3: Register and dispatch the command**

Add the import near other research runners. Add parser arguments `--trade-date`, `--evidence-path`, `--output-dir`, and optional `--service`. Dispatch to `run_consumer_oversold_weekly` and print one machine-readable line per artifact plus selected row counts:

```text
consumer_oversold|expected|<path>
consumer_oversold|early|<path>
consumer_oversold|scores|<path>
consumer_oversold|exclusions|<path>
consumer_oversold|coverage|<path>
consumer_oversold|report|<path>
consumer_oversold|expected_rows|<n>
consumer_oversold|early_rows|<n>
```

- [ ] **Step 4: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_cli.py -q
rtk git add src/stock_research/cli.py tests/test_consumer_oversold_cli.py
rtk git commit -m "feat: add consumer oversold weekly CLI"
```

### Task 11: Build this week's evidence packet and generate candidates

**Files:**
- Create: `outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_repair_evidence.csv`
- Generate: `outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_expected_repair_top20.csv`
- Generate: `outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_early_validation_top20.csv`
- Generate: `outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_full_scores.csv`
- Generate: `outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_exclusions.csv`
- Generate: `outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_data_coverage_audit.json`
- Generate: `outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_weekly_report.md`

- [ ] **Step 1: Run an evidence-gap pre-scan**

Use `2026-07-28` as the first weekly price cutoff. A read-only database check on 2026-07-29 found 5,192 adjusted daily-bar assets for 2026-07-28, making it the latest complete market date. Run the pipeline with the header-only template copied to the dated output directory. Expected: zero selected rows, a populated quantitative score/exclusion universe, and evidence-gap warnings rather than fabricated candidates.

- [ ] **Step 2: Research only quantitatively eligible names**

For each row passing market, oversold, valuation, and automated balance-sheet gates, collect source-dated evidence available by the trade date. Use company announcements and official operating disclosures first; use traceable analyst research or reputable market-data pages only for forward expectations. Record one row per asset in `consumer_oversold_repair_evidence.csv`.

Every row must state the next validation event and invalidation condition. Mark audit, pledge/debt, or permanent-impairment review `unknown` when not verified; such rows remain excluded.

- [ ] **Step 3: Generate this week's artifacts**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli consumer-oversold-weekly \
  --trade-date 2026-07-28 \
  --evidence-path outputs/research/consumer_oversold_weekly/2026-07-28/consumer_oversold_repair_evidence.csv \
  --output-dir outputs/research/consumer_oversold_weekly/2026-07-28
```

Expected: command exits 0 and prints all six artifact paths. Either list may contain fewer than 20 rows.

- [ ] **Step 4: Verify the weekly result contract**

Run a Python assertion command that verifies:

- each list has 0–20 rows;
- the two asset sets are disjoint;
- every selected row has `evidence_complete=true`;
- every selected row has no hard-risk trigger or unknown review;
- every selected row meets the price, relative-return, score, and base-upside gates;
- every selected row contains a source URL, source date, next validation date, risk, and invalidation condition;
- the full score table can recompute `composite_score` from components;
- the coverage audit trade date equals `2026-07-28`.

- [ ] **Step 5: Commit only source and curated evidence policy changes**

Generated research outputs are operational artifacts and remain ignored unless the repository policy explicitly tracks the dated output folder. Do not force-add ignored outputs. Commit any required tracked evidence/config file separately and never mix unrelated existing output changes.

### Task 12: Add PIT snapshot evaluation for 20/60/120-day outcomes

**Files:**
- Create: `src/stock_research/consumer_oversold/evaluation.py`
- Create: `tests/test_consumer_oversold_evaluation.py`
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_consumer_oversold_cli.py`

- [ ] **Step 1: Write failing forward-evaluation tests**

Use two weekly snapshots and daily bars that include each asset plus its consumer-subindustry benchmark. Assert:

```python
def test_forward_evaluation_computes_20_60_120_day_absolute_and_excess_returns():
    result = evaluate_consumer_oversold_snapshots(snapshots, bars, horizons=(20, 60, 120))
    row = result["detail"].query("asset_id == 'A' and horizon == 20").iloc[0]
    assert row["forward_return"] == pytest.approx(0.20)
    assert row["industry_forward_return"] == pytest.approx(0.05)
    assert row["excess_return"] == pytest.approx(0.15)


def test_forward_evaluation_keeps_incomplete_horizons_pending():
    result = evaluate_consumer_oversold_snapshots(snapshots, short_bars, horizons=(20, 60, 120))
    row = result["detail"].query("asset_id == 'A' and horizon == 120").iloc[0]
    assert row["evaluation_status"] == "pending"
    assert pd.isna(row["forward_return"])
```

Add a summary assertion for bucket-level count, win rate, median return, median excess return, and maximum drawdown.

- [ ] **Step 2: Verify RED**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_evaluation.py -q
```

Expected: missing evaluation module.

- [ ] **Step 3: Implement PIT snapshot evaluation**

Expose `evaluate_consumer_oversold_snapshots(snapshots, bars, horizons=(20, 60, 120)) -> dict[str, pd.DataFrame]` and keyword-only `run_consumer_oversold_evaluation(snapshots_root, end_date, output_dir, service=SETTINGS.research_service) -> dict[str, Any]`.

Snapshot membership is immutable: evaluate the asset and bucket recorded on the weekly trade date and never rebuild historical membership with current evidence. For each horizon, use the horizon-th subsequent trading close. If it is not yet available, emit `evaluation_status=pending`. Compute asset return, equal-weight subindustry return, excess return, path maximum drawdown, and `excess_win = excess_return > 0`.

Write `consumer_oversold_forward_evaluation_detail.csv`, `consumer_oversold_forward_evaluation_summary.csv`, and `consumer_oversold_forward_evaluation_report.md`. Summaries group by bucket and horizon and include completed count, pending count, win rate, median return, median excess return, and median maximum drawdown.

- [ ] **Step 4: Register the evaluation CLI**

Add `consumer-oversold-evaluate` with `--snapshots-root`, `--end-date`, `--output-dir`, and optional `--service`. Print paths using the prefix `consumer_oversold_evaluation|`.

- [ ] **Step 5: Run tests and commit**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_consumer_oversold_evaluation.py tests/test_consumer_oversold_cli.py -q
rtk git add src/stock_research/consumer_oversold/evaluation.py src/stock_research/cli.py tests/test_consumer_oversold_evaluation.py tests/test_consumer_oversold_cli.py
rtk git commit -m "feat: evaluate consumer repair snapshots"
```

### Task 13: Run focused regression and final review

**Files:**
- Verify all files from Tasks 1–11.

- [ ] **Step 1: Run the complete feature regression set**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_consumer_oversold_contracts.py \
  tests/test_consumer_oversold_universe.py \
  tests/test_consumer_oversold_features.py \
  tests/test_consumer_oversold_fundamentals.py \
  tests/test_consumer_oversold_evidence.py \
  tests/test_consumer_oversold_scoring.py \
  tests/test_consumer_oversold_reporting.py \
  tests/test_consumer_oversold_loaders.py \
  tests/test_consumer_oversold_pipeline.py \
  tests/test_consumer_oversold_cli.py \
  tests/test_consumer_oversold_evaluation.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run adjacent PIT and universe regressions**

```bash
rtk /Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_point_in_time_finance.py \
  tests/test_finance_ttm.py \
  tests/test_factor_fundamental.py \
  tests/test_factor_value.py \
  tests/test_universe.py \
  tests/test_industry_membership_service.py \
  tests/test_watchlist_fundamental_pit_context.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run repository hygiene checks**

```bash
rtk git diff --check
rtk git status --short
```

Expected: no whitespace errors; only intentional files appear.

- [ ] **Step 4: Review the generated report manually**

Confirm that the report does not describe already-completed repair as an opportunity, does not duplicate names between buckets, does not hide missing evidence, and does not present the research list as a trade instruction.

- [ ] **Step 5: Request independent code review**

Review the complete implementation against `docs/superpowers/specs/2026-07-29-consumer-oversold-repair-candidates-design.md`. Resolve every Critical and Important issue and re-run the affected tests before delivery.
