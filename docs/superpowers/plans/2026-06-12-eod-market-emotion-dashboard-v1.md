# EOD Market Emotion Dashboard V1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Market Monitor into an EOD market emotion dashboard with composite strength, breadth, liquidity, limit-up ecology,赚钱效应, drawdown pressure, weight/index context, and stock lists.

**Architecture:** Reuse the existing `market_emotion_state_v1` daily factor instead of inventing a new formula in the dashboard. Extend `/api/market-monitor/eod` with one normalized `market_emotion` object and stock-list tabs, then render those fields in `MarketMonitorWorkspace` while keeping the page clearly labeled as last-completed-trading-day data. Keep realtime auction and intraday projections out of V1, but reserve visible "pending source" states for those gaps.

**Tech Stack:** Python, pandas, existing FastAPI dashboard route, TypeScript, React, CSS, pytest, Vitest, in-app browser verification.

---

## File Structure

- Modify `src/stock_research/dashboard/market_monitor.py`
  - Load the latest or requested daily market emotion row.
  - Normalize it into a dashboard-friendly API shape.
  - Build EOD stock lists for `limit_up`, `broken_limit_up`, and `limit_down`.
  - Leave `auction` and richer `weight_performance` as explicit pending sections when data is unavailable.
- Modify `tests/test_dashboard_market_monitor.py`
  - Cover emotion-row mapping, stock-list mapping, fallback behavior, and freshness warnings.
- Modify `tests/test_dashboard_app.py`
  - Update route payload fixture with the new fields.
- Modify `dashboard/src/api/types.ts`
  - Add typed `market_emotion`, `profit_effect`, `emotion_stock_lists`, and related row types.
- Modify `dashboard/src/components/MarketMonitorWorkspace.tsx`
  - Replace the current coverage-first view with the EOD emotion dashboard layout.
  - Add stock-list tabs: `竞价`, `涨停`, `炸板`, `跌停`.
  - Keep strategy TopN and generated reports below the emotion sections.
- Modify `dashboard/src/styles.css`
  - Add focused styles for score panel, component cards,赚钱效应 table, stock-list tabs/table, and pending states.
- Modify `dashboard/tests/app-shell.test.tsx`
  - Update Market Monitor assertions to check the new EOD emotion experience.
- Modify `dashboard/tests/home-cockpit.test.tsx`
  - Keep home cockpit compatibility with the extended payload.

---

### Task 1: Backend API Shape for EOD Market Emotion

**Files:**
- Modify: `src/stock_research/dashboard/market_monitor.py`
- Modify: `tests/test_dashboard_market_monitor.py`
- Modify: `tests/test_dashboard_app.py`

- [ ] **Step 1: Write failing backend tests for market emotion mapping**

Add this test to `tests/test_dashboard_market_monitor.py`:

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

    assert payload["market_emotion"]["summary"] == {
        "score": 73.6,
        "state": "hot",
        "risk_state": "medium",
        "style_signal_hint": "growth_favorable",
        "position_budget_hint": "reduced",
        "status": "available",
    }
    assert payload["market_emotion"]["breadth"]["up_count"] == 3610
    assert payload["market_emotion"]["breadth"]["down_count"] == 1492
    assert payload["market_emotion"]["liquidity"]["amount_ratio_5_20"] == 1.18
    assert payload["market_emotion"]["limit_performance"]["limit_up_count"] == 90
    assert payload["market_emotion"]["profit_effect"]["limit_up_success_rate"] == 0.7361
    assert payload["market_emotion"]["profit_effect"]["limit_up_profit_rate"] == 0.026
    assert payload["market_emotion"]["drawdown_pressure"]["broken_limit_up_rate"] == 0.3793
    assert payload["market_emotion"]["weight_performance"]["status"] == "pending_source"
```

- [ ] **Step 2: Run the backend test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_market_monitor.py::test_build_market_monitor_eod_maps_market_emotion_row -q
```

Expected: fail because `load_market_emotion_row` and `market_emotion` do not exist yet.

- [ ] **Step 3: Implement market emotion loaders and mapper**

In `src/stock_research/dashboard/market_monitor.py`, add imports:

```python
import math
from collections.abc import Mapping

from stock_research.db import connect, fetch_all
```

