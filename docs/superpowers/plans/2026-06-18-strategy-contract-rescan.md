# Strategy Contract Rescan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-scan LHB Shortline, Mid Trend, and Tech Bottleneck to select the official return-first, balanced, and drawdown-first versions, then lock those selections behind a machine-checkable strategy contract.

**Architecture:** Add a small strategy research contract layer that can consume scan summaries, rank candidates into three profiles, and validate that backend/EOD manifest outputs match the accepted contract. Reuse existing scan engines instead of creating new strategy logic: LHB phase18c/phase14e outputs, Mid Trend weekly control/optimization outputs, and Tech Bottleneck Serenity C2 outputs.

**Tech Stack:** Python, pandas, pytest, existing `stock_research` CLI/research modules, local `outputs/research` artifacts, dashboard EOD manifest JSON.

---

## Official Selection Rules

Each strategy must produce three profiles:

- `return_first`: maximize `final_equity` or `total_return`, but reject candidates with missing trades, missing positions, or implausible artifact lineage.
- `balanced`: maximize a composite score using return, max drawdown, Sharpe/Calmar when present, turnover, and strategy simplicity. This is the default deployed profile.
- `drawdown_first`: minimize absolute `max_drawdown`, but reject candidates whose return is weak relative to the candidate set.

Common eligibility rules:

- Backtest range must use point-in-time data only up to the requested `end_date`.
- The selected row must include enough identity fields to reproduce the run: engine, variant/protection, top_n, frequency, cost, adjust_type, input source, and benchmark artifact path.
- Candidate artifacts must include summary plus either positions/trades or a deterministic candidate source.
- Any strategy that cannot produce a valid scan for the requested end date is marked `unconfirmed`, not silently promoted.

## File Map

- Create: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/strategy_contracts.py`
  - Owns dataclasses for accepted strategy contract rows and profile selection metadata.
- Create: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/strategy_contract_rescan.py`
  - Loads existing or newly generated scan summaries and ranks three profiles per strategy.
- Create: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_strategy_contract_rescan.py`
  - TDD coverage for ranking rules and contract validation.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/cli.py`
  - Add `rescan-official-strategy-contracts`.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/dashboard/backtests.py`
  - Validate manifest strategy summaries against the accepted contract before using them.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/dashboard/review_queue.py`
  - Ignore strategy manifest artifacts that fail contract validation.
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/dashboard/readiness.py`
  - Surface strategy contract mismatch as not ready.

## Task 1: Selection Rules

**Files:**
- Create: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_strategy_contract_rescan.py`
- Create: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/strategy_contract_rescan.py`

- [ ] **Step 1: Write failing tests for three-profile selection**

Add tests that build a small candidate DataFrame and assert:

```python
def test_selects_return_balanced_and_drawdown_profiles():
    candidates = pd.DataFrame([
        {"strategy_id": "mid_trend", "variant": "fast", "final_equity": 3.0, "total_return": 2.0, "max_drawdown": -0.35, "sharpe": 2.0, "trade_rows": 40, "position_rows": 80},
        {"strategy_id": "mid_trend", "variant": "balanced", "final_equity": 2.5, "total_return": 1.5, "max_drawdown": -0.18, "sharpe": 2.8, "trade_rows": 35, "position_rows": 80},
        {"strategy_id": "mid_trend", "variant": "defensive", "final_equity": 1.9, "total_return": 0.9, "max_drawdown": -0.08, "sharpe": 2.1, "trade_rows": 20, "position_rows": 70},
    ])

    profiles = select_strategy_profiles(candidates, strategy_id="mid_trend")

    assert profiles["return_first"]["variant"] == "fast"
    assert profiles["balanced"]["variant"] == "balanced"
    assert profiles["drawdown_first"]["variant"] == "defensive"
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: fails because `stock_research.strategy_contract_rescan` does not exist.

- [ ] **Step 3: Implement minimal profile selector**

Implement:

```python
def select_strategy_profiles(candidates: pd.DataFrame, *, strategy_id: str) -> dict[str, dict[str, Any]]:
    ...
```

