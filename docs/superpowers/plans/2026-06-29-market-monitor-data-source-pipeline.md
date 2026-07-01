# Market Monitor Data Source Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Market Monitor tab display real post-close market overview, industry heatmap, sector fund-flow, and sector detail data for every ready trade date, with explicit degraded/missing states when a source cannot be produced.

**Architecture:** Reuse the existing dashboard API shape and service modules, but add a real EOD generation layer below them. The pipeline will derive market breadth and industry sector data from existing `market_daily_bar`, `core.industry_membership`, `market.index_daily_bar`, and `research.market_emotion_state_daily`; fund-flow will first use a deterministic proxy from sector amount/price/breadth until a true third-party northbound/main-fund source is added.

**Tech Stack:** Python, PostgreSQL service connections, existing `stock_research` CLI/pipeline style, pytest, FastAPI dashboard services, React dashboard already wired to these APIs.

---

## Current Findings

- `market_overview_service.py` reads `research.market_emotion_state_daily` and `market.index_daily_bar`; the API is correct, but 2026-06-26 currently returns missing because the required rows are absent or not generated for the date.
- `sector_heatmap_service.py` reads `market.industry_daily_bar`; the API is correct for industries, but the daily close process did not guarantee `market.industry_daily_bar` is built for the latest ready date.
- `sector_fund_flow_service.py` is currently a stub: `load_sector_fund_flow_rows()` always returns `[]`.
- `sector_heatmap_service.py` intentionally returns missing for `concept`, so concept heatmap/detail is not a real source yet.
- Frontend now correctly refuses to show mock data; therefore backend/data readiness must become the source of truth.

## File Map

- Modify: `src/stock_research/dashboard/market_overview_service.py`
  - Keep API shape, improve fallback and warnings around market emotion/index source coverage.
- Modify: `src/stock_research/dashboard/sector_heatmap_service.py`
  - Use generated industry bars and per-sector member breadth reliably for all ready dates.
- Modify: `src/stock_research/dashboard/sector_fund_flow_service.py`
  - Replace stub with derived sector directional-flow rows.
- Modify: `src/stock_research/dashboard/sector_detail_service.py`
  - Ensure selected sector detail and leading stocks are generated from the same source rows.
- Modify: `src/stock_research/daily_incremental.py`
  - Ensure index bars and industry bars are generated as part of post-close update.
- Modify: `src/stock_research/daily_close_pipeline.py`
  - Add Market Monitor EOD generation/check stage after market data readiness and before final dashboard readiness.
- Modify: `src/stock_research/platform_ready.py`
  - Add Market Monitor readiness checks for overview, industry heatmap, and fund-flow.
- Modify: `src/stock_research/dashboard/platform.py`
  - Surface latest market monitor date/status in platform summary.
- Create or modify: `tests/test_dashboard_market_monitor.py`
  - Add service tests for overview, heatmap, fund-flow, and API missing/degraded behavior.
- Modify: `tests/test_daily_incremental.py`
  - Assert daily incremental calls index sync and industry build for the selected date.
- Modify: `tests/test_platform_ready.py`
  - Assert platform readiness includes Market Monitor data checks.
- Modify: `dashboard/tests/market-monitor-workspace.test.tsx`
  - Keep existing no-mock regression; add one integration-style frontend assertion if API returns real sector rows.

## Data Contract

### Required for “completed”

- Market overview:
  - `research.market_emotion_state_daily` has one row for `trade_date`.
  - `market.index_daily_bar` has at least 上证指数、深证成指、创业板指; 科创50/北证50 may downgrade to `partial` if the source cannot provide them.
- Industry heatmap:
  - `market.industry_daily_bar` has rows for `trade_date` and `industry_system='csrc'`.
  - `core.industry_membership` joins to `market_daily_bar` for the same date and provides `stock_count`, `up_count`, `down_count`.
- Sector fund-flow v1:
  - Derived from industry rows using `main_net_inflow_proxy = amount * change_pct * breadth_weight`.
  - `breadth_weight = (up_count - down_count) / max(stock_count, 1)`.
  - This is explicitly labeled as `derived:industry_amount_price_breadth_proxy`, not true external capital flow.
