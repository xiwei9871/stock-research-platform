# Midtrend EOD And Research Sequence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put accepted Mid Trend v2 top10 and post-exit review artifacts into daily EOD, then run three research-only packages: fundamental interaction bad-buy research, top10 stability validation, and position sizing / industry concentration diagnostics.

**Architecture:** Keep trading strategy code immutable. Add small orchestration and research modules that consume existing strategy outputs, PIT fundamental features, canonical attribution artifacts, and top10 candidate artifacts. Daily EOD produces review artifacts; research modules produce CSV/Markdown diagnostics only.

**Tech Stack:** Python, pandas, pytest, existing `stock-research` CLI, Vite/React Daily Review Lite already integrated.

---

## File Structure

- Modify: `src/stock_research/strategy_daily_eod.py`
  - Add Mid Trend v2 top10 daily package discovery/copy/generation hooks.
  - Add PIT/canonical review artifact generation hook.
  - Add Daily Review Lite artifact generation hook.
  - Preserve v1 top5 behavior.
- Modify: `src/stock_research/cli.py`
  - Add CLI entries for the three research-only packages.
- Create: `src/stock_research/midtrend_fundamental_interaction_badbuy_research_v1.py`
  - Diagnose bad-buy interaction buckets using canonical PIT denominator events.
- Create: `src/stock_research/midtrend_top10_stability_validation_v1.py`
  - Validate top10 across month, quarter, regime, industry, slot, and winner dependency.
- Create: `src/stock_research/midtrend_position_sizing_industry_research_v1.py`
  - Research-only sizing and industry concentration diagnostics.
- Modify/Create tests:
  - `tests/test_strategy_daily_eod.py`
  - `tests/test_midtrend_fundamental_interaction_badbuy_research_v1.py`
  - `tests/test_midtrend_top10_stability_validation_v1.py`
  - `tests/test_midtrend_position_sizing_industry_research_v1.py`

## Guardrails

- Do not modify `current_mid_trend_strategy_v1` behavior.
- Do not modify `current_mid_trend_strategy_v2_top10_candidate` trading rules.
- Do not add fundamental entry filters.
- Do not add re-entry rules.
- Do not add slow exit, generic carry, or ownership hold.
- All interaction, sizing, and industry concentration outputs are `RESEARCH_ONLY`.
- Missing fundamentals remain `quality_unknown`.
- Use canonical PIT buckets where PIT rows exist.

---

### Task 1: Daily EOD Mid Trend Artifact Chain

**Files:**
- Modify: `src/stock_research/strategy_daily_eod.py`
- Test: `tests/test_strategy_daily_eod.py`

- [ ] **Step 1: Write failing test for EOD artifact chain**

Add a test that stubs four Mid Trend artifact builders and verifies EOD summary contains:

```python
def test_run_strategy_daily_eod_writes_midtrend_v1_v2_and_review_artifacts(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setattr(eod, "apply_strategy_daily_eod_status_schema", lambda **_kwargs: None)
    monkeypatch.setattr(eod, "upsert_strategy_daily_eod_status", lambda payload, **_kwargs: captured.update(payload=payload))

    def runner(*, trade_date, output_dir, service):
        path = Path(output_dir) / "strategy_mid_trend_review.csv"
        pd.DataFrame([{"trade_date": trade_date, "asset_id": "A"}]).to_csv(path, index=False)
        return {"status": "success", "review_rows": 1, "paths": {"review": str(path)}}

    def artifact_builder(*, trade_date, output_dir, service):
        files = {}
        for name in [
            "midtrend_v1_top5_reference.csv",
            "midtrend_v2_top10_candidate.csv",
            "midtrend_canonical_pit_review_labels.csv",
            "midtrend_post_exit_watch_daily_review_lite.json",
        ]:
            path = Path(output_dir) / name
            path.write_text("x", encoding="utf-8")
            files[name] = str(path)
        return {"status": "success", "paths": files, "review_rows": 0}

    result = eod.run_strategy_daily_eod(
        trade_date="2026-06-24",
        output_root=tmp_path,
        dependency_checker=lambda **_kwargs: {"status": "success"},
        lhb_runner=runner,
        mid_runner=runner,
        tech_runner=runner,
        midtrend_artifact_builder=artifact_builder,
    )

    assert result["status"] == "success"
    assert result["strategy_status"]["midtrend_artifacts"] == "success"
    assert "midtrend_v2_top10_candidate.csv" in result["midtrend_artifacts"]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_daily_eod.py::test_run_strategy_daily_eod_writes_midtrend_v1_v2_and_review_artifacts -q
```

