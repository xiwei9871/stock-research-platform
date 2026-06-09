# Top10 Historical News Effectiveness Review v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a first-pass historical effectiveness review for Top10 historical news artifacts, joining the completed `2025-01-02..2026-05-19` replacement-source backfill to forward-return labels and producing coverage/source-type/bucket summaries plus a markdown report.

**Architecture:** Read the historical backfill artifacts from the completed replacement-source output directory, derive future-return and forward-drawdown labels from `public.market_daily_bar` (`adjust_type=qfq`), then build one base analysis frame and three summary views: coverage, source type, and feature buckets. Keep the review module read-only with file outputs only; do not mutate the upstream backfill or strategy code.

**Tech Stack:** Python, pandas, existing DB access helpers, `public.market_daily_bar`, pytest.

---

## File Structure

### New files to create

- `src/stock_research/top10_historical_news_effectiveness_review.py`
  - Load historical backfill artifacts
  - Build future-return / forward-drawdown labels
  - Build base review frame
  - Build summary tables
  - Write markdown report

- `tests/test_top10_historical_news_effectiveness_review.py`
  - Module-level tests for joins, label derivation, summary generation, and report output

### Existing files to modify

- `src/stock_research/cli.py`
  - Add `review-top10-historical-news-effectiveness`

### Existing files to read but not modify

- `src/stock_research/labels.py`
  - Reuse horizon conventions and `future_return` semantics

- `outputs/research/top10_historical_news_backfill_20250102_20260519_replacement/*`
  - Primary review input

## Task 1: Scaffold the Review Module and CLI Contract

**Files:**
- Create: `src/stock_research/top10_historical_news_effectiveness_review.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_top10_historical_news_effectiveness_review.py`

- [ ] **Step 1: Write the failing smoke test for artifact loading and CLI wiring**

Add a test that checks the new module can load the three input files from `--base-dir` and that CLI forwards arguments correctly.

```python
def test_review_top10_historical_news_effectiveness_cli_forwards_args(monkeypatch, tmp_path):
    recorded = {}

    monkeypatch.setattr(
        "stock_research.cli.run_top10_historical_news_effectiveness_review",
        lambda **kwargs: recorded.update(kwargs) or {"paths": {}},
    )

    args = [
        "stock-research",
        "review-top10-historical-news-effectiveness",
        "--base-dir",
        str(tmp_path / "base"),
        "--adjust-type",
        "qfq",
        "--output-dir",
        str(tmp_path / "out"),
    ]

    exit_code = cli.main(args)

    assert exit_code == 0
    assert recorded["base_dir"] == str(tmp_path / "base")
    assert recorded["adjust_type"] == "qfq"
    assert recorded["output_dir"] == str(tmp_path / "out")
```

```python
def test_load_review_inputs_reads_required_historical_artifacts(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    pd.DataFrame(
        [{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "stock_name": "江苏银行"}]
    ).to_csv(base / "historical_top10_candidates.csv", index=False)
    pd.DataFrame(
        [{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "notice_count_3d": 1}]
    ).to_csv(base / "historical_news_feature_daily.csv", index=False)
    pd.DataFrame(
        [{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "historical_event_summary": "近3日有1条公告"}]
    ).to_csv(base / "historical_top10_news_enrichment.csv", index=False)

    payload = load_review_inputs(base_dir=base)

    assert list(payload) == ["candidates", "features", "enrichment"]
    assert len(payload["candidates"]) == 1
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q
```

Expected:

- FAIL because the module and CLI command do not exist yet.

- [ ] **Step 3: Write the minimal module scaffold and CLI entry**

Create the module with:

```python
def load_review_inputs(*, base_dir: str | Path) -> dict[str, pd.DataFrame]:
    base = Path(base_dir)
    return {
        "candidates": pd.read_csv(base / "historical_top10_candidates.csv", low_memory=False),
        "features": pd.read_csv(base / "historical_news_feature_daily.csv", low_memory=False),
        "enrichment": pd.read_csv(base / "historical_top10_news_enrichment.csv", low_memory=False),
    }


def run_top10_historical_news_effectiveness_review(
    *,
    base_dir: str | Path,
    adjust_type: str,
    output_dir: str | Path,
) -> dict[str, object]:
    payload = load_review_inputs(base_dir=base_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    return {"payload": payload, "paths": {}}
```

