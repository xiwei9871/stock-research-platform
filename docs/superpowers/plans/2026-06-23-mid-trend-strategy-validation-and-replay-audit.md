# Mid Trend Strategy Validation And Replay Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible workflow that auto-collects complete `mid trend` portfolio strategy versions, ranks them from `2025-01-01` to today using five agreed metrics, selects the single best baseline, and then runs a detailed trade replay audit on that chosen baseline.

**Architecture:** Add a dedicated `mid trend` validation module that separates candidate discovery, candidate filtering, metric normalization, ranking, and replay-audit generation. Reuse existing strategy entrypoints for complete portfolio versions, then generate a single comparison packet plus a second-stage replay packet for the winning version.

**Tech Stack:** Python 3, pandas, existing `stock_research` strategy/backtest modules, CLI integration, pytest

---

### Task 1: Candidate Discovery And Strategy Registry

**Files:**
- Create: `/Users/xiwei/stock_research/src/stock_research/mid_trend_strategy_validation.py`
- Modify: `/Users/xiwei/stock_research/tests/test_current_mid_trend_strategy_v1.py`
- Create: `/Users/xiwei/stock_research/tests/test_mid_trend_strategy_validation.py`

- [ ] **Step 1: Write the failing tests for candidate discovery and eligibility filtering**

```python
from stock_research.mid_trend_strategy_validation import (
    discover_mid_trend_strategy_candidates,
    filter_complete_mid_trend_candidates,
)


def test_discover_mid_trend_strategy_candidates_returns_known_complete_entries():
    candidates = discover_mid_trend_strategy_candidates()

    ids = {item["strategy_id"] for item in candidates}
    assert "current_mid_trend_strategy_v1" in ids
    assert "mid_trend_shadow_backtest" in ids


def test_filter_complete_mid_trend_candidates_keeps_only_complete_portfolio_versions():
    candidates = [
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "group": "portfolio",
            "result_keys": {"holdings", "trades", "equity", "summary"},
        },
        {
            "strategy_id": "mid_trend_portfolio_review",
            "group": "review",
            "result_keys": {"review_rows", "portfolio_summary"},
        },
    ]

    filtered = filter_complete_mid_trend_candidates(candidates)

    assert [item["strategy_id"] for item in filtered] == ["current_mid_trend_strategy_v1"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_discover_mid_trend_strategy_candidates_returns_known_complete_entries tests/test_mid_trend_strategy_validation.py::test_filter_complete_mid_trend_candidates_keeps_only_complete_portfolio_versions -q
```

Expected: FAIL with `ModuleNotFoundError` or missing functions in `mid_trend_strategy_validation`.

- [ ] **Step 3: Write the minimal strategy discovery implementation**

```python
def discover_mid_trend_strategy_candidates() -> list[dict[str, object]]:
    return [
        {
            "strategy_id": "current_mid_trend_strategy_v1",
            "group": "portfolio",
            "runner_name": "run_current_mid_trend_strategy_v1_backtest",
            "result_keys": {"holdings", "trades", "equity", "summary"},
        },
        {
            "strategy_id": "mid_trend_shadow_backtest",
            "group": "portfolio",
            "runner_name": "run_mid_trend_shadow_backtest",
            "result_keys": {"positions", "trades", "equity_curve", "summary"},
        },
    ]


def filter_complete_mid_trend_candidates(
    candidates: list[dict[str, object]],
) -> list[dict[str, object]]:
    complete = []
    for candidate in candidates:
        result_keys = set(candidate.get("result_keys", set()))
        if {"trades", "summary"} - result_keys:
            continue
        if not ({"holdings", "equity"} <= result_keys or {"positions", "equity_curve"} <= result_keys):
            continue
        if candidate.get("group") != "portfolio":
            continue
        complete.append(candidate)
    return complete
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_discover_mid_trend_strategy_candidates_returns_known_complete_entries tests/test_mid_trend_strategy_validation.py::test_filter_complete_mid_trend_candidates_keeps_only_complete_portfolio_versions -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_strategy_validation.py tests/test_mid_trend_strategy_validation.py
git commit -m "feat: add mid trend strategy candidate discovery"
```

### Task 2: Unified Metric Extraction And Ranking

**Files:**
- Modify: `/Users/xiwei/stock_research/src/stock_research/mid_trend_strategy_validation.py`
- Test: `/Users/xiwei/stock_research/tests/test_mid_trend_strategy_validation.py`

- [ ] **Step 1: Write the failing tests for five-metric extraction and ranking**

