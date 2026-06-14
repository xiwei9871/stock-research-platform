# EOD Market Monitor Phase 7 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and commit the Phase 7 EOD Market Monitor workspace while separating it from unrelated Backtest, Strategy Validation, and strategy experiment work already present in the dirty worktree.

**Architecture:** Keep `src/stock_research/dashboard/market_monitor.py` as the backend payload boundary and `dashboard/src/components/MarketMonitorWorkspace.tsx` as the frontend workspace boundary. The API remains `/api/market-monitor/eod`, with typed additions for `market_emotion` and `emotion_stock_lists`, and the UI renders latest-EOD or historical-EOD payloads without realtime polling.

**Tech Stack:** Python dashboard service with pytest, React/TypeScript dashboard with Vitest and Playwright, existing PostgreSQL helper APIs, existing dashboard API client and CSS.

---

## File Structure

Phase 7 files to stage and commit:

- Modify: `src/stock_research/dashboard/market_monitor.py`  
  Adds EOD emotion payload assembly, historical-date behavior, JSON-safe value conversion, stock-list loading, and fallback behavior.
- Modify: `tests/test_dashboard_market_monitor.py`  
  Backend unit coverage for payload mapping, historical mode, missing-source fallback, and stock-list queries.
- Modify: `tests/test_dashboard_app.py`  
  API integration fixture coverage for the new payload fields.
- Modify: `dashboard/src/api/types.ts`  
  Adds typed market emotion and stock-list response contracts.
