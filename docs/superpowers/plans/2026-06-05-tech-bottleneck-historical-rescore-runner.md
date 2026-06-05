# Tech Bottleneck Historical Rescore Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a historical re-scoring experiment runner that consumes existing candidate snapshots with `tech_bottleneck_score`, joins future bars, and reports 20D/60D diagnostics plus 120D/250D/500D validation.

**Architecture:** Add a focused experiment module that works on DataFrames and file inputs. It does not scan the full market, does not generate new investment advice, and does not require database schema changes; it only evaluates scored candidates from existing pools.

**Tech Stack:** Python 3.11+, pandas, argparse CLI, pytest, existing `stock_research` CLI conventions.

---

## Preconditions

This plan should be executed after the `tech-bottleneck-discovery` implementation branch is merged or rebased into the working branch. It expects the following functions and command from that branch:

- `stock_research.tech_bottleneck_discovery.build_tech_bottleneck_packets`
- `stock_research.tech_bottleneck_discovery.run_tech_bottleneck_discovery_from_files`
- CLI command: `tech-bottleneck-discovery`

This plan adds a second command for evaluation:

```bash
stock-research tech-bottleneck-historical-rescore \
  --packets-csv outputs/tech_bottleneck_discovery/example/packets.csv \
  --bars-csv data/manual/tech_bottleneck_bars_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/historical_rescore_example \
  --run-id tech-bottleneck-historical-example
```

## File Structure

- Create `src/stock_research/tech_bottleneck_experiment.py`
  - Owns horizon outcome calculation, bucket assignment, bucket summary, markdown rendering, artifact writing, and file runner.
- Modify `src/stock_research/cli.py`
  - Adds `tech-bottleneck-historical-rescore` command.
- Create `tests/test_tech_bottleneck_experiment.py`
  - Unit tests for forward returns, partial horizons, buckets, summary metrics, artifact writing, and file runner.
- Create `data/manual/tech_bottleneck_bars_example.csv`
  - Small deterministic price fixture for CLI smoke.
- Modify `docs/tech-bottleneck-discovery-runbook.md`
  - Adds the historical re-score experiment command and horizon interpretation.

## Data Contracts

### Packets / Scored Candidates CSV

Required columns:

- `run_id`
- `asset_id`
- `stock_name`
- `trade_date`
- `candidate_state`
- `tech_bottleneck_score`
- `chokepoint_score`
- `underpricing_score`
- `evidence_score`
- `catalyst_score`
- `risk_penalty`

Optional columns:

- `candidate_source`
- `base_strategy_rank`
- `base_strategy_score`
- `review_decision`

### Bars CSV

Required columns:

- `asset_id`
- `trade_date`
- `close`

Optional columns:

- `open`
- `high`
- `low`
- `amount`

### Output Artifacts

For a run with `--run-id tech-bottleneck-historical-example`:

- `outcomes.csv`: one row per candidate with horizon returns and max drawdowns.
- `bucket_summary.csv`: one row per score bucket and horizon role.
- `summary.md`: human-readable experiment summary.

## Task 1: Forward Horizon Outcomes

**Files:**
- Create: `src/stock_research/tech_bottleneck_experiment.py`
- Test: `tests/test_tech_bottleneck_experiment.py`

- [ ] **Step 1: Write failing tests for horizon outcomes**