Normalize metric names:

- `return_metric = final_equity - 1` if `final_equity` exists; else `total_return`.
- `drawdown_abs = abs(max_drawdown)`.
- `balanced_score = normalized_return + normalized_sharpe + normalized_drawdown_control`.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: passes.

## Task 2: Strategy-Specific Scan Loaders

**Files:**
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/strategy_contract_rescan.py`
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_strategy_contract_rescan.py`

- [ ] **Step 1: Write loader normalization tests**

Cover these source shapes:

- LHB `lhb_phase18c_summary_v1.csv` with `strategy`, `top_n`, `final_equity`, `max_drawdown`.
- Mid Trend `mid_trend_shadow_weekly_control_summary.csv` with `variant_name`, `top_n`, `transaction_cost_bps`.
- Tech Bottleneck `serenity_tight3b_c2_matrix_summary.csv` with `universe`, `frequency`, `protection_name`, `top_n`.

- [ ] **Step 2: Run loader tests and verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: fails because loader functions do not exist.

- [ ] **Step 3: Implement loaders**

Implement:

```python
load_lhb_scan_candidates(paths: Sequence[Path]) -> pd.DataFrame
load_mid_trend_scan_candidates(paths: Sequence[Path]) -> pd.DataFrame
load_tech_bottleneck_scan_candidates(paths: Sequence[Path]) -> pd.DataFrame
```

Each returned row must contain:

- `strategy_id`
- `engine`
- `variant`
- `profile_candidate_source`
- `top_n`
- `frequency`
- `protection_name`
- `transaction_cost_bps`
- `adjust_type`
- `final_equity`
- `total_return`
- `max_drawdown`
- `sharpe`
- `trade_rows`
- `position_rows`
- `benchmark_artifact_path`

- [ ] **Step 4: Verify loaders**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: passes.

## Task 3: Contract Model

**Files:**
- Create: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/strategy_contracts.py`
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_strategy_contract_rescan.py`

- [ ] **Step 1: Write contract validation tests**

Assert that a manifest summary passes only when expected identity fields match:

```python
def test_contract_rejects_mismatched_variant():
    contract = StrategyContract(
        contract_id="mid_trend:balanced:v1",
        strategy_id="mid_trend",
        profile="balanced",
        engine="mid_trend_v1",
        variant="top5_weekly_max2_selective_trend_holding_protection_v1",
        top_n=5,
        transaction_cost_bps=20.0,
        adjust_type="hfq",
    )
    summary = {"engine_version": "mid_trend_v1", "variant_name": "other", "top_n": 5, "transaction_cost_bps": 20.0, "adjust_type": "hfq"}

    result = validate_strategy_summary_against_contract(summary, contract)

    assert result.status == "failed"
    assert "variant" in result.reason
```

- [ ] **Step 2: Run and verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: fails because contract model does not exist.

- [ ] **Step 3: Implement dataclasses and validator**

Implement:

```python
@dataclass(frozen=True)
class StrategyContract:
    contract_id: str
    strategy_id: str
    profile: str
    engine: str
    variant: str
    top_n: int
    transaction_cost_bps: float
    adjust_type: str
    frequency: str | None = None
    protection_name: str | None = None
    benchmark_artifact_path: str = ""

@dataclass(frozen=True)
class ContractValidationResult:
    status: str
    reason: str
```

Implement exact checks for engine, variant, top_n, cost, adjust_type, frequency, protection.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: passes.

## Task 4: CLI Report

**Files:**
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/cli.py`
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_strategy_contract_rescan.py`

- [ ] **Step 1: Write CLI dispatch test**

Patch the runner and assert CLI prints:

- `strategy_contract_rescan|summary|`
- `strategy_contract_rescan|contracts|`
- `strategy_contract_rescan|rows|`

- [ ] **Step 2: Run and verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: fails because CLI command is missing.

- [ ] **Step 3: Add `rescan-official-strategy-contracts`**

Arguments:

- `--start-date`
- `--end-date`
- `--output-dir`
- `--use-existing-artifacts`