Add helpers above `build_market_monitor_eod`:

```python
def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def load_market_emotion_row(trade_date: str) -> dict[str, Any] | None:
    if not trade_date:
        return None
    sql = """
        SELECT *
        FROM research.market_emotion_state_daily
        WHERE trade_date = %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    with connect() as conn:
        rows = fetch_all(conn, sql, (trade_date,))
    return dict(rows[0]) if rows else None


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

- [ ] **Step 4: Attach `market_emotion` to the route payload**

Inside `build_market_monitor_eod`, after `reports` is assigned, add:

```python
    emotion_row = load_market_emotion_row(selected_trade_date) if selected_trade_date else None
    emotion_payload = build_market_emotion_payload(emotion_row)
```

Then include in the returned dict:

```python
        "market_emotion": emotion_payload,
```

Keep the old `market_breadth` key for backward compatibility, but fill it from emotion when available:

```python
        "market_breadth": {
            "advancers": emotion_payload["breadth"].get("up_count"),
            "decliners": emotion_payload["breadth"].get("down_count"),
            "limit_up": emotion_payload["limit_performance"].get("limit_up_count"),
            "limit_down": emotion_payload["limit_performance"].get("limit_down_count"),
            "advancing_ratio": (
                emotion_payload["breadth"].get("up_count") / emotion_payload["breadth"].get("traded_count")
                if emotion_payload["breadth"].get("up_count") is not None
                and emotion_payload["breadth"].get("traded_count")
                else None
            ),
            "turnover_change_pct": None,
            "status": emotion_payload["breadth"].get("status", "pending_source"),
        },
```

- [ ] **Step 5: Update route fixture test**

In `tests/test_dashboard_app.py::test_market_monitor_eod_route_returns_payload`, add to the fake return:

```python
"market_emotion": {
    "summary": {"score": 73.6, "state": "hot", "risk_state": "medium", "status": "available"},
    "components": [],
    "breadth": {"status": "available"},
    "liquidity": {"status": "available"},
    "limit_performance": {"status": "available"},
    "profit_effect": {"status": "available"},
    "drawdown_pressure": {"status": "available"},
    "weight_performance": {"status": "pending_source"},
},
"emotion_stock_lists": {"auction": [], "limit_up": [], "broken_limit_up": [], "limit_down": []},
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py::test_market_monitor_eod_route_returns_payload -q
```

Expected: all selected backend tests pass.

- [ ] **Step 7: Commit backend API shape**

Run:

```bash
git add src/stock_research/dashboard/market_monitor.py tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py
git commit -m "feat: expose eod market emotion payload"
```

---

### Task 2: Backend Stock Lists for 涨停 / 炸板 / 跌停

**Files:**
- Modify: `src/stock_research/dashboard/market_monitor.py`
- Modify: `tests/test_dashboard_market_monitor.py`

- [ ] **Step 1: Write failing stock-list test**

Add this test to `tests/test_dashboard_market_monitor.py`:

```python
def test_build_market_monitor_eod_includes_emotion_stock_lists(monkeypatch):
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
    monkeypatch.setattr(market_monitor, "load_market_emotion_row", lambda trade_date: None)
    monkeypatch.setattr(
        market_monitor,
        "load_emotion_stock_lists",
        lambda trade_date: {
            "auction": [],
            "limit_up": [
                {
                    "asset_id": "CN:SH:601958",
                    "symbol": "601958",
                    "name": "金钼股份",
                    "amount": 3038000000.0,
                    "pct_chg": 10.0,
                    "board": "金属钼",
                    "limit_up_streak": 1,
                }
            ],
            "broken_limit_up": [
                {
                    "asset_id": "CN:SZ:000001",
                    "symbol": "000001",
                    "name": "平安银行",
                    "amount": 1030000000.0,
                    "pct_chg": 4.2,
                    "board": "银行",
                    "limit_up_streak": 0,
                }
            ],
            "limit_down": [],
        },
    )

    payload = market_monitor.build_market_monitor_eod()

    assert payload["emotion_stock_lists"]["limit_up"][0]["name"] == "金钼股份"
    assert payload["emotion_stock_lists"]["limit_up"][0]["amount"] == 3038000000.0
    assert payload["emotion_stock_lists"]["broken_limit_up"][0]["tab"] == "broken_limit_up"
    assert payload["emotion_stock_lists"]["auction_status"] == "pending_source"