Create `tests/test_tech_bottleneck_experiment.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from stock_research.tech_bottleneck_experiment import (
    build_historical_rescore_report,
    render_historical_rescore_summary,
    run_historical_rescore_from_files,
    write_historical_rescore_artifacts,
)


def _packets() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "run_id": "packet-run",
                "candidate_source": "industry-focus",
                "asset_id": "A",
                "stock_name": "高分材料",
                "trade_date": "2026-01-02",
                "candidate_state": "conviction_candidate",
                "tech_bottleneck_score": 4.5,
                "chokepoint_score": 35.0,
                "underpricing_score": 32.0,
                "evidence_score": 5.0,
                "catalyst_score": 4.0,
                "risk_penalty": 1.0,
                "base_strategy_rank": 3,
                "base_strategy_score": 0.82,
            },
            {
                "run_id": "packet-run",
                "candidate_source": "industry-focus",
                "asset_id": "B",
                "stock_name": "中分设备",
                "trade_date": "2026-01-02",
                "candidate_state": "research",
                "tech_bottleneck_score": 2.8,
                "chokepoint_score": 23.0,
                "underpricing_score": 25.0,
                "evidence_score": 2.5,
                "catalyst_score": 2.0,
                "risk_penalty": 2.0,
                "base_strategy_rank": 8,
                "base_strategy_score": 0.70,
            },
            {
                "run_id": "packet-run",
                "candidate_source": "industry-focus",
                "asset_id": "C",
                "stock_name": "低分概念",
                "trade_date": "2026-01-02",
                "candidate_state": "reject",
                "tech_bottleneck_score": 1.1,
                "chokepoint_score": 10.0,
                "underpricing_score": 15.0,
                "evidence_score": 1.0,
                "catalyst_score": 1.0,
                "risk_penalty": 4.0,
                "base_strategy_rank": 12,
                "base_strategy_score": 0.60,
            },
        ]
    )


def _bars() -> pd.DataFrame:
    rows = []
    price_paths = {
        "A": [10.0, 11.0, 12.0, 13.0, 15.0, 18.0],
        "B": [20.0, 19.0, 21.0, 20.0, 22.0, 23.0],
        "C": [30.0, 27.0, 24.0, 22.0, 21.0, 20.0],
    }
    dates = [
        "2026-01-02",
        "2026-01-05",
        "2026-01-06",
        "2026-01-07",
        "2026-01-08",
        "2026-01-09",
    ]
    for asset_id, prices in price_paths.items():
        for trade_date, close in zip(dates, prices, strict=True):
            rows.append({"asset_id": asset_id, "trade_date": trade_date, "close": close})
    return pd.DataFrame(rows)


def test_build_historical_rescore_report_computes_horizon_returns_and_drawdowns() -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(1, 2, 4, 5),
    )
    outcomes = report["outcomes"].set_index("asset_id")

    assert outcomes.loc["A", "bucket"] == "high"
    assert outcomes.loc["A", "return_1d"] == 0.10
    assert outcomes.loc["A", "return_4d"] == 0.50
    assert outcomes.loc["A", "max_drawdown_4d"] == 0.0
    assert outcomes.loc["A", "horizon_5d_status"] == "complete"

    assert outcomes.loc["C", "bucket"] == "low"
    assert round(float(outcomes.loc["C", "return_4d"]), 4) == -0.30
    assert round(float(outcomes.loc["C", "max_drawdown_4d"]), 4) == -0.30
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_experiment.py::test_build_historical_rescore_report_computes_horizon_returns_and_drawdowns -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stock_research.tech_bottleneck_experiment'`.

- [ ] **Step 3: Implement outcome calculation**