Output files:

- `official_strategy_profile_candidates.csv`
- `official_strategy_contracts.json`
- `official_strategy_contract_rescan_report.md`

- [ ] **Step 4: Verify CLI**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py -q
```

Expected: passes.

## Task 5: Run Real Rescan

**Files:**
- Outputs only under `/Users/xiwei/stock_research/outputs/research/official_strategy_contract_rescan_<start>_<end>/`

- [ ] **Step 1: Run existing-artifact rescan first**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli \
  rescan-official-strategy-contracts \
  --start-date 2025-01-01 \
  --end-date 2026-06-17 \
  --output-dir /Users/xiwei/stock_research/outputs/research/official_strategy_contract_rescan_20250101_20260617 \
  --use-existing-artifacts
```

Expected: writes candidate and contract files.

- [ ] **Step 2: Review selected profiles**

Read:

```bash
/Users/xiwei/stock_research/.venv/bin/python - <<'PY'
import pandas as pd
p='/Users/xiwei/stock_research/outputs/research/official_strategy_contract_rescan_20250101_20260617/official_strategy_profile_candidates.csv'
df=pd.read_csv(p)
print(df[df['selected_profile'].notna()].to_string(index=False))
PY
```

Expected: three selected profiles per strategy, or explicit `unconfirmed` reason.

- [ ] **Step 3: If existing artifacts are stale, run fresh strategy scans**

Run fresh scans only for stale strategies:

- LHB: phase18c/phase14e through 2026-06-17.
- Mid Trend: weekly control through 2026-06-17 using DB base tables and accepted variants.
- Tech Bottleneck: Serenity C2 through 2026-06-17.

Expected: output paths are included in final report.

## Task 6: Backend Contract Enforcement

**Files:**
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/dashboard/backtests.py`
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/dashboard/review_queue.py`
- Modify: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/src/stock_research/dashboard/readiness.py`
- Test: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_dashboard_backtests.py`
- Test: `/Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web/tests/test_dashboard_review_queue.py`

- [ ] **Step 1: Write failing tests for mismatch rejection**

Add tests where manifest says `strategy_mid_trend` success but variant differs from contract. Assert:

- Review Queue excludes it or labels it untrusted.
- Readiness shows strategy not ready.
- Backtest summary includes mismatch warning.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
```

Expected: fails because contract enforcement is not wired.

- [ ] **Step 3: Wire validation**

Load `official_strategy_contracts.json` from latest output path or default config path. Validate manifest summaries before rendering strategy readiness or Review Queue rows.

- [ ] **Step 4: Verify GREEN**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_strategy_contract_rescan.py tests/test_dashboard_backtests.py tests/test_dashboard_review_queue.py -q
```

Expected: passes.

## Task 7: End-to-End Verification

**Files:**
- No new files unless defects are found.

- [ ] **Step 1: Run targeted backend tests**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_strategy_contract_rescan.py \
  tests/test_dashboard_backtests.py \
  tests/test_dashboard_review_queue.py \
  tests/test_tech_bottleneck_v1.py \
  tests/test_mid_trend_shadow_weekly_control.py \
  tests/test_lhb_shortline_v1.py \
  -q
```

Expected: all pass.

- [ ] **Step 2: Query local backend**

Run:

```bash
curl -s http://127.0.0.1:8765/api/platform/readiness | /Users/xiwei/stock_research/.venv/bin/python -m json.tool | head -120
```

Expected: strategy health shows contract status per strategy.

- [ ] **Step 3: Browser smoke test**

Open `http://127.0.0.1:5174/` and verify:

- Home shows strategy readiness based on contract validation.
- Review Queue uses only contract-valid strategy artifacts.
- Any unconfirmed strategy is labeled clearly and not mixed with confirmed review items.

## Self-Review

- Scope is focused on official strategy selection and contract validation.
- The plan does not alter strategy math until scans prove which variants should be accepted.
- The plan keeps fresh scan outputs outside source control unless explicitly committed later.
- TDD is required for selector, contract validation, CLI dispatch, and backend enforcement.
