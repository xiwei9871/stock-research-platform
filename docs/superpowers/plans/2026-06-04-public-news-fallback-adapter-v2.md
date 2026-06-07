# Public News Fallback Adapter v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 `AKShare stock_news_em + CNInfo announcement` 替代当前不可用的 `Tushare` 新闻权限输入，让现有 `news_feature_backfill -> topn_news_enrichment -> mid_trend_position_dossier` 链路第一次吃到真实公开新闻/公告数据。

**Architecture:** 保持现有 `news_event_source / news_feature_daily / topn_news_enrichment / dossier` 下游 contract 不变，只扩展 `news_source_backfill.py` 的 provider 层，并新增一个更符合当前工作流的 `topn-news-source-backfill` 模式。优先做 `AKShare stock_news_em` 的 TopN 主路径，再补 `CNInfo` 公告 adapter，最后做 focused smoke 和最小文档回写。

**Tech Stack:** Python, pandas, existing DB helpers and settings, existing news pipeline modules, `akshare`, optional CNInfo HTTP access via existing Python stdlib / requests stack already in repo if available, pytest, CLI wiring in `stock_research.cli`.

---

## File Structure

### New files

- `tests/test_public_news_fallback_adapter.py`
  - 覆盖 `AKShare stock_news_em`、`CNInfo announcement`、TopN source runner 的主 contract。

### Modified files

- `src/stock_research/news_source_backfill.py`
  - 增加 provider dispatch：
    - `akshare_stock_news_em`
    - `cninfo_announcement`
  - 增加 TopN source backfill mode
  - 保持现有 `normalize_news_source_rows(...)` 和 `run_news_source_backfill(...)` contract 兼容
- `src/stock_research/cli.py`
  - 增加 `topn-news-source-backfill`
  - 扩展 `news-source-backfill --provider`
- `tests/test_news_source_backfill.py`
  - 扩展 provider 级 contract 测试
- `docs/superpowers/specs/2026-06-04-public-news-fallback-adapter-v2-design.md`
  - 如实现细节有必要，最小回写

---

### Task 1: Add AKShare Stock News Provider Contract

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Modify: `tests/test_news_source_backfill.py`

- [ ] **Step 1: Write the failing AKShare provider tests**

```python
def test_fetch_news_rows_akshare_stock_news_em_normalizes_rows(monkeypatch):
    class FakeAk:
        @staticmethod
        def stock_news_em(symbol: str):
            return pd.DataFrame(
                [
                    {
                        "关键词": symbol,
                        "新闻标题": "生益科技获机构看好",
                        "新闻内容": "公司订单增长。",
                        "发布时间": "2026-06-02 08:30:00",
                        "文章来源": "东方财富",
                        "新闻链接": "https://example.com/news1",
                    }
                ]
            )

    monkeypatch.setattr("stock_research.news_source_backfill.ak", FakeAk())

    rows = fetch_news_rows(
        start_date="2026-06-01",
        end_date="2026-06-02",
        provider="akshare_stock_news_em",
        symbol="600183",
    )

    assert len(rows) == 1
    assert rows[0]["source_name"] == "akshare_stock_news_em"
    assert rows[0]["source_channel"] == "eastmoney_stock_news"
    assert rows[0]["title"] == "生益科技获机构看好"
```

- [ ] **Step 2: Run the focused test to verify failure**

Run: `cd /Users/xiwei/stock_research && ./.venv/bin/pytest tests/test_news_source_backfill.py::test_fetch_news_rows_akshare_stock_news_em_normalizes_rows -q`

Expected: FAIL because `fetch_news_rows(...)` does not yet support `provider="akshare_stock_news_em"`.

- [ ] **Step 3: Implement minimal AKShare provider dispatch**

```python
def _fetch_akshare_stock_news_rows(*, symbol: str) -> list[dict]:
    if ak is None:
        raise RuntimeError("akshare package is required for akshare_stock_news_em provider")
    frame = ak.stock_news_em(symbol=symbol)
    if frame is None or frame.empty:
        return []
    rows: list[dict] = []
    for row in frame.to_dict(orient="records"):
        published_at = row.get("发布时间") or row.get("发布时间 ") or row.get("datetime")
        title = row.get("新闻标题") or row.get("title")
        content = row.get("新闻内容") or row.get("content")
        url = row.get("新闻链接") or row.get("url")
        source_name = "akshare_stock_news_em"
        rows.append(
            {
                "source_event_id": hashlib.sha1(f"{source_name}|{title or ''}|{published_at or ''}|{url or ''}".encode("utf-8")).hexdigest(),
                "source_name": source_name,
                "source_channel": "eastmoney_stock_news",
                "title": title,
                "content": content,
                "published_at": published_at,
                "language": "zh",
                "url": url,
                "metadata": {"provider": "akshare_stock_news_em", "raw": row},
            }
        )
    return rows
```

