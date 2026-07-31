# Consumer Oversold 3–5 Day Balanced Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a point-in-time V2 consumer-oversold ranking that keeps repair quality as a hard first gate, adds a real 3–5 day activation gate and score, publishes one deterministic Top20 plus reserve list, and validates the frozen 2026-07-27 ranking against 2026-07-28 through 2026-07-30.

**Architecture:** Preserve V1 defaults and sealed releases. Add versioned V2 configuration, activation feature/scoring code in a focused module, version-aware ranking in the existing scoring layer, and version-aware orchestration/reporting in the existing pipeline. Add a dedicated forward-validation module for Top20/Top30 segments and optional five-minute diagnostics so evaluation logic does not contaminate selection logic.

**Tech Stack:** Python 3.12, pandas, NumPy, psycopg/PostgreSQL, Click CLI, pytest, existing atomic release/manifest infrastructure.

---

## File Structure

- Create `src/stock_research/consumer_oversold/activation.py`: daily technical readiness, continuation, capital-efficiency, catalyst-timing, activation coverage, second gate, and activation score.
- Create `src/stock_research/consumer_oversold/v2_evaluation.py`: immutable Top20/Top30 3-day/5-day evaluation and five-minute diagnostics.
- Modify `src/stock_research/consumer_oversold/contracts.py`: V2 configuration fields and validation.
- Modify `src/stock_research/consumer_oversold/elasticity.py`: add point-in-time continuation-return features without changing V1 elasticity weights.
- Modify `src/stock_research/consumer_oversold/scoring.py`: versioned first gate and deterministic V2 ranking.
- Modify `src/stock_research/consumer_oversold/pipeline.py`: compute V1 and V2 side by side, select the requested publication version, preserve V1 behavior by default.
- Modify `src/stock_research/consumer_oversold/reporting.py`: render V2 fields and preserve atomic sealed releases.
- Modify `src/stock_research/consumer_oversold/loaders.py`: load daily fields needed by technical readiness and load five-minute outcome bars only in evaluation.
- Modify `src/stock_research/cli.py`: expose `--ranking-version` and the V2 frozen-evaluation command.
- Create `tests/test_consumer_oversold_activation.py`: activation feature, gate, coverage, sweet-spot, and no-name-branch tests.
- Modify `tests/test_consumer_oversold_contracts.py`, `tests/test_consumer_oversold_elasticity.py`, `tests/test_consumer_oversold_scoring.py`, `tests/test_consumer_oversold_pipeline.py`, `tests/test_consumer_oversold_reporting.py`, and `tests/test_consumer_oversold_cli.py`.
- Create `tests/test_consumer_oversold_v2_evaluation.py`: Top20/Top30, segment, horizon, and minute-diagnostic tests.

### Task 1: Add V2 Configuration Without Changing V1 Defaults

**Files:**
- Modify: `src/stock_research/consumer_oversold/contracts.py`
- Test: `tests/test_consumer_oversold_contracts.py`

- [ ] **Step 1: Write failing configuration tests**

```python
def test_v2_config_defaults_match_approved_design():
    config = ConsumerOversoldConfig(trade_date="2026-07-27", ranking_version="v2")

    assert config.v2_min_composite_score == 30.0
    assert config.v2_min_technical_readiness_score == 35.0
    assert config.v2_repair_rank_weight == 0.55
    assert config.v2_activation_rank_weight == 0.45
    assert (
        config.technical_readiness_weight,
        config.continuation_character_weight,
        config.residual_price_space_weight,
        config.capital_efficiency_weight,
        config.catalyst_timing_weight,
    ) == (0.30, 0.25, 0.20, 0.15, 0.10)


@pytest.mark.parametrize("ranking_version", ["", "V2", "v3", None])
def test_config_rejects_unknown_ranking_version(ranking_version):
    with pytest.raises(ValueError, match="ranking_version must be v1 or v2"):
        ConsumerOversoldConfig(
            trade_date="2026-07-27",
            ranking_version=ranking_version,
        )
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_contracts.py -q`

Expected: FAIL because `ranking_version` and V2 fields do not exist.

- [ ] **Step 3: Add the V2 fields and exact validation**

```python
@dataclass(frozen=True)
class ConsumerOversoldConfig:
    trade_date: str
    ranking_version: str = "v1"
    v2_min_composite_score: float = 30.0
    v2_min_technical_readiness_score: float = 35.0
    v2_repair_rank_weight: float = 0.55
    v2_activation_rank_weight: float = 0.45
    technical_readiness_weight: float = 0.30
    continuation_character_weight: float = 0.25
    residual_price_space_weight: float = 0.20
    capital_efficiency_weight: float = 0.15
    catalyst_timing_weight: float = 0.10

    def __post_init__(self) -> None:
        validate_trade_date(self.trade_date)
        if self.ranking_version not in {"v1", "v2"}:
            raise ValueError("ranking_version must be v1 or v2")
        _validate_number(
            "v2_min_composite_score",
            self.v2_min_composite_score,
            minimum=0.0,
            maximum=100.0,
        )
        _validate_number(
            "v2_min_technical_readiness_score",
            self.v2_min_technical_readiness_score,
            minimum=0.0,
            maximum=100.0,
        )
        _validate_weight_sum(
            "v2 repair and activation rank weights",
            (self.v2_repair_rank_weight, self.v2_activation_rank_weight),
        )
        _validate_weight_sum(
            "v2 activation component weights",
            (
                self.technical_readiness_weight,
                self.continuation_character_weight,
                self.residual_price_space_weight,
                self.capital_efficiency_weight,
                self.catalyst_timing_weight,
            ),
        )
```