```

- [ ] **Step 2: Run the stock-list test and verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_market_monitor.py::test_build_market_monitor_eod_includes_emotion_stock_lists -q
```

Expected: fail because `load_emotion_stock_lists` and `emotion_stock_lists` do not exist yet.

- [ ] **Step 3: Implement stock-list loader**

In `src/stock_research/dashboard/market_monitor.py`, add:

```python
def load_emotion_stock_lists(trade_date: str, *, limit: int = 30) -> dict[str, list[dict[str, Any]]]:
    if not trade_date:
        return {"auction": [], "limit_up": [], "broken_limit_up": [], "limit_down": []}
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
            CASE
                WHEN s.limit_up_price IS NOT NULL
                 AND b.high >= s.limit_up_price * 0.999
                 AND NOT s.is_limit_up
                THEN TRUE
                ELSE FALSE
            END AS is_broken_limit_up
        FROM market_daily_bar b
        LEFT JOIN core.asset_status_daily s
          ON s.trade_date = b.trade_date AND s.asset_id = b.asset_id
        LEFT JOIN core.asset a
          ON a.asset_id = b.asset_id
        WHERE b.trade_date = %s
          AND b.adjust_type = 'hfq'
          AND COALESCE(s.is_trade, TRUE)
          AND NOT COALESCE(s.is_suspended, FALSE)
          AND NOT COALESCE(s.is_st, FALSE)
        ORDER BY b.amount DESC NULLS LAST
    """
    with connect() as conn:
        rows = [dict(row) for row in fetch_all(conn, sql, (trade_date,))]

    lists = {"auction": [], "limit_up": [], "broken_limit_up": [], "limit_down": []}
    for row in rows:
        normalized = {
            "asset_id": row.get("asset_id"),
            "symbol": row.get("symbol"),
            "name": row.get("name"),
            "amount": _number(row.get("amount")),
            "pct_chg": _number(row.get("pct_chg")),
            "board": row.get("board") or "",
            "limit_up_streak": None,
        }
        if row.get("is_limit_up") and len(lists["limit_up"]) < limit:
            lists["limit_up"].append({**normalized, "tab": "limit_up"})
        if row.get("is_broken_limit_up") and len(lists["broken_limit_up"]) < limit:
            lists["broken_limit_up"].append({**normalized, "tab": "broken_limit_up"})
        if row.get("is_limit_down") and len(lists["limit_down"]) < limit:
            lists["limit_down"].append({**normalized, "tab": "limit_down"})
    return lists
```

- [ ] **Step 4: Attach normalized stock lists**

Inside `build_market_monitor_eod`, add:

```python
    emotion_stock_lists = load_emotion_stock_lists(selected_trade_date) if selected_trade_date else {
        "auction": [],
        "limit_up": [],
        "broken_limit_up": [],
        "limit_down": [],
    }
```

Include in the returned dict:

```python
        "emotion_stock_lists": {
            "auction": emotion_stock_lists.get("auction", []),
            "limit_up": emotion_stock_lists.get("limit_up", []),
            "broken_limit_up": emotion_stock_lists.get("broken_limit_up", []),
            "limit_down": emotion_stock_lists.get("limit_down", []),
            "auction_status": "pending_source",
        },
```

- [ ] **Step 5: Run backend stock-list tests**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_market_monitor.py -q
```

Expected: all dashboard market monitor tests pass.

- [ ] **Step 6: Commit backend stock lists**

Run:

```bash
git add src/stock_research/dashboard/market_monitor.py tests/test_dashboard_market_monitor.py
git commit -m "feat: add eod market emotion stock lists"
```

---

### Task 3: TypeScript API Types

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/tests/app-shell.test.tsx`
- Modify: `dashboard/tests/home-cockpit.test.tsx`

- [ ] **Step 1: Update frontend fixtures to the intended new shape**