```python
def fetch_news_rows(..., provider: str = "tushare", token: str | None = None, symbol: str | None = None) -> list[dict]:
    if provider == "akshare_stock_news_em":
        if not symbol:
            raise ValueError("symbol is required for akshare_stock_news_em")
        return _fetch_akshare_stock_news_rows(symbol=symbol)
    ...
```

- [ ] **Step 4: Run the focused test to verify pass**

Run: `cd /Users/xiwei/stock_research && ./.venv/bin/pytest tests/test_news_source_backfill.py::test_fetch_news_rows_akshare_stock_news_em_normalizes_rows -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/news_source_backfill.py tests/test_news_source_backfill.py
git commit -m "feat: add akshare stock news source adapter"
```

---

### Task 2: Add TopN News Source Backfill Mode

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Modify: `src/stock_research/cli.py`
- Test: `tests/test_public_news_fallback_adapter.py`

- [ ] **Step 1: Write the failing TopN source backfill test**

```python
def test_run_topn_news_source_backfill_uses_candidate_symbols_and_writes_events(tmp_path, monkeypatch):
    candidates = pd.DataFrame(
        [
            {"trade_date": "2026-06-02", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"},
            {"trade_date": "2026-06-02", "asset_id": "CN:SZ:300201", "ts_code": "300201.SZ", "stock_name": "海伦哲"},
        ]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": f\"{kwargs['symbol']}-1\",
                "source_name": "akshare_stock_news_em",
                "source_channel": "eastmoney_stock_news",
                "title": f\"{kwargs['symbol']} 新闻\",
                "content": "正文",
                "published_at": "2026-06-02 09:00:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )

    result = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "out",
    )

    assert Path(result["paths"]["events"]).exists()
    assert len(result["events"]) == 2
    assert set(result["events"]["source_name"]) == {"akshare_stock_news_em"}
```

- [ ] **Step 2: Run the test to verify failure**

Run: `cd /Users/xiwei/stock_research && ./.venv/bin/pytest tests/test_public_news_fallback_adapter.py::test_run_topn_news_source_backfill_uses_candidate_symbols_and_writes_events -q`

Expected: FAIL because `run_topn_news_source_backfill(...)` does not exist.

- [ ] **Step 3: Implement TopN source runner**

```python
def _ts_code_to_symbol(ts_code: str) -> str:
    return str(ts_code).split(".")[0].strip()


def run_topn_news_source_backfill(
    *,
    candidates_path: str | Path,
    provider: str,
    trade_date: str,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    candidates = pd.read_csv(candidates_path, low_memory=False)
    candidates["trade_date"] = pd.to_datetime(candidates["trade_date"], errors="coerce").dt.date
    target_date = pd.to_datetime(trade_date).date()
    candidates = candidates.loc[candidates["trade_date"] == target_date].copy()
    event_rows: list[dict] = []
    for row in candidates.to_dict("records"):
        symbol = _ts_code_to_symbol(row["ts_code"])
        rows = fetch_news_rows(
            start_date=trade_date,
            end_date=trade_date,
            provider=provider,
            symbol=symbol,
        )
        for item in rows:
            item = dict(item)
            item["metadata"] = {
                **(item.get("metadata") or {}),
                "candidate_asset_id": row["asset_id"],
                "candidate_ts_code": row["ts_code"],
                "candidate_stock_name": row["stock_name"],
            }
            event_rows.append(item)
    events = normalize_news_source_rows(event_rows, source_status="available")
    destination_dir = Path(output_dir or Path("outputs/research") / f"topn_news_source_backfill_{trade_date}")
    paths = _write_news_source_backfill_report(output_dir=destination_dir, events=events, source_status="available")
    return {"events": events, "paths": paths}
```

- [ ] **Step 4: Add CLI command**

