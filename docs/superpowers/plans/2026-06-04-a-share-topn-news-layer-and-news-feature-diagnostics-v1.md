# A股 TopN News Layer & News Feature Diagnostics v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 A 股新闻原始事件层、mention/feature 层、TopN 新闻增强层和 diagnostics 产物，先服务于 Top5/Top10 解释和新闻特征验证，不直接接入全市场排序。

**Architecture:** 采用三层设计：`news_source_backfill` 负责原始新闻抓取与标准化，`news_features` 负责 mention 映射与 `news_feature_daily` 聚合，`topn_news_enrichment` 负责 TopN 人读增强；`position_dossier` 只消费增强结果，diagnostics 独立验证新闻特征是否更像机会解释或风险解释。

**Tech Stack:** Python, pandas, existing DB helpers in `stock_research.db`, Tushare optional provider integration, pytest, CLI wiring in `stock_research.cli`.

---

## File Structure

### New files

- `src/stock_research/news_source_backfill.py`
  - 新闻原始事件的 provider 抽象、标准化、去重、落盘/落库。
- `src/stock_research/news_features.py`
  - mention 映射、PIT 过滤、`news_feature_daily` 聚合、diagnostics 基础统计。
- `src/stock_research/topn_news_enrichment.py`
  - 只对 `Top5/Top10` 做新闻增强事实归纳。
- `tests/test_news_source_backfill.py`
  - provider 可用/不可用、标准化、去重、replay/live 边界测试。
- `tests/test_news_features.py`
  - mention 映射、daily feature 聚合、样本不足时 diagnostics 行为测试。
- `tests/test_topn_news_enrichment.py`
  - TopN 增强摘要、质量分层、position_dossier 消费契约测试。

### Modified files

- `src/stock_research/schema.py`
  - 增加 `research.news_event_source`、`research.news_event_mention`、`research.news_feature_daily` schema。
- `src/stock_research/cli.py`
  - 新增 backfill / feature / diagnostics / enrichment CLI。
- `src/stock_research/mid_trend_position_dossier.py`
  - 可选接入 TopN 新闻增强输入，并在 Markdown/CSV 中展示。
- `tests/test_mid_trend_position_dossier.py`
  - 验证 dossier 在有/无新闻增强输入时行为稳定。

---

### Task 1: Add News Schemas and Raw Event Contracts

**Files:**
- Create: `tests/test_news_source_backfill.py`
- Create: `src/stock_research/news_source_backfill.py`
- Modify: `src/stock_research/schema.py`

- [ ] **Step 1: Write the failing schema and normalization tests**