Create `src/stock_research/tech_bottleneck_experiment.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_HORIZONS = (20, 60, 120, 250, 500)
OUTCOME_BASE_COLUMNS = [
    "run_id",
    "candidate_source",
    "asset_id",
    "stock_name",
    "trade_date",
    "candidate_state",
    "bucket",
    "tech_bottleneck_score",
    "base_strategy_rank",
    "base_strategy_score",
]


def build_historical_rescore_report(
    *,
    packets: pd.DataFrame,
    bars: pd.DataFrame,
    run_id: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, pd.DataFrame]:
    normalized_packets = _normalize_packets(packets)
    normalized_bars = _normalize_bars(bars)
    outcomes = _build_outcomes(
        packets=normalized_packets,
        bars=normalized_bars,
        run_id=run_id,
        horizons=horizons,
    )
    bucket_summary = _build_bucket_summary(outcomes=outcomes, horizons=horizons)
    return {"outcomes": outcomes, "bucket_summary": bucket_summary}


def _build_outcomes(
    *,
    packets: pd.DataFrame,
    bars: pd.DataFrame,
    run_id: str,
    horizons: tuple[int, ...],
) -> pd.DataFrame:
    if packets.empty:
        return pd.DataFrame(columns=_outcome_columns(horizons))
    bars_by_asset = {
        asset_id: frame.sort_values("trade_date").reset_index(drop=True)
        for asset_id, frame in bars.groupby("asset_id", sort=False)
    }
    rows: list[dict[str, Any]] = []
    for packet in packets.to_dict("records"):
        asset_id = str(packet.get("asset_id", ""))
        asset_bars = bars_by_asset.get(asset_id, pd.DataFrame(columns=bars.columns))
        row = {
            "run_id": run_id,
            "candidate_source": _safe_text(packet.get("candidate_source")) or "unknown",
            "asset_id": asset_id,
            "stock_name": _safe_text(packet.get("stock_name")),
            "trade_date": _iso_date(packet.get("trade_date")),
            "candidate_state": _safe_text(packet.get("candidate_state")),
            "bucket": _bucket_for_score(packet.get("tech_bottleneck_score")),
            "tech_bottleneck_score": _safe_float(packet.get("tech_bottleneck_score")),
            "base_strategy_rank": _safe_float(packet.get("base_strategy_rank")),
            "base_strategy_score": _safe_float(packet.get("base_strategy_score")),
        }
        row.update(_horizon_metrics(asset_bars, row["trade_date"], horizons))
        rows.append(row)
    return pd.DataFrame(rows, columns=_outcome_columns(horizons))


def _horizon_metrics(
    asset_bars: pd.DataFrame,
    trade_date: str,
    horizons: tuple[int, ...],
) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    frame = asset_bars[asset_bars["trade_date"] >= pd.to_datetime(trade_date)].copy()
    frame = frame.sort_values("trade_date").reset_index(drop=True)
    if frame.empty:
        for horizon in horizons:
            metrics[f"return_{horizon}d"] = pd.NA
            metrics[f"max_drawdown_{horizon}d"] = pd.NA
            metrics[f"horizon_{horizon}d_status"] = "missing_entry_bar"
        return metrics
    entry_close = float(frame.iloc[0]["close"])
    for horizon in horizons:
        if len(frame) <= horizon:
            metrics[f"return_{horizon}d"] = pd.NA
            metrics[f"max_drawdown_{horizon}d"] = pd.NA
            metrics[f"horizon_{horizon}d_status"] = "partial"
            continue
        window = frame.iloc[: horizon + 1]
        end_close = float(window.iloc[-1]["close"])
        returns = window["close"].astype(float) / entry_close - 1.0
        metrics[f"return_{horizon}d"] = round(end_close / entry_close - 1.0, 6)
        metrics[f"max_drawdown_{horizon}d"] = round(float(returns.min()), 6)
        metrics[f"horizon_{horizon}d_status"] = "complete"
    return metrics


def _build_bucket_summary(*, outcomes: pd.DataFrame, horizons: tuple[int, ...]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if outcomes.empty:
        return pd.DataFrame(columns=_bucket_summary_columns(horizons))
    pool_means = {
        horizon: pd.to_numeric(outcomes[f"return_{horizon}d"], errors="coerce").mean()
        for horizon in horizons
    }
    for bucket in ["high", "medium", "low"]:
        bucket_frame = outcomes[outcomes["bucket"] == bucket]
        row: dict[str, Any] = {"bucket": bucket, "candidate_count": int(len(bucket_frame))}
        for horizon in horizons:
            returns = pd.to_numeric(bucket_frame[f"return_{horizon}d"], errors="coerce")
            drawdowns = pd.to_numeric(bucket_frame[f"max_drawdown_{horizon}d"], errors="coerce")
            complete = bucket_frame[f"horizon_{horizon}d_status"].eq("complete")
            mean_return = returns.mean()
            row[f"complete_count_{horizon}d"] = int(complete.sum())
            row[f"mean_return_{horizon}d"] = _round_or_na(mean_return)
            row[f"median_return_{horizon}d"] = _round_or_na(returns.median())
            row[f"win_rate_{horizon}d"] = _round_or_na((returns > 0).mean())
            row[f"mean_max_drawdown_{horizon}d"] = _round_or_na(drawdowns.mean())
            row[f"excess_return_{horizon}d"] = _round_or_na(mean_return - pool_means[horizon])
        rows.append(row)
    return pd.DataFrame(rows, columns=_bucket_summary_columns(horizons))


def render_historical_rescore_summary(
    *,
    run_id: str,
    bucket_summary: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> str:
    lines = [
        "# tech-bottleneck historical rescore summary",
        "",
        f"- Run ID: `{run_id}`",
        "- Short-term diagnostics: 20D / 60D",
        "- Primary validation: 120D / 250D",
        "- Long-cycle observation: 500D",
        "",
        "## Buckets",
        "",
    ]
    for row in bucket_summary.to_dict("records"):
        lines.append(f"### {row['bucket']}")
        lines.append(f"- Candidates: {row['candidate_count']}")
        for horizon in horizons:
            lines.append(
                f"- {horizon}D mean return: {row.get(f'mean_return_{horizon}d')} "
                f"excess: {row.get(f'excess_return_{horizon}d')}"
            )
        lines.append("")
    return "\n".join(lines)


def write_historical_rescore_artifacts(
    *,
    report: dict[str, pd.DataFrame],
    output_dir: Path,
    run_id: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = output_dir / "outcomes.csv"
    bucket_summary_path = output_dir / "bucket_summary.csv"
    summary_path = output_dir / "summary.md"
    report["outcomes"].to_csv(outcomes_path, index=False)
    report["bucket_summary"].to_csv(bucket_summary_path, index=False)
    summary_path.write_text(
        render_historical_rescore_summary(
            run_id=run_id,
            bucket_summary=report["bucket_summary"],
            horizons=horizons,
        ),
        encoding="utf-8",
    )
    return {"outcomes": outcomes_path, "bucket_summary": bucket_summary_path, "summary": summary_path}


def run_historical_rescore_from_files(
    *,
    packets_csv: Path,
    bars_csv: Path,
    output_dir: Path,
    run_id: str,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Path]:
    packets = pd.read_csv(packets_csv)
    bars = pd.read_csv(bars_csv)
    report = build_historical_rescore_report(
        packets=packets,
        bars=bars,
        run_id=run_id,
        horizons=horizons,
    )
    return write_historical_rescore_artifacts(
        report=report,
        output_dir=output_dir,
        run_id=run_id,
        horizons=horizons,
    )


def _normalize_packets(packets: pd.DataFrame) -> pd.DataFrame:
    normalized = packets.copy()
    for column in OUTCOME_BASE_COLUMNS:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["tech_bottleneck_score"] = pd.to_numeric(normalized["tech_bottleneck_score"], errors="coerce")
    return normalized


def _normalize_bars(bars: pd.DataFrame) -> pd.DataFrame:
    normalized = bars.copy()
    for column in ["asset_id", "trade_date", "close"]:
        if column not in normalized.columns:
            normalized[column] = pd.NA
    normalized["asset_id"] = normalized["asset_id"].map(_safe_text)
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="coerce")
    normalized["close"] = pd.to_numeric(normalized["close"], errors="coerce")
    normalized = normalized.dropna(subset=["asset_id", "trade_date", "close"])
    return normalized.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)


def _outcome_columns(horizons: tuple[int, ...]) -> list[str]:
    columns = list(OUTCOME_BASE_COLUMNS)
    for horizon in horizons:
        columns.extend(
            [
                f"return_{horizon}d",
                f"max_drawdown_{horizon}d",
                f"horizon_{horizon}d_status",
            ]
        )
    return columns


def _bucket_summary_columns(horizons: tuple[int, ...]) -> list[str]:
    columns = ["bucket", "candidate_count"]
    for horizon in horizons:
        columns.extend(
            [
                f"complete_count_{horizon}d",
                f"mean_return_{horizon}d",
                f"median_return_{horizon}d",
                f"win_rate_{horizon}d",
                f"mean_max_drawdown_{horizon}d",
                f"excess_return_{horizon}d",
            ]
        )
    return columns


def _bucket_for_score(value: Any) -> str:
    score = _safe_float(value)
    if pd.isna(score):
        return "unknown"
    if score >= 3.5:
        return "high"
    if score >= 2.0:
        return "medium"
    return "low"


def _safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return float("nan")
        return float(value)
    except Exception:
        return float("nan")


def _round_or_na(value: Any) -> Any:
    try:
        if pd.isna(value):
            return pd.NA
        return round(float(value), 6)
    except Exception:
        return pd.NA


def _iso_date(value: Any) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()
```