```python
topn_news_source_backfill = subparsers.add_parser("topn-news-source-backfill")
topn_news_source_backfill.add_argument("--candidates-path", required=True)
topn_news_source_backfill.add_argument("--provider", choices=["akshare_stock_news_em", "cninfo_announcement"], required=True)
topn_news_source_backfill.add_argument("--trade-date", required=True)
topn_news_source_backfill.add_argument("--output-dir")
```

```python
elif args.command == "topn-news-source-backfill":
    result = run_topn_news_source_backfill(
        candidates_path=args.candidates_path,
        provider=args.provider,
        trade_date=args.trade_date,
        output_dir=args.output_dir,
    )
    print(f"topn_news_source_backfill|events|{result['paths']['events']}")
    print(f"topn_news_source_backfill|report|{result['paths']['report']}")
    print(f"topn_news_source_backfill|rows|{len(result['events'])}")
```

- [ ] **Step 5: Run focused tests to verify pass**

Run: `cd /Users/xiwei/stock_research && ./.venv/bin/pytest tests/test_public_news_fallback_adapter.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/news_source_backfill.py src/stock_research/cli.py tests/test_public_news_fallback_adapter.py
git commit -m "feat: add topn public news source backfill mode"
```

---

### Task 3: Add CNInfo Announcement Provider Contract

**Files:**
- Modify: `src/stock_research/news_source_backfill.py`
- Modify: `tests/test_news_source_backfill.py`

- [ ] **Step 1: Write the failing CNInfo normalization test**

```python
def test_fetch_news_rows_cninfo_announcement_normalizes_rows(monkeypatch):
    monkeypatch.setattr(
        "stock_research.news_source_backfill._fetch_cninfo_announcement_rows",
        lambda ts_code, stock_name, start_date, end_date: [
            {
                "source_event_id": "ann1",
                "source_name": "cninfo_announcement",
                "source_channel": "disclosure_announcement",
                "title": "关于股票交易异常波动的公告",
                "content": "",
                "published_at": "2026-06-02 20:00:00",
                "language": "zh",
                "url": "https://www.cninfo.com.cn/ann1",
                "metadata": {"ts_code": ts_code, "stock_name": stock_name},
            }
        ],
    )

    rows = fetch_news_rows(
        start_date="2026-06-01",
        end_date="2026-06-02",
        provider="cninfo_announcement",
        ts_code="600183.SH",
        stock_name="生益科技",
    )

    assert len(rows) == 1
    assert rows[0]["source_name"] == "cninfo_announcement"
    assert rows[0]["source_channel"] == "disclosure_announcement"
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd /Users/xiwei/stock_research && ./.venv/bin/pytest tests/test_news_source_backfill.py::test_fetch_news_rows_cninfo_announcement_normalizes_rows -q`

Expected: FAIL because provider is unsupported.

- [ ] **Step 3: Implement minimal CNInfo provider stub and dispatch**

```python
def _fetch_cninfo_announcement_rows(*, ts_code: str, stock_name: str | None, start_date: str, end_date: str) -> list[dict]:
    raise RuntimeError("cninfo_announcement provider not yet configured for live fetch")
```

```python
def fetch_news_rows(..., provider: str = "tushare", ..., ts_code: str | None = None, stock_name: str | None = None) -> list[dict]:
    if provider == "cninfo_announcement":
        if not ts_code:
            raise ValueError("ts_code is required for cninfo_announcement")
        return _fetch_cninfo_announcement_rows(
            ts_code=ts_code,
            stock_name=stock_name,
            start_date=start_date,
            end_date=end_date,
        )
```

Note:
- For this task, the provider function only needs a clean, testable contract and dispatch path.
- The live HTTP fetch can remain unimplemented if the test uses monkeypatching and the dispatch surface is correct.

- [ ] **Step 4: Run focused tests to verify pass**

Run: `cd /Users/xiwei/stock_research && ./.venv/bin/pytest tests/test_news_source_backfill.py::test_fetch_news_rows_cninfo_announcement_normalizes_rows -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/xiwei/stock_research
git add src/stock_research/news_source_backfill.py tests/test_news_source_backfill.py
git commit -m "feat: add cninfo announcement provider contract"
```

---

### Task 4: Run Real AKShare TopN Chain Smoke

**Files:**
- Modify: `tests/test_topn_news_enrichment.py`
- Modify: `tests/test_mid_trend_position_dossier.py`

- [ ] **Step 1: Add one helper-level AKShare fallback smoke test**