Insert these fields alongside the current dataclass defaults and append these checks to the current `__post_init__`; retain every existing V1 field and validation unchanged.

- [ ] **Step 4: Run the contract tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_contracts.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/contracts.py tests/test_consumer_oversold_contracts.py
git commit -m "feat: add consumer ranking V2 configuration"
```

### Task 2: Extend Point-in-Time Continuation Features

**Files:**
- Modify: `src/stock_research/consumer_oversold/elasticity.py`
- Test: `tests/test_consumer_oversold_elasticity.py`

- [ ] **Step 1: Add failing tests for cumulative continuation and strict cutoff**

```python
def test_stock_character_adds_big_up_cumulative_returns_without_future_leakage():
    bars = _stock_character_bars(
        pct_changes=[0.0, 8.0, 2.0, 3.0, -1.0, 4.0, 99.0],
        closes=[100.0, 108.0, 110.16, 113.4648, 112.330152, 116.823358, 999.0],
        dates=[
            "2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23",
            "2026-07-24", "2026-07-27", "2026-07-28",
        ],
    )

    row = compute_stock_character_features(bars, trade_date="2026-07-27").iloc[0]

    assert row["median_return_after_big_up_3d"] == pytest.approx(112.330152 / 108.0 - 1.0)
    assert row["median_return_after_big_up_5d"] == pytest.approx(116.823358 / 108.0 - 1.0)
    assert row["strong_move_retention_5d_rate"] == 1.0
    assert row["history_sessions"] == 6
```

- [ ] **Step 2: Run the focused test and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_elasticity.py -q`

Expected: FAIL because the three new columns are absent.

- [ ] **Step 3: Add the feature columns and helpers**

```python
STOCK_CHARACTER_COLUMNS = [
    # existing columns
    "median_return_after_big_up_3d",
    "median_return_after_big_up_5d",
    "strong_move_retention_5d_rate",
]


def _forward_returns(
    close: pd.Series,
    event_positions: list[int],
    horizon: int,
) -> list[float]:
    return [
        float(close.iloc[position + horizon] / close.iloc[position] - 1.0)
        for position in event_positions
        if position + horizon < len(close)
    ]


def _median_forward_return(close: pd.Series, event_positions: list[int], horizon: int) -> float:
    outcomes = _forward_returns(close, event_positions, horizon)
    return float(np.median(outcomes)) if outcomes else math.nan


def _strong_move_retention_rate(close: pd.Series, event_positions: list[int], horizon: int) -> float:
    outcomes = _forward_returns(close, event_positions, horizon)
    return float(np.mean([value > 0.0 for value in outcomes])) if outcomes else math.nan
```

Add these keys to each result row:

```python
"median_return_after_big_up_3d": _median_forward_return(close, event_positions, 3),
"median_return_after_big_up_5d": _median_forward_return(close, event_positions, 5),
"strong_move_retention_5d_rate": _strong_move_retention_rate(close, event_positions, 5),
```

Do not add the new fields to `STOCK_ELASTICITY_FIELDS`; V1 scores must remain byte-for-byte unchanged for identical inputs.

- [ ] **Step 4: Run elasticity tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_elasticity.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/elasticity.py tests/test_consumer_oversold_elasticity.py
git commit -m "feat: measure consumer strong-move continuation"
```

### Task 3: Implement Daily Technical Readiness Features

**Files:**
- Create: `src/stock_research/consumer_oversold/activation.py`
- Create: `tests/test_consumer_oversold_activation.py`

- [ ] **Step 1: Write failing tests for cutoff, trend turn, and falling-knife detection**

```python
def test_technical_readiness_uses_only_bars_through_cutoff():
    bars = _activation_bars("A", end="2026-07-28", future_close=999.0)
    membership = pd.DataFrame({"asset_id": ["A"], "consumer_subindustry": ["auto_oem"]})

    result = compute_technical_readiness_features(
        bars,
        membership,
        trade_date="2026-07-27",
    ).iloc[0]

    assert result["latest_trade_date"] == "2026-07-27"
    assert result["return_5d"] != pytest.approx(999.0)


def test_falling_knife_requires_all_four_conditions():
    result = score_technical_readiness(_falling_knife_cross_section()).set_index("asset_id")

    assert bool(result.loc["knife", "falling_knife"])
    assert not bool(result.loc["turning", "falling_knife"])
    assert result.loc["turning", "technical_readiness_score"] > result.loc[
        "knife", "technical_readiness_score"
    ]