- [ ] **Step 4: Run outcome test**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_experiment.py::test_build_historical_rescore_report_computes_horizon_returns_and_drawdowns -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/stock_research/tech_bottleneck_experiment.py tests/test_tech_bottleneck_experiment.py
git commit -m "feat: add tech bottleneck historical outcomes"
```

## Task 2: Bucket Summary And Markdown Report

**Files:**
- Modify: `tests/test_tech_bottleneck_experiment.py`
- Modify: `src/stock_research/tech_bottleneck_experiment.py`

- [ ] **Step 1: Add bucket summary tests**

Append to `tests/test_tech_bottleneck_experiment.py`:

```python
def test_build_historical_rescore_report_summarizes_buckets() -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )
    summary = report["bucket_summary"].set_index("bucket")

    assert summary.loc["high", "candidate_count"] == 1
    assert summary.loc["medium", "candidate_count"] == 1
    assert summary.loc["low", "candidate_count"] == 1
    assert summary.loc["high", "mean_return_4d"] == 0.5
    assert summary.loc["low", "mean_return_4d"] == -0.3
    assert summary.loc["high", "excess_return_4d"] > 0


def test_render_historical_rescore_summary_labels_horizon_roles() -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(20, 60, 120, 250, 500),
    )

    markdown = render_historical_rescore_summary(
        run_id="rescore-run",
        bucket_summary=report["bucket_summary"],
        horizons=(20, 60, 120, 250, 500),
    )

    assert "Short-term diagnostics: 20D / 60D" in markdown
    assert "Primary validation: 120D / 250D" in markdown
    assert "Long-cycle observation: 500D" in markdown
    assert "### high" in markdown