In `src/stock_research/cli.py`, add:

```python
review_top10_historical_news_effectiveness = subparsers.add_parser(
    "review-top10-historical-news-effectiveness"
)
review_top10_historical_news_effectiveness.add_argument("--base-dir", required=True)
review_top10_historical_news_effectiveness.add_argument("--adjust-type", default="qfq")
review_top10_historical_news_effectiveness.add_argument("--output-dir", required=True)
```

and the dispatch block:

```python
elif args.command == "review-top10-historical-news-effectiveness":
    result = run_top10_historical_news_effectiveness_review(
        base_dir=args.base_dir,
        adjust_type=args.adjust_type,
        output_dir=args.output_dir,
    )
    return 0
```

- [ ] **Step 4: Run the focused tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q
```

Expected:

- PASS for the new loading and CLI tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/top10_historical_news_effectiveness_review.py src/stock_research/cli.py tests/test_top10_historical_news_effectiveness_review.py
git commit -m "feat: scaffold top10 historical news effectiveness review"
```

## Task 2: Build Future-Return and Forward-Drawdown Labels

**Files:**
- Modify: `src/stock_research/top10_historical_news_effectiveness_review.py`
- Test: `tests/test_top10_historical_news_effectiveness_review.py`

- [ ] **Step 1: Write failing tests for label generation**

Add tests for `future_1d/3d/5d/10d/20d_return` and forward drawdown columns using a tiny synthetic bar series.

```python
def test_build_future_return_labels_from_close_series():
    bars = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-02", "close": 10.0, "low": 9.8},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-03", "close": 11.0, "low": 10.5},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-06", "close": 12.0, "low": 11.2},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-07", "close": 11.5, "low": 10.9},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-08", "close": 13.0, "low": 12.4},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-09", "close": 14.0, "low": 13.5},
        ]
    )

    labels = build_future_label_frame(bars=bars)
    row = labels.loc[(labels["asset_id"] == "CN:SH:600919") & (labels["trade_date"] == "2025-01-02")].iloc[0]

    assert round(row["future_1d_return"], 6) == 0.10
    assert round(row["future_3d_return"], 6) == 0.15
```

```python
def test_build_future_drawdown_labels_uses_forward_window_lows():
    bars = pd.DataFrame(
        [
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-02", "close": 10.0, "low": 9.8},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-03", "close": 11.0, "low": 8.5},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-06", "close": 12.0, "low": 9.0},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-07", "close": 11.5, "low": 10.0},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-08", "close": 13.0, "low": 11.5},
            {"asset_id": "CN:SH:600919", "trade_date": "2025-01-09", "close": 14.0, "low": 13.5},
        ]
    )

    labels = build_future_label_frame(bars=bars)
    row = labels.loc[(labels["asset_id"] == "CN:SH:600919") & (labels["trade_date"] == "2025-01-02")].iloc[0]

    assert round(row["future_5d_max_drawdown"], 6) == -0.15
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q -k 'future_return or drawdown'
```

Expected:

- FAIL because label generation does not exist yet.

- [ ] **Step 3: Implement minimal label generation**

Add:

```python
RETURN_HORIZONS = [1, 3, 5, 10, 20]
```

```python
def build_future_label_frame(*, bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["low"] = pd.to_numeric(frame["low"], errors="coerce")
    frame = frame.sort_values(["asset_id", "trade_date"]).reset_index(drop=True)

    for horizon in RETURN_HORIZONS:
        frame[f"future_{horizon}d_return"] = frame.groupby("asset_id")["close"].shift(-horizon) / frame["close"] - 1.0
        frame[f"future_{horizon}d_max_drawdown"] = frame.groupby("asset_id", group_keys=False).apply(
            lambda group: _forward_max_drawdown(group, horizon)
        )
    frame["trade_date"] = frame["trade_date"].dt.date.astype(str)
    return frame
```