In `dashboard/tests/app-shell.test.tsx`, update `makeMarketMonitorPayload` to include:

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
  components: [
    { key: 'breadth', label: '涨跌家数', score: 68.2 },
    { key: 'limit', label: '涨停表现', score: 75.4 },
    { key: 'relay', label: '连板接力', score: 71.1 },
    { key: 'feedback', label: '赚钱效应', score: 66.8 },
    { key: 'liquidity', label: '市场量能', score: 82.0 }
  ],
  breadth: {
    traded_count: 5207,
    up_count: 3610,
    down_count: 1492,
    strong_up_count: 269,
    strong_down_count: 55,
    status: 'available'
  },
  liquidity: { total_amount: 1280000000000, amount_ratio_5_20: 1.18, status: 'available' },
  limit_performance: {
    limit_up_count: 90,
    limit_down_count: 10,
    broken_limit_up_count: 55,
    broken_limit_up_rate: 0.3793,
    first_board_count: 58,
    second_board_count: 21,
    third_board_plus_count: 11,
    high_board_height: 6,
    status: 'available'
  },
  profit_effect: {
    limit_up_success_rate: 0.7361,
    limit_up_profit_rate: 0.026,
    limit_up_limit_down_rate: 0.026,
    relay_profit_rate: 0.018,
    relay_success_rate: 0.615,
    relay_continue_rate: 0.312,
    broken_profit_rate: 0.007,
    broken_success_rate: 0.564,
    broken_limit_down_rate: 0.073,
    status: 'available'
  },
  drawdown_pressure: {
    strong_down_count: 55,
    limit_down_count: 10,
    broken_limit_up_rate: 0.3793,
    yesterday_limit_up_limit_down_rate: 0.026,
    status: 'available'
  },
  weight_performance: { status: 'pending_source' }
},
emotion_stock_lists: {
  auction_status: 'pending_source',
  auction: [],
  limit_up: [
    {
      tab: 'limit_up',
      asset_id: 'CN:SH:601958',
      symbol: '601958',
      name: '金钼股份',
      amount: 3038000000,
      pct_chg: 10,
      board: '金属钼',
      limit_up_streak: 1
    }
  ],
  broken_limit_up: [],
  limit_down: []
}
```

Add the same minimal `market_emotion` and `emotion_stock_lists` fields to the mocked payload in `dashboard/tests/home-cockpit.test.tsx`.

- [ ] **Step 2: Run typecheck/build and verify it fails**

Run:

```bash
cd dashboard
pnpm build
```

Expected: TypeScript fails because `MarketMonitorPayload` does not yet define `market_emotion` and `emotion_stock_lists`.

- [ ] **Step 3: Add API types**

In `dashboard/src/api/types.ts`, add before `MarketMonitorPayload`:

```typescript
export type MarketEmotionStatus = 'available' | 'pending_source' | string;

export type MarketEmotionSummary = {
  score: number | null;
  state: string;
  risk_state: string;
  style_signal_hint?: string;
  position_budget_hint?: string;
  status: MarketEmotionStatus;
};

export type MarketEmotionComponent = {
  key: string;
  label: string;
  score: number | null;
};

export type MarketEmotionPayload = {
  summary: MarketEmotionSummary;
  components: MarketEmotionComponent[];
  breadth: {
    traded_count?: number | null;
    up_count?: number | null;
    down_count?: number | null;
    strong_up_count?: number | null;
    strong_down_count?: number | null;
    status: MarketEmotionStatus;
  };
  liquidity: {
    total_amount?: number | null;
    amount_ratio_5_20?: number | null;
    status: MarketEmotionStatus;
  };
  limit_performance: {
    limit_up_count?: number | null;
    limit_down_count?: number | null;
    broken_limit_up_count?: number | null;
    broken_limit_up_rate?: number | null;
    first_board_count?: number | null;
    second_board_count?: number | null;
    third_board_plus_count?: number | null;
    high_board_height?: number | null;
    status: MarketEmotionStatus;
  };
  profit_effect: {
    limit_up_success_rate?: number | null;
    limit_up_profit_rate?: number | null;
    limit_up_limit_down_rate?: number | null;
    relay_profit_rate?: number | null;
    relay_success_rate?: number | null;
    relay_continue_rate?: number | null;
    broken_profit_rate?: number | null;
    broken_success_rate?: number | null;
    broken_limit_down_rate?: number | null;
    status: MarketEmotionStatus;
  };
  drawdown_pressure: {
    strong_down_count?: number | null;
    limit_down_count?: number | null;
    broken_limit_up_rate?: number | null;
    yesterday_limit_up_limit_down_rate?: number | null;
    status: MarketEmotionStatus;
  };
  weight_performance: {
    status: MarketEmotionStatus;
  };
};