```

- [ ] **Step 2: Run bucket tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_experiment.py::test_build_historical_rescore_report_summarizes_buckets tests/test_tech_bottleneck_experiment.py::test_render_historical_rescore_summary_labels_horizon_roles -q
```

Expected: PASS.

- [ ] **Step 3: Run all experiment tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_experiment.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/tech_bottleneck_experiment.py tests/test_tech_bottleneck_experiment.py
git commit -m "feat: summarize tech bottleneck score buckets"
```

## Task 3: Artifact Writer And File Runner

**Files:**
- Modify: `tests/test_tech_bottleneck_experiment.py`
- Modify: `src/stock_research/tech_bottleneck_experiment.py`

- [ ] **Step 1: Add artifact and file-runner tests**

Append to `tests/test_tech_bottleneck_experiment.py`:

```python
def test_write_historical_rescore_artifacts(tmp_path: Path) -> None:
    report = build_historical_rescore_report(
        packets=_packets(),
        bars=_bars(),
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )

    paths = write_historical_rescore_artifacts(
        report=report,
        output_dir=tmp_path,
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )

    assert paths["outcomes"].exists()
    assert paths["bucket_summary"].exists()
    assert paths["summary"].exists()
    assert "tech-bottleneck historical rescore summary" in paths["summary"].read_text(encoding="utf-8")