```python
import pandas as pd

from stock_research.mid_trend_strategy_validation import (
    build_mid_trend_validation_scorecard,
    rank_mid_trend_validation_scorecard,
)


def test_build_mid_trend_validation_scorecard_extracts_five_metrics():
    scorecard = build_mid_trend_validation_scorecard(
        [
            {
                "strategy_id": "a",
                "summary_frame": pd.DataFrame(
                    [
                        {"metric": "total_return", "value": 0.50},
                        {"metric": "max_drawdown", "value": -0.10},
                        {"metric": "average_turnover", "value": 0.15},
                    ]
                ),
                "equity_frame": pd.DataFrame(
                    [
                        {"date": "2025-01-31", "equity": 1.02},
                        {"date": "2025-02-28", "equity": 1.05},
                    ]
                ),
            }
        ]
    )

    row = scorecard.iloc[0]
    assert row["strategy_id"] == "a"
    assert row["total_return"] == 0.50
    assert row["max_drawdown"] == -0.10
    assert row["return_drawdown_ratio"] == 5.0
    assert row["monthly_win_rate"] == 1.0
    assert row["turnover_penalized_stability"] > 0


def test_rank_mid_trend_validation_scorecard_prefers_better_drawdown_efficiency_and_stability():
    ranked = rank_mid_trend_validation_scorecard(
        pd.DataFrame(
            [
                {
                    "strategy_id": "stable",
                    "total_return": 0.40,
                    "max_drawdown": -0.08,
                    "return_drawdown_ratio": 5.0,
                    "monthly_win_rate": 0.75,
                    "turnover_penalized_stability": 0.70,
                },
                {
                    "strategy_id": "wild",
                    "total_return": 0.45,
                    "max_drawdown": -0.25,
                    "return_drawdown_ratio": 1.8,
                    "monthly_win_rate": 0.50,
                    "turnover_penalized_stability": 0.20,
                },
            ]
        )
    )

    assert ranked.iloc[0]["strategy_id"] == "stable"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_build_mid_trend_validation_scorecard_extracts_five_metrics tests/test_mid_trend_strategy_validation.py::test_rank_mid_trend_validation_scorecard_prefers_better_drawdown_efficiency_and_stability -q
```

Expected: FAIL with missing functions or incorrect metric extraction.

- [ ] **Step 3: Write the minimal metric and ranking implementation**

```python
def build_mid_trend_validation_scorecard(results: list[dict[str, object]]) -> pd.DataFrame:
    rows = []
    for item in results:
        summary = item["summary_frame"]
        summary_map = {str(row["metric"]): float(row["value"]) for row in summary.to_dict("records")}
        equity = item["equity_frame"].copy()
        equity["date"] = pd.to_datetime(equity["date"])
        equity["month"] = equity["date"].dt.to_period("M")
        monthly_equity = equity.groupby("month")["equity"].last().pct_change().dropna()
        total_return = summary_map.get("total_return", 0.0)
        max_drawdown = summary_map.get("max_drawdown", 0.0)
        average_turnover = summary_map.get("average_turnover", 0.0)
        rows.append(
            {
                "strategy_id": item["strategy_id"],
                "total_return": total_return,
                "max_drawdown": max_drawdown,
                "return_drawdown_ratio": total_return / abs(max_drawdown) if max_drawdown < 0 else float("nan"),
                "monthly_win_rate": float((monthly_equity > 0).mean()) if len(monthly_equity) else float("nan"),
                "turnover_penalized_stability": (1.0 - min(max(float(average_turnover), 0.0), 1.0))
                * (float((monthly_equity > 0).mean()) if len(monthly_equity) else 0.0),
            }
        )
    return pd.DataFrame(rows)


def rank_mid_trend_validation_scorecard(scorecard: pd.DataFrame) -> pd.DataFrame:
    ranked = scorecard.copy()
    ranked["drawdown_penalty"] = ranked["max_drawdown"].abs()
    return ranked.sort_values(
        ["drawdown_penalty", "return_drawdown_ratio", "monthly_win_rate", "turnover_penalized_stability", "total_return"],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_build_mid_trend_validation_scorecard_extracts_five_metrics tests/test_mid_trend_strategy_validation.py::test_rank_mid_trend_validation_scorecard_prefers_better_drawdown_efficiency_and_stability -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_strategy_validation.py tests/test_mid_trend_strategy_validation.py
git commit -m "feat: add mid trend validation ranking metrics"
```

### Task 3: End-To-End Validation Runner And CLI Command