export type EmotionStockListRow = {
  tab: 'auction' | 'limit_up' | 'broken_limit_up' | 'limit_down' | string;
  asset_id: string;
  symbol: string;
  name: string;
  amount: number | null;
  pct_chg: number | null;
  board: string;
  limit_up_streak: number | null;
};

export type EmotionStockLists = {
  auction_status: MarketEmotionStatus;
  auction: EmotionStockListRow[];
  limit_up: EmotionStockListRow[];
  broken_limit_up: EmotionStockListRow[];
  limit_down: EmotionStockListRow[];
};
```

Then add fields to `MarketMonitorPayload`:

```typescript
  market_emotion: MarketEmotionPayload;
  emotion_stock_lists: EmotionStockLists;
```

- [ ] **Step 4: Run build**

Run:

```bash
cd dashboard
pnpm build
```

Expected: build passes or only fails in components that still need to render the new fields. If component failures appear, keep them for Task 4.

- [ ] **Step 5: Commit types**

Run:

```bash
git add dashboard/src/api/types.ts dashboard/tests/app-shell.test.tsx dashboard/tests/home-cockpit.test.tsx
git commit -m "feat: type market emotion dashboard payload"
```

---

### Task 4: Market Monitor UI Redesign

**Files:**
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Modify: `dashboard/tests/app-shell.test.tsx`

- [ ] **Step 1: Write failing UI assertions**

In `dashboard/tests/app-shell.test.tsx`, replace the body of `it('renders EOD market monitor data without implying realtime data', ...)` with assertions like:

```typescript
expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
expect(screen.getByText('Last Completed Trading Day')).toBeInTheDocument();
expect(screen.getByText('2026-06-10')).toBeInTheDocument();
expect(screen.getByText('综合强度')).toBeInTheDocument();
expect(screen.getByText('73.6')).toBeInTheDocument();
expect(screen.getByText('hot')).toBeInTheDocument();
expect(screen.getByText('涨跌家数')).toBeInTheDocument();
expect(screen.getByText('3,610')).toBeInTheDocument();
expect(screen.getByText('市场量能')).toBeInTheDocument();
expect(screen.getByText('1.18x')).toBeInTheDocument();
expect(screen.getByText('涨停表现')).toBeInTheDocument();
expect(screen.getByText('最高 6 板')).toBeInTheDocument();
expect(screen.getByText('赚钱效应')).toBeInTheDocument();
expect(screen.getByText('73.61%')).toBeInTheDocument();
expect(screen.getByText('2.60%')).toBeInTheDocument();
expect(screen.getByRole('tab', { name: '竞价 0' })).toBeInTheDocument();
expect(screen.getByRole('tab', { name: '涨停 1' })).toBeInTheDocument();
expect(screen.getByRole('tab', { name: '炸板 0' })).toBeInTheDocument();
expect(screen.getByRole('tab', { name: '跌停 0' })).toBeInTheDocument();
expect(screen.getByText('金钼股份')).toBeInTheDocument();
expect(screen.getByText('30.38亿')).toBeInTheDocument();
expect(screen.getByText('权重表现待接入')).toBeInTheDocument();
```

- [ ] **Step 2: Run UI test and verify it fails**

Run:

```bash
cd dashboard
pnpm vitest run tests/app-shell.test.tsx
```

Expected: fail because the current Market Monitor does not render the EOD emotion dashboard.

- [ ] **Step 3: Add formatting helpers**

In `dashboard/src/components/MarketMonitorWorkspace.tsx`, add:

```typescript
type StockTabKey = 'auction' | 'limit_up' | 'broken_limit_up' | 'limit_down';

function formatPercent(value: number | null | undefined, digits = 2) {
  return typeof value === 'number' ? `${(value * 100).toFixed(digits)}%` : '-';
}