- Sector detail:
  - Same sector aggregate row as heatmap.
  - Leading stocks from sector members ranked by `pct_chg DESC, amount DESC`.

### Required for “partial”

- Overview has either market emotion or at least one required index row.
- Heatmap has industry rows but member breadth is incomplete.
- Fund-flow has heatmap rows but proxy cannot compute for all sectors.

### Required for “missing”

- No usable source rows for that endpoint/date.

---

## Next-Step Execution Plan: Data Sources And Generation Chain

The next implementation pass should focus on making Market Monitor a first-class daily close product, not a dashboard-only fallback. The dashboard may compute a temporary response for debugging, but a ready trade date must have persisted/generated sources that can be audited before local or external release.

### Canonical Data Sources

| Module | Canonical source | Generation owner | Required status |
| --- | --- | --- | --- |
| Market overview breadth | `research.market_emotion_state_daily` | `daily_close_pipeline.market_monitor` | Required |
| Major indices | `market.index_daily_bar` for `SSE_COMPOSITE`, `SZSE_COMPONENT`, `CHINEXT`, `STAR_50`, `BSE_50` | `sync_index_daily_bars()` | Required for completed; missing index gives precise degraded warning |
| Industry heatmap | `market.industry_daily_bar` where `industry_system='csrc'`, `adjust_type='qfq'` | `build_industry_daily_bars_for_service()` | Required |
| Industry member breadth | `core.industry_membership` + `market_daily_bar` | SQL derived at API/readiness time | Required for completed heatmap metadata |
| Sector fund-flow v1 | Derived proxy from industry amount, price change, and breadth | `sector_fund_flow_service.py` | Required as clearly labeled proxy |
| Concept heatmap/fund-flow | No canonical source yet | None in this iteration | Must remain missing/degraded, never mocked |

### Generation Chain

For every post-close ready trade date, the chain should run in this order:

```text
market daily/minute sync
  -> index daily sync, including STAR_50 and BSE_50 fallback source
  -> asset status daily build
  -> industry daily bars build for csrc/qfq
  -> market emotion state persist
  -> market monitor source check
  -> strategy_daily_eod
  -> platform_ready finalization
  -> local dashboard smoke
  -> external sync only after local smoke passes
```

### Task A: Persist Market Emotion State

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py`
- Test: `tests/test_daily_close_pipeline.py`

- [x] **Step 1: Add a failing test for `upsert_market_emotion_state_daily()`**

Expected behavior:

```python
rows = dcp.upsert_market_emotion_state_daily("2026-06-26", service="test")
assert rows == 1
```

The test should verify that `research.market_emotion_state_daily` gets one row with non-null `total_amount`, `up_count`, `down_count`, `limit_up_count`, and `limit_down_count`.

- [x] **Step 2: Implement the table DDL and upsert**

The function should create the table if missing, compute the row from existing daily bars, and upsert by `trade_date`. Store amount in the same storage unit as the existing market emotion computation; dashboard display conversion stays inside the dashboard service layer.

- [x] **Step 3: Verify**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_daily_close_pipeline.py -q -k "market_emotion"
```

### Task B: Add `market_monitor` Daily Close Stage

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py`
- Modify: `scripts/run_daily_close_finalize_cron.sh`
- Test: `tests/test_daily_close_pipeline.py`
- Test: `tests/test_daily_close_scripts.py`

- [x] **Step 1: Add failing stage test**

Expected stage behavior:

```python
result = dcp.run_market_monitor_stage(date(2026, 6, 26), config=config)