- Modify: `dashboard/src/api/client.ts`  
  Confirms `trade_date`, `score_version`, and `top_n` query behavior for EOD monitor requests.
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`  
  Renders EOD cockpit, date selector, emotion cards, stock-list tabs, TopN preview, generated reports, loading, warnings, and errors.
- Modify: `dashboard/src/styles.css`  
  Adds only Market Monitor selectors: `.market-date-controls`, `.market-emotion-summary`, `.emotion-dashboard-grid`, `.stock-tabs`, `.emotion-stock-table`, and responsive variants.
- Modify: `dashboard/tests/app-shell.test.tsx`  
  Frontend workspace behavior coverage for monitor rendering, historical date loading, partial payloads, request ordering, and tab accessibility.
- Modify: `dashboard/tests/client.test.ts`  
  API client query-string coverage.
- Modify: `dashboard/tests/home-cockpit.test.tsx`  
  Home cockpit fixture update for new monitor fields.

Do not stage these during Phase 7:

- `dashboard/src/components/BacktestCharts.tsx`
- `dashboard/src/components/BacktestLabWorkspace.tsx`
- `dashboard/src/components/BacktestResultDetail.tsx`
- `dashboard/tests/backtest-lab-workspace.test.tsx`
- `src/stock_research/dashboard/backtests.py`
- `src/stock_research/dashboard/strategy_catalog.py`
- `src/stock_research/vectorized_topn_backtest.py`
- `tests/test_dashboard_backtests.py`
- `tests/test_dashboard_strategy_catalog.py`
- `tests/test_vectorized_topn_backtest.py`
- `src/stock_research/lhb_data.py`
- `src/stock_research/lhb_shortline_v1.py`
- `src/stock_research/mid_trend_v1.py`
- `src/stock_research/tech_bottleneck_v1.py`
- Their corresponding strategy experiment tests.
- Older untracked plan drafts unrelated to Phase 7.

---

### Task 1: Worktree Triage And Phase 7 Patch Boundary

**Files:**
- Inspect: all files listed in File Structure.
- Modify: none.
- Test: none.

- [ ] **Step 1: Capture dirty worktree inventory**

Run:

```bash
git status --short
git diff --stat
```

Expected: dirty files include Phase 7 monitor files plus unrelated Backtest, Strategy Validation, and strategy experiment files.

- [ ] **Step 2: Inspect only Phase 7 diffs**

Run:

```bash
git diff -- src/stock_research/dashboard/market_monitor.py tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py dashboard/src/api/types.ts dashboard/src/api/client.ts dashboard/src/components/MarketMonitorWorkspace.tsx dashboard/src/styles.css dashboard/tests/app-shell.test.tsx dashboard/tests/client.test.ts dashboard/tests/home-cockpit.test.tsx
```

Expected: output contains only EOD Monitor payload, UI, style, and test changes. If unrelated Backtest or strategy changes appear inside `dashboard/src/api/types.ts`, `dashboard/src/styles.css`, `dashboard/tests/app-shell.test.tsx`, or `dashboard/tests/client.test.ts`, stage those files with `git add -p` later and accept only Phase 7 hunks.

- [ ] **Step 3: Document triage result in the implementation log**

Add this note to the task execution summary, not to the repository:

```text
Phase 7 stage boundary: market_monitor backend, MarketMonitorWorkspace, monitor API types/client, monitor CSS, and monitor tests only. Backtest, Strategy Validation, strategy experiment, and old plan draft changes remain unstaged.
```

- [ ] **Step 4: Commit nothing**

This task is an audit gate. Do not stage or commit in Task 1.

---

### Task 2: Backend EOD Emotion Payload

**Files:**
- Modify: `tests/test_dashboard_market_monitor.py`
- Modify: `src/stock_research/dashboard/market_monitor.py`

- [ ] **Step 1: Write or verify failing backend payload tests**

Ensure `tests/test_dashboard_market_monitor.py` contains tests with these behaviors:

```python
def test_build_market_monitor_eod_maps_market_emotion_row(monkeypatch):
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-12",
            "latest_factor_date": "2026-06-12",
            "latest_score_date": "2026-06-12",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(
        market_monitor,
        "load_market_emotion_row",
        lambda trade_date: {
            "trade_date": "2026-06-12",
            "emotion_score": 73.6,
            "emotion_state": "hot",
            "risk_state": "medium",
            "breadth_score": 68.2,
            "limit_score": 75.4,
            "relay_score": 71.1,
            "feedback_score": 66.8,
            "liquidity_score": 82.0,
            "traded_count": 5207,
            "up_count": 3610,
            "down_count": 1492,
            "strong_up_count": 269,
            "strong_down_count": 55,
            "limit_up_count": 90,
            "limit_down_count": 10,
            "broken_limit_up_count": 55,
            "broken_limit_up_rate": 0.3793,
            "first_board_count": 58,
            "second_board_count": 21,
            "third_board_plus_count": 11,
            "high_board_height": 6,
            "yesterday_limit_up_avg_return": 0.026,
            "yesterday_limit_up_red_rate": 0.7361,
            "yesterday_limit_up_limit_down_rate": 0.026,
            "yesterday_relay_avg_return": 0.018,
            "yesterday_relay_red_rate": 0.615,
            "yesterday_relay_continue_rate": 0.312,
            "yesterday_broken_avg_return": 0.007,
            "yesterday_broken_red_rate": 0.564,
            "yesterday_broken_limit_down_rate": 0.073,
            "total_amount": 1280000000000.0,
            "amount_ratio_5_20": 1.18,
            "style_signal_hint": "growth_favorable",
            "position_budget_hint": "reduced",
        },
    )
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    payload = market_monitor.build_market_monitor_eod()

    assert payload["market_emotion"]["summary"]["score"] == 73.6
    assert payload["market_emotion"]["summary"]["state"] == "hot"
    assert payload["market_emotion"]["summary"]["risk_state"] == "medium"
    assert payload["market_emotion"]["breadth"]["up_count"] == 3610
    assert payload["market_emotion"]["liquidity"]["amount_ratio_5_20"] == 1.18
    assert payload["market_emotion"]["limit_performance"]["limit_up_count"] == 90
    assert payload["market_emotion"]["profit_effect"]["limit_up_success_rate"] == 0.7361
    assert payload["market_emotion"]["drawdown_pressure"]["broken_limit_up_rate"] == 0.3793
    assert payload["market_emotion"]["weight_performance"]["status"] == "pending_source"
    assert payload["market_breadth"]["advancers"] == 3610
    assert payload["market_breadth"]["advancing_ratio"] == 3610 / 5207
```

- [ ] **Step 2: Run test to verify RED if implementation is absent**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py::test_build_market_monitor_eod_maps_market_emotion_row -q
```

Expected on a clean pre-Phase-7 implementation: FAIL because `market_emotion` is absent or incomplete. If the dirty worktree already makes it PASS, record that the test is validating existing draft code and continue by auditing the implementation against the expected fields.

- [ ] **Step 3: Implement the backend payload helpers**

In `src/stock_research/dashboard/market_monitor.py`, ensure these helpers exist with this behavior:

```python
def _number(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def build_market_emotion_payload(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "summary": {
                "score": None,
                "state": "unavailable",
                "risk_state": "unknown",
                "style_signal_hint": "",
                "position_budget_hint": "",
                "status": "pending_source",
            },
            "components": [],
            "breadth": {"status": "pending_source"},
            "liquidity": {"status": "pending_source"},
            "limit_performance": {"status": "pending_source"},
            "profit_effect": {"status": "pending_source"},
            "drawdown_pressure": {"status": "pending_source"},
            "weight_performance": {"status": "pending_source"},
        }
    return {
        "summary": {
            "score": _number(row.get("emotion_score")),
            "state": str(row.get("emotion_state") or "unknown"),
            "risk_state": str(row.get("risk_state") or "unknown"),
            "style_signal_hint": str(row.get("style_signal_hint") or ""),
            "position_budget_hint": str(row.get("position_budget_hint") or ""),
            "status": "available",
        },
        "components": [
            {"key": "breadth", "label": "涨跌家数", "score": _number(row.get("breadth_score"))},
            {"key": "limit", "label": "涨停表现", "score": _number(row.get("limit_score"))},
            {"key": "relay", "label": "连板接力", "score": _number(row.get("relay_score"))},
            {"key": "feedback", "label": "赚钱效应", "score": _number(row.get("feedback_score"))},
            {"key": "liquidity", "label": "市场量能", "score": _number(row.get("liquidity_score"))},
        ],
        "breadth": {
            "traded_count": _number(row.get("traded_count")),
            "up_count": _number(row.get("up_count")),
            "down_count": _number(row.get("down_count")),
            "strong_up_count": _number(row.get("strong_up_count")),
            "strong_down_count": _number(row.get("strong_down_count")),
            "status": "available",
        },
        "liquidity": {
            "total_amount": _number(row.get("total_amount")),
            "amount_ratio_5_20": _number(row.get("amount_ratio_5_20")),
            "status": "available",
        },
        "limit_performance": {
            "limit_up_count": _number(row.get("limit_up_count")),
            "limit_down_count": _number(row.get("limit_down_count")),
            "broken_limit_up_count": _number(row.get("broken_limit_up_count")),
            "broken_limit_up_rate": _number(row.get("broken_limit_up_rate")),
            "first_board_count": _number(row.get("first_board_count")),
            "second_board_count": _number(row.get("second_board_count")),
            "third_board_plus_count": _number(row.get("third_board_plus_count")),
            "high_board_height": _number(row.get("high_board_height")),
            "status": "available",
        },
        "profit_effect": {
            "limit_up_success_rate": _number(row.get("yesterday_limit_up_red_rate")),
            "limit_up_profit_rate": _number(row.get("yesterday_limit_up_avg_return")),
            "limit_up_limit_down_rate": _number(row.get("yesterday_limit_up_limit_down_rate")),
            "relay_profit_rate": _number(row.get("yesterday_relay_avg_return")),
            "relay_success_rate": _number(row.get("yesterday_relay_red_rate")),
            "relay_continue_rate": _number(row.get("yesterday_relay_continue_rate")),
            "broken_profit_rate": _number(row.get("yesterday_broken_avg_return")),
            "broken_success_rate": _number(row.get("yesterday_broken_red_rate")),
            "broken_limit_down_rate": _number(row.get("yesterday_broken_limit_down_rate")),
            "status": "available",
        },
        "drawdown_pressure": {
            "strong_down_count": _number(row.get("strong_down_count")),
            "limit_down_count": _number(row.get("limit_down_count")),
            "broken_limit_up_rate": _number(row.get("broken_limit_up_rate")),
            "yesterday_limit_up_limit_down_rate": _number(row.get("yesterday_limit_up_limit_down_rate")),
            "status": "available",
        },
        "weight_performance": {"status": "pending_source"},
    }
```

- [ ] **Step 4: Run backend payload tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py -q
```

Expected: all tests in `tests/test_dashboard_market_monitor.py` pass.

- [ ] **Step 5: Stage and commit only backend payload files**

Run:

```bash
git add src/stock_research/dashboard/market_monitor.py tests/test_dashboard_market_monitor.py
git diff --cached --stat
git commit -m "feat: add eod market emotion payload"
```

Expected staged files: only `src/stock_research/dashboard/market_monitor.py` and `tests/test_dashboard_market_monitor.py`.

---

### Task 3: Backend Historical Mode And Stock Lists

**Files:**
- Modify: `tests/test_dashboard_market_monitor.py`
- Modify: `src/stock_research/dashboard/market_monitor.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write or verify failing tests for historical mode and stock lists**

Ensure these tests exist:

```python
def test_build_market_monitor_eod_uses_historical_mode_for_explicit_trade_date(monkeypatch):
    requested_top_scores: list[tuple[str, str, int]] = []
    monkeypatch.setattr(
        market_monitor,
        "load_platform_summary",
        lambda score_version="manual_v1", top_n=5: {
            "latest_market_date": "2026-06-11",
            "latest_factor_date": "2026-06-11",
            "latest_score_date": "2026-06-11",
            "market_asset_count": 5300,
            "score_asset_count": 3100,
            "factor_count": 42,
            "topn_preview": [{"trade_date": "2026-06-11", "asset_id": "LATEST.SZ", "rank": 1, "score_total": 99.0, "score_version": "manual_v1", "score_components": {}}],
        },
    )
    monkeypatch.setattr(market_monitor, "load_report_links", lambda trade_date: [])
    monkeypatch.setattr(market_monitor, "load_market_emotion_row", lambda trade_date: None)
    monkeypatch.setattr(market_monitor, "load_emotion_stock_lists", lambda trade_date: {})

    def fake_load_top_scores(trade_date: str, score_version: str, top_n: int):
        requested_top_scores.append((trade_date, score_version, top_n))
        return [{"trade_date": trade_date, "asset_id": "HIST.SZ", "rank": 1, "score_total": 88.0, "score_version": score_version, "score_components": {}}]

    monkeypatch.setattr(market_monitor, "load_top_scores_for_dashboard", fake_load_top_scores, raising=False)

    payload = market_monitor.build_market_monitor_eod(trade_date="2026-06-10")

    assert payload["trade_date"] == "2026-06-10"
    assert payload["freshness"]["label"] == "Historical EOD"
    assert requested_top_scores == [("2026-06-10", "manual_v1", 5)]
    assert payload["strategy_signal_summary"]["topn_preview"][0]["asset_id"] == "HIST.SZ"
    assert not any("differs from market monitor trade date" in warning for warning in payload["warnings"])
```

```python
def test_load_emotion_stock_lists_maps_query_rows_and_limits_each_list(monkeypatch):
    captured = {}

    def fake_fetch_all(conn, sql, params):
        captured["sql"] = sql
        captured["params"] = params
        return [
            {"asset_id": "601958.SH", "symbol": "601958", "name": "金钼股份", "amount": Decimal("3038000000.0"), "pct_chg": Decimal("10.02"), "board": "main", "is_limit_up": True, "is_broken_limit_up": False, "is_limit_down": False},
            {"asset_id": "000001.SZ", "symbol": "000001", "name": "平安银行", "amount": Decimal("2010000000.5"), "pct_chg": Decimal("4.30"), "board": "main", "is_limit_up": False, "is_broken_limit_up": True, "is_limit_down": False},
            {"asset_id": "300001.SZ", "symbol": "300001", "name": "特锐德", "amount": Decimal("1500000000"), "pct_chg": Decimal("-20.0"), "board": "gem", "is_limit_up": False, "is_broken_limit_up": False, "is_limit_down": True},
        ]

    monkeypatch.setattr(market_monitor, "connect", lambda service: _fake_connection())
    monkeypatch.setattr(market_monitor, "fetch_all", fake_fetch_all)

    result = market_monitor.load_emotion_stock_lists("2026-06-12", limit=1)

    assert result["limit_up"][0]["name"] == "金钼股份"
    assert result["broken_limit_up"][0]["asset_id"] == "000001.SZ"
    assert result["limit_down"][0]["tab"] == "limit_down"
    assert len(result["limit_up"]) == 1
    assert captured["params"] == ["2026-06-12"]
    assert "FROM market_daily_bar b" in captured["sql"]
    assert "JOIN core.asset_status_daily s" in captured["sql"]
    assert "LEFT JOIN core.asset_master a" in captured["sql"]
```

- [ ] **Step 2: Run tests to verify RED if implementation is absent**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py::test_build_market_monitor_eod_uses_historical_mode_for_explicit_trade_date tests/test_dashboard_market_monitor.py::test_load_emotion_stock_lists_maps_query_rows_and_limits_each_list -q
```

Expected on a clean pre-Phase-7 implementation: FAIL because explicit historical TopN loading or stock lists are absent. If dirty draft code passes, audit SQL and payload shape before continuing.

- [ ] **Step 3: Implement historical mode and stock lists**

Ensure `build_market_monitor_eod` contains this behavior:

```python
explicit_trade_date = bool(trade_date)
selected_trade_date = trade_date or latest_market_date

topn_preview = (
    load_top_scores_for_dashboard(selected_trade_date, score_version, top_n)
    if explicit_trade_date and selected_trade_date
    else list(summary.get("topn_preview") or [])
)