function formatAmountYi(value: number | null | undefined) {
  return typeof value === 'number' ? `${(value / 100000000).toFixed(2)}亿` : '-';
}

function formatRatio(value: number | null | undefined) {
  return typeof value === 'number' ? `${value.toFixed(2)}x` : '-';
}
```

Keep the existing `formatCount` and `formatScore`.

- [ ] **Step 4: Add active stock-list tab state**

Inside `MarketMonitorWorkspace`, add:

```typescript
const [activeStockTab, setActiveStockTab] = useState<StockTabKey>('limit_up');
```

Add derived values before `return`:

```typescript
const emotion = payload?.market_emotion;
const stockLists = payload?.emotion_stock_lists;
const stockTabs: Array<{ key: StockTabKey; label: string; count: number; status?: string }> = [
  { key: 'auction', label: '竞价', count: stockLists?.auction.length ?? 0, status: stockLists?.auction_status },
  { key: 'limit_up', label: '涨停', count: stockLists?.limit_up.length ?? 0 },
  { key: 'broken_limit_up', label: '炸板', count: stockLists?.broken_limit_up.length ?? 0 },
  { key: 'limit_down', label: '跌停', count: stockLists?.limit_down.length ?? 0 }
];
const activeStockRows = stockLists?.[activeStockTab] ?? [];
```

- [ ] **Step 5: Replace the coverage-first layout with EOD emotion sections**

In `MarketMonitorWorkspace.tsx`, keep the header, errors, warnings, and freshness `status-strip`. Replace the current `cockpit-grid`, first `workspace-panel`, and stockless summary with:

```tsx
<section className="emotion-dashboard-grid" aria-label="EOD market emotion summary">
  <article className="emotion-score-panel">
    <span>综合强度</span>
    <strong>{formatScore(emotion?.summary.score)}</strong>
    <div>
      <span className="status-chip neutral">{emotion?.summary.state ?? '-'}</span>
      <span className="status-chip neutral">Risk {emotion?.summary.risk_state ?? '-'}</span>
    </div>
    <p className="muted">{emotion?.summary.position_budget_hint || 'EOD only'}</p>
  </article>
  <article className="emotion-card">
    <span>涨跌家数</span>
    <strong>{formatCount(emotion?.breadth.up_count)} / {formatCount(emotion?.breadth.down_count)}</strong>
    <small>强涨 {formatCount(emotion?.breadth.strong_up_count)} · 强跌 {formatCount(emotion?.breadth.strong_down_count)}</small>
  </article>
  <article className="emotion-card">
    <span>市场量能</span>
    <strong>{formatAmountYi(emotion?.liquidity.total_amount)}</strong>
    <small>5/20日量比 {formatRatio(emotion?.liquidity.amount_ratio_5_20)}</small>
  </article>
  <article className="emotion-card">
    <span>涨停表现</span>
    <strong>{formatCount(emotion?.limit_performance.limit_up_count)} / {formatCount(emotion?.limit_performance.limit_down_count)}</strong>
    <small>炸板 {formatCount(emotion?.limit_performance.broken_limit_up_count)} · 最高 {formatCount(emotion?.limit_performance.high_board_height)} 板</small>
  </article>
  <article className="emotion-card">
    <span>大幅回撤</span>
    <strong>{formatCount(emotion?.drawdown_pressure.strong_down_count)}</strong>
    <small>炸板率 {formatPercent(emotion?.drawdown_pressure.broken_limit_up_rate)}</small>
  </article>
  <article className="emotion-card pending">
    <span>权重表现</span>
    <strong>待接入</strong>
    <small>指数与大市值表现将在后续接入</small>
  </article>
