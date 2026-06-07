# Mid Trend Portfolio Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable `Markdown + CSV` portfolio-review report for the mid-trend strategy that covers portfolio summary, Top5 full sections, Top6-10 short sections, and evidence-backed labels.

**Architecture:** Add a new `mid_trend_portfolio_review` module that consumes existing strategy replay outputs, watch-funnel Top10, PIT report features, and enriched research-packet candidates. Keep report generation separate from strategy state and keep all judgments traceable to structured fields. Wire it into `cli.py` with a dedicated command and validate with synthetic tests plus one real-window smoke run.

**Tech Stack:** Python, pandas, existing project CSV outputs, `research.stock_report_feature_daily`, existing CLI pattern, pytest

---

## File Map

- Create: `src/stock_research/mid_trend_portfolio_review.py`
  - Build portfolio review rows from holdings, trades, Top10 candidates, research packet candidates, and PIT report evidence.
  - Render Markdown and write CSV.

- Modify: `src/stock_research/cli.py`
  - Add `build-mid-trend-portfolio-review` parser and command dispatch.

- Test: `tests/test_mid_trend_portfolio_review.py`
  - Cover holding-only day, rebalance day, label generation, Top5 full fields, Top6-10 short fields, Markdown/CSV output, and CLI dispatch.

- Optional reuse only, no behavior changes unless required by tests:
  - `src/stock_research/mid_trend_research_packet.py`
  - `src/stock_research/stock_report_research.py`
  - `src/stock_research/mid_trend_shadow_weekly_control.py`

---

### Task 1: Build Core Review Rows

**Files:**
- Create: `src/stock_research/mid_trend_portfolio_review.py`
- Test: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Write the failing tests for row building and label generation**

```python
from pathlib import Path

import pandas as pd

from stock_research.mid_trend_portfolio_review import (
    build_mid_trend_portfolio_review_from_frames,
)


def test_portfolio_review_builds_top5_full_and_top6_10_short_sections(tmp_path: Path):
    top10 = pd.DataFrame(
        [
            {"trade_date": "2026-06-04", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "shadow_top10_rank": 1, "mid_trend_funnel_score": 84.7, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "电子"},
            {"trade_date": "2026-06-04", "asset_id": "CN:SZ:300201", "ts_code": "300201.SZ", "stock_name": "海伦哲", "shadow_top10_rank": 2, "mid_trend_funnel_score": 84.3, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "neutral", "industry_name": "机械"},
            {"trade_date": "2026-06-04", "asset_id": "CN:SH:603931", "ts_code": "603931.SH", "stock_name": "格林达", "shadow_top10_rank": 3, "mid_trend_funnel_score": 84.0, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "化工"},
            {"trade_date": "2026-06-04", "asset_id": "CN:SH:688390", "ts_code": "688390.SH", "stock_name": "固德威", "shadow_top10_rank": 4, "mid_trend_funnel_score": 82.4, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "电力设备"},
            {"trade_date": "2026-06-04", "asset_id": "CN:SZ:300831", "ts_code": "300831.SZ", "stock_name": "派瑞股份", "shadow_top10_rank": 5, "mid_trend_funnel_score": 70.1, "mid_trend_layer": "high_elasticity_watch", "market_regime": "mainline", "mainline_status": "neutral", "industry_name": "电子"},
            {"trade_date": "2026-06-04", "asset_id": "CN:SH:688301", "ts_code": "688301.SH", "stock_name": "奕瑞科技", "shadow_top10_rank": 6, "mid_trend_funnel_score": 82.3, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "医疗器械"},
        ]
    )
    holdings = pd.DataFrame(
        [
            {"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-04", "asset_id": "CN:SH:600183", "weight": 0.2},
            {"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-04", "asset_id": "CN:SZ:300201", "weight": 0.2},
            {"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-04", "asset_id": "CN:SH:603931", "weight": 0.2},
            {"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-04", "asset_id": "CN:SH:688390", "weight": 0.2},
            {"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-04", "asset_id": "CN:SZ:300831", "weight": 0.2},
        ]
    )
    trades = pd.DataFrame(
        [
            {"variant_name": "top5_weekly_max_2_replacements", "trade_date": "2026-06-04", "asset_id": "CN:SH:603931", "side": "buy", "turnover_contribution": 0.2, "transaction_cost": 0.0004, "reason": "weekly_rebalance"},
            {"variant_name": "top5_weekly_max_2_replacements", "trade_date": "2026-06-04", "asset_id": "CN:SZ:000811", "side": "sell", "turnover_contribution": 0.2, "transaction_cost": 0.0004, "reason": "weekly_rebalance"},
        ]
    )
    research = pd.DataFrame(
        [
            {"trade_date": "2026-06-04", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "broker_report_count_90d": 3, "research_support_score_pit": 33, "target_price_median_pit": 103.5, "target_upside_median_pit": pd.NA, "broker_coverage_count_pit": 3, "pdf_target_price_count_90d": 3, "pdf_target_price_high_confidence_count_90d": 1, "pdf_profit_forecast_count_90d": 3, "pdf_risk_section_count_90d": 3, "latest_pdf_risk_summary": "下游需求不及预期风险；行业竞争加剧风险。", "fundamental_hard_risk": "no_clear_hard_risk", "fundamental_quality_note": "No obvious hard fundamental risk."},
            {"trade_date": "2026-06-04", "asset_id": "CN:SZ:300201", "ts_code": "300201.SZ", "broker_report_count_90d": 0, "research_support_score_pit": 0, "target_price_median_pit": pd.NA, "target_upside_median_pit": pd.NA, "broker_coverage_count_pit": 0, "pdf_target_price_count_90d": 0, "pdf_target_price_high_confidence_count_90d": 0, "pdf_profit_forecast_count_90d": 0, "pdf_risk_section_count_90d": 0, "latest_pdf_risk_summary": "", "fundamental_hard_risk": "no_clear_hard_risk", "fundamental_quality_note": "No obvious hard fundamental risk."},
        ]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=trades,
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    review = result["review_rows"]
    assert set(review["section"]) == {"top5", "top6_10"}
    assert review[review["section"].eq("top5")]["final_label"].notna().all()
    assert review[review["section"].eq("top6_10")]["final_label"].eq("仅讨论").all()
    assert "main_positive_evidence" in review.columns
    assert "latest_pdf_risk_summary" in review.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q tests/test_mid_trend_portfolio_review.py::test_portfolio_review_builds_top5_full_and_top6_10_short_sections
```