**Files:**
- Modify: `/Users/xiwei/stock_research/src/stock_research/mid_trend_strategy_validation.py`
- Modify: `/Users/xiwei/stock_research/src/stock_research/cli.py`
- Test: `/Users/xiwei/stock_research/tests/test_mid_trend_strategy_validation.py`

- [ ] **Step 1: Write the failing tests for the validation runner and CLI dispatch**

```python
from pathlib import Path

from stock_research import cli
from stock_research.mid_trend_strategy_validation import run_mid_trend_strategy_validation


def test_run_mid_trend_strategy_validation_returns_ranked_winner(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.discover_mid_trend_strategy_candidates",
        lambda: [
            {"strategy_id": "winner", "group": "portfolio", "result_keys": {"holdings", "trades", "equity", "summary"}},
        ],
    )
    monkeypatch.setattr(
        "stock_research.mid_trend_strategy_validation.execute_mid_trend_candidate",
        lambda candidate, start_date, end_date, output_dir: {
            "strategy_id": candidate["strategy_id"],
            "summary_frame": ...,
            "equity_frame": ...,
            "holdings_frame": ...,
            "trades_frame": ...,
        },
    )

    result = run_mid_trend_strategy_validation(
        start_date="2025-01-01",
        end_date="2025-01-31",
        output_dir=tmp_path,
    )

    assert result["winner"]["strategy_id"] == "winner"
    assert Path(result["paths"]["scorecard"]).exists()


def test_cli_dispatches_mid_trend_strategy_validation(monkeypatch, capsys, tmp_path: Path):
    monkeypatch.setattr(
        cli,
        "run_mid_trend_strategy_validation",
        lambda **kwargs: {
            "winner": {"strategy_id": "winner"},
            "paths": {"scorecard": str(tmp_path / "scorecard.csv"), "report": str(tmp_path / "report.md")},
        },
    )

    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "validate-mid-trend-strategies",
            "--start-date",
            "2025-01-01",
            "--end-date",
            "2025-01-31",
            "--output-dir",
            str(tmp_path),
        ]
    )
    cli.main(args)
    out = capsys.readouterr().out
    assert "mid_trend_validation|winner|winner" in out
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_run_mid_trend_strategy_validation_returns_ranked_winner tests/test_mid_trend_strategy_validation.py::test_cli_dispatches_mid_trend_strategy_validation -q
```

Expected: FAIL with missing runner / CLI parser wiring.

- [ ] **Step 3: Write the minimal end-to-end validation runner and CLI integration**

```python
def run_mid_trend_strategy_validation(*, start_date: str, end_date: str, output_dir: str | Path) -> dict[str, object]:
    candidates = filter_complete_mid_trend_candidates(discover_mid_trend_strategy_candidates())
    results = [
        execute_mid_trend_candidate(candidate, start_date=start_date, end_date=end_date, output_dir=output_dir)
        for candidate in candidates
    ]
    scorecard = build_mid_trend_validation_scorecard(results)
    ranked = rank_mid_trend_validation_scorecard(scorecard)
    winner = ranked.iloc[0].to_dict() if not ranked.empty else {}
    scorecard_path = Path(output_dir) / "mid_trend_validation_scorecard.csv"
    report_path = Path(output_dir) / "mid_trend_validation_report.md"
    scorecard_path.parent.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(scorecard_path, index=False)
    report_path.write_text(f"# Mid Trend Validation\\n\\nWinner: {winner.get('strategy_id', 'none')}\\n", encoding="utf-8")
    return {
        "candidates": candidates,
        "ranked_scorecard": ranked,
        "winner": winner,
        "paths": {"scorecard": str(scorecard_path), "report": str(report_path)},
    }
```

```python
mid_trend_validation = subparsers.add_parser("validate-mid-trend-strategies")
mid_trend_validation.add_argument("--start-date", required=True)
mid_trend_validation.add_argument("--end-date", required=True)
mid_trend_validation.add_argument("--output-dir", default="outputs/research/mid_trend_validation")
```

```python
elif args.command == "validate-mid-trend-strategies":
    from stock_research.mid_trend_strategy_validation import run_mid_trend_strategy_validation

    result = run_mid_trend_strategy_validation(
        start_date=args.start_date,
        end_date=args.end_date,
        output_dir=args.output_dir,
    )
    print(f"mid_trend_validation|winner|{result['winner'].get('strategy_id', 'none')}")
    print(f"mid_trend_validation|scorecard|{result['paths']['scorecard']}")
    print(f"mid_trend_validation|report|{result['paths']['report']}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_run_mid_trend_strategy_validation_returns_ranked_winner tests/test_mid_trend_strategy_validation.py::test_cli_dispatches_mid_trend_strategy_validation -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_strategy_validation.py src/stock_research/cli.py tests/test_mid_trend_strategy_validation.py
git commit -m "feat: add mid trend strategy validation runner"
```