```python
def _forward_max_drawdown(group: pd.DataFrame, horizon: int) -> pd.Series:
    values = []
    lows = group["low"].tolist()
    closes = group["close"].tolist()
    for idx, close in enumerate(closes):
        window = lows[idx + 1 : idx + horizon + 1]
        if not window or pd.isna(close) or close == 0:
            values.append(pd.NA)
            continue
        values.append(min(window) / close - 1.0)
    return pd.Series(values, index=group.index)
```

- [ ] **Step 4: Run the focused tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q -k 'future_return or drawdown'
```

Expected:

- PASS for the label tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/top10_historical_news_effectiveness_review.py tests/test_top10_historical_news_effectiveness_review.py
git commit -m "feat: add future return and drawdown labels for news review"
```

## Task 3: Build the Base Review Frame

**Files:**
- Modify: `src/stock_research/top10_historical_news_effectiveness_review.py`
- Test: `tests/test_top10_historical_news_effectiveness_review.py`

- [ ] **Step 1: Write failing tests for joining candidates, features, enrichment, and labels**

```python
def test_build_review_base_frame_keeps_uncovered_candidates():
    candidates = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "stock_name": "江苏银行"},
            {"trade_date": "2025-01-02", "asset_id": "CN:SH:600066", "ts_code": "600066.SH", "stock_name": "宇通客车"},
        ]
    )
    features = pd.DataFrame(
        [{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "notice_count_3d": 1}]
    )
    enrichment = pd.DataFrame(
        [{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "historical_event_summary": "近3日有1条公告"}]
    )
    labels = pd.DataFrame(
        [
            {"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "future_5d_return": 0.05},
            {"trade_date": "2025-01-02", "asset_id": "CN:SH:600066", "future_5d_return": -0.01},
        ]
    )

    frame = build_review_base_frame(
        candidates=candidates,
        features=features,
        enrichment=enrichment,
        labels=labels,
    )

    assert len(frame) == 2
    assert frame["asset_id"].tolist() == ["CN:SH:600919", "CN:SH:600066"]
    assert pd.isna(frame.loc[frame["asset_id"] == "CN:SH:600066", "notice_count_3d"]).all()
```

```python
def test_build_review_base_frame_derives_source_type_group():
    candidates = pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "stock_name": "江苏银行"}])
    features = pd.DataFrame(
        [{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "notice_count_10d": 2, "research_report_count_20d": 1}]
    )
    enrichment = pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "historical_event_summary": "近20日有2条公告 + 1篇机构研报"}])
    labels = pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "future_5d_return": 0.02}])

    frame = build_review_base_frame(candidates=candidates, features=features, enrichment=enrichment, labels=labels)

    assert frame.iloc[0]["source_type_group"] == "notice_and_report"
    assert frame.iloc[0]["coverage_group"] == "historical_summary_present"
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q -k 'base_frame or source_type_group'
```

Expected:

- FAIL because base-frame assembly does not exist yet.

- [ ] **Step 3: Implement minimal base-frame assembly**

Add:

```python
def build_review_base_frame(
    *,
    candidates: pd.DataFrame,
    features: pd.DataFrame,
    enrichment: pd.DataFrame,
    labels: pd.DataFrame,
) -> pd.DataFrame:
    frame = candidates.copy()
    for payload in (features, enrichment, labels):
        frame = frame.merge(payload, on=["trade_date", "asset_id"], how="left")
    frame["coverage_group"] = frame.apply(_coverage_group, axis=1)
    frame["source_type_group"] = frame.apply(_source_type_group, axis=1)
    return frame
```

```python
def _coverage_group(row: pd.Series) -> str:
    summary = str(row.get("historical_event_summary") or "").strip()
    attention = str(row.get("news_attention_level") or "").strip().lower()
    if summary:
        return "historical_summary_present"
    if attention and attention != "unknown":
        return "news_feature_only"
    return "no_news_feature"
```