```

- [ ] **Step 2: Run the new test file and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_activation.py -q`

Expected: FAIL with import errors for the new module.

- [ ] **Step 3: Implement the feature interface**

```python
TECHNICAL_FEATURE_COLUMNS = (
    "asset_id",
    "latest_trade_date",
    "return_5d",
    "return_10d",
    "return_20d",
    "relative_return_5d",
    "relative_return_10d",
    "relative_strength_improvement_5d",
    "ma5_slope_5d",
    "ma10_slope_5d",
    "distance_ma5",
    "distance_ma10",
    "distance_ma20",
    "position_20d",
    "amount_ratio_5d_20d",
    "turnover_change_5d_20d",
    "volatility_ratio_5d_20d",
    "new_low_20d_within_3d",
    "technical_feature_coverage",
)


def compute_technical_readiness_features(
    bars: pd.DataFrame,
    membership: pd.DataFrame,
    *,
    trade_date: str,
) -> pd.DataFrame:
    """Return daily point-in-time activation features, one row per member."""
    required = ("asset_id", "trade_date", "close", "amount", "turnover_rate")
    missing = [column for column in required if column not in bars.columns]
    if missing:
        raise ValueError(f"bars missing required columns: {', '.join(missing)}")
    if membership.duplicated("asset_id").any():
        raise ValueError("membership must contain unique asset_id rows")
    cutoff = pd.Timestamp(validate_trade_date(trade_date))
    frame = bars.loc[:, required].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.normalize()
    frame = frame.loc[frame["trade_date"].le(cutoff)]
    if frame.duplicated(["asset_id", "trade_date"]).any():
        raise ValueError("bars must contain unique asset_id and trade_date pairs")
    frame = frame.merge(membership, on="asset_id", how="inner", validate="many_to_one")
    return _technical_rows(frame, cutoff).reindex(columns=TECHNICAL_FEATURE_COLUMNS)
```

Implement `_technical_rows` in the same file as a deterministic group-by over `asset_id`. Use simple close-to-close returns for5/10/20 sessions, peer-mean subtraction for relative returns, current five-day relative return minus the preceding five-day relative return for improvement, `close / mean - 1` for moving-average distance, five-session moving-average change for slopes, `(close-low20)/(high20-low20)` for position, mean amount and turnover ratios for5/20 sessions, standard-deviation ratio for5/20 sessions, and a last-three-session comparison with the rolling20-session low. Coverage is false unless all fields are finite and at least20 sessions exist.

Implement `score_technical_readiness(features)` with these fixed weights:

```python
technical_readiness_score = (
    0.30 * trend_turn_score
    + 0.25 * relative_strength_improvement_score
    + 0.20 * volume_turnover_confirmation_score
    + 0.15 * moving_average_location_score
    + 0.10 * volatility_transition_score
)
```

Set `falling_knife=True` only when all are true: close below MA5 and MA10, MA5 slope negative, 5-day relative return in the bottom 20% of the covered cross-section, and a 20-day low occurred within the last three sessions.

- [ ] **Step 4: Run activation tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_activation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/activation.py tests/test_consumer_oversold_activation.py
git commit -m "feat: add point-in-time technical readiness"
```

### Task 4: Implement Activation Components and the Second Gate

**Files:**
- Modify: `src/stock_research/consumer_oversold/activation.py`
- Modify: `tests/test_consumer_oversold_activation.py`

- [ ] **Step 1: Add failing tests for sweet-spot, extension, coverage, and no special names**

```python
def test_capital_efficiency_prefers_middle_band_over_both_extremes():
    scored = score_activation_candidates(_activation_rows_with_cap_percentiles()).set_index("asset_id")

    assert scored.loc["middle", "capital_efficiency_score"] > scored.loc[
        "micro", "capital_efficiency_score"
    ]
    assert scored.loc["middle", "capital_efficiency_score"] > scored.loc[
        "mega", "capital_efficiency_score"
    ]


def test_extension_requires_all_three_conditions():
    scored = score_activation_candidates(_extension_rows()).set_index("asset_id")

    assert bool(scored.loc["all_three", "overextended"])
    assert not bool(scored.loc["missing_space_condition", "overextended"])


@pytest.mark.parametrize("stock_name", ["北汽蓝谷", "赛力斯", "舍得酒业", "江淮汽车"])
def test_activation_has_no_name_or_code_branches(stock_name):
    left = _complete_activation_row(asset_id="A", stock_name=stock_name)
    right = _complete_activation_row(asset_id="B", stock_name="普通样本")
    result = score_activation_candidates(pd.DataFrame([left, right]))

    assert result.loc[result.asset_id.eq("A"), "activation_score"].iloc[0] == pytest.approx(
        result.loc[result.asset_id.eq("B"), "activation_score"].iloc[0]
    )
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_activation.py -q`

Expected: FAIL because activation components and gate are absent.

- [ ] **Step 3: Implement exact component scoring**

```python
def _capital_sweet_spot_score(cap_percentile: pd.Series) -> pd.Series:
    lower = 35.0 + 4.0 * cap_percentile
    upper = 95.0 - (60.0 / 35.0) * (cap_percentile - 65.0)
    return pd.Series(
        np.select(
            [cap_percentile.lt(15.0), cap_percentile.le(65.0)],
            [lower, 95.0],
            default=upper,
        ),
        index=cap_percentile.index,
        dtype="float64",
    ).clip(35.0, 95.0)