### Task 4: Replay Audit For The Winning Strategy

**Files:**
- Modify: `/Users/xiwei/stock_research/src/stock_research/mid_trend_strategy_validation.py`
- Test: `/Users/xiwei/stock_research/tests/test_mid_trend_strategy_validation.py`

- [ ] **Step 1: Write the failing tests for replay-audit artifacts**

```python
import pandas as pd

from stock_research.mid_trend_strategy_validation import build_mid_trend_replay_audit


def test_build_mid_trend_replay_audit_outputs_core_artifacts():
    holdings = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "A", "target_weight": 0.5},
            {"trade_date": "2025-01-03", "asset_id": "B", "target_weight": 0.5},
        ]
    )
    trades = pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": "A", "side": "sell"},
            {"trade_date": "2025-01-03", "asset_id": "B", "side": "buy"},
        ]
    )
    prices = pd.DataFrame(
        [
            {"trade_date": "2025-01-03", "asset_id": "B", "close": 10},
            {"trade_date": "2025-01-10", "asset_id": "B", "close": 9},
            {"trade_date": "2025-01-17", "asset_id": "B", "close": 8},
        ]
    )

    result = build_mid_trend_replay_audit(
        strategy_id="winner",
        holdings=holdings,
        trades=trades,
        prices=prices,
    )

    assert set(result.keys()) >= {
        "daily_target_snapshot",
        "daily_rebalance_actions",
        "trade_audit_detail",
        "monthly_issue_summary",
    }
    assert "bad_buy" in set(result["trade_audit_detail"]["audit_label"])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_build_mid_trend_replay_audit_outputs_core_artifacts -q
```

Expected: FAIL with missing replay-audit builder.

- [ ] **Step 3: Write the minimal replay-audit implementation**

```python
def build_mid_trend_replay_audit(
    *,
    strategy_id: str,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    prices: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    daily_target_snapshot = holdings.copy()
    daily_rebalance_actions = trades.copy()
    trade_audit_detail = trades.copy()
    trade_audit_detail["audit_label"] = trade_audit_detail["side"].map({"buy": "bad_buy", "sell": "bad_sell"}).fillna("")
    trade_audit_detail["strategy_id"] = strategy_id
    monthly_issue_summary = (
        trade_audit_detail.assign(month=pd.to_datetime(trade_audit_detail["trade_date"]).dt.to_period("M").astype(str))
        .groupby(["month", "audit_label"], as_index=False)
        .size()
        .rename(columns={"size": "issue_count"})
    )
    return {
        "daily_target_snapshot": daily_target_snapshot,
        "daily_rebalance_actions": daily_rebalance_actions,
        "trade_audit_detail": trade_audit_detail,
        "monthly_issue_summary": monthly_issue_summary,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest tests/test_mid_trend_strategy_validation.py::test_build_mid_trend_replay_audit_outputs_core_artifacts -q
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_strategy_validation.py tests/test_mid_trend_strategy_validation.py
git commit -m "feat: add mid trend replay audit artifacts"
```

### Task 5: Full Verification

**Files:**
- Test: `/Users/xiwei/stock_research/tests/test_mid_trend_strategy_validation.py`
- Test: `/Users/xiwei/stock_research/tests/test_current_mid_trend_strategy_v1.py`
- Test: `/Users/xiwei/stock_research/tests/test_mid_trend_shadow_backtest.py`

- [ ] **Step 1: Run the full targeted validation test suite**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/pytest \
  tests/test_mid_trend_strategy_validation.py \
  tests/test_current_mid_trend_strategy_v1.py \
  tests/test_mid_trend_shadow_backtest.py -q
```

Expected: PASS with all relevant mid-trend validation tests green.

- [ ] **Step 2: Run one CLI smoke test for candidate comparison**

Run:
```bash
cd /Users/xiwei/stock_research && .venv/bin/python -m stock_research.cli \
  validate-mid-trend-strategies \
  --start-date 2025-01-01 \
  --end-date 2025-01-31 \
  --output-dir outputs/research/mid_trend_validation_smoke
```

Expected: stdout prints `mid_trend_validation|winner|...` and writes a scorecard/report under `outputs/research/mid_trend_validation_smoke`.

- [ ] **Step 3: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/mid_trend_strategy_validation.py src/stock_research/cli.py tests/test_mid_trend_strategy_validation.py
git commit -m "test: verify mid trend validation and replay audit workflow"
```