"freshness": {
    "mode": "eod",
    "label": "Historical EOD" if explicit_trade_date else "Last Completed Trading Day",
    "is_realtime": False,
    "latest_market_date": latest_market_date,
    "latest_factor_date": latest_factor_date,
    "latest_score_date": latest_score_date,
}
```

Ensure stock-list loading uses daily bar and asset status:

```python
sql = """
    SELECT
        b.asset_id,
        COALESCE(a.symbol, b.asset_id) AS symbol,
        COALESCE(a.name, b.asset_id) AS name,
        b.amount,
        b.pct_chg,
        COALESCE(a.board, '') AS board,
        s.is_limit_up,
        s.is_limit_down,
        (
            b.high >= s.limit_up_price * 0.999
            AND NOT COALESCE(s.is_limit_up, false)
        ) AS is_broken_limit_up
    FROM market_daily_bar b
    JOIN core.asset_status_daily s
      ON s.trade_date = b.trade_date
     AND s.asset_id = b.asset_id
    LEFT JOIN core.asset_master a
      ON a.asset_id = b.asset_id
    WHERE b.trade_date = %s
      AND b.adjust_type = 'hfq'
      AND s.is_trade
      AND NOT s.is_suspended
      AND NOT s.is_st
      AND (
            COALESCE(s.is_limit_up, false)
            OR COALESCE(s.is_limit_down, false)
            OR (
                b.high >= s.limit_up_price * 0.999
                AND NOT COALESCE(s.is_limit_up, false)
            )
      )
    ORDER BY b.amount DESC NULLS LAST
"""
```

- [ ] **Step 4: Update API integration fixture**

In `tests/test_dashboard_app.py`, ensure the `/api/market-monitor/eod` expected payload fixture includes:

```python
"market_emotion": {
    "summary": {"score": None, "state": "unavailable", "risk_state": "unknown", "style_signal_hint": "", "position_budget_hint": "", "status": "pending_source"},
    "components": [],
    "breadth": {"status": "pending_source"},
    "liquidity": {"status": "pending_source"},
    "limit_performance": {"status": "pending_source"},
    "profit_effect": {"status": "pending_source"},
    "drawdown_pressure": {"status": "pending_source"},
    "weight_performance": {"status": "pending_source"},
},
"emotion_stock_lists": {
    "auction_status": "pending_source",
    "auction": [],
    "limit_up": [],
    "broken_limit_up": [],
    "limit_down": [],
},
```

- [ ] **Step 5: Run backend and API integration tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py -q
```

Expected: all selected backend tests pass.

- [ ] **Step 6: Stage and commit only backend historical/list files**

Run:

```bash
git add src/stock_research/dashboard/market_monitor.py tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py
git diff --cached --stat
git commit -m "feat: add eod monitor historical stock lists"
```

Expected staged files: only these three files.

---

### Task 4: Frontend Types And API Client Contract

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] **Step 1: Write or verify client contract test**

Ensure `dashboard/tests/client.test.ts` contains:

```typescript
it('fetches EOD market monitor with optional trade date', async () => {
  mockFetch.mockResolvedValueOnce({
    ok: true,
    json: async () => ({ trade_date: '2026-06-10' })
  } as Response);

  const result = await fetchMarketMonitorEod({ tradeDate: '2026-06-10', topN: 3 });

  expect(fetch).toHaveBeenCalledWith('/api/market-monitor/eod?trade_date=2026-06-10&top_n=3');
  expect(result).toEqual({ trade_date: '2026-06-10' });
});
```

- [ ] **Step 2: Run test to verify RED if client does not support trade date**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected on a clean pre-Phase-7 implementation: FAIL if `tradeDate` is not serialized. If dirty draft code passes, audit that the URL parameter is named `trade_date`.

- [ ] **Step 3: Implement API client and types**

Ensure `dashboard/src/api/client.ts` contains:

```typescript
type MarketMonitorParams = {
  tradeDate?: string;
  scoreVersion?: string;
  topN?: number;
};

export async function fetchMarketMonitorEod(params: MarketMonitorParams = {}): Promise<MarketMonitorPayload> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.scoreVersion) searchParams.set('score_version', params.scoreVersion);
  searchParams.set('top_n', String(params.topN ?? 5));
  return getJson(`/api/market-monitor/eod?${searchParams.toString()}`);
}
```

Ensure `dashboard/src/api/types.ts` defines:

```typescript
export type MarketEmotionStatus = 'available' | 'pending_source' | string;

export type MarketEmotionSummary = {
  score: number | null;
  state: string;
  risk_state: string;
  style_signal_hint: string;
  position_budget_hint: string;
  status: MarketEmotionStatus;
};

export type MarketEmotionPayload = {
  summary: MarketEmotionSummary;
  components: Array<{ key: string; label: string; score: number | null }>;
  breadth: { traded_count?: number | null; up_count?: number | null; down_count?: number | null; strong_up_count?: number | null; strong_down_count?: number | null; status: MarketEmotionStatus };
  liquidity: { total_amount?: number | null; amount_ratio_5_20?: number | null; status: MarketEmotionStatus };
  limit_performance: { limit_up_count?: number | null; limit_down_count?: number | null; broken_limit_up_count?: number | null; broken_limit_up_rate?: number | null; first_board_count?: number | null; second_board_count?: number | null; third_board_plus_count?: number | null; high_board_height?: number | null; status: MarketEmotionStatus };
  profit_effect: { limit_up_success_rate?: number | null; limit_up_profit_rate?: number | null; limit_up_limit_down_rate?: number | null; relay_profit_rate?: number | null; relay_success_rate?: number | null; relay_continue_rate?: number | null; broken_profit_rate?: number | null; broken_success_rate?: number | null; broken_limit_down_rate?: number | null; status: MarketEmotionStatus };
  drawdown_pressure: { strong_down_count?: number | null; limit_down_count?: number | null; broken_limit_up_rate?: number | null; yesterday_limit_up_limit_down_rate?: number | null; status: MarketEmotionStatus };
  weight_performance: { status: MarketEmotionStatus };
};

export type EmotionStockListRow = {
  name: string;
  asset_id: string;
  symbol: string;
  amount: number | null;
  pct_chg: number | null;
  board: string | null;
  tab: string;
  limit_up_streak?: number | null;
};

export type EmotionStockLists = {
  auction_status: MarketEmotionStatus;
  auction: EmotionStockListRow[];
  limit_up: EmotionStockListRow[];
  broken_limit_up: EmotionStockListRow[];
  limit_down: EmotionStockListRow[];
};
```

And extend `MarketMonitorPayload`:

```typescript
market_emotion: MarketEmotionPayload;
emotion_stock_lists: EmotionStockLists;
```

- [ ] **Step 4: Run client tests**

Run:

```bash
cd dashboard && npm test -- --run tests/client.test.ts
```

Expected: client tests pass.

- [ ] **Step 5: Stage and commit only type/client files**

Because `dashboard/src/api/types.ts` and `dashboard/tests/client.test.ts` may contain unrelated dirty hunks, use patch staging:

```bash
git add dashboard/src/api/client.ts
git add -p dashboard/src/api/types.ts
git add -p dashboard/tests/client.test.ts
git diff --cached --stat
git commit -m "feat: type eod monitor payload"
```

Expected staged hunks: only monitor API types/client tests.

---

### Task 5: Frontend Market Monitor Workspace

**Files:**
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write or verify workspace rendering tests**

Ensure `dashboard/tests/app-shell.test.tsx` includes behaviors equivalent to:

```typescript
it('renders EOD market monitor data without implying realtime data', async () => {
  apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(makeMarketMonitorPayload());

  render(<AppShell />);
  fireEvent.click(screen.getByRole('button', { name: 'Market Monitor' }));

  expect(await screen.findByText('综合强度')).toBeInTheDocument();
  expect(screen.getByText('73.6')).toBeInTheDocument();
  expect(screen.getByText('Last Completed Trading Day')).toBeInTheDocument();
  expect(screen.getByText('No')).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: /涨停/ })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByText('金钼股份')).toBeInTheDocument();
});
```

```typescript
it('loads market monitor history for a selected trade date', async () => {
  apiMocks.fetchMarketMonitorEod
    .mockResolvedValueOnce(makeMarketMonitorPayload())
    .mockResolvedValueOnce(makeMarketMonitorPayload({ trade_date: '2026-06-09', freshness: { mode: 'eod', label: 'Historical EOD', is_realtime: false, latest_market_date: '2026-06-12', latest_factor_date: '2026-06-12', latest_score_date: '2026-06-12' } }));

  render(<AppShell />);
  fireEvent.click(screen.getByRole('button', { name: 'Market Monitor' }));
  fireEvent.change(await screen.findByLabelText('Market monitor trade date'), { target: { value: '2026-06-09' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load Date' }));

  await waitFor(() => expect(apiMocks.fetchMarketMonitorEod).toHaveBeenLastCalledWith({ topN: 5, tradeDate: '2026-06-09' }));
  expect(await screen.findByText('Historical EOD')).toBeInTheDocument();
});
```

```typescript
it('supports keyboard navigation across market monitor stock tabs', async () => {
  apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(makeMarketMonitorPayload());

  render(<AppShell />);
  fireEvent.click(screen.getByRole('button', { name: 'Market Monitor' }));
  const limitUpTab = await screen.findByRole('tab', { name: /涨停/ });
  limitUpTab.focus();
  fireEvent.keyDown(screen.getByRole('tablist', { name: 'Market emotion stock lists' }), { key: 'ArrowRight' });

  expect(screen.getByRole('tab', { name: /炸板/ })).toHaveAttribute('aria-selected', 'true');
});
```