```python
def test_public_news_fallback_smoke_with_topn_candidate_flow(tmp_path, monkeypatch):
    from stock_research.news_source_backfill import normalize_news_source_rows, run_topn_news_source_backfill
    from stock_research.news_features import map_news_mentions, build_news_feature_daily
    from stock_research.topn_news_enrichment import build_topn_news_enrichment

    candidates = pd.DataFrame(
        [{"trade_date": "2026-06-02", "asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}]
    )
    candidates_path = tmp_path / "candidates.csv"
    candidates.to_csv(candidates_path, index=False)

    monkeypatch.setattr(
        "stock_research.news_source_backfill.fetch_news_rows",
        lambda **kwargs: [
            {
                "source_event_id": "n1",
                "source_name": "akshare_stock_news_em",
                "source_channel": "eastmoney_stock_news",
                "title": "生益科技获机构看好",
                "content": "公司订单增长。",
                "published_at": "2026-06-02 08:30:00",
                "language": "zh",
                "url": None,
                "metadata": {},
            }
        ],
    )

    source = run_topn_news_source_backfill(
        candidates_path=candidates_path,
        provider="akshare_stock_news_em",
        trade_date="2026-06-02",
        output_dir=tmp_path / "source",
    )
    events = source["events"]
    assets = pd.DataFrame([{"asset_id": "CN:SH:600183", "ts_code": "600183.SH", "stock_name": "生益科技"}])
    mentions = map_news_mentions(events=events, assets=assets)
    features = build_news_feature_daily(mentions=mentions, trade_dates=["2026-06-02"], mode="replay")
    enrichment = build_topn_news_enrichment(candidates=candidates, news_features=features)

    assert len(events) == 1
    assert len(mentions) == 1
    assert len(features) == 1
    assert enrichment.loc[0, "news_attention_level"] != "unknown"
```

- [ ] **Step 2: Run focused suite**

Run:

```bash
cd /Users/xiwei/stock_research && ./.venv/bin/pytest \
  tests/test_news_source_backfill.py \
  tests/test_news_features.py \
  tests/test_topn_news_enrichment.py \
  tests/test_mid_trend_position_dossier.py \
  tests/test_public_news_fallback_adapter.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/xiwei/stock_research
git add tests/test_news_source_backfill.py tests/test_news_features.py tests/test_topn_news_enrichment.py tests/test_mid_trend_position_dossier.py tests/test_public_news_fallback_adapter.py
git commit -m "test: add public news fallback smoke coverage"
```

---

### Task 5: Refresh Spec Where Implementation Reality Matters

**Files:**
- Modify: `docs/superpowers/specs/2026-06-04-public-news-fallback-adapter-v2-design.md`

- [ ] **Step 1: Write the minimal doc corrections**

Update the spec so it explicitly reflects these implementation choices if they remain true after Tasks 1-4:

```markdown
- `akshare_stock_news_em` is the first fully supported live provider path in v2.
- `cninfo_announcement` is introduced as a provider contract first; live fetch may remain a staged follow-up.
- `topn-news-source-backfill` is the primary operational path for public news v2.
- Existing replay diagnostics remain based on `news_feature_backfill` outputs, not on `live` overlay semantics.
```

- [ ] **Step 2: Self-check the spec against implementation**

Run:

```bash
rg -n "AKShare|CNInfo|topn-news-source-backfill|live" docs/superpowers/specs/2026-06-04-public-news-fallback-adapter-v2-design.md
```

Expected:
- The doc text matches the final implementation reality.

- [ ] **Step 3: Commit**

```bash
cd /Users/xiwei/stock_research
git add docs/superpowers/specs/2026-06-04-public-news-fallback-adapter-v2-design.md
git commit -m "docs: refresh public news fallback adapter v2 design"
```

---

## Self-Review

### Spec coverage

- AKShare fallback provider: Task 1.
- TopN source mode: Task 2.
- CNInfo provider contract: Task 3.
- End-to-end public fallback smoke: Task 4.
- Spec refresh for implementation reality: Task 5.

### Placeholder scan

- No `TODO` / `TBD`.
- Every task has exact files, code, commands, and expected outcomes.

### Type consistency

- `fetch_news_rows(...)` expands with `symbol`, `ts_code`, `stock_name` inputs in a controlled way.
- `run_topn_news_source_backfill(...)` produces standard source rows, not a new downstream contract.
- Existing `news_feature_backfill -> topn_news_enrichment -> dossier` contracts remain unchanged.