</section>
```

- [ ] **Step 6: Add赚钱效应 and component breakdown panels**

Add below the emotion grid:

```tsx
<section className="workspace-panel">
  <div className="section-heading">
    <h2>赚钱效应</h2>
    <span className="status-chip neutral">EOD</span>
  </div>
  <div className="profit-effect-table">
    <div><span>昨日涨停成功率</span><strong>{formatPercent(emotion?.profit_effect.limit_up_success_rate)}</strong></div>
    <div><span>昨日涨停盈利率</span><strong>{formatPercent(emotion?.profit_effect.limit_up_profit_rate)}</strong></div>
    <div><span>昨日连板成功率</span><strong>{formatPercent(emotion?.profit_effect.relay_success_rate)}</strong></div>
    <div><span>昨日连板盈利率</span><strong>{formatPercent(emotion?.profit_effect.relay_profit_rate)}</strong></div>
    <div><span>昨日炸板修复率</span><strong>{formatPercent(emotion?.profit_effect.broken_success_rate)}</strong></div>
    <div><span>昨日炸板盈利率</span><strong>{formatPercent(emotion?.profit_effect.broken_profit_rate)}</strong></div>
  </div>
</section>

<section className="workspace-panel">
  <div className="section-heading">
    <h2>情绪拆解</h2>
    <span className="status-chip neutral">0-100</span>
  </div>
  <div className="emotion-component-grid">
    {(emotion?.components ?? []).map((component) => (
      <div key={component.key}>
        <span>{component.label}</span>
        <strong>{formatScore(component.score)}</strong>
      </div>
    ))}
  </div>
</section>
```

- [ ] **Step 7: Add stock-list tabs and table**

Add below the component breakdown:

```tsx
<section className="workspace-panel">
  <div className="section-heading">
    <h2>股票列表</h2>
    <span className="status-chip neutral">EOD</span>
  </div>
  <div className="emotion-stock-tabs" role="tablist" aria-label="Market emotion stock lists">
    {stockTabs.map((tabItem) => (
      <button
        key={tabItem.key}
        type="button"
        role="tab"
        aria-selected={activeStockTab === tabItem.key}
        className={activeStockTab === tabItem.key ? 'active' : ''}
        onClick={() => setActiveStockTab(tabItem.key)}
      >
        {tabItem.label} <span>{tabItem.count}</span>
      </button>
    ))}
  </div>
  {activeStockTab === 'auction' && stockLists?.auction_status === 'pending_source' ? (
    <p className="muted">竞价数据待接入。</p>
  ) : null}
  <div className="emotion-stock-table">
    <div className="emotion-stock-row header">
      <span>股票名称</span>
      <span>成交额</span>
      <span>涨幅</span>
      <span>板块</span>
    </div>
    {activeStockRows.map((row) => (
      <div className="emotion-stock-row" key={`${row.tab}-${row.asset_id}`}>
        <strong>{row.name}<small>{row.symbol}</small></strong>
        <span>{formatAmountYi(row.amount)}</span>
        <span>{formatPercent(row.pct_chg, 2)}</span>
        <span>{row.board || '-'}</span>
      </div>
    ))}
    {activeStockRows.length === 0 ? <p className="muted">暂无股票。</p> : null}
  </div>
</section>
```

- [ ] **Step 8: Add CSS**

In `dashboard/src/styles.css`, add focused styles:

```css
.emotion-dashboard-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: minmax(220px, 1.2fr) repeat(auto-fit, minmax(170px, 1fr));
}

.emotion-score-panel,
.emotion-card {
  background: #ffffff;
  border: 1px solid #d9dee7;
  border-radius: 6px;
  display: grid;
  gap: 6px;
  min-width: 0;
  padding: 12px;
}

.emotion-score-panel strong {
  color: #cf2f2f;
  font-size: 36px;
  line-height: 1;
}

.emotion-score-panel > span,
.emotion-card > span,
.profit-effect-table span,
.emotion-component-grid span {
  color: #667085;
  font-size: 12px;
  font-weight: 600;
}

.emotion-card strong {
  color: #202936;
  font-size: 20px;
}

.emotion-card small {
  color: #667085;
}

.emotion-card.pending strong {
  color: #98a2b3;
}

.profit-effect-table,
.emotion-component-grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.profit-effect-table div,
.emotion-component-grid div {
  border: 1px solid #edf1f5;
  border-radius: 5px;
  display: grid;
  gap: 4px;
  padding: 9px;
}

.profit-effect-table strong {
  color: #cf2f2f;
  font-size: 18px;
}

.emotion-stock-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.emotion-stock-tabs button {
  min-height: 32px;
  border: 1px solid #cfd8e3;
  border-radius: 5px;
  background: #ffffff;
  color: #475467;
  cursor: pointer;
  font: inherit;
  padding: 6px 10px;
}