```python
def test_normalize_news_rows_deduplicates_same_source_event():
    rows = [
        {"source_event_id": "n1", "title": "A", "published_at": "2026-06-01 09:01:00", "source_name": "tushare_news"},
        {"source_event_id": "n1", "title": "A", "published_at": "2026-06-01 09:01:00", "source_name": "tushare_news"},
    ]
    frame = normalize_news_source_rows(rows, source_status="available")
    assert len(frame) == 1
    assert frame.loc[0, "hash_key"]


def test_normalize_news_rows_sets_permission_denied_status():
    frame = normalize_news_source_rows([], source_status="permission_denied")
    assert list(frame.columns) == NEWS_SOURCE_COLUMNS
    assert frame.empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_news_source_backfill.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing `normalize_news_source_rows`.

- [ ] **Step 3: Add schema strings for the three news tables**

```python
CREATE TABLE IF NOT EXISTS research.news_event_source (
    source_event_id text PRIMARY KEY,
    source_name text NOT NULL,
    source_channel text,
    title text NOT NULL,
    content text,
    published_at timestamptz NOT NULL,
    collected_at timestamptz NOT NULL DEFAULT now(),
    language text NOT NULL DEFAULT 'zh',
    url text,
    hash_key text NOT NULL,
    source_status text NOT NULL CHECK (source_status IN ('available', 'permission_denied', 'disabled')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
```

```python
CREATE TABLE IF NOT EXISTS research.news_event_mention (
    source_event_id text NOT NULL REFERENCES research.news_event_source(source_event_id),
    asset_id text,
    ts_code text,
    stock_name text,
    mention_role text,
    mention_confidence double precision,
    theme_name text,
    theme_confidence double precision,
    mapping_method text NOT NULL,
    trade_date date,
    PRIMARY KEY (source_event_id, asset_id, theme_name, mapping_method)
);
```

```python
CREATE TABLE IF NOT EXISTS research.news_feature_daily (
    trade_date date NOT NULL,
    asset_id text NOT NULL,
    ts_code text,
    news_count_1d integer NOT NULL DEFAULT 0,
    news_count_3d integer NOT NULL DEFAULT 0,
    news_count_5d integer NOT NULL DEFAULT 0,
    major_news_count_3d integer NOT NULL DEFAULT 0,
    source_diversity_3d integer NOT NULL DEFAULT 0,
    overnight_news_count integer NOT NULL DEFAULT 0,
    preopen_news_count integer NOT NULL DEFAULT 0,
    headline_keyword_positive_count_3d integer NOT NULL DEFAULT 0,
    headline_keyword_risk_count_3d integer NOT NULL DEFAULT 0,
    theme_news_burst_flag boolean NOT NULL DEFAULT false,
    news_first_seen_gap integer,
    news_attention_level text NOT NULL DEFAULT 'low',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (trade_date, asset_id)
);
```

- [ ] **Step 4: Implement raw event normalization contract**

```python
NEWS_SOURCE_COLUMNS = [
    "source_event_id",
    "source_name",
    "source_channel",
    "title",
    "content",
    "published_at",
    "collected_at",
    "language",
    "url",
    "hash_key",
    "source_status",
    "metadata",
]


def normalize_news_source_rows(rows: list[dict], *, source_status: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=NEWS_SOURCE_COLUMNS)
    frame["title"] = frame["title"].fillna("").astype(str).str.strip()
    frame["published_at"] = pd.to_datetime(frame["published_at"], errors="coerce")
    frame["collected_at"] = pd.Timestamp.utcnow()
    frame["source_status"] = source_status
    frame["hash_key"] = (
        frame["source_name"].fillna("").astype(str)
        + "|"
        + frame["title"]
        + "|"
        + frame["published_at"].astype(str)
    ).map(lambda text: hashlib.sha1(text.encode("utf-8")).hexdigest())
    frame = frame.drop_duplicates(subset=["source_event_id", "hash_key"], keep="first")
    return frame.reindex(columns=NEWS_SOURCE_COLUMNS)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_news_source_backfill.py -v`
Expected: PASS with the new schema/normalization coverage green.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/schema.py src/stock_research/news_source_backfill.py tests/test_news_source_backfill.py
git commit -m "feat: add news source schemas and normalization"
```

---

### Task 2: Add Tushare Provider Wrapper and Backfill CLI Core

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_news_source_backfill.py`

- [ ] **Step 1: Write failing provider/CLI tests**

```python
def test_fetch_news_rows_returns_permission_denied_result_when_provider_unavailable(monkeypatch):
    monkeypatch.setattr("stock_research.news_source_backfill.build_tushare_news_client", lambda token=None: (_ for _ in ()).throw(RuntimeError("permission denied")))
    result = run_news_source_backfill(start_date="2026-06-01", end_date="2026-06-02", provider="tushare")
    assert result["source_status"] == "permission_denied"
    assert result["events"].empty


def test_news_source_backfill_cli_prints_paths(monkeypatch, capsys):
    monkeypatch.setattr("stock_research.cli.run_news_source_backfill", lambda **kwargs: {"source_status": "disabled", "paths": {"events": "a.csv", "report": "b.md"}, "events": pd.DataFrame()})
    parser = build_parser()
    args = parser.parse_args(["news-source-backfill", "--start-date", "2026-06-01", "--end-date", "2026-06-02"])
    run_cli_command(args)
    out = capsys.readouterr().out
    assert "news_source_backfill|events|a.csv" in out
    assert "news_source_backfill|report|b.md" in out
    assert "news_source_backfill|source_status|disabled" in out
```

- [ ] **Step 2: Run focused tests to verify failure**

Run: `pytest tests/test_news_source_backfill.py -v`
Expected: FAIL because `run_news_source_backfill` and CLI branch do not exist.

- [ ] **Step 3: Implement provider wrapper and backfill runner**

```python
def build_tushare_news_client(token: str | None = None):
    import tushare as ts
    if token:
        ts.set_token(token)
    return ts.pro_api()


def run_news_source_backfill(*, start_date: str, end_date: str, provider: str = "tushare", token: str | None = None, output_dir: str = "outputs/research") -> dict:
    try:
        rows = fetch_news_rows(start_date=start_date, end_date=end_date, provider=provider, token=token)
        source_status = "available"
    except RuntimeError as exc:
        if "permission" in str(exc).lower():
            rows = []
            source_status = "permission_denied"
        else:
            raise
    frame = normalize_news_source_rows(rows, source_status=source_status)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    events_path = output_path / f"news_source_backfill_{start_date}_{end_date}.csv"
    report_path = output_path / f"news_source_backfill_{start_date}_{end_date}.md"
    frame.to_csv(events_path, index=False)
    report_path.write_text(
        f"# News Source Backfill\\n\\n- provider: {provider}\\n- source_status: {source_status}\\n- rows: {len(frame)}\\n",
        encoding="utf-8",
    )
    return {"source_status": source_status, "events": frame, "paths": {"events": str(events_path), "report": str(report_path)}}
```

- [ ] **Step 4: Wire a CLI command**

```python
news_source_backfill = subparsers.add_parser("news-source-backfill")
news_source_backfill.add_argument("--start-date", required=True)
news_source_backfill.add_argument("--end-date", required=True)
news_source_backfill.add_argument("--provider", default="tushare")
news_source_backfill.add_argument("--token")
news_source_backfill.add_argument("--output-dir", default="outputs/research")
```

```python
elif args.command == "news-source-backfill":
    result = run_news_source_backfill(
        start_date=args.start_date,
        end_date=args.end_date,
        provider=args.provider,
        token=args.token,
        output_dir=args.output_dir,
    )
    print(f"news_source_backfill|events|{result['paths']['events']}")
    print(f"news_source_backfill|report|{result['paths']['report']}")
    print(f"news_source_backfill|source_status|{result['source_status']}")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_news_source_backfill.py -v`
Expected: PASS, including permission-denied and CLI output tests.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/news_source_backfill.py src/stock_research/cli.py tests/test_news_source_backfill.py
git commit -m "feat: add news source backfill runner and cli"
```

---

### Task 3: Implement Mention Mapping and Daily News Features

**Files:**
- Create: `tests/test_news_features.py`
- Create: `src/stock_research/news_features.py`
- Modify: `src/stock_research/cli.py`

- [ ] **Step 1: Write failing tests for mention mapping and feature aggregation**

```python
def test_map_news_mentions_matches_ts_code_and_stock_name():
    events = pd.DataFrame([
        {"source_event_id": "n1", "title": "生益科技获机构看好", "content": "600183.SH 生益科技", "published_at": "2026-06-01 08:30:00"},
    ])
    assets = pd.DataFrame([{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}])
    mentions = map_news_mentions(events=events, assets=assets)
    assert mentions.loc[0, "asset_id"] == "CN:SH:600183"
    assert mentions.loc[0, "mapping_method"] in {"ts_code", "stock_name"}


def test_build_news_feature_daily_respects_replay_cutoff():
    mentions = pd.DataFrame([
        {"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "published_at": "2026-06-02 09:00:00", "trade_date": "2026-06-02", "title": "订单增长", "source_name": "cls"},
        {"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "published_at": "2026-06-03 09:00:00", "trade_date": "2026-06-03", "title": "风险提示", "source_name": "cls"},
    ])
    feature = build_news_feature_daily(mentions=mentions, trade_dates=["2026-06-02"], mode="replay")
    assert feature.loc[0, "news_count_1d"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_news_features.py -v`
Expected: FAIL because `map_news_mentions` and `build_news_feature_daily` are undefined.

- [ ] **Step 3: Implement deterministic mention mapping**

```python
def map_news_mentions(*, events: pd.DataFrame, assets: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for event in events.to_dict("records"):
        haystack = " ".join(str(event.get(col, "")) for col in ("title", "content"))
        for asset in assets.to_dict("records"):
            if asset["ts_code"] and asset["ts_code"] in haystack:
                rows.append(
                    {
                        "source_event_id": event["source_event_id"],
                        "asset_id": asset["asset_id"],
                        "ts_code": asset["ts_code"],
                        "stock_name": asset["stock_name"],
                        "mention_role": "direct",
                        "mention_confidence": 1.0,
                        "theme_name": "",
                        "theme_confidence": 0.0,
                        "mapping_method": "ts_code",
                        "trade_date": pd.to_datetime(event["published_at"]).date().isoformat(),
                        "published_at": event["published_at"],
                        "title": event.get("title", ""),
                        "content": event.get("content", ""),
                        "source_name": event.get("source_name", ""),
                        "source_channel": event.get("source_channel", ""),
                    }
                )
            elif asset["stock_name"] and asset["stock_name"] in haystack:
                rows.append(
                    {
                        "source_event_id": event["source_event_id"],
                        "asset_id": asset["asset_id"],
                        "ts_code": asset["ts_code"],
                        "stock_name": asset["stock_name"],
                        "mention_role": "direct",
                        "mention_confidence": 0.8,
                        "theme_name": "",
                        "theme_confidence": 0.0,
                        "mapping_method": "stock_name",
                        "trade_date": pd.to_datetime(event["published_at"]).date().isoformat(),
                        "published_at": event["published_at"],
                        "title": event.get("title", ""),
                        "content": event.get("content", ""),
                        "source_name": event.get("source_name", ""),
                        "source_channel": event.get("source_channel", ""),
                    }
                )
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Implement PIT daily feature builder**

```python
POSITIVE_KEYWORDS = ("中标", "订单", "涨价", "扩产", "合作", "预增", "政策支持")
RISK_KEYWORDS = ("减持", "问询", "监管", "澄清", "风险提示", "下修", "停牌核查", "跌停")


def build_news_feature_daily(*, mentions: pd.DataFrame, trade_dates: list[str], mode: str = "replay") -> pd.DataFrame:
    rows: list[dict] = []
    mentions = mentions.copy()
    mentions["published_at"] = pd.to_datetime(mentions["published_at"])
    mentions["trade_date"] = pd.to_datetime(mentions["trade_date"]).dt.date
    for trade_date in pd.to_datetime(pd.Series(trade_dates)).dt.date.tolist():
        cutoff = pd.Timestamp(trade_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        asof = mentions.loc[mentions["published_at"] <= cutoff] if mode == "replay" else mentions
        for asset_id, asset_frame in asof.groupby("asset_id"):
            asset_frame = asset_frame.sort_values("published_at")
            window_1d = asset_frame.loc[asset_frame["trade_date"] == trade_date]
            window_3d = asset_frame.loc[asset_frame["trade_date"] >= trade_date - pd.Timedelta(days=2)]
            window_5d = asset_frame.loc[asset_frame["trade_date"] >= trade_date - pd.Timedelta(days=4)]
            positive_count = count_keywords(window_3d, POSITIVE_KEYWORDS)
            risk_count = count_keywords(window_3d, RISK_KEYWORDS)
            rows.append(
                {
                    "trade_date": str(trade_date),
                    "asset_id": asset_id,
                    "ts_code": asset_frame["ts_code"].iloc[-1],
                    "news_count_1d": int(window_1d.shape[0]),
                    "news_count_3d": int(window_3d.shape[0]),
                    "news_count_5d": int(window_5d.shape[0]),
                    "major_news_count_3d": int((window_3d["source_channel"] == "major_news").sum()),
                    "source_diversity_3d": int(window_3d["source_name"].nunique()),
                    "overnight_news_count": int((window_1d["published_at"].dt.hour < 9).sum()),
                    "preopen_news_count": int(((window_1d["published_at"].dt.hour == 9) & (window_1d["published_at"].dt.minute < 30)).sum()),
                    "headline_keyword_positive_count_3d": positive_count,
                    "headline_keyword_risk_count_3d": risk_count,
                    "theme_news_burst_flag": bool(window_3d.shape[0] >= 5 and window_3d["source_name"].nunique() >= 3),
                    "news_first_seen_gap": int((pd.Timestamp(trade_date) - window_5d["published_at"].min().normalize()).days) if not window_5d.empty else None,
                    "news_attention_level": classify_news_attention(
                        news_count_3d=int(window_3d.shape[0]),
                        major_news_count_3d=int((window_3d["source_channel"] == "major_news").sum()),
                        source_diversity_3d=int(window_3d["source_name"].nunique()),
                    ),
                }
            )
    return pd.DataFrame(rows)
```

- [ ] **Step 5: Add CLI entry to build features from source/mention files**

```python
news_feature_backfill = subparsers.add_parser("news-feature-backfill")
news_feature_backfill.add_argument("--events-path", required=True)
news_feature_backfill.add_argument("--start-date", required=True)
news_feature_backfill.add_argument("--end-date", required=True)
news_feature_backfill.add_argument("--mode", choices=["replay", "live"], default="replay")
news_feature_backfill.add_argument("--output-dir", default="outputs/research")
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/test_news_features.py -v`
Expected: PASS for mention mapping, PIT cutoff, and bucket logic.

- [ ] **Step 7: Commit**

```bash
git add src/stock_research/news_features.py src/stock_research/cli.py tests/test_news_features.py
git commit -m "feat: add news mention mapping and daily features"
```

---

### Task 4: Implement TopN News Enrichment

**Files:**
- Create: `tests/test_topn_news_enrichment.py`
- Create: `src/stock_research/topn_news_enrichment.py`
- Modify: `src/stock_research/cli.py`

- [ ] **Step 1: Write failing TopN enrichment tests**

```python
def test_build_topn_news_enrichment_summarizes_catalyst_and_risk():
    candidates = pd.DataFrame([
        {"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技", "trade_date": "2026-06-02"}
    ])
    features = pd.DataFrame([
        {"trade_date": "2026-06-02", "asset_id": "CN:SH:600183", "news_attention_level": "high", "headline_keyword_positive_count_3d": 3, "headline_keyword_risk_count_3d": 1, "major_news_count_3d": 2}
    ])
    enriched = build_topn_news_enrichment(candidates=candidates, news_features=features)
    assert enriched.loc[0, "theme_catalyst_summary"]
    assert enriched.loc[0, "news_enrichment_quality_flag"] in {"rich", "medium", "thin"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_topn_news_enrichment.py -v`
Expected: FAIL because enrichment module does not exist.

- [ ] **Step 3: Implement TopN enrichment builder**

```python
def build_topn_news_enrichment(*, candidates: pd.DataFrame, news_features: pd.DataFrame) -> pd.DataFrame:
    merged = candidates.merge(news_features, on=["trade_date", "asset_id"], how="left")
    merged["theme_catalyst_summary"] = merged.apply(
        lambda row: "近3日催化较密集，偏主题/公司共振" if row.get("headline_keyword_positive_count_3d", 0) >= 2 else "",
        axis=1,
    )
    merged["news_risk_summary"] = merged.apply(
        lambda row: "风险关键词抬升，需防拥挤或监管扰动" if row.get("headline_keyword_risk_count_3d", 0) >= 2 else "",
        axis=1,
    )
    merged["overnight_catalyst_note"] = merged.apply(
        lambda row: "存在隔夜/盘前催化" if (row.get("overnight_news_count", 0) + row.get("preopen_news_count", 0)) > 0 else "",
        axis=1,
    )
    merged["news_consensus_summary"] = merged.apply(build_news_consensus_summary, axis=1)
    merged["news_enrichment_quality_flag"] = merged.apply(classify_news_enrichment_quality, axis=1)
    return merged[TOPN_NEWS_ENRICHMENT_COLUMNS]
```

- [ ] **Step 4: Add CLI for enrichment**

```python
topn_news_enrichment = subparsers.add_parser("topn-news-enrichment")
topn_news_enrichment.add_argument("--candidates-path", required=True)
topn_news_enrichment.add_argument("--news-features-path", required=True)
topn_news_enrichment.add_argument("--output-dir", default="outputs/research")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_topn_news_enrichment.py -v`
Expected: PASS with deterministic summaries and quality flags.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/topn_news_enrichment.py src/stock_research/cli.py tests/test_topn_news_enrichment.py
git commit -m "feat: add topn news enrichment"
```

---

### Task 5: Add News Feature Diagnostics

**Files:**
- Modify: `src/stock_research/news_features.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_news_features.py`

- [ ] **Step 1: Write failing diagnostics tests**

```python
def test_news_feature_diagnostics_returns_bucket_summary_with_small_samples():
    features = pd.DataFrame([
        {"trade_date": "2026-06-02", "asset_id": "A", "news_attention_level": "high", "news_count_3d": 4, "future_5d_return": 0.03},
        {"trade_date": "2026-06-03", "asset_id": "B", "news_attention_level": "low", "news_count_3d": 0, "future_5d_return": -0.01},
    ])
    result = run_news_feature_diagnostics(feature_frame=features, output_dir="tmp")
    assert "bucket" in result["bucket_summary"].columns
    assert result["warnings"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_news_features.py -v`
Expected: FAIL because `run_news_feature_diagnostics` does not exist.

- [ ] **Step 3: Implement diagnostics summary functions**

```python
def summarize_news_feature_buckets(feature_frame: pd.DataFrame) -> pd.DataFrame:
    frame = feature_frame.copy()
    frame["bucket"] = pd.qcut(frame["news_count_3d"].rank(method="first"), 4, labels=False, duplicates="drop")
    return (
        frame.groupby("bucket", dropna=False)
        .agg(
            sample_count=("asset_id", "count"),
            avg_future_5d_return=("future_5d_return", "mean"),
            avg_future_10d_return=("future_10d_return", "mean"),
        )
        .reset_index()
    )
```

```python
def run_news_feature_diagnostics(*, feature_frame: pd.DataFrame, output_dir: str) -> dict:
    warnings: list[str] = []
    if feature_frame["asset_id"].nunique() < 20:
        warnings.append("sample_too_small_for_strong_conclusion")
    bucket_summary = summarize_news_feature_buckets(feature_frame)
    regime_summary = summarize_news_feature_regimes(feature_frame)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    bucket_path = output_path / "news_feature_bucket_effectiveness.csv"
    regime_path = output_path / "news_feature_regime_effectiveness.csv"
    report_path = output_path / "news_feature_diagnostics_report.md"
    bucket_summary.to_csv(bucket_path, index=False)
    regime_summary.to_csv(regime_path, index=False)
    report_path.write_text(
        "# News Feature Diagnostics\\n\\n"
        f"- warnings: {', '.join(warnings) if warnings else 'none'}\\n"
        f"- bucket_rows: {len(bucket_summary)}\\n"
        f"- regime_rows: {len(regime_summary)}\\n",
        encoding="utf-8",
    )
    return {
        "bucket_summary": bucket_summary,
        "regime_summary": regime_summary,
        "warnings": warnings,
        "paths": {
            "bucket_summary": str(bucket_path),
            "regime_summary": str(regime_path),
            "report": str(report_path),
        },
    }
```

- [ ] **Step 4: Add diagnostics CLI**

```python
news_feature_diagnostics = subparsers.add_parser("news-feature-diagnostics")
news_feature_diagnostics.add_argument("--feature-path", required=True)
news_feature_diagnostics.add_argument("--output-dir", default="outputs/research")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_news_features.py -v`
Expected: PASS, with warnings emitted for small samples instead of crashes.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/news_features.py src/stock_research/cli.py tests/test_news_features.py
git commit -m "feat: add news feature diagnostics"
```

---

### Task 6: Integrate TopN News Enrichment into Position Dossier

**Files:**
- Modify: `src/stock_research/mid_trend_position_dossier.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Write failing dossier integration tests**

```python
def test_position_dossier_includes_news_sections_when_enrichment_present(tmp_path):
    portfolio_review = pd.DataFrame([
        {
            "trade_date": "2026-06-02",
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
            "final_label": "高优先级持有",
            "current_role": "持有",
            "candidate_rank": 1,
            "target_weight": 0.2,
        }
    ])
    research_packet = pd.DataFrame([
        {
            "trade_date": "2026-06-02",
            "asset_id": "CN:SH:600183",
            "ts_code": "600183.SH",
            "stock_name": "生益科技",
            "main_positive_evidence": "主线趋势延续",
            "main_risk_evidence": "估值扩张过快",
            "why_hold_or_change": "继续持有，等待趋势确认",
        }
    ])
    news_enrichment = pd.DataFrame([
        {"trade_date": "2026-06-02", "asset_id": "CN:SH:600183", "news_consensus_summary": "催化集中", "news_risk_summary": "风险可控", "news_attention_level": "high"}
    ])
    result = build_mid_trend_position_dossier_from_frames(
        trade_date="2026-06-02",
        portfolio_review=portfolio_review,
        research_packet=research_packet,
        news_enrichment=news_enrichment,
        output_dir=tmp_path,
    )
    assert "新闻/催化观察" in result["report_text"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_mid_trend_position_dossier.py -v`
Expected: FAIL because dossier does not accept `news_enrichment`.

- [ ] **Step 3: Extend dossier inputs and rendering**

```python
def build_mid_trend_position_dossier_from_frames(
    *,
    trade_date: str,
    portfolio_review: pd.DataFrame,
    research_packet: pd.DataFrame,
    news_enrichment: pd.DataFrame | None = None,
    output_dir: str | Path = "outputs/research",
    mode: str = "replay",
):
    holdings = load_current_holdings(portfolio_review=portfolio_review, trade_date=trade_date)
    if news_enrichment is not None and not news_enrichment.empty:
        holdings = holdings.merge(
            news_enrichment[
                ["trade_date", "asset_id", "news_consensus_summary", "news_risk_summary", "theme_catalyst_summary", "overnight_catalyst_note", "news_attention_level"]
            ],
            on=["trade_date", "asset_id"],
            how="left",
        )
    return render_mid_trend_position_dossier(
        trade_date=trade_date,
        holdings=holdings,
        research_packet=research_packet,
        output_dir=output_dir,
        mode=mode,
    )
```

```python
lines.append("**新闻/催化观察**")
lines.append(f"- 新闻关注层级：{row.get('news_attention_level') or 'unknown'}")
if row.get("theme_catalyst_summary"):
    lines.append(f"- 催化：{row['theme_catalyst_summary']}")
if row.get("news_risk_summary"):
    lines.append(f"- 风险：{row['news_risk_summary']}")
```

- [ ] **Step 4: Add optional CLI argument**

```python
mid_trend_position_dossier.add_argument("--news-enrichment-path")
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_mid_trend_position_dossier.py -v`
Expected: PASS for both enriched and non-enriched dossier paths.

- [ ] **Step 6: Commit**

```bash
git add src/stock_research/mid_trend_position_dossier.py src/stock_research/cli.py tests/test_mid_trend_position_dossier.py
git commit -m "feat: integrate news enrichment into position dossier"
```

---

### Task 7: End-to-End Smoke and Documentation Refresh

**Files:**
- Modify: `docs/superpowers/specs/2026-06-04-a-share-topn-news-layer-and-news-feature-diagnostics-v1-design.md` (only if implementation realities require clarifications)
- Test: `tests/test_news_source_backfill.py`
- Test: `tests/test_news_features.py`
- Test: `tests/test_topn_news_enrichment.py`
- Test: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Add one smoke test that exercises the nominal local path**

```python
def test_topn_news_pipeline_smoke(tmp_path):
    events = normalize_news_source_rows(
        [
            {
                "source_event_id": "n1",
                "source_name": "cls",
                "source_channel": "major_news",
                "title": "生益科技订单增长",
                "content": "600183.SH 生益科技获订单增长",
                "published_at": "2026-06-02 08:40:00",
                "language": "zh",
                "url": "https://example.com/n1",
                "metadata": {},
            }
        ],
        source_status="available",
    )
    mentions = map_news_mentions(
        events=events,
        assets=pd.DataFrame([{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]),
    )
    features = build_news_feature_daily(mentions=mentions, trade_dates=["2026-06-02"], mode="replay")
    enrichment = build_topn_news_enrichment(
        candidates=pd.DataFrame([
            {"trade_date": "2026-06-02", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}
        ]),
        news_features=features,
    )
    assert not enrichment.empty
```

- [ ] **Step 2: Run focused suite**

Run: `pytest tests/test_news_source_backfill.py tests/test_news_features.py tests/test_topn_news_enrichment.py tests/test_mid_trend_position_dossier.py -v`
Expected: PASS

- [ ] **Step 3: Run full regression suite**

Run: `pytest -q`
Expected: PASS with existing suite green and no regressions in `portfolio_review`, `position_dossier`, `research_narrative`.

- [ ] **Step 4: Refresh spec wording only if actual implementation differs**

```markdown
- Clarify provider fallback behavior if the implemented CLI emits `disabled` instead of `permission_denied`.
- Clarify whether `news_event_mention` stores theme-only rows with `asset_id` null.
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-06-04-a-share-topn-news-layer-and-news-feature-diagnostics-v1-design.md tests/test_news_source_backfill.py tests/test_news_features.py tests/test_topn_news_enrichment.py tests/test_mid_trend_position_dossier.py
git commit -m "test: cover end-to-end topn news pipeline"
```

---

## Self-Review

### Spec coverage

- Raw event layer: covered by Tasks 1-2.
- Mention + feature layer: covered by Task 3.
- TopN enhancement layer: covered by Task 4.
- Diagnostics outputs: covered by Task 5.
- Dossier integration: covered by Task 6.
- Replay/live and failure handling: covered by Tasks 2-3 and tested directly.

### Placeholder scan

- No `TODO`/`TBD`.
- All tasks include concrete files, code examples, commands, and expected outcomes.

### Type consistency

- Raw events normalize into `NEWS_SOURCE_COLUMNS`.
- Feature builder consumes `mentions` with `published_at`, `trade_date`, `asset_id`.
- TopN enrichment consumes `candidates + news_features`.
- Dossier consumes optional `news_enrichment`.