- [ ] **Step 2: Run tests to verify RED if workspace UI is absent**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx
```

Expected on a clean pre-Phase-7 implementation: FAIL because emotion cards, date loading, or tab behavior are absent. If dirty draft code passes, audit that the UI does not imply realtime behavior.

- [ ] **Step 3: Implement workspace rendering**

Ensure `dashboard/src/components/MarketMonitorWorkspace.tsx` includes:

```typescript
const [tradeDateInput, setTradeDateInput] = useState('');
const [loadingTradeDate, setLoadingTradeDate] = useState<string | null>(null);
const [activeStockTab, setActiveStockTab] = useState<StockTabKey>('limit_up');

const loadMarketMonitor = useCallback(async (tradeDate?: string) => {
  const requestedTradeDate = tradeDate?.trim();
  const requestId = requestIdRef.current + 1;
  requestIdRef.current = requestId;
  setIsLoading(true);
  setLoadingTradeDate(requestedTradeDate || null);
  setError(null);
  try {
    const latestPayload = await fetchMarketMonitorEod(
      requestedTradeDate ? { topN: 5, tradeDate: requestedTradeDate } : { topN: 5 }
    );
    if (isMountedRef.current && requestId === requestIdRef.current) {
      setPayload(latestPayload);
      setTradeDateInput(latestPayload.trade_date || requestedTradeDate || '');
    }
  } catch (err: unknown) {
    if (isMountedRef.current && requestId === requestIdRef.current) {
      setError(err instanceof Error ? err.message : String(err));
    }
  } finally {
    if (isMountedRef.current && requestId === requestIdRef.current) {
      setIsLoading(false);
      setLoadingTradeDate(null);
    }
  }
}, []);
```

Render the date form:

```tsx
<form className="market-date-controls" aria-label="Market monitor date controls" onSubmit={handleTradeDateSubmit}>
  <label>
    <span>Trade Date</span>
    <input
      aria-label="Market monitor trade date"
      name="market-monitor-trade-date"
      type="date"
      value={tradeDateInput}
      onChange={(event) => setTradeDateInput(event.target.value)}
    />
  </label>
  <button type="submit" disabled={isLoading || !tradeDateInput}>
    {isLoading ? 'Loading...' : 'Load Date'}
  </button>
</form>
```

Render stock tabs with accessible keyboard behavior:

```tsx
<div className="stock-tabs" role="tablist" aria-label="Market emotion stock lists" onKeyDown={handleStockTabKeyDown}>
  {STOCK_TABS.map((tab) => (
    <button
      aria-controls={`stock-panel-${tab.key}`}
      aria-selected={activeStockTab === tab.key}
      id={`stock-tab-${tab.key}`}
      key={tab.key}
      onClick={() => selectStockTab(tab.key)}
      role="tab"
      tabIndex={activeStockTab === tab.key ? 0 : -1}
      type="button"
    >
      {tab.label} {stockCount(tab.key)}
    </button>
  ))}
</div>
```

- [ ] **Step 4: Run frontend workspace tests**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx
```

Expected: selected app-shell tests pass.

- [ ] **Step 5: Stage and commit only workspace files**

Because `dashboard/tests/app-shell.test.tsx` may contain unrelated dirty hunks, use patch staging:

```bash
git add dashboard/src/components/MarketMonitorWorkspace.tsx
git add -p dashboard/tests/app-shell.test.tsx
git diff --cached --stat
git commit -m "feat: add eod market monitor workspace"
```

Expected staged files: `MarketMonitorWorkspace.tsx` and only market-monitor hunks in `app-shell.test.tsx`.

---

### Task 6: Monitor Styling And Home Fixtures

**Files:**
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/home-cockpit.test.tsx`

- [ ] **Step 1: Verify fixture tests cover new monitor fields**

Ensure `dashboard/tests/home-cockpit.test.tsx` uses a monitor fixture containing:

```typescript
market_emotion: {
  summary: {
    score: 73.6,
    state: 'hot',
    risk_state: 'medium',
    style_signal_hint: 'growth_favorable',
    position_budget_hint: 'reduced',
    status: 'available'
  },
  components: [],
  breadth: { up_count: 3610, down_count: 1492, status: 'available' },
  liquidity: { total_amount: 1280000000000, amount_ratio_5_20: 1.18, status: 'available' },
  limit_performance: { limit_up_count: 90, limit_down_count: 10, broken_limit_up_count: 55, high_board_height: 6, status: 'available' },
  profit_effect: { status: 'available' },
  drawdown_pressure: { status: 'available' },
  weight_performance: { status: 'pending_source' }
},
emotion_stock_lists: {
  auction_status: 'pending_source',
  auction: [],
  limit_up: [],
  broken_limit_up: [],
  limit_down: []
}
```

- [ ] **Step 2: Run home cockpit tests**

Run:

```bash
cd dashboard && npm test -- --run tests/home-cockpit.test.tsx
```

Expected: home cockpit tests pass with new typed monitor fixture.

- [ ] **Step 3: Add compact monitor styles**

In `dashboard/src/styles.css`, add only monitor-specific selectors:

```css
.market-date-controls {
  display: flex;
  align-items: end;
  gap: 12px;
  flex-wrap: wrap;
}