.emotion-stock-tabs button.active {
  border-color: #cf2f2f;
  color: #cf2f2f;
  font-weight: 700;
}

.emotion-stock-tabs span {
  margin-left: 4px;
}

.emotion-stock-table {
  display: grid;
  margin-top: 10px;
}

.emotion-stock-row {
  display: grid;
  grid-template-columns: minmax(160px, 1.2fr) minmax(100px, 0.8fr) minmax(80px, 0.6fr) minmax(140px, 1fr);
  gap: 10px;
  align-items: center;
  border-bottom: 1px solid #edf1f5;
  min-width: 0;
  padding: 9px 0;
}

.emotion-stock-row.header {
  color: #667085;
  font-size: 12px;
  font-weight: 700;
}

.emotion-stock-row strong {
  display: grid;
  gap: 2px;
}

.emotion-stock-row small {
  color: #98a2b3;
  font-weight: 500;
}
```

- [ ] **Step 9: Run UI tests**

Run:

```bash
cd dashboard
pnpm vitest run tests/app-shell.test.tsx
```

Expected: all app-shell tests pass.

- [ ] **Step 10: Commit UI redesign**

Run:

```bash
git add dashboard/src/components/MarketMonitorWorkspace.tsx dashboard/src/styles.css dashboard/tests/app-shell.test.tsx
git commit -m "feat: redesign market monitor as eod emotion dashboard"
```

---

### Task 5: Home Cockpit Compatibility and Full Verification

**Files:**
- Modify: `dashboard/tests/home-cockpit.test.tsx`
- Verify: browser at `http://127.0.0.1:5174/`

- [ ] **Step 1: Run home cockpit tests**

Run:

```bash
cd dashboard
pnpm vitest run tests/home-cockpit.test.tsx
```

Expected: pass. If it fails because mock payloads lack required new fields, update the fixture with the same minimal `market_emotion` and `emotion_stock_lists` shape from Task 3.

- [ ] **Step 2: Run focused backend and frontend checks**

Run:

```bash
.venv/bin/pytest tests/test_dashboard_market_monitor.py tests/test_dashboard_app.py::test_market_monitor_eod_route_returns_payload -q
cd dashboard
pnpm vitest run tests/app-shell.test.tsx tests/home-cockpit.test.tsx
pnpm build
```

Expected: all commands pass.

- [ ] **Step 3: Browser verification**

Open `http://127.0.0.1:5174/`, navigate to Market Monitor, and verify:

- The page still says `Last Completed Trading Day`.
- The top panel shows `综合强度`.
- The six main dimensions are visible: `涨跌家数`, `市场量能`, `涨停表现`, `赚钱效应`, `大幅回撤`, `权重表现`.
- `股票列表` has tabs for `竞价`, `涨停`, `炸板`, and `跌停`.
- `竞价` shows a pending-source note instead of fake data.
- The layout does not overlap at desktop width and remains readable around 390px mobile width.

- [ ] **Step 4: Commit verification fixture updates**

Run if Task 5 changed any tests:

```bash
git add dashboard/tests/home-cockpit.test.tsx
git commit -m "test: keep home cockpit market monitor fixture current"
```

If no files changed, skip the commit.

---

## Self-Review Checklist

- [ ] The plan keeps V1 EOD-only and does not imply realtime market emotion.
- [ ] 开盘啦-inspired concepts are represented as a framework, not copied formula or UI.
- [ ] 综合强度 maps to existing `emotion_score`.
- [ ] 涨跌家数 maps to `up_count`, `down_count`, `strong_up_count`, and `strong_down_count`.
- [ ] 市场量能 maps to `total_amount` and `amount_ratio_5_20`.
- [ ] 涨停表现 maps to limit-up, limit-down, broken-board, board-height, and relay counts.
- [ ] 赚钱效应 maps to prior-day limit-up, relay, and broken-board feedback.
- [ ] 大幅回撤 has a V1 proxy using strong-down, limit-down, and broken-board pressure.
- [ ] 权重表现 and 竞价 are explicit pending-source gaps.
- [ ] Backend, frontend types, UI, and verification steps are all covered.