```python
def _source_type_group(row: pd.Series) -> str:
    notice = float(pd.to_numeric(pd.Series([row.get("notice_count_10d")]), errors="coerce").fillna(0).iloc[0]) > 0
    report = float(pd.to_numeric(pd.Series([row.get("research_report_count_20d")]), errors="coerce").fillna(0).iloc[0]) > 0
    if notice and report:
        return "notice_and_report"
    if notice:
        return "notice_only"
    if report:
        return "report_only"
    return "no_historical_event"
```

- [ ] **Step 4: Run the focused tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q -k 'base_frame or source_type_group'
```

Expected:

- PASS for base-frame tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/top10_historical_news_effectiveness_review.py tests/test_top10_historical_news_effectiveness_review.py
git commit -m "feat: build historical news review base frame"
```

## Task 4: Build Coverage and Source-Type Summaries

**Files:**
- Modify: `src/stock_research/top10_historical_news_effectiveness_review.py`
- Test: `tests/test_top10_historical_news_effectiveness_review.py`

- [ ] **Step 1: Write failing tests for grouped summary outputs**

```python
def test_build_coverage_summary_aggregates_returns_and_drawdowns():
    frame = pd.DataFrame(
        [
            {"coverage_group": "historical_summary_present", "future_5d_return": 0.10, "future_10d_return": 0.15, "future_10d_max_drawdown": -0.03},
            {"coverage_group": "historical_summary_present", "future_5d_return": 0.00, "future_10d_return": 0.05, "future_10d_max_drawdown": -0.02},
            {"coverage_group": "no_news_feature", "future_5d_return": -0.02, "future_10d_return": -0.01, "future_10d_max_drawdown": -0.08},
        ]
    )

    summary = build_group_summary(frame, group_col="coverage_group")

    row = summary.loc[summary["coverage_group"] == "historical_summary_present"].iloc[0]
    assert row["sample_count"] == 2
    assert round(row["avg_future_5d_return"], 6) == 0.05
```

```python
def test_build_source_type_summary_includes_notice_and_report_group():
    frame = pd.DataFrame(
        [
            {"source_type_group": "notice_and_report", "future_5d_return": 0.03, "future_10d_return": 0.04, "future_20d_max_drawdown": -0.04},
            {"source_type_group": "notice_only", "future_5d_return": -0.01, "future_10d_return": 0.00, "future_20d_max_drawdown": -0.08},
        ]
    )

    summary = build_group_summary(frame, group_col="source_type_group")
    assert set(summary["source_type_group"]) == {"notice_and_report", "notice_only"}
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q -k 'coverage_summary or source_type_summary'
```

Expected:

- FAIL because grouped summaries do not exist yet.

- [ ] **Step 3: Implement grouped summary builder**

Add:

```python
SUMMARY_RETURN_COLUMNS = [
    "future_1d_return",
    "future_3d_return",
    "future_5d_return",
    "future_10d_return",
    "future_20d_return",
]
SUMMARY_DRAWDOWN_COLUMNS = [
    "future_5d_max_drawdown",
    "future_10d_max_drawdown",
    "future_20d_max_drawdown",
]
```

```python
def build_group_summary(frame: pd.DataFrame, *, group_col: str) -> pd.DataFrame:
    rows = []
    for key, group in frame.groupby(group_col, dropna=False):
        data = {
            group_col: key,
            "sample_count": int(len(group)),
            "win_rate_5d": float((pd.to_numeric(group["future_5d_return"], errors="coerce") > 0).mean()),
            "win_rate_10d": float((pd.to_numeric(group["future_10d_return"], errors="coerce") > 0).mean()),
        }
        for col in SUMMARY_RETURN_COLUMNS + SUMMARY_DRAWDOWN_COLUMNS:
            if col in group.columns:
                data[f"avg_{col}"] = float(pd.to_numeric(group[col], errors="coerce").mean())
        rows.append(data)
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run the focused tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q -k 'coverage_summary or source_type_summary'
```

Expected:

- PASS for grouped-summary tests.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/top10_historical_news_effectiveness_review.py tests/test_top10_historical_news_effectiveness_review.py
git commit -m "feat: add grouped summaries for historical news review"
```

## Task 5: Build Feature Bucket Summaries and Report Output

**Files:**
- Modify: `src/stock_research/top10_historical_news_effectiveness_review.py`
- Test: `tests/test_top10_historical_news_effectiveness_review.py`

- [ ] **Step 1: Write failing tests for bucket summaries and report files**

```python
def test_build_count_bucket_summary_uses_0_1_2plus_buckets():
    frame = pd.DataFrame(
        [
            {"notice_count_3d": 0, "future_5d_return": -0.01},
            {"notice_count_3d": 1, "future_5d_return": 0.02},
            {"notice_count_3d": 3, "future_5d_return": 0.05},
        ]
    )

    summary = build_count_bucket_summary(frame, feature_name="notice_count_3d")

    assert summary["bucket"].tolist() == ["0", "1", "2+"]
```

```python
def test_run_review_writes_all_outputs(tmp_path, monkeypatch):
    base = tmp_path / "base"
    out = tmp_path / "out"
    base.mkdir()
    pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "stock_name": "江苏银行"}]).to_csv(base / "historical_top10_candidates.csv", index=False)
    pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "notice_count_3d": 1, "notice_count_10d": 1, "research_report_count_20d": 0, "news_attention_level": "low"}]).to_csv(base / "historical_news_feature_daily.csv", index=False)
    pd.DataFrame([{"trade_date": "2025-01-02", "asset_id": "CN:SH:600919", "ts_code": "600919.SH", "stock_name": "江苏银行", "historical_event_summary": "近3日有1条公告"}]).to_csv(base / "historical_top10_news_enrichment.csv", index=False)

    monkeypatch.setattr(
        "stock_research.top10_historical_news_effectiveness_review.load_daily_bars_for_review",
        lambda **kwargs: pd.DataFrame(
            [
                {"asset_id": "CN:SH:600919", "trade_date": "2025-01-02", "close": 10.0, "low": 9.8},
                {"asset_id": "CN:SH:600919", "trade_date": "2025-01-03", "close": 10.5, "low": 10.1},
                {"asset_id": "CN:SH:600919", "trade_date": "2025-01-06", "close": 10.8, "low": 10.3},
                {"asset_id": "CN:SH:600919", "trade_date": "2025-01-07", "close": 11.0, "low": 10.6},
                {"asset_id": "CN:SH:600919", "trade_date": "2025-01-08", "close": 11.2, "low": 10.8},
                {"asset_id": "CN:SH:600919", "trade_date": "2025-01-09", "close": 11.4, "low": 11.0},
            ]
        ),
    )

    result = run_top10_historical_news_effectiveness_review(base_dir=base, adjust_type="qfq", output_dir=out)

    assert Path(result["paths"]["base"]).exists()
    assert Path(result["paths"]["coverage_summary"]).exists()
    assert Path(result["paths"]["source_type_summary"]).exists()
    assert Path(result["paths"]["feature_bucket_summary"]).exists()
    assert Path(result["paths"]["report"]).exists()
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q -k 'bucket or writes_all_outputs'
```

Expected:

- FAIL because bucket summaries and output writing do not exist yet.

- [ ] **Step 3: Implement bucket summaries, DB bar loader, and report writing**

Add:

```python
BUCKET_FEATURES = [
    "notice_count_3d",
    "notice_count_10d",
    "research_report_count_20d",
    "rating_action_count_20d",
    "risk_notice_count_20d",
]
```

```python
def bucket_0_1_2plus(value: object) -> str:
    number = int(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])
    if number <= 0:
        return "0"
    if number == 1:
        return "1"
    return "2+"
```

```python
def build_count_bucket_summary(frame: pd.DataFrame, *, feature_name: str) -> pd.DataFrame:
    data = frame.copy()
    data["bucket"] = data[feature_name].map(bucket_0_1_2plus)
    summary = build_group_summary(data, group_col="bucket")
    summary.insert(0, "feature_name", feature_name)
    return summary