Expected: fail because `run_strategy_daily_eod` does not accept `midtrend_artifact_builder`.

- [ ] **Step 3: Implement minimal EOD artifact builder hook**

Add optional parameter:

```python
midtrend_artifact_builder: StrategyRunner | None = None
```

Call it after `mid_runner`, store status as `strategy_status["midtrend_artifacts"]`, write returned paths into summary key `midtrend_artifacts`.

- [ ] **Step 4: Add default artifact builder**

Implement:

```python
def build_midtrend_daily_review_artifacts_eod(*, trade_date: str, output_dir: str | Path, service: str) -> dict[str, Any]:
    ...
```

Default behavior:
- copy/latest-link existing v1 top5 review from EOD output as historical reference.
- copy latest accepted top10 candidate package rows for the trade date when available.
- call existing canonical/Daily Review Lite artifact generators if prerequisite files exist.
- degrade gracefully with `status="success"` and warnings when optional artifacts are missing.

- [ ] **Step 5: Verify tests**

Run:

```bash
rtk .venv/bin/pytest tests/test_strategy_daily_eod.py tests/test_strategy_daily_eod_cli.py -q
```

Expected: pass.

---

### Task 2: Fundamental Interaction Bad-Buy Research

**Files:**
- Create: `src/stock_research/midtrend_fundamental_interaction_badbuy_research_v1.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_midtrend_fundamental_interaction_badbuy_research_v1.py`

- [ ] **Step 1: Write failing tests**

Test:
- interaction denominator construction from `bad_buy_denominator_events_canonical.csv`
- groups include:
  - `high_elasticity + quality_weak`
  - `high_elasticity + deteriorating`
  - `mainline_weak + quality_weak`
  - `mainline_weak + deteriorating`
  - `quality_weak + rank_edge`
  - `quality_weak + weak_stock_excess`
  - `quality_weak + weak_drawdown_quality`
- outputs include bad_buy_rate, net contribution, winner contribution, loser contribution, worst loss, sample count.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_midtrend_fundamental_interaction_badbuy_research_v1.py -q
```

Expected: fail because module is missing.

- [ ] **Step 3: Implement module**

Inputs:
- `outputs/research/midtrend_daily_review_lite_and_badbuy_denominator_v1_20260628/bad_buy_denominator_events_canonical.csv`

Outputs:
- `bad_buy_interaction_denominator.csv`
- `bad_buy_interaction_net_contribution.csv`
- `high_elasticity_quality_weak_analysis.csv`
- `mainline_weak_quality_weak_analysis.csv`
- `deteriorating_quality_interaction_analysis.csv`
- `fundamental_interaction_rule_candidates_research_only.md`
- `run_params.csv`
- `code_audit.md`
- `final_interpretation.md`

- [ ] **Step 4: Add CLI**

Command:

```bash
stock-research midtrend-fundamental-interaction-badbuy-research --output-dir outputs/research/midtrend_fundamental_interaction_badbuy_research_v1_20260628
```

- [ ] **Step 5: Run real package**

Run:

```bash
rtk env PYTHONPATH=src .venv/bin/stock-research midtrend-fundamental-interaction-badbuy-research --output-dir outputs/research/midtrend_fundamental_interaction_badbuy_research_v1_20260628
```

Expected: output files exist and final interpretation marks all rules `RESEARCH_ONLY`.

---

### Task 3: Top10 Stability Validation

**Files:**
- Create: `src/stock_research/midtrend_top10_stability_validation_v1.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_midtrend_top10_stability_validation_v1.py`

- [ ] **Step 1: Write failing tests**

Test that the runner groups accepted top10 candidate outputs by:
- month
- quarter
- confirmed regime state
- industry
- slot bucket
- top winner dependency

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_midtrend_top10_stability_validation_v1.py -q
```