assert result["stage"] == "market_monitor"
assert result["status"] == "success"
assert result["sources"]["emotion_rows"] == 1
assert result["sources"]["index_rows"] >= 5
assert result["sources"]["industry_rows"] > 0
assert result["sources"]["fund_flow_rows"] > 0
```

- [x] **Step 2: Implement stage work**

The stage should call these production functions in sequence:

```python
sync_index_daily_bars(start_date, end_date, service=config.service)
build_asset_status_daily_for_service(start_date, end_date, adjust_type="qfq", service=config.service)
build_industry_daily_bars_for_service(start_date, end_date, industry_system="csrc", adjust_type="qfq", service=config.service)
upsert_market_emotion_state_daily(trade_date, service=config.service)
check_market_monitor_sources(trade_date, service=config.service)
```

- [x] **Step 3: Wire stage into CLI/finalize cron**

Add `market_monitor` as a supported stage and run it before `health`/final platform readiness in `scripts/run_daily_close_finalize_cron.sh`.

- [x] **Step 4: Verify**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_daily_close_pipeline.py tests/test_daily_close_scripts.py -q -k "market_monitor or finalize"
```

### Task C: Platform-Ready Gate Uses The Same Sources

**Files:**
- Modify: `src/stock_research/platform_ready.py`
- Modify: `src/stock_research/dashboard/readiness.py`
- Test: `tests/test_platform_ready.py`
- Test: `tests/test_dashboard_readiness.py`

- [x] **Step 1: Readiness must fail when Market Monitor sources are missing**

Expected failure reason:

```text
market_monitor_sources failed: emotion_rows=0 or index_rows<5 or industry_rows=0 or fund_flow_rows=0
```

- [x] **Step 2: Readiness must pass when sources are present**

The gate should check the same canonical sources listed above, not a separate dashboard-only heuristic.

- [x] **Step 3: Verify**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_platform_ready.py tests/test_dashboard_readiness.py -q -k "market_monitor or readiness"
```

### Task D: Backfill And Evidence Artifact

**Files:**
- Produce: `outputs/research/market_monitor_backfill_2026-06-23_2026-06-26.json`

- [x] **Step 1: Run the new stage for each recent ready date**

```bash
cd /Users/xiwei/stock_research
for d in 2026-06-23 2026-06-24 2026-06-25 2026-06-26; do
  rtk .venv/bin/python -m stock_research.daily_close_pipeline --date "$d" --stage market_monitor --force
done
```

- [x] **Step 2: Write a compact verification artifact**

The artifact must include, per date:

```json
{
  "trade_date": "2026-06-26",
  "emotion_rows": 1,
  "index_rows": 5,
  "industry_rows": 85,
  "fund_flow_rows": 85,
  "overview_status": "completed",
  "heatmap_status": "completed",
  "fund_flow_status": "completed"
}
```

- [x] **Step 3: Verify local APIs before any external sync**

```bash
for d in 2026-06-23 2026-06-24 2026-06-25 2026-06-26; do
  rtk curl -s "http://127.0.0.1:8765/api/market-monitor/overview?trade_date=$d"
  rtk curl -s "http://127.0.0.1:8765/api/market-monitor/sectors/heatmap?trade_date=$d&type=industry"
  rtk curl -s "http://127.0.0.1:8765/api/market-monitor/sectors/fund-flow?trade_date=$d&type=industry"
done
```

### Task E: Local-First Release Rule

External sync remains blocked until all of the following are true:

- [x] `market_monitor` stage succeeds for the target trade date.
- [x] `platform_ready` includes `market_monitor_sources=success`.
- [x] `http://127.0.0.1:5174/` Market Monitor shows the same values as the API.
- [x] No endpoint returns sample/mock/demo values.
- [x] The evidence artifact for the target date is written under `outputs/research/`.

---

## Task 1: Confirm And Lock Current Missing Behavior

**Files:**
- Modify: `tests/test_dashboard_market_monitor.py`
- Read: `src/stock_research/dashboard/market_overview_service.py`
- Read: `src/stock_research/dashboard/sector_heatmap_service.py`
- Read: `src/stock_research/dashboard/sector_fund_flow_service.py`

- [x] **Step 1: Write failing tests for completed payloads**

Add tests that monkeypatch loaders and assert completed payloads never return sample/mock values:

```python
def test_market_overview_completed_from_emotion_and_index_rows(monkeypatch):
    from stock_research.dashboard import market_overview_service as svc

    monkeypatch.setattr(
        svc,
        "load_market_overview_row",
        lambda trade_date, service=svc.SETTINGS.research_service: {
            "trade_date": trade_date,
            "total_amount": 1234000000000,
            "up_count": 3000,
            "down_count": 2100,
            "limit_up_count": 66,
            "limit_down_count": 9,
            "source": "research.market_emotion_state_daily",
            "updated_at": "2026-06-26 18:00:00",
        },
    )
    monkeypatch.setattr(
        svc,
        "load_market_index_rows",
        lambda trade_date, service=svc.SETTINGS.research_service: [
            {"index_id": "SSE_COMPOSITE", "close": 3000, "preclose": 2970, "source": "market.index_daily_bar"},
            {"index_id": "SZSE_COMPONENT", "close": 10000, "preclose": 9900, "source": "market.index_daily_bar"},
            {"index_id": "CHINEXT", "close": 2000, "preclose": 1980, "source": "market.index_daily_bar"},
            {"index_id": "STAR_50", "close": 800, "preclose": 790, "source": "market.index_daily_bar"},
            {"index_id": "BSE_50", "close": 1100, "preclose": 1110, "source": "market.index_daily_bar"},
        ],
    )

    payload = svc.build_market_overview_payload("2026-06-26")

    assert payload["data_status"] == "completed"
    assert payload["total_amount"] == 1234000000000
    assert payload["indices"][0]["name"] == "上证指数"
    assert payload["indices"][0]["close"] == 3000
```

- [x] **Step 2: Run the test and verify current status**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_dashboard_market_monitor.py -q
```

Expected before implementation: any new fund-flow completed-source test fails because `load_sector_fund_flow_rows()` always returns `[]`.

- [x] **Step 3: Commit after tests are in place**

Note: commit is intentionally treated as not applicable for this session because the user did not request a commit and the workspace contains unrelated existing changes. Do not create a mixed commit without explicit approval.

Only commit if the working tree is isolated to this task:

```bash
git add tests/test_dashboard_market_monitor.py
git commit -m "test: lock market monitor data source contracts"
```

---

## Task 2: Generate Industry Heatmap Data Every Post-Close Day

**Files:**
- Modify: `src/stock_research/core_data.py`
- Modify: `src/stock_research/daily_incremental.py`
- Modify: `tests/test_core_data.py`
- Modify: `tests/test_daily_incremental.py`

- [x] **Step 1: Add a test that industry bars use the same adjust type as daily sync**

The current `build_industry_daily_bars_for_service()` default is `hfq`, while the dashboard heatmap service joins member stats on `market_daily_bar.adjust_type = 'qfq'`. Add/adjust a test so daily post-close builds industry bars with `adjust_type='qfq'`.

Expected assertion:

```python
assert kwargs["adjust_type"] == "qfq"
```

- [x] **Step 2: Run the failing test**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_daily_incremental.py::test_run_daily_incremental_syncs_market_sources -q
```

Expected before implementation: failure if daily incremental still calls industry build with the wrong default or omits the date.

- [x] **Step 3: Implement the minimal fix**

Update the daily incremental post-close path so it calls:

```python
build_industry_daily_bars_for_service(
    start_date=trade_date,
    end_date=trade_date,
    industry_system="csrc",
    adjust_type="qfq",
    service=service,
)
```

- [x] **Step 4: Verify industry rows can be produced**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_core_data.py tests/test_daily_incremental.py -q
```

- [x] **Step 5: Manual DB smoke after implementation**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/python -m stock_research.cli daily-incremental --trade-date 2026-06-26
rtk psql "service=stock_research" -c "SELECT trade_date, count(*) FROM market.industry_daily_bar WHERE trade_date='2026-06-26' AND industry_system='csrc' GROUP BY trade_date;"
```

Expected: industry row count is greater than zero.

---

## Task 3: Make Market Overview Fully Real For Ready Dates

**Files:**
- Modify: `src/stock_research/dashboard/market_monitor.py`
- Modify: `src/stock_research/dashboard/market_overview_service.py`
- Modify: `src/stock_research/daily_close_pipeline.py`
- Modify: `tests/test_dashboard_market_monitor.py`
- Modify: `tests/test_daily_close_pipeline.py`