Expected:

- import error or missing module/function failure for `mid_trend_portfolio_review`

- [ ] **Step 3: Write the minimal review builder implementation**

Create `src/stock_research/mid_trend_portfolio_review.py` with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def build_mid_trend_portfolio_review_from_frames(
    *,
    trade_date: str,
    strategy_variant: str,
    top10: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    research_packet_candidates: pd.DataFrame,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    normalized_top10 = _normalize_top10(top10, trade_date)
    normalized_holdings = _normalize_holdings(holdings, trade_date, strategy_variant)
    normalized_trades = _normalize_trades(trades, trade_date, strategy_variant)
    normalized_research = _normalize_research(research_packet_candidates, trade_date)
    review_rows = _build_review_rows(
        normalized_top10,
        normalized_holdings,
        normalized_trades,
        normalized_research,
    )
    portfolio_summary = _build_portfolio_summary(
        trade_date=trade_date,
        strategy_variant=strategy_variant,
        review_rows=review_rows,
        trades=normalized_trades,
    )
    markdown = _render_markdown(portfolio_summary, review_rows)
    result = {
        "portfolio_summary": portfolio_summary,
        "review_rows": review_rows,
        "report": markdown,
        "paths": {},
    }
    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        review_path = output / f"mid_trend_portfolio_review_{trade_date}.csv"
        report_path = output / f"mid_trend_portfolio_review_{trade_date}.md"
        review_rows.to_csv(review_path, index=False)
        report_path.write_text(markdown, encoding="utf-8")
        result["paths"] = {"csv": str(review_path), "report": str(report_path)}
    return result
```

Also implement helpers:

- `_normalize_top10`
- `_normalize_holdings`
- `_normalize_trades`
- `_normalize_research`
- `_build_review_rows`
- `_build_portfolio_summary`
- `_render_markdown`

Minimal row-building rules:

- `top5` means `shadow_top10_rank <= 5`
- `top6_10` means `6 <= shadow_top10_rank <= 10`
- `is_current_holding = asset_id in holdings`
- `is_new_buy = asset_id in buy trades`
- `is_candidate_sell = asset_id in sell trades`
- `final_label`:
  - Top6-10: `仅讨论`
  - Top5 + holding + `research_support_score_pit >= 20`: `高优先级持有`
  - Top5 + holding otherwise: `低优先级持有`
  - Top5 + not holding + `is_new_buy`: `候选调入`
  - not Top5 + `is_candidate_sell`: `候选调出`

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q tests/test_mid_trend_portfolio_review.py::test_portfolio_review_builds_top5_full_and_top6_10_short_sections
```

Expected:

- `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/mid_trend_portfolio_review.py tests/test_mid_trend_portfolio_review.py
git commit -m "feat: add mid-trend portfolio review builder"
```

### Task 2: Cover Rebalance and Holding-Only Cases

**Files:**
- Modify: `tests/test_mid_trend_portfolio_review.py`
- Modify: `src/stock_research/mid_trend_portfolio_review.py`

- [ ] **Step 1: Write failing tests for holding-only and rebalance-day behavior**

```python
def test_portfolio_review_marks_rebalance_reasons_and_action_summary(tmp_path: Path):
    top10 = pd.DataFrame(
        [
            {"trade_date": "2026-06-01", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "shadow_top10_rank": 1, "mid_trend_funnel_score": 84.7, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "电子"},
            {"trade_date": "2026-06-01", "asset_id": "CN:SH:603931", "ts_code": "603931.SH", "stock_name": "格林达", "shadow_top10_rank": 2, "mid_trend_funnel_score": 84.0, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "化工"},
        ]
    )
    holdings = pd.DataFrame(
        [{"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-01", "asset_id": "CN:SH:600183", "weight": 0.5},
         {"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-01", "asset_id": "CN:SH:603931", "weight": 0.5}]
    )
    trades = pd.DataFrame(
        [{"variant_name": "top5_weekly_max_2_replacements", "trade_date": "2026-06-01", "asset_id": "CN:SH:603931", "side": "buy", "turnover_contribution": 0.5, "transaction_cost": 0.001, "reason": "weekly_rebalance"}]
    )
    research = pd.DataFrame()

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-01",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=trades,
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    summary = result["portfolio_summary"]
    assert summary["rebalance_triggered"] is True
    assert summary["buy_count"] == 1
    assert "weekly_rebalance" in summary["rebalance_reason_summary"]


def test_portfolio_review_holding_only_day_has_no_trade_reason(tmp_path: Path):
    top10 = pd.DataFrame(
        [{"trade_date": "2026-06-02", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "shadow_top10_rank": 1, "mid_trend_funnel_score": 84.7, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "电子"}]
    )
    holdings = pd.DataFrame(
        [{"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-01", "asset_id": "CN:SH:600183", "weight": 1.0}]
    )
    trades = pd.DataFrame(columns=["variant_name", "trade_date", "asset_id", "side", "turnover_contribution", "transaction_cost", "reason"])
    research = pd.DataFrame()

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-02",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=trades,
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    assert result["portfolio_summary"]["rebalance_triggered"] is False
    assert result["review_rows"].iloc[0]["why_hold_or_change"] == "holding_day_no_rebalance"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q \
  tests/test_mid_trend_portfolio_review.py::test_portfolio_review_marks_rebalance_reasons_and_action_summary \
  tests/test_mid_trend_portfolio_review.py::test_portfolio_review_holding_only_day_has_no_trade_reason
```

Expected:

- failures on missing summary fields or incorrect review-row reasoning

- [ ] **Step 3: Extend implementation for portfolio summary and narrative fields**

Update `src/stock_research/mid_trend_portfolio_review.py` to include:

```python
summary = {
    "trade_date": trade_date,
    "strategy_variant": strategy_variant,
    "review_mode": "rebalance_review" if not trades.empty else "holding_review",
    "current_position_count": int(review_rows["is_current_holding"].sum()),
    "top5_count": int(review_rows["section"].eq("top5").sum()),
    "top10_count": int(len(review_rows)),
    "rebalance_triggered": bool(not trades.empty),
    "buy_count": int(trades["side"].eq("buy").sum()),
    "sell_count": int(trades["side"].eq("sell").sum()),
    "turnover": float(pd.to_numeric(trades["turnover_contribution"], errors="coerce").fillna(0).sum()),
    "transaction_cost": float(pd.to_numeric(trades["transaction_cost"], errors="coerce").fillna(0).sum()),
    "rebalance_reason_summary": "|".join(sorted(set(trades["reason"].dropna().astype(str)))) if not trades.empty else "",
}
```

And row-level defaults:

```python
if row["is_new_buy"]:
    row["why_hold_or_change"] = "rebalance_day_new_buy"
elif row["is_candidate_sell"]:
    row["why_hold_or_change"] = "rebalance_day_candidate_sell"
elif row["is_current_holding"] and not rebalance_triggered:
    row["why_hold_or_change"] = "holding_day_no_rebalance"
else:
    row["why_hold_or_change"] = "discussion_only"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q tests/test_mid_trend_portfolio_review.py
```

Expected:

- all `test_mid_trend_portfolio_review.py` tests pass

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/mid_trend_portfolio_review.py tests/test_mid_trend_portfolio_review.py
git commit -m "feat: add portfolio review summary and label logic"
```

### Task 3: Add CLI and Output Contract

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_mid_trend_portfolio_review.py`

- [ ] **Step 1: Write failing CLI dispatch test**

```python
from pathlib import Path

import pandas as pd

from stock_research import cli


def test_cli_dispatches_mid_trend_portfolio_review(monkeypatch, capsys, tmp_path: Path):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "review_rows": pd.DataFrame([{"ts_code": "600183.SH"}]),
            "paths": {
                "csv": str(tmp_path / "review.csv"),
                "report": str(tmp_path / "review.md"),
            },
        }

    monkeypatch.setattr(cli, "run_mid_trend_portfolio_review", fake_run)

    cli.main_for_args(
        [
            "build-mid-trend-portfolio-review",
            "--trade-date", "2026-06-04",
            "--strategy-variant", "top5_weekly_max_2_replacements",
            "--top10-path", "outputs/research/mid_trend_shadow_top10.csv",
            "--holdings-path", "outputs/research/mid_trend_shadow_weekly_control_positions.csv",
            "--trades-path", "outputs/research/mid_trend_shadow_weekly_control_trades.csv",
            "--research-packet-path", "outputs/research/mid_trend_research_packet_candidates.csv",
            "--output-dir", str(tmp_path),
        ]
    )

    assert captured["trade_date"] == "2026-06-04"
    assert captured["strategy_variant"] == "top5_weekly_max_2_replacements"
    out = capsys.readouterr().out
    assert "mid_trend_portfolio_review|csv|" in out
    assert "mid_trend_portfolio_review|rows|1" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q tests/test_mid_trend_portfolio_review.py::test_cli_dispatches_mid_trend_portfolio_review
```

Expected:

- parser or dispatch failure for missing command

- [ ] **Step 3: Add CLI parser and dispatch**

Modify `src/stock_research/cli.py`:

```python
from stock_research.mid_trend_portfolio_review import run_mid_trend_portfolio_review
```

Add parser:

```python
mid_trend_portfolio_review = subparsers.add_parser("build-mid-trend-portfolio-review")
mid_trend_portfolio_review.add_argument("--trade-date", required=True)
mid_trend_portfolio_review.add_argument("--strategy-variant", required=True)
mid_trend_portfolio_review.add_argument("--top10-path", required=True)
mid_trend_portfolio_review.add_argument("--holdings-path", required=True)
mid_trend_portfolio_review.add_argument("--trades-path", required=True)
mid_trend_portfolio_review.add_argument("--research-packet-path", required=True)
mid_trend_portfolio_review.add_argument("--output-dir", default="outputs/research")
```

Add dispatch:

```python
elif args.command == "build-mid-trend-portfolio-review":
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

Also add `run_mid_trend_portfolio_review()` in the new module to read CSV inputs and delegate into `build_mid_trend_portfolio_review_from_frames()`.

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q tests/test_mid_trend_portfolio_review.py::test_cli_dispatches_mid_trend_portfolio_review
```

Expected:

- `1 passed`

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/cli.py src/stock_research/mid_trend_portfolio_review.py tests/test_mid_trend_portfolio_review.py
git commit -m "feat: add portfolio review cli"
```

### Task 4: Real-Window Smoke and Full Verification

**Files:**
- Modify: `tests/test_mid_trend_portfolio_review.py`
- Use existing outputs under `outputs/research/`

- [ ] **Step 1: Write a synthetic output-shape test for Markdown and CSV**

```python
def test_portfolio_review_writes_markdown_and_csv(tmp_path: Path):
    top10 = pd.DataFrame(
        [{"trade_date": "2026-06-04", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "shadow_top10_rank": 1, "mid_trend_funnel_score": 84.7, "mid_trend_layer": "stable_trend_watch", "market_regime": "mainline", "mainline_status": "sustained_mainline", "industry_name": "电子"}]
    )
    holdings = pd.DataFrame(
        [{"variant_name": "top5_weekly_max_2_replacements", "rebalance_date": "2026-06-04", "asset_id": "CN:SH:600183", "weight": 1.0}]
    )
    trades = pd.DataFrame(columns=["variant_name", "trade_date", "asset_id", "side", "turnover_contribution", "transaction_cost", "reason"])
    research = pd.DataFrame(
        [{"trade_date": "2026-06-04", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "broker_report_count_90d": 3, "research_support_score_pit": 33, "fundamental_hard_risk": "no_clear_hard_risk"}]
    )

    result = build_mid_trend_portfolio_review_from_frames(
        trade_date="2026-06-04",
        strategy_variant="top5_weekly_max_2_replacements",
        top10=top10,
        holdings=holdings,
        trades=trades,
        research_packet_candidates=research,
        output_dir=tmp_path,
    )

    assert Path(result["paths"]["csv"]).exists()
    assert Path(result["paths"]["report"]).exists()
    report = Path(result["paths"]["report"]).read_text(encoding="utf-8")
    assert "Portfolio Summary" in report
    assert "Top5 Execution Pool" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q tests/test_mid_trend_portfolio_review.py::test_portfolio_review_writes_markdown_and_csv
```

Expected:

- report section-name failure or missing output-path failure

- [ ] **Step 3: Finalize renderer and run real-window smoke command**

Ensure `_render_markdown()` produces sections:

```python
lines = [
    "# Mid Trend Portfolio Review",
    "",
    "## Portfolio Summary",
    ...
    "## Top5 Execution Pool",
    ...
    "## Top6-10 Discussion Pool",
]
```

Run the real smoke command:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/python -m stock_research.cli build-mid-trend-portfolio-review \
  --trade-date 2026-06-01 \
  --strategy-variant top5_weekly_max_2_replacements \
  --top10-path outputs/research/mid_trend_watch_funnel_context_fixed_20260602/mid_trend_watch_top10.csv \
  --holdings-path outputs/research/mid_trend_shadow_weekly_control_context_fixed_20260602/mid_trend_shadow_weekly_control_positions.csv \
  --trades-path outputs/research/mid_trend_shadow_weekly_control_context_fixed_20260602/mid_trend_shadow_weekly_control_trades.csv \
  --research-packet-path outputs/research/mid_trend_research_packet_20260602_pdf_enriched/mid_trend_research_packet_candidates.csv \
  --output-dir outputs/research/mid_trend_portfolio_review_20260601
```

Expected:

- Markdown written
- CSV written
- Top5 rows present
- Top6-10 rows present

- [ ] **Step 4: Run full verification**

Run:

```bash
PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/pytest -q
```

Expected:

- full suite passes

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/mid_trend_portfolio_review.py src/stock_research/cli.py tests/test_mid_trend_portfolio_review.py
git commit -m "feat: add mid-trend portfolio review report"
```