def _catalyst_timing_score(
    days_to_window: pd.Series,
    has_window: pd.Series,
    catalyst_verifiability_score: pd.Series,
) -> pd.Series:
    return pd.Series(
        np.select(
            [
                catalyst_verifiability_score.le(0.0),
                has_window & days_to_window.le(20),
                has_window & days_to_window.le(60),
            ],
            [0.0, 100.0, 60.0],
            default=20.0,
        ),
        index=days_to_window.index,
        dtype="float64",
    )
```

Compute continuation character using fixed internal weights: strong-move counts 20%, upside-tail/asymmetry 15%, post-move positive rates 35%, 3/5-day cumulative returns 20%, streak/retention 10%.

Compute residual-price-space score as the equal-weight mean of the ten approved, direction-normalized percentiles: 1-year and 2-year drawdown, 1-year and 2-year range position, MA120 and MA250 distance, 60-day and 120-day rebound, 6-month relative return, and valuation percentile. Coverage fails if any field is missing.

Compute `overextended=True` only when 10-day return is at or above the covered cross-section 90th percentile, rebound from the 60-day low is at least 30%, and residual-price-space score is below 25.

Compute final activation score exactly as:

```python
frame["activation_score"] = (
    config.technical_readiness_weight * frame["technical_readiness_score"]
    + config.continuation_character_weight * frame["continuation_character_score"]
    + config.residual_price_space_weight * frame["residual_price_space_score"]
    + config.capital_efficiency_weight * frame["capital_efficiency_score"]
    + config.catalyst_timing_weight * frame["catalyst_timing_score"]
).where(frame["activation_coverage"])
```

Second-gate eligibility is:

```python
frame["activation_eligible"] = (
    frame["activation_coverage"]
    & frame["technical_readiness_score"].ge(config.v2_min_technical_readiness_score)
    & ~frame["falling_knife"]
    & ~frame["overextended"]
    & frame["market_capacity_coverage"]
)
```

Store deterministic pipe-separated reasons from: `activation_coverage_incomplete`, `technical_readiness_below_threshold`, `falling_knife`, `overextended`, and `market_capacity_coverage_insufficient`.

- [ ] **Step 4: Run activation tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_activation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/activation.py tests/test_consumer_oversold_activation.py
git commit -m "feat: score balanced consumer activation"
```

### Task 5: Add the Revised First Gate and V2 Ranking

**Files:**
- Modify: `src/stock_research/consumer_oversold/scoring.py`
- Modify: `tests/test_consumer_oversold_scoring.py`

- [ ] **Step 1: Write failing tests for the North-BAIC edge and deterministic ranking**

```python
def test_v2_gate_does_not_use_oversold_60_as_an_independent_cutoff():
    row = unified_rows(
        oversold_score=56.98,
        return_6m=-0.3125,
        max_drawdown_12m=-0.3913,
        relative_return_6m=-0.1007,
        base_upside=2.01,
        composite_score=34.54,
    )

    result = apply_candidate_gates(
        pd.DataFrame([row]),
        ConsumerOversoldConfig(trade_date="2026-07-27", ranking_version="v2"),
    ).iloc[0]

    assert bool(result["eligible"])
    assert "oversold_score_below_threshold" not in result["exclusion_reasons"]


def test_v2_gate_requires_composite_score_30():
    row = unified_rows(composite_score=29.99, oversold_score=100.0)
    result = apply_candidate_gates(
        pd.DataFrame([row]),
        ConsumerOversoldConfig(trade_date="2026-07-27", ranking_version="v2"),
    ).iloc[0]

    assert not bool(result["eligible"])
    assert result["exclusion_reasons"] == "composite_score_below_v2_threshold"


def test_rank_v2_candidates_uses_55_45_and_activation_tiebreak():
    ranked = rank_v2_candidates(_v2_rank_rows(), V2_CONFIG)

    assert ranked["final_rank"].tolist() == [1, 2, 3]
    assert ranked.iloc[0]["final_rank_score_v2"] == pytest.approx(
        0.55 * ranked.iloc[0]["repair_rank_percentile"]
        + 0.45 * ranked.iloc[0]["activation_rank_percentile"]
    )
```

- [ ] **Step 2: Run scoring tests and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_scoring.py -q`

Expected: FAIL because V2 gating/ranking is absent.

- [ ] **Step 3: Version the gate without changing V1 behavior**

Inside `apply_candidate_gates`, retain the existing V1 oversold threshold when `config.ranking_version == "v1"`. For V2, skip that reason and add:

```python
if config.ranking_version == "v2":
    if math.isnan(row.composite_score) or not _decimal_aware_ge(
        raw_row.composite_score,
        row.composite_score,
        config.v2_min_composite_score,
    ):
        reasons.add("composite_score_below_v2_threshold")