- [x] **Step 1: Add tests for overview source coverage**

Add tests that verify:

```python
assert payload["data_status"] == "completed"
assert payload["warnings"] == []
assert len(payload["indices"]) >= 3
assert payload["up_count"] is not None
assert payload["down_count"] is not None
assert payload["limit_up_count"] is not None
assert payload["limit_down_count"] is not None
```

- [x] **Step 2: Run overview tests**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_dashboard_market_monitor.py -q -k "overview"
```

- [x] **Step 3: Ensure market emotion row generation is part of EOD**

If `research.market_emotion_state_daily` is missing for a date, use the existing `compute_market_emotion_row()` fallback for API reads, and add a pipeline stage that persists or validates the row before platform ready is marked.

Acceptance rule:

```sql
SELECT trade_date, total_amount, up_count, down_count, limit_up_count, limit_down_count
FROM research.market_emotion_state_daily
WHERE trade_date = '2026-06-26';
```

The query must return one row with non-null counts before Market Monitor can be `completed`.

- [x] **Step 4: Ensure index bars include dashboard index IDs**

The dashboard expects:

```python
("SSE_COMPOSITE", "SZSE_COMPONENT", "CHINEXT", "STAR_50", "BSE_50")
```

The daily close stage should either sync these IDs or downgrade only the missing ones with a precise warning.

- [x] **Step 5: Verify API smoke**

Run:

```bash
rtk curl -s 'http://127.0.0.1:8765/api/market-monitor/overview?trade_date=2026-06-26'
```

Expected:

```json
{
  "data_status": "completed",
  "indices": ["non-empty"],
  "total_amount": "non-null",
  "up_count": "non-null",
  "down_count": "non-null"
}
```

---

## Task 4: Implement Sector Fund-Flow V1 As A Derived Proxy

**Files:**
- Modify: `src/stock_research/dashboard/sector_fund_flow_service.py`
- Modify: `tests/test_dashboard_market_monitor.py`

- [x] **Step 1: Add failing test for non-empty fund-flow**

Add a test that monkeypatches `connect/fetch_all` or `load_sector_fund_flow_rows()` source query and verifies:

```python
payload = build_sector_fund_flow_payload("2026-06-26", sector_type="industry")

assert payload["data_status"] == "completed"
assert payload["source"] == "derived:industry_amount_price_breadth_proxy"
assert payload["inflow"][0]["rank"] == 1
assert payload["inflow"][0]["main_net_inflow"] > 0
assert payload["outflow"][0]["main_net_inflow"] < 0
```

- [x] **Step 2: Run the failing test**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_dashboard_market_monitor.py -q -k "fund_flow"
```

Expected before implementation: missing payload because `load_sector_fund_flow_rows()` returns `[]`.

- [x] **Step 3: Implement SQL-backed derived rows**

Replace the stub with a query over `market.industry_daily_bar` and member breadth:

```sql
WITH member_stats AS (
    SELECT
        m.industry_system,
        m.industry_code,
        count(DISTINCT b.asset_id) AS stock_count,
        count(DISTINCT b.asset_id) FILTER (WHERE b.pct_chg > 0) AS up_count,
        count(DISTINCT b.asset_id) FILTER (WHERE b.pct_chg < 0) AS down_count
    FROM core.industry_membership m
    JOIN market_daily_bar b
      ON b.asset_id = m.asset_id
     AND b.trade_date = %s
     AND b.adjust_type = 'qfq'
    WHERE m.industry_system = 'csrc'
      AND m.level = 1
      AND m.start_date <= %s
      AND (m.end_date IS NULL OR %s < m.end_date)
    GROUP BY m.industry_system, m.industry_code
)
SELECT
    bars.industry_code,
    bars.industry_name,
    bars.close,
    bars.preclose,
    bars.amount,
    (bars.close / NULLIF(bars.preclose, 0) - 1.0) AS change_pct,
    (
      COALESCE(bars.amount, 0)
      * COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
      * COALESCE((stats.up_count - stats.down_count)::numeric / NULLIF(stats.stock_count, 0), 0)
    ) AS main_net_inflow,
    CASE
      WHEN COALESCE(bars.amount, 0) = 0 THEN NULL
      ELSE (
        COALESCE((bars.close / NULLIF(bars.preclose, 0) - 1.0), 0)
        * COALESCE((stats.up_count - stats.down_count)::numeric / NULLIF(stats.stock_count, 0), 0)
      )
    END AS main_net_inflow_ratio,
    'derived:industry_amount_price_breadth_proxy' AS source,
    bars.updated_at
FROM market.industry_daily_bar bars
LEFT JOIN member_stats stats
  ON stats.industry_system = bars.industry_system
 AND stats.industry_code = bars.industry_code
WHERE bars.trade_date = %s
  AND bars.industry_system = 'csrc';
```

