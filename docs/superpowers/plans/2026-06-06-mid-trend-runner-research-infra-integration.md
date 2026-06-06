# Mid-Trend Runner Research Infra Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit `--write-research-infra` path to the real mid-trend portfolio review runner and CLI so daily review outputs can include standardized method-layer evidence sidecars.

**Architecture:** Keep `build_mid_trend_portfolio_review_from_frames(...)` pure and unchanged. Add opt-in sidecar writing at `run_mid_trend_portfolio_review(...)` by wrapping its existing builder call with `build_mid_trend_review_with_research_infra(...)`, then pass the same flag through the CLI and print stable artifact paths only when present.

**Tech Stack:** Python 3.11+, pandas, pytest, existing `stock_research.research_infra.mid_trend_integration` wrapper, existing `stock_research.cli` parser/dispatcher.

---

## Implementation Workspace Requirement

Execute this plan only in a workspace that contains these real mid-trend files:

- `src/stock_research/mid_trend_portfolio_review.py`
- `tests/test_mid_trend_portfolio_review.py`
- `src/stock_research/cli.py`
- `src/stock_research/research_infra/mid_trend_integration.py`

In the current project state, `mid_trend_portfolio_review.py` exists in the main worktree as uncommitted work, not in the isolated `method-infra-first-slice` branch. If executing in the main worktree, preserve all unrelated dirty changes and edit only the files listed in this plan.

## File Structure

- Modify `src/stock_research/mid_trend_portfolio_review.py`
  - Import `build_mid_trend_review_with_research_infra`.
  - Add `write_research_infra: bool = False` to `run_mid_trend_portfolio_review(...)`.
  - Replace the direct builder return with a wrapper call around a local `review_builder` closure.
- Modify `src/stock_research/cli.py`
  - Add `--write-research-infra` to `build-mid-trend-portfolio-review`.
  - Pass `write_research_infra=args.write_research_infra` to the runner.
  - Print research-infra paths only when `result` contains `research_infra`.
- Modify `tests/test_mid_trend_portfolio_review.py`
  - Update existing CLI dispatch expectation to include `write_research_infra=False`.
  - Add runner enabled-mode test.
  - Add CLI enabled-mode test.

## Task 1: Runner Opt-In Integration

**Files:**
- Modify: `tests/test_mid_trend_portfolio_review.py`
- Modify: `src/stock_research/mid_trend_portfolio_review.py`

- [ ] **Step 1: Write the failing runner enabled-mode test**

Append this test after `test_run_mid_trend_portfolio_review_reads_csvs_and_delegates` in `tests/test_mid_trend_portfolio_review.py`:

```python
def test_run_mid_trend_portfolio_review_writes_research_infra_when_enabled(
    tmp_path: Path,
) -> None:
    top10_path = tmp_path / "top10.csv"
    holdings_path = tmp_path / "holdings.csv"
    trades_path = tmp_path / "trades.csv"
    research_path = tmp_path / "research.csv"

    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "stock_name": "生益科技",
                "shadow_top10_rank": 1,
                "mid_trend_funnel_score": 84.7,
                "mid_trend_layer": "stable_trend_watch",
                "market_regime": "mainline",
                "mainline_status": "sustained_mainline",
                "industry_name": "电子",
            }
        ]
    ).to_csv(top10_path, index=False)
    pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "rebalance_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "weight": 1.0,
            }
        ]
    ).to_csv(holdings_path, index=False)
    pd.DataFrame(
        [
            {
                "variant_name": "top5_weekly_max_2_replacements",
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "side": "buy",
                "turnover_contribution": 0.2,
                "transaction_cost": 0.0004,
                "reason": "weekly_rebalance",
            }
        ]
    ).to_csv(trades_path, index=False)
    pd.DataFrame(
        [
            {
                "trade_date": "2026-06-04",
                "asset_id": "CN:SH:600183",
                "ts_code": "600183.SH",
                "broker_report_count_90d": 3,
                "research_support_score_pit": 33,
                "pdf_target_price_count_90d": 3,
                "pdf_profit_forecast_count_90d": 3,
                "pdf_risk_section_count_90d": 3,
            }
        ]
    ).to_csv(research_path, index=False)

    result = run_mid_trend_portfolio_review(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10_path=top10_path,
        holdings_path=holdings_path,
        trades_path=trades_path,
        research_packet_path=research_path,
        output_dir=tmp_path / "review_output",
        write_research_infra=True,
    )

    assert "research_infra" in result
    research_infra = result["research_infra"]
    assert Path(research_infra["research_infra_dir"]).is_dir()
    assert Path(research_infra["research_signals_json_path"]).exists()
    assert Path(research_infra["attribution_cards_json_path"]).exists()
    assert Path(research_infra["attribution_cards_md_path"]).exists()
    assert Path(research_infra["experiment_registry_path"]).exists()
    assert Path(research_infra["run_card"]["run_card_json_path"]).exists()
    assert research_infra["research_signal_count"] == 3
```