else:
    if math.isnan(row.oversold_score) or not _decimal_aware_ge(
        raw_row.oversold_score,
        row.oversold_score,
        config.min_oversold_score,
    ):
        reasons.add("oversold_score_below_threshold")
```

Keep the existing absolute 6-month, drawdown, relative-return, base-upside, evidence, risk, balance-sheet, repair-completion, and repair-bucket checks for both versions.

- [ ] **Step 4: Implement deterministic V2 ranking**

```python
def rank_v2_candidates(
    scored_rows: pd.DataFrame,
    config: ConsumerOversoldConfig,
) -> pd.DataFrame:
    frame = _prepare_strict_assets(scored_rows, "scored_rows")
    ranked = frame.loc[
        frame["eligible"] & frame["activation_eligible"] & frame["activation_coverage"]
    ].copy()
    ranked["repair_rank_percentile"] = _rank_percentile(ranked["composite_score"])
    ranked["activation_rank_percentile"] = _rank_percentile(ranked["activation_score"])
    ranked["final_rank_score_v2"] = (
        config.v2_repair_rank_weight * ranked["repair_rank_percentile"]
        + config.v2_activation_rank_weight * ranked["activation_rank_percentile"]
    )
    ranked["final_rank_score"] = ranked["final_rank_score_v2"]
    ranked = ranked.sort_values(
        [
            "final_rank_score_v2",
            "activation_rank_percentile",
            "repair_rank_percentile",
            "asset_id",
        ],
        ascending=[False, False, False, True],
        kind="stable",
    )
    ranked["final_rank"] = np.arange(1, len(ranked) + 1, dtype=int)
    return ranked.reset_index(drop=True)
```

- [ ] **Step 5: Run V1 and V2 scoring tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_scoring.py -q`

Expected: PASS, including existing V1 exact-score tests.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/consumer_oversold/scoring.py tests/test_consumer_oversold_scoring.py
git commit -m "feat: add V2 repair gate and balanced rank"
```

### Task 6: Integrate V2 Into the Pipeline and Preserve V1 Releases

**Files:**
- Modify: `src/stock_research/consumer_oversold/pipeline.py`
- Modify: `tests/test_consumer_oversold_pipeline.py`

- [ ] **Step 1: Write failing integration tests**

```python
def test_v2_pipeline_publishes_top20_and_top30_diagnostics_without_changing_v1():
    v1 = build_consumer_oversold_weekly_from_frames(
        frames=_complete_frames(),
        evidence=_complete_evidence(),
        config=ConsumerOversoldConfig(trade_date="2026-07-27", ranking_version="v1"),
    )
    v2 = build_consumer_oversold_weekly_from_frames(
        frames=_complete_frames(),
        evidence=_complete_evidence(),
        config=ConsumerOversoldConfig(trade_date="2026-07-27", ranking_version="v2"),
    )

    assert "activation_score" not in v1["top20"].columns
    assert "activation_score" in v2["top20"].columns
    assert v2["coverage"]["ranking_version"] == "v2"
    assert len(v2["top30"]) == min(30, len(v2["ranked_pool"]))
    assert set(v2["comparison"]["asset_id"]) == set(v2["scores"]["asset_id"])
```

- [ ] **Step 2: Run the focused pipeline test and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_pipeline.py -q`

Expected: FAIL because V2 pipeline fields and frames are absent.

- [ ] **Step 3: Add V2 orchestration after common feature construction**

Import and call:

```python
technical = compute_technical_readiness_features(
    bars,
    membership,
    trade_date=config.trade_date,
)
stock_character = compute_stock_character_features(stock_bars, trade_date=config.trade_date)
```

For `ranking_version="v2"`:

1. call `apply_candidate_gates(scored, config)` with V2 semantics;
2. merge technical, continuation, residual, capacity and evidence timing fields one-to-one;
3. call `score_activation_candidates`;
4. call `rank_v2_candidates`;
5. derive `top20`, `reserve`, `top30`, and `ranked_pool` from the same immutable ranked frame;
6. build a V1/V2 comparison by computing the V1 rank with a separate `dataclasses.replace(config, ranking_version="v1")` instance;
7. add `ranking_version`, V2 thresholds, component weights, and activation coverage to the coverage JSON.

Do not overwrite an existing V1 directory. The CLI must use a versioned destination such as `.../2026-07-27/v2` for V2 output.

- [ ] **Step 4: Add explicit V2 output columns**

Append these fields to the V2 output schema while retaining existing identity, repair, evidence, and risk fields:

```python
V2_OUTPUT_COLUMNS = [
    *UNIFIED_OUTPUT_COLUMNS,
    "ranking_version",
    "final_rank_score_v2",
    "activation_rank_percentile",
    "activation_score",
    "technical_readiness_score",
    "continuation_character_score",
    "residual_price_space_score",
    "capital_efficiency_score",
    "catalyst_timing_score",
    "activation_coverage",
    "activation_eligible",
    "activation_exclusion_reasons",
    "falling_knife",
    "overextended",
]
```