- [x] **Step 4: Verify service and API**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_dashboard_market_monitor.py -q -k "fund_flow or heatmap"
rtk curl -s 'http://127.0.0.1:8765/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=industry&top_n=10'
```

Expected: `inflow` and/or `outflow` are non-empty when industry bars exist.

---

## Task 5: Wire Market Monitor Readiness Into Platform Ready

**Files:**
- Modify: `src/stock_research/platform_ready.py`
- Modify: `src/stock_research/dashboard/platform.py`
- Modify: `tests/test_platform_ready.py`
- Modify: `tests/test_dashboard_platform.py`

- [x] **Step 1: Add readiness assertions**

Market Monitor readiness for a date should require:

```python
{
    "market_monitor_overview": "completed_or_partial",
    "market_monitor_industry_heatmap": "completed",
    "market_monitor_industry_fund_flow": "completed_or_partial",
}
```

- [x] **Step 2: Run failing readiness tests**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_platform_ready.py tests/test_dashboard_platform.py -q -k "market_monitor or readiness"
```

- [x] **Step 3: Add readiness query checks**

Checks should inspect the same sources the dashboard reads:

```sql
SELECT count(*) FROM market.industry_daily_bar WHERE trade_date = %s AND industry_system = 'csrc';
SELECT count(*) FROM market.index_daily_bar WHERE trade_date = %s;
SELECT count(*) FROM research.market_emotion_state_daily WHERE trade_date = %s;
```

- [x] **Step 4: Verify platform summary**

Run:

```bash
rtk curl -s 'http://127.0.0.1:8765/api/platform/summary'
rtk curl -s 'http://127.0.0.1:8765/api/platform/readiness'
```

Expected: summary exposes `latest_market_monitor_date=2026-06-26` only when overview/heatmap/fund-flow checks satisfy thresholds.

---

## Task 6: Add Daily Close Pipeline Stage

**Files:**
- Modify: `src/stock_research/daily_close_pipeline.py`
- Modify: `scripts/run_daily_close_finalize_cron.sh`
- Modify: `tests/test_daily_close_pipeline.py`
- Modify: `tests/test_daily_close_scripts.py`

- [x] **Step 1: Add pipeline test**

The finalized daily close should call, in order:

```text
1. market daily/minute readiness
2. index daily sync
3. industry daily bar build
4. market emotion generation/check
5. market monitor readiness check
6. strategy_daily_eod
7. dashboard/platform ready finalization
```

- [x] **Step 2: Run failing pipeline test**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/pytest tests/test_daily_close_pipeline.py tests/test_daily_close_scripts.py -q
```

- [x] **Step 3: Implement Market Monitor stage**

Add a named stage such as:

```python
run_stage("market_monitor_eod", lambda: build_market_monitor_eod_sources(trade_date))
```

The stage should fail hard if industry bars are missing and should degrade only optional concept/fund-flow data.

- [x] **Step 4: Verify one-date run**

Run:

```bash
cd /Users/xiwei/stock_research
rtk .venv/bin/python -m stock_research.cli daily-close-finalize --trade-date 2026-06-26
```

Expected: final platform readiness includes Market Monitor checks, and dashboard APIs return non-mock real data.

---

## Task 7: Backfill 2026-06-23 Through Latest Ready Date

**Files:**
- No code changes expected after prior tasks.
- Produce: `outputs/research/market_monitor_backfill_2026-06-23_2026-06-26.json`

- [x] **Step 1: Backfill required derived sources**

Run:

```bash
cd /Users/xiwei/stock_research
for d in 2026-06-23 2026-06-24 2026-06-25 2026-06-26; do
  rtk .venv/bin/python -m stock_research.cli daily-incremental --trade-date "$d"