Expected: fail because module is missing.

- [ ] **Step 3: Implement module**

Inputs:
- accepted top10 candidate `equity`, `daily_holdings`, `trade_changes`, `summary`
- optional v1 baseline for comparison

Outputs:
- `top10_monthly_stability.csv`
- `top10_quarterly_stability.csv`
- `top10_regime_stability.csv`
- `top10_industry_stability.csv`
- `top10_slot_stability.csv`
- `top10_winner_dependency.csv`
- `top10_vs_v1_stability_summary.csv`
- `run_params.csv`
- `code_audit.md`
- `final_interpretation.md`

- [ ] **Step 4: Add CLI and run real package**

Command:

```bash
rtk env PYTHONPATH=src .venv/bin/stock-research midtrend-top10-stability-validation --output-dir outputs/research/midtrend_top10_stability_validation_v1_20260628
```

Expected: output files exist; report answers whether top10 is broad-based or concentrated.

---

### Task 4: Position Sizing And Industry Concentration Research

**Files:**
- Create: `src/stock_research/midtrend_position_sizing_industry_research_v1.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_midtrend_position_sizing_industry_research_v1.py`

- [ ] **Step 1: Write failing tests**

Test research-only diagnostics for:
- top10 equal weight reference
- rank decay proxy
- volatility cap proxy
- industry exposure/contribution
- concentration buckets

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
rtk .venv/bin/pytest tests/test_midtrend_position_sizing_industry_research_v1.py -q
```

Expected: fail because module is missing.

- [ ] **Step 3: Implement module**

Inputs:
- accepted top10 candidate `daily_holdings`, `trade_changes`, `industry_exposure`

Outputs:
- `position_sizing_proxy_comparison.csv`
- `rank_decay_weight_diagnostics.csv`
- `volatility_cap_weight_diagnostics.csv`
- `industry_concentration_diagnostics.csv`
- `industry_contribution_summary.csv`
- `industry_concentration_rule_candidates_research_only.md`
- `run_params.csv`
- `code_audit.md`
- `final_interpretation.md`

- [ ] **Step 4: Add CLI and run real package**

Command:

```bash
rtk env PYTHONPATH=src .venv/bin/stock-research midtrend-position-sizing-industry-research --output-dir outputs/research/midtrend_position_sizing_industry_research_v1_20260628
```

Expected: report keeps all sizing/cap ideas `RESEARCH_ONLY`.

---

### Task 5: Final Verification

- [ ] **Run backend focused tests**

```bash
rtk .venv/bin/pytest \
  tests/test_strategy_daily_eod.py \
  tests/test_midtrend_fundamental_interaction_badbuy_research_v1.py \
  tests/test_midtrend_top10_stability_validation_v1.py \
  tests/test_midtrend_position_sizing_industry_research_v1.py -q
```

- [ ] **Run dashboard tests/build if Daily Review Lite files changed**

```bash
cd dashboard
rtk pnpm test
rtk pnpm build
```

- [ ] **Verify output packages**

Check:
- `outputs/research/midtrend_fundamental_interaction_badbuy_research_v1_20260628`
- `outputs/research/midtrend_top10_stability_validation_v1_20260628`
- `outputs/research/midtrend_position_sizing_industry_research_v1_20260628`

- [ ] **Final policy check**

Confirm:
- no strategy trading logic changed
- v1 top5 unchanged
- v2 top10 unchanged
- no fundamental filter added
- no re-entry added
- no slow exit/carry/ownership hold added

---

## Self-Review

- Spec coverage: all four requested steps have tasks and outputs.
- Placeholder scan: no TBD/TODO placeholders.
- Type consistency: all new runner names and output names are stable.
- Scope: all strategy-like ideas remain research-only except daily EOD artifact generation.