- [ ] **Step 5: Run pipeline tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_pipeline.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/consumer_oversold/pipeline.py tests/test_consumer_oversold_pipeline.py
git commit -m "feat: integrate balanced V2 consumer pipeline"
```

### Task 7: Publish and Report V2 Artifacts Atomically

**Files:**
- Modify: `src/stock_research/consumer_oversold/contracts.py`
- Modify: `src/stock_research/consumer_oversold/reporting.py`
- Modify: `tests/test_consumer_oversold_contracts.py`
- Modify: `tests/test_consumer_oversold_reporting.py`

- [ ] **Step 1: Write failing reporting tests**

```python
def test_v2_report_contains_components_gates_and_top30_segments(tmp_path):
    payload = _v2_payload()
    result = write_consumer_oversold_artifacts(payload, output_dir=tmp_path)

    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert "排名版本：v2" in report
    assert "3—5日启动分" in report
    assert "技术启动" in report
    assert "第二门槛排除原因" in report
    assert "Top 21—30" in report


def test_v2_manifest_covers_every_published_file(tmp_path):
    result = write_consumer_oversold_artifacts(_v2_payload(), output_dir=tmp_path)
    release = Path(result["paths"]["report"]).parent
    manifest = (release / ".manifest.sha256").read_text(encoding="utf-8")

    assert "consumer_oversold_v2_top30.csv" in manifest
    assert "consumer_oversold_v1_v2_comparison.csv" in manifest
```

- [ ] **Step 2: Run reporting tests and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_reporting.py -q`

Expected: FAIL because V2 payload files are not supported.

- [ ] **Step 3: Add version-aware filenames and rendering**

Add V2-only filenames to `contracts.py` while leaving `UNIFIED_OUTPUT_FILENAMES` unchanged for V1:

```python
V2_OUTPUT_FILENAMES = {
    **UNIFIED_OUTPUT_FILENAMES,
    "top30": "consumer_oversold_v2_top30.csv",
    "ranked_pool": "consumer_oversold_v2_ranked_pool.csv",
    "comparison": "consumer_oversold_v1_v2_comparison.csv",
}
```

Select the filename contract from `coverage["ranking_version"]`. Validate that Top20 is ranks1—20, reserve begins at21, Top30 is ranks1—30, all are subsets of the ranked pool, and all selected assets exist in preaudit.

Render a V2 report with:

- V2 first- and second-gate counts;
- five activation components;
- Top20 and 21—30 tables;
- V1/V2 movement;
- explicit no-manual-adjustment statement;
- data cutoff and publication status.

- [ ] **Step 4: Run reporting tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_reporting.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/contracts.py src/stock_research/consumer_oversold/reporting.py tests/test_consumer_oversold_contracts.py tests/test_consumer_oversold_reporting.py
git commit -m "feat: publish sealed consumer V2 artifacts"
```

### Task 8: Add Top20/Top30 Forward Evaluation and Five-Minute Diagnostics

**Files:**
- Create: `src/stock_research/consumer_oversold/v2_evaluation.py`
- Create: `tests/test_consumer_oversold_v2_evaluation.py`
- Modify: `src/stock_research/consumer_oversold/loaders.py`

- [ ] **Step 1: Write failing outcome tests**

```python
def test_v2_evaluation_reports_top20_top30_and_three_rank_segments():
    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(30),
        qualified_pool=_qualified_pool_snapshot(45),
        daily_bars=_three_day_daily_bars(45),
        minute_bars=_complete_minute_bars(30),
        horizons=(3,),
    )

    summary = result["summary"].set_index("group")
    assert set(summary.index) == {"top20", "top30", "01-10", "11-20", "21-30"}
    assert summary.loc["top30", "member_count"] == 30
    assert summary.loc["top30", "rising_count"] == 18
    assert summary.loc["top30", "rising_ratio"] == pytest.approx(0.60)
    assert summary.loc["top30", "gte_5pct_count"] == 4
    assert "balanced_evaluation" in summary.columns
    assert "qualified_pool_excess_return" in summary.columns


def test_minute_diagnostics_degrade_without_blocking_daily_evaluation():
    result = evaluate_v2_snapshot(
        snapshot=_ranked_snapshot(30),
        qualified_pool=_qualified_pool_snapshot(45),
        daily_bars=_three_day_daily_bars(45),
        minute_bars=pd.DataFrame(),
        horizons=(3,),
    )

    assert result["coverage"]["daily_complete"] is True
    assert result["coverage"]["minute_complete"] is False
    assert result["coverage"]["evaluation_status"] == "daily_complete_minute_degraded"
```

- [ ] **Step 2: Run tests and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_v2_evaluation.py -q`

Expected: FAIL with import errors.

- [ ] **Step 3: Implement immutable evaluation**