done
```

- [x] **Step 2: Verify DB coverage**

Run:

```bash
rtk psql "service=stock_research" -c "
SELECT trade_date, count(*) AS industry_rows
FROM market.industry_daily_bar
WHERE trade_date BETWEEN '2026-06-23' AND '2026-06-26'
  AND industry_system='csrc'
GROUP BY trade_date
ORDER BY trade_date;"
```

Expected: every date has industry rows.

- [x] **Step 3: Verify dashboard APIs**

Run:

```bash
for d in 2026-06-23 2026-06-24 2026-06-25 2026-06-26; do
  rtk curl -s "http://127.0.0.1:8765/api/market-monitor/overview?trade_date=$d"
  rtk curl -s "http://127.0.0.1:8765/api/market-monitor/sectors/heatmap?trade_date=$d&type=industry"
  rtk curl -s "http://127.0.0.1:8765/api/market-monitor/sectors/fund-flow?trade_date=$d&type=industry"
done
```

Expected:

- Overview is `completed` or clearly `partial` with exact missing index warnings.
- Industry heatmap is `completed`.
- Industry fund-flow is `completed` when heatmap rows exist.

---

## Task 8: Frontend Verification And External Sync Gate

**Files:**
- Modify only if needed: `dashboard/tests/market-monitor-workspace.test.tsx`
- No production frontend code expected unless API contract changes.

- [x] **Step 1: Verify local UI**

Use browser/Playwright against:

```text
http://127.0.0.1:5174/
```

Expected:

- Market Monitor shows real index numbers from API, not mock sample values.
- Industry heatmap has sector chips.
- Fund-flow panel has inflow/outflow rows or explicit degraded warning.

- [x] **Step 2: Run dashboard tests and build**

Run:

```bash
cd /Users/xiwei/stock_research/dashboard
rtk pnpm test -- market-monitor-workspace.test.tsx
rtk pnpm build
```

- [x] **Step 3: Release gate**

Local no-side-effect release gate was added and verified with:

```bash
rtk .venv/bin/python scripts/check_market_monitor_local_release.py --trade-date 2026-06-26 --api-base http://127.0.0.1:8765/api
```

External release/publish remains intentionally paused.

Additional hardening completed:

- `ops.daily_pipeline_status` now stores `market_monitor_status` and migrates the column with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.
- `research.market_emotion_state_daily` now adds missing output columns with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, so an older partial table will not break the upsert path.
- 2026-06-26 DB row verified with `market_monitor_status=success`.

Do not sync external until local passes:

```bash
cd /Users/xiwei/stock_research/.worktrees/v0.1-local-eod-web
rtk deploy/check_dashboard_release.sh
```

Expected: release check includes Market Monitor overview/heatmap/fund-flow smoke checks.

---

## Recommended Execution Order

1. Task 1: lock tests.
2. Task 2: ensure industry daily bars are generated for the ready date.
3. Task 4: implement derived fund-flow proxy.
4. Task 3: complete overview/index/emotion readiness.
5. Task 5 and Task 6: wire readiness and daily close pipeline.
6. Task 7: backfill current week.
7. Task 8: verify local UI, then decide whether to publish externally.

## Explicit Non-Goals For This Iteration

- Do not restore frontend mock data.
- Do not build realtime/pan-zhong market monitor.
- Do not claim true main-fund flow unless a real third-party fund-flow data source is integrated.
- Do not make concept heatmap look real until concept membership/source data exists.
- Do not block the whole platform because optional concept data is missing.