def test_run_historical_rescore_from_files(tmp_path: Path) -> None:
    packets_csv = tmp_path / "packets.csv"
    bars_csv = tmp_path / "bars.csv"
    output_dir = tmp_path / "out"
    _packets().to_csv(packets_csv, index=False)
    _bars().to_csv(bars_csv, index=False)

    paths = run_historical_rescore_from_files(
        packets_csv=packets_csv,
        bars_csv=bars_csv,
        output_dir=output_dir,
        run_id="rescore-run",
        horizons=(1, 2, 4),
    )

    assert paths["outcomes"] == output_dir / "outcomes.csv"
    outcomes = pd.read_csv(paths["outcomes"])
    assert set(outcomes["asset_id"]) == {"A", "B", "C"}
    summary = pd.read_csv(paths["bucket_summary"]).set_index("bucket")
    assert summary.loc["high", "candidate_count"] == 1
```

- [ ] **Step 2: Run artifact tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_experiment.py::test_write_historical_rescore_artifacts tests/test_tech_bottleneck_experiment.py::test_run_historical_rescore_from_files -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/stock_research/tech_bottleneck_experiment.py tests/test_tech_bottleneck_experiment.py
git commit -m "feat: write tech bottleneck rescore artifacts"
```

## Task 4: CLI Command

**Files:**
- Modify: `src/stock_research/cli.py`
- Modify: `tests/test_tech_bottleneck_experiment.py`

- [ ] **Step 1: Add CLI import and parser**

Modify `src/stock_research/cli.py`.

Add this import near the `tech_bottleneck_discovery` import:

```python
from stock_research.tech_bottleneck_experiment import run_historical_rescore_from_files
```

Add this parser setup inside `build_parser()` after the `tech-bottleneck-discovery` parser:

```python
    tech_bottleneck_rescore = subparsers.add_parser(
        "tech-bottleneck-historical-rescore",
        help="Evaluate historical tech bottleneck scored candidates across forward horizons.",
    )
    tech_bottleneck_rescore.add_argument("--packets-csv", required=True)
    tech_bottleneck_rescore.add_argument("--bars-csv", required=True)
    tech_bottleneck_rescore.add_argument("--output-dir", required=True)
    tech_bottleneck_rescore.add_argument("--run-id", required=True)
    tech_bottleneck_rescore.add_argument(
        "--horizons",
        default="20,60,120,250,500",
        help="Comma-separated trading-day horizons.",
    )
```

Add this dispatch branch inside `main_for_args()` after the `tech-bottleneck-discovery` branch:

```python
    elif args.command == "tech-bottleneck-historical-rescore":
        horizons = tuple(int(item) for item in str(args.horizons).split(",") if item.strip())
        paths = run_historical_rescore_from_files(
            packets_csv=Path(args.packets_csv),
            bars_csv=Path(args.bars_csv),
            output_dir=Path(args.output_dir),
            run_id=str(args.run_id),
            horizons=horizons,
        )
        print(json.dumps({key: str(value) for key, value in paths.items()}, ensure_ascii=False, indent=2))
```

- [ ] **Step 2: Add CLI parser smoke test**

Append to `tests/test_tech_bottleneck_experiment.py`:

```python
from stock_research.cli import build_parser


def test_cli_parser_accepts_historical_rescore_command() -> None:
    args = build_parser().parse_args(
        [
            "tech-bottleneck-historical-rescore",
            "--packets-csv",
            "packets.csv",
            "--bars-csv",
            "bars.csv",
            "--output-dir",
            "out",
            "--run-id",
            "run",
            "--horizons",
            "20,60,120",
        ]
    )

    assert args.command == "tech-bottleneck-historical-rescore"
    assert args.horizons == "20,60,120"
```