```python
GROUPS = {
    "top20": lambda rank: rank <= 20,
    "top30": lambda rank: rank <= 30,
    "01-10": lambda rank: rank <= 10,
    "11-20": lambda rank: 11 <= rank <= 20,
    "21-30": lambda rank: 21 <= rank <= 30,
}


def evaluate_v2_snapshot(
    *,
    snapshot: pd.DataFrame,
    qualified_pool: pd.DataFrame,
    daily_bars: pd.DataFrame,
    minute_bars: pd.DataFrame,
    horizons: tuple[int, ...] = (3, 5),
) -> dict[str, pd.DataFrame | dict[str, object]]:
    """Evaluate fixed V2 members; never recompute membership or scores."""
    _validate_snapshot(snapshot)
    _validate_qualified_pool(qualified_pool)
    detail = _daily_forward_detail(snapshot, daily_bars, horizons)
    qualified_detail = _daily_forward_detail(qualified_pool, daily_bars, horizons)
    summary = _group_summary(detail, qualified_detail)
    minute_detail, minute_complete = _minute_diagnostics(snapshot, minute_bars)
    daily_complete = bool(detail["evaluation_status"].eq("completed").all())
    coverage = {
        "daily_complete": daily_complete,
        "minute_complete": minute_complete,
        "evaluation_status": (
            "complete"
            if daily_complete and minute_complete
            else "daily_complete_minute_degraded"
            if daily_complete
            else "daily_incomplete"
        ),
    }
    return {
        "detail": detail,
        "summary": summary,
        "minute_detail": minute_detail,
        "coverage": coverage,
    }
```

Define the five private helpers in the same task. `_validate_snapshot` requires unique assets and consecutive positive `final_rank` values. `_validate_qualified_pool` requires unique assets and verifies that every selected asset is present in the full double-gate-qualified pool. `_daily_forward_detail` uses the frozen-date close as entry and computes horizon close return, path maximum drawdown, maximum high return and high-to-close fade without changing membership. `_group_summary` applies `GROUPS` and reports member count, rising count/ratio, mean, median, positive-only mean, counts at3/5/7%, median drawdown, Spearman correlation, and excess return versus the full double-gate-qualified equal-weight pool. It also normalizes breadth, strength and risk/retention to0—100 and calculates `balanced_evaluation = 0.40*breadth + 0.40*strength + 0.20*risk_retention`; across completed horizons calculate `overall_evaluation = 0.30*evaluation_3d + 0.70*evaluation_5d`. `_minute_diagnostics` returns degraded coverage unless every selected asset has exactly48 bars per requested outcome day; when complete it reports first-high time, above-entry bar ratio, morning/afternoon retention and limit-up hold.

Add loader functions that query HFQ daily closes for returns, raw daily OHLC for limit/high diagnostics, and raw five-minute bars for the outcome period. Every SQL query must filter dates explicitly; no query used for ranking may call the minute loader.

- [ ] **Step 4: Run evaluation tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_v2_evaluation.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/consumer_oversold/v2_evaluation.py src/stock_research/consumer_oversold/loaders.py tests/test_consumer_oversold_v2_evaluation.py
git commit -m "feat: evaluate consumer V2 repair breadth and strength"
```

### Task 9: Add CLI Commands and Historical Evidence Reconstruction Guardrails

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_consumer_oversold_cli.py`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_consumer_weekly_accepts_v2_ranking_version(monkeypatch, runner):
    captured = {}
    monkeypatch.setattr(
        cli,
        "_run_consumer_oversold_weekly",
        lambda **kwargs: captured.update(kwargs) or _v2_result(),
    )

    result = runner.invoke(
        cli.main,
        [
            "consumer-oversold-weekly",
            "--trade-date", "2026-07-27",
            "--ranking-version", "v2",
            "--evidence-path", "evidence.csv",
            "--output-dir", "output/v2",
        ],
    )

    assert result.exit_code == 0
    assert captured["ranking_version"] == "v2"


def test_v2_evaluate_rejects_outcome_before_snapshot():
    with pytest.raises(ValueError, match="end_date must be after snapshot_trade_date"):
        run_v2_evaluation(
            snapshot_dir="snapshot",
            end_date="2026-07-26",
            service="stock_research",
            output_dir="evaluation",
        )
```

- [ ] **Step 2: Run CLI tests and confirm failure**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_cli.py -q`

Expected: FAIL because the option and evaluation command do not exist.

- [ ] **Step 3: Add version and evaluation options**

Add `--ranking-version` with `click.Choice(["v1", "v2"], case_sensitive=True)` and default `v1`. Pass it into `ConsumerOversoldConfig` through `run_consumer_oversold_weekly`.

Add command:

```text
consumer-oversold-v2-evaluate
  --snapshot-dir PATH
  --end-date YYYY-MM-DD
  --output-dir PATH
  --service SERVICE
```

The evaluator must read the sealed snapshot and reject writable/unverified release directories using the existing manifest verification pattern.

For the 2026-07-27 retrospective evidence file, allow only evidence rows whose source, audit, pledge/debt, and impairment publication dates are all on or before 2026-07-27. Add provenance fields:

```text
evidence_reconstruction_mode=retrospective_point_in_time
evidence_information_cutoff=2026-07-27
```