.market-emotion-summary {
  display: grid;
  grid-template-columns: minmax(180px, 1.2fr) repeat(5, minmax(140px, 1fr));
  gap: 12px;
}

.emotion-dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.7fr);
  gap: 16px;
}

.stock-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.stock-tabs button[aria-selected="true"] {
  background: var(--color-text);
  color: var(--color-surface);
}

.emotion-stock-table {
  width: 100%;
  border-collapse: collapse;
}
```

Use existing local variables and neighboring styles where possible. Do not introduce a one-note purple/blue gradient palette.

- [ ] **Step 4: Run style-sensitive frontend tests**

Run:

```bash
cd dashboard && npm test -- --run tests/home-cockpit.test.tsx tests/app-shell.test.tsx
```

Expected: tests pass.

- [ ] **Step 5: Stage and commit only monitor CSS and home fixture hunks**

Because `dashboard/src/styles.css` and `dashboard/tests/home-cockpit.test.tsx` may contain unrelated dirty hunks, use patch staging:

```bash
git add -p dashboard/src/styles.css
git add -p dashboard/tests/home-cockpit.test.tsx
git diff --cached --stat
git commit -m "style: polish eod market monitor"
```

Expected staged hunks: only monitor CSS and home monitor fixture changes.

---

### Task 7: Final Integration Verification

**Files:**
- Inspect: all Phase 7 files.
- Modify: none unless verification finds a bug. If a bug appears, write a failing test first, fix minimally, rerun verification, and commit with a focused message.

- [ ] **Step 1: Confirm unrelated dirty files remain unstaged**

Run:

```bash
git status --short
git diff --cached --stat
```

Expected: no staged changes. Dirty unrelated Backtest, Strategy Validation, strategy experiment, and old plan draft files may remain unstaged.

- [ ] **Step 2: Run backend monitor and API tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/pytest tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py -q
```

Expected: selected backend tests pass.

- [ ] **Step 3: Run focused frontend tests**

Run:

```bash
cd dashboard && npm test -- --run tests/app-shell.test.tsx tests/client.test.ts tests/home-cockpit.test.tsx
```

Expected: selected frontend tests pass.

- [ ] **Step 4: Run production build**

Run:

```bash
cd dashboard && npm run build
```

Expected: TypeScript and Vite production build pass.

- [ ] **Step 5: Run e2e smoke tests**

Run:

```bash
cd dashboard && npm run test:e2e
```

Expected: Playwright tests pass.

- [ ] **Step 6: Review final git history and worktree**

Run:

```bash
git log --oneline -8
git status --short
```

Expected: recent commits include Phase 7 design and Phase 7 implementation commits. Remaining dirty files are unrelated to Phase 7 and have not been staged or reverted.

- [ ] **Step 7: Final user report**

Report:

```text
Phase 7 EOD Monitor is complete.
Verification:
- pytest tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py -q: passed
- npm test -- --run tests/app-shell.test.tsx tests/client.test.ts tests/home-cockpit.test.tsx: passed
- npm run build: passed
- npm run test:e2e: passed
Remaining dirty worktree: unrelated Backtest, Strategy Validation, strategy experiment, and old plan draft changes remain unstaged.
```

---

## Self-Review

Spec coverage:

- Worktree triage is covered by Task 1.
- Backend EOD payload and fallbacks are covered by Tasks 2 and 3.
- Frontend types and client contract are covered by Task 4.
- Frontend workspace behavior is covered by Task 5.
- Styling and home fixtures are covered by Task 6.
- Build and e2e verification are covered by Task 7.

Placeholder scan:

- The plan contains no unresolved markers or incomplete steps.

Type consistency:

- Backend response fields use `market_emotion` and `emotion_stock_lists`.
- Frontend types use `MarketEmotionPayload`, `EmotionStockLists`, and `EmotionStockListRow`.
- API client parameter names map `tradeDate` to `trade_date`, `scoreVersion` to `score_version`, and `topN` to `top_n`.