- [ ] **Step 3: Run CLI parser test**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_experiment.py::test_cli_parser_accepts_historical_rescore_command -q
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/stock_research/cli.py tests/test_tech_bottleneck_experiment.py
git commit -m "feat: add tech bottleneck historical rescore cli"
```

## Task 5: Example Data And Runbook Update

**Files:**
- Create: `data/manual/tech_bottleneck_bars_example.csv`
- Modify: `docs/tech-bottleneck-discovery-runbook.md`

- [ ] **Step 1: Add example bars CSV**

Create `data/manual/tech_bottleneck_bars_example.csv`:

```csv
asset_id,trade_date,close
CN:SH:688001,2026-06-05,10.0
CN:SH:688001,2026-06-08,10.5
CN:SH:688001,2026-06-09,11.0
CN:SH:688001,2026-06-10,11.5
CN:SH:688001,2026-06-11,12.0
CN:SH:688001,2026-06-12,12.5
```

- [ ] **Step 2: Update runbook**

Append to `docs/tech-bottleneck-discovery-runbook.md`:

````markdown
## Historical Re-Score Experiment

Use this after packet generation to evaluate scored candidates against future bars. The 20D and 60D horizons are diagnostics only. The main validation horizons are 120D and 250D; 500D is a long-cycle observation horizon.

```bash
stock-research tech-bottleneck-historical-rescore \
  --packets-csv outputs/tech_bottleneck_discovery/example/packets.csv \
  --bars-csv data/manual/tech_bottleneck_bars_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/historical_rescore_example \
  --run-id tech-bottleneck-historical-example \
  --horizons 1,2,4,5
```

Outputs:

- `outcomes.csv`
- `bucket_summary.csv`
- `summary.md`
````

- [ ] **Step 3: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_experiment.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add data/manual/tech_bottleneck_bars_example.csv docs/tech-bottleneck-discovery-runbook.md
git commit -m "docs: add tech bottleneck rescore runbook"
```

## Task 6: Final Verification

**Files:**
- Verify all files from prior tasks.

- [ ] **Step 1: Run focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_tech_bottleneck_discovery.py tests/test_tech_bottleneck_experiment.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI help smoke**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-historical-rescore --help
```

Expected: help includes `--packets-csv`, `--bars-csv`, `--output-dir`, `--run-id`, and `--horizons`.

- [ ] **Step 3: Run packet generation example**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-discovery \
  --candidates-csv data/manual/tech_bottleneck_candidates_example.csv \
  --evidence-csv data/manual/tech_bottleneck_evidence_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/example \
  --run-id tech-bottleneck-example
```

Expected: `outputs/tech_bottleneck_discovery/example/packets.csv` exists.

- [ ] **Step 4: Run historical rescore example**

Run:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli tech-bottleneck-historical-rescore \
  --packets-csv outputs/tech_bottleneck_discovery/example/packets.csv \
  --bars-csv data/manual/tech_bottleneck_bars_example.csv \
  --output-dir outputs/tech_bottleneck_discovery/historical_rescore_example \
  --run-id tech-bottleneck-historical-example \
  --horizons 1,2,4,5
```

Expected: JSON printed to stdout with `outcomes`, `bucket_summary`, and `summary` paths.

- [ ] **Step 5: Inspect generated summary**

Run:

```bash
sed -n '1,120p' outputs/tech_bottleneck_discovery/historical_rescore_example/summary.md
```

Expected: includes `Short-term diagnostics`, `Primary validation`, and bucket sections.

- [ ] **Step 6: Confirm clean git status**

Run:

```bash
git status --short
```

Expected: no tracked changes. Output artifacts under `outputs/` should be ignored.

## Self-Review Checklist

- Spec coverage: existing candidate pools, no full-market scan, 20D/60D diagnostics, 120D/250D primary validation, 500D long-cycle observation, bucket summaries, artifact outputs, and CLI are covered.
- No placeholders: every task includes exact files, test code, implementation code, commands, and expected outputs.
- Type consistency: `build_historical_rescore_report`, `render_historical_rescore_summary`, `write_historical_rescore_artifacts`, and `run_historical_rescore_from_files` are introduced before CLI use.
- Scope: no database migration, dashboard UI, social-media source ingestion, broker integration, or production promotion.