Do not copy a row merely because its review snapshot date is later; validate every underlying publication date independently and fail on any later source.

- [ ] **Step 4: Run CLI tests**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_cli.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py tests/test_consumer_oversold_cli.py
git commit -m "feat: expose consumer V2 ranking and evaluation"
```

### Task 10: Run the Frozen 2026-07-27 Test and Produce the Comparison

**Files:**
- Create: `outputs/research/consumer_oversold_daily/2026-07-27/v2/` through the application publisher
- Create: `outputs/research/consumer_oversold_daily/2026-07-27/v2_evaluation_2026-07-30/` through the evaluator
- Test: existing consumer suite plus generated artifact invariants

- [ ] **Step 1: Run the complete focused consumer test suite**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_consumer_oversold_contracts.py \
  tests/test_consumer_oversold_features.py \
  tests/test_consumer_oversold_fundamentals.py \
  tests/test_consumer_oversold_elasticity.py \
  tests/test_consumer_oversold_activation.py \
  tests/test_consumer_oversold_scoring.py \
  tests/test_consumer_oversold_pipeline.py \
  tests/test_consumer_oversold_reporting.py \
  tests/test_consumer_oversold_evaluation.py \
  tests/test_consumer_oversold_v2_evaluation.py \
  tests/test_consumer_oversold_cli.py -q
```

Expected: all selected tests PASS with zero failures.

- [ ] **Step 2: Generate the frozen V2 snapshot**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/stock-research consumer-oversold-weekly \
  --trade-date 2026-07-27 \
  --ranking-version v2 \
  --evidence-path outputs/research/consumer_oversold_daily/2026-07-27/consumer_oversold_repair_evidence_pit.csv \
  --output-dir outputs/research/consumer_oversold_daily/2026-07-27/v2
```

Expected machine lines: `ranking_version|v2`, `as_of_trade_date|2026-07-27`, and paths under the V2 directory. No source cutoff may exceed 2026-07-27.

- [ ] **Step 3: Verify the snapshot before reading outcomes**

Run a read-only verification command that checks:

- manifest digests;
- Top20 ranks1—20;
- Top30 ranks1—30 or an explicit below-30 coverage warning;
- no duplicate assets;
- `max_data_date <= 2026-07-27` for every ranking input;
- no hard-coded special-stock branch in source (`rg "北汽蓝谷|赛力斯|舍得酒业|江淮汽车|600733|601127|600702|600418" src/stock_research/consumer_oversold`).

Expected: all invariants pass; the source search returns no ranking logic matches.

- [ ] **Step 4: Evaluate 2026-07-28 through 2026-07-30**

Run:

```bash
rtk /Users/xiwei/stock_research/.venv/bin/stock-research consumer-oversold-v2-evaluate \
  --snapshot-dir outputs/research/consumer_oversold_daily/2026-07-27/v2/current \
  --end-date 2026-07-30 \
  --output-dir outputs/research/consumer_oversold_daily/2026-07-27/v2_evaluation_2026-07-30
```

Expected outputs:

- per-stock daily and cumulative returns for28、29、30日；
- Top20 and Top30 breadth/strength summaries;
- rank segments1—10、11—20、21—30;
- V1/V2 membership and performance comparison;
- Spearman rank diagnostics;
- minute coverage and intraday retention diagnostics;
- explicit North BAIC case row if it passes the universal rules, or its universal exclusion reason if it does not.

- [ ] **Step 5: Run regression tests after artifact generation**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_*.py -q`

Expected: all consumer tests PASS with zero failures.

- [ ] **Step 6: Commit implementation and reproducibility metadata**

Do not commit generated market-data artifacts unless repository policy already tracks equivalent research outputs. Commit code, tests, configuration, and any small reproducibility manifest:

```bash
git add src/stock_research/consumer_oversold tests/test_consumer_oversold_*.py src/stock_research/cli.py
git commit -m "feat: deliver balanced 3-5d consumer ranking V2"
```

### Task 11: Final Verification and Review

**Files:**
- Review all files changed in Tasks1—10

- [ ] **Step 1: Run whitespace and status checks**

Run: `rtk git diff --check`

Expected: no output.

Run: `rtk git status --short`

Expected: only intentionally generated ignored outputs, or a clean tracked worktree.

- [ ] **Step 2: Run the complete consumer suite once more**

Run: `rtk /Users/xiwei/stock_research/.venv/bin/pytest tests/test_consumer_oversold_*.py -q`

Expected: zero failures.

- [ ] **Step 3: Inspect the final V1/V2 report against the approved spec**

Confirm all of these are present:

- revised first gate with no independent oversold-score60 cutoff;
- composite-score30 floor;
- technical-readiness35 floor;
- 55/45 final score;
- five activation components;
- Top20, Top30 and three rank segments;
- 3-day results for July28—30;
- no stock-specific protection;
- daily evaluation remains usable when minute diagnostics degrade.

- [ ] **Step 4: Request code review**

Use the `requesting-code-review` skill against the implementation commits. Address only findings within this V2 scope, rerun focused tests after each correction, then rerun the final complete consumer suite.