- [ ] **Step 2: Strengthen the existing default-mode runner test**

In `test_run_mid_trend_portfolio_review_reads_csvs_and_delegates`, change:

```python
    run_mid_trend_portfolio_review(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10_path=tmp_path / "top10.csv",
        holdings_path=tmp_path / "holdings.csv",
        trades_path=tmp_path / "trades.csv",
        research_packet_path=tmp_path / "research.csv",
    )
```

to:

```python
    result = run_mid_trend_portfolio_review(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10_path=tmp_path / "top10.csv",
        holdings_path=tmp_path / "holdings.csv",
        trades_path=tmp_path / "trades.csv",
        research_packet_path=tmp_path / "research.csv",
    )
```

Then add this assertion after the existing `captured["output_dir"]` assertion:

```python
    assert "research_infra" not in result
```

- [ ] **Step 3: Run the runner tests and verify the enabled test fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_mid_trend_portfolio_review.py::test_run_mid_trend_portfolio_review_writes_research_infra_when_enabled tests/test_mid_trend_portfolio_review.py::test_run_mid_trend_portfolio_review_reads_csvs_and_delegates -q
```

Expected: fail with a message equivalent to:

```text
TypeError: run_mid_trend_portfolio_review() got an unexpected keyword argument 'write_research_infra'
```

- [ ] **Step 4: Add the runner implementation**

In `src/stock_research/mid_trend_portfolio_review.py`, add this import below the existing imports:

```python
from stock_research.research_infra.mid_trend_integration import (
    build_mid_trend_review_with_research_infra,
)
```

Change the runner signature from:

```python
def run_mid_trend_portfolio_review(
    *,
    trade_date: str,
    strategy_variant: str,
    top10_path: str | Path,
    holdings_path: str | Path,
    trades_path: str | Path,
    research_packet_path: str | Path,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
```

to:

```python
def run_mid_trend_portfolio_review(
    *,
    trade_date: str,
    strategy_variant: str,
    top10_path: str | Path,
    holdings_path: str | Path,
    trades_path: str | Path,
    research_packet_path: str | Path,
    output_dir: str | Path | None = None,
    write_research_infra: bool = False,
) -> dict[str, Any]:
```

Replace the final direct return:

```python
    return build_mid_trend_portfolio_review_from_frames(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        top10=top10,
        holdings=holdings,
        trades=trades,
        research_packet_candidates=research_packet_candidates,
        output_dir=normalized_output_dir,
    )
```

with:

```python
    def build_review() -> dict[str, Any]:
        return build_mid_trend_portfolio_review_from_frames(
            trade_date=trade_date,
            strategy_variant=strategy_variant,
            top10=top10,
            holdings=holdings,
            trades=trades,
            research_packet_candidates=research_packet_candidates,
            output_dir=normalized_output_dir,
        )

    return build_mid_trend_review_with_research_infra(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        review_builder=build_review,
        output_dir=normalized_output_dir,
        write_research_infra=write_research_infra,
    )
```

- [ ] **Step 5: Run the runner tests and verify they pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_mid_trend_portfolio_review.py::test_run_mid_trend_portfolio_review_writes_research_infra_when_enabled tests/test_mid_trend_portfolio_review.py::test_run_mid_trend_portfolio_review_reads_csvs_and_delegates -q
```

Expected:

```text
2 passed
```

## Task 2: CLI Flag And Artifact Output

**Files:**
- Modify: `tests/test_mid_trend_portfolio_review.py`
- Modify: `src/stock_research/cli.py`

- [ ] **Step 1: Update the existing CLI dispatch test default expectation**

In `test_cli_dispatches_mid_trend_portfolio_review`, update the `captured` assertion from:

```python
    assert captured == {
        "trade_date": "2026-06-04",
        "strategy_variant": "top5_weekly_max_2_replacements",
        "top10_path": "outputs/research/mid_trend_shadow_top10.csv",
        "holdings_path": "outputs/research/mid_trend_shadow_weekly_control_positions.csv",
        "trades_path": "outputs/research/mid_trend_shadow_weekly_control_trades.csv",
        "research_packet_path": "outputs/research/mid_trend_research_packet_candidates.csv",
        "output_dir": str(tmp_path),
    }
```

to:

```python
    assert captured == {
        "trade_date": "2026-06-04",
        "strategy_variant": "top5_weekly_max_2_replacements",
        "top10_path": "outputs/research/mid_trend_shadow_top10.csv",
        "holdings_path": "outputs/research/mid_trend_shadow_weekly_control_positions.csv",
        "trades_path": "outputs/research/mid_trend_shadow_weekly_control_trades.csv",
        "research_packet_path": "outputs/research/mid_trend_research_packet_candidates.csv",
        "output_dir": str(tmp_path),
        "write_research_infra": False,
    }
```

- [ ] **Step 2: Add the CLI enabled-mode test**

Append this test after `test_cli_dispatches_mid_trend_portfolio_review`:

```python
def test_cli_dispatches_mid_trend_portfolio_review_with_research_infra(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    captured = {}
    run_card_path = tmp_path / "research_infra" / "run_card" / "run_card.json"

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "review_rows": pd.DataFrame([{"ts_code": "600183.SH"}]),
            "paths": {
                "csv": str(tmp_path / "review.csv"),
                "report": str(tmp_path / "review.md"),
            },
            "research_infra": {
                "research_infra_dir": str(tmp_path / "research_infra"),
                "research_signals_json_path": str(
                    tmp_path / "research_infra" / "research_signals.json"
                ),
                "attribution_cards_json_path": str(
                    tmp_path / "research_infra" / "attribution_cards.json"
                ),
                "run_card": {
                    "run_card_json_path": str(run_card_path),
                },
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_portfolio_review", fake_run, raising=False)

    cli.main_for_args(
        [
            "build-mid-trend-portfolio-review",
            "--trade-date",
            "2026-06-04",
            "--strategy-variant",
            "top5_weekly_max_2_replacements",
            "--top10-path",
            "outputs/research/mid_trend_shadow_top10.csv",
            "--holdings-path",
            "outputs/research/mid_trend_shadow_weekly_control_positions.csv",
            "--trades-path",
            "outputs/research/mid_trend_shadow_weekly_control_trades.csv",
            "--research-packet-path",
            "outputs/research/mid_trend_research_packet_candidates.csv",
            "--output-dir",
            str(tmp_path),
            "--write-research-infra",
        ]
    )

    assert captured["write_research_infra"] is True
    out = capsys.readouterr().out
    assert f"mid_trend_portfolio_review|csv|{tmp_path / 'review.csv'}" in out
    assert f"mid_trend_portfolio_review|report|{tmp_path / 'review.md'}" in out
    assert "mid_trend_portfolio_review|rows|1" in out
    assert f"mid_trend_portfolio_review|research_infra|{tmp_path / 'research_infra'}" in out
    assert (
        "mid_trend_portfolio_review|research_signals|"
        f"{tmp_path / 'research_infra' / 'research_signals.json'}"
    ) in out
    assert (
        "mid_trend_portfolio_review|attribution_cards|"
        f"{tmp_path / 'research_infra' / 'attribution_cards.json'}"
    ) in out
    assert f"mid_trend_portfolio_review|run_card|{run_card_path}" in out
```

- [ ] **Step 3: Run the CLI tests and verify they fail**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_mid_trend_portfolio_review.py::test_cli_dispatches_mid_trend_portfolio_review tests/test_mid_trend_portfolio_review.py::test_cli_dispatches_mid_trend_portfolio_review_with_research_infra -q
```

Expected: fail because `write_research_infra` is not passed by default and `--write-research-infra` is not accepted yet.

- [ ] **Step 4: Add the CLI parser flag**

In `src/stock_research/cli.py`, immediately after:

```python
    mid_trend_portfolio_review.add_argument("--output-dir", default="outputs/research")
```

add:

```python
    mid_trend_portfolio_review.add_argument(
        "--write-research-infra",
        action="store_true",
        help="Write standardized research_infra sidecar artifacts for this review.",
    )
```

- [ ] **Step 5: Pass the flag to the runner and print artifact paths**

In the `elif args.command == "build-mid-trend-portfolio-review":` block, change:

```python
        result = run_mid_trend_portfolio_review(
            trade_date=args.trade_date,
            strategy_variant=args.strategy_variant,
            top10_path=args.top10_path,
            holdings_path=args.holdings_path,
            trades_path=args.trades_path,
            research_packet_path=args.research_packet_path,
            output_dir=args.output_dir,
        )
        print(f"mid_trend_portfolio_review|csv|{result['paths']['csv']}")
        print(f"mid_trend_portfolio_review|report|{result['paths']['report']}")
        print(f"mid_trend_portfolio_review|rows|{len(result['review_rows'])}")
```

to:

```python
        result = run_mid_trend_portfolio_review(
            trade_date=args.trade_date,
            strategy_variant=args.strategy_variant,
            top10_path=args.top10_path,
            holdings_path=args.holdings_path,
            trades_path=args.trades_path,
            research_packet_path=args.research_packet_path,
            output_dir=args.output_dir,
            write_research_infra=args.write_research_infra,
        )
        print(f"mid_trend_portfolio_review|csv|{result['paths']['csv']}")
        print(f"mid_trend_portfolio_review|report|{result['paths']['report']}")
        print(f"mid_trend_portfolio_review|rows|{len(result['review_rows'])}")
        research_infra = result.get("research_infra")
        if research_infra:
            print(
                "mid_trend_portfolio_review|research_infra|"
                f"{research_infra['research_infra_dir']}"
            )
            print(
                "mid_trend_portfolio_review|research_signals|"
                f"{research_infra['research_signals_json_path']}"
            )
            print(
                "mid_trend_portfolio_review|attribution_cards|"
                f"{research_infra['attribution_cards_json_path']}"
            )
            print(
                "mid_trend_portfolio_review|run_card|"
                f"{research_infra['run_card']['run_card_json_path']}"
            )
```

- [ ] **Step 6: Run the CLI tests and verify they pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_mid_trend_portfolio_review.py::test_cli_dispatches_mid_trend_portfolio_review tests/test_mid_trend_portfolio_review.py::test_cli_dispatches_mid_trend_portfolio_review_with_research_infra -q
```

Expected:

```text
2 passed
```

## Task 3: Focused Verification And Commit

**Files:**
- No additional file changes expected.

- [ ] **Step 1: Run focused mid-trend and research-infra verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_mid_trend_portfolio_review.py \
  tests/test_research_infra_mid_trend_integration.py \
  -q
```

Expected: all tests in both files pass.

- [ ] **Step 2: Run broader method-layer verification**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_run_card.py \
  tests/test_factor_eval.py \
  tests/test_research_infra_run_evidence.py \
  tests/test_research_infra_experiment_registry.py \
  tests/test_research_infra_feature_registry.py \
  tests/test_research_infra_research_signals.py \
  tests/test_research_infra_factor_cards.py \
  tests/test_research_infra_attribution_cards.py \
  tests/test_research_infra_mid_trend_integration.py \
  tests/test_mid_trend_portfolio_review.py \
  -q
```

Expected: all listed tests pass.

- [ ] **Step 3: Review touched diff only**

Run:

```bash
git diff -- src/stock_research/mid_trend_portfolio_review.py src/stock_research/cli.py tests/test_mid_trend_portfolio_review.py
```

Confirm the diff only includes:

- runner opt-in parameter and wrapper call
- CLI flag and artifact output lines
- tests for default and enabled behavior

- [ ] **Step 4: Commit**

Run:

```bash
git add src/stock_research/mid_trend_portfolio_review.py src/stock_research/cli.py tests/test_mid_trend_portfolio_review.py
git commit -m "feat: wire research infra into mid-trend review runner"
```

If executing in the dirty main worktree, stage only the hunks from this plan and do not stage unrelated user changes.

## Self-Review

- Spec coverage:
  - Runner opt-in parameter: Task 1.
  - Builder unchanged: Task 1 wraps only the runner.
  - CLI flag and output lines: Task 2.
  - Default behavior unchanged: Task 1 and Task 2 default tests.
  - Enabled behavior writes sidecars: Task 1 enabled test.
  - Error propagation: implementation does not catch wrapper exceptions.
  - No trading/execution scope: touched files are review runner, CLI, and tests only.
- Placeholder scan: no `TBD`, `TODO`, or unspecified code blocks remain.
- Type consistency: the plan consistently uses `write_research_infra`, `research_infra`, `research_signals_json_path`, `attribution_cards_json_path`, and `run_card["run_card_json_path"]`.