```

```python
def load_daily_bars_for_review(*, asset_ids: list[str], end_date: str, adjust_type: str) -> pd.DataFrame:
    sql = """
    SELECT asset_id, trade_date, close, low
    FROM market_daily_bar
    WHERE adjust_type = %s
      AND asset_id = ANY(%s)
      AND trade_date <= %s
    ORDER BY asset_id, trade_date
    """
    with connect(SETTINGS.research_service) as conn:
        rows = fetch_all(conn, sql, [adjust_type, asset_ids, end_date])
    return pd.DataFrame(rows)
```

Complete `run_top10_historical_news_effectiveness_review(...)` to:

1. load inputs
2. load bars
3. build labels
4. build base frame
5. build coverage summary
6. build source-type summary
7. build per-feature bucket summaries
8. write:
   - `top10_historical_news_effectiveness_base.csv`
   - `top10_historical_news_effectiveness_coverage_summary.csv`
   - `top10_historical_news_effectiveness_source_type_summary.csv`
   - `top10_historical_news_effectiveness_feature_bucket_summary.csv`
   - `top10_historical_news_effectiveness_report.md`

- [ ] **Step 4: Run the focused tests to verify pass**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest /Users/xiwei/stock_research/tests/test_top10_historical_news_effectiveness_review.py -q
```

Expected:

- PASS for the full module test file.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/top10_historical_news_effectiveness_review.py src/stock_research/cli.py tests/test_top10_historical_news_effectiveness_review.py
git commit -m "feat: add top10 historical news effectiveness review outputs"
```

## Task 6: Run the Real Review and Verify Outputs

**Files:**
- No code changes expected unless verification exposes a small bug

- [ ] **Step 1: Run the real review command against the completed historical replacement base**

Run:

```bash
cd /Users/xiwei/stock_research && PYTHONPATH=/Users/xiwei/stock_research/src .venv/bin/python -m stock_research.cli review-top10-historical-news-effectiveness \
  --base-dir outputs/research/top10_historical_news_backfill_20250102_20260519_replacement \
  --adjust-type qfq \
  --output-dir outputs/research/top10_historical_news_effectiveness_review_v1
```

Expected:

- all five output files written

- [ ] **Step 2: Run the broad verification suite**

Run:

```bash
cd /Users/xiwei/stock_research && /Users/xiwei/stock_research/.venv/bin/pytest \
  tests/test_top10_historical_news_effectiveness_review.py \
  tests/test_news_source_backfill.py \
  tests/test_public_news_fallback_adapter.py \
  tests/test_news_features.py \
  tests/test_topn_news_enrichment.py -q
```

Expected:

- PASS across the review stack and the existing historical-news stack

- [ ] **Step 3: Record the key review outputs**

Capture from the generated CSV/report:

- best and worst `coverage_group`
- best and worst `source_type_group`
- any monotonic pattern in:
  - `notice_count_3d`
  - `notice_count_10d`
  - `research_report_count_20d`
- whether `risk_notice_count_20d` behaves more like a risk signal

- [ ] **Step 4: Commit any final fixes if needed**

```bash
cd /Users/xiwei/stock_research
git add -A
git commit -m "test: verify top10 historical news effectiveness review"
```

If verification required no code change, skip this commit.

## Self-Review

Spec coverage check:

- load historical artifacts: Task 1
- derive future returns and drawdowns: Task 2
- build base review frame: Task 3
- build coverage and source-type summaries: Task 4
- build feature bucket summaries and markdown report: Task 5
- run real review and verify outputs: Task 6

Placeholder scan:

- No `TBD`, `TODO`, or implicit future steps remain inside task instructions

Type consistency:

- module function names are consistent:
  - `load_review_inputs`
  - `load_daily_bars_for_review`
  - `build_future_label_frame`
  - `build_review_base_frame`
  - `build_group_summary`
  - `build_count_bucket_summary`
  - `run_top10_historical_news_effectiveness_review`
