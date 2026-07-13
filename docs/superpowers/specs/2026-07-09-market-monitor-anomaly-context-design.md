# Market Monitor Anomaly Context Design

## Goal

Add a read-only EOD anomaly context layer to Market Monitor so operators can understand why a heat area is notable before opening a stock workspace.

## Scope

In scope:
- Build a backend read model for market anomaly context.
- Use existing daily bars, industry membership, and asset status data.
- Return hot industries, hot stocks, anomaly tags, and explanation bullets.
- Surface the read model in Market Monitor.
- Preserve the existing click-through flow into Stock Workspace.

Out of scope:
- No realtime monitoring.
- No alerts.
- No trading signal.
- No write operations.
- No Agent/RAG.
- No publication or external delivery changes.

## Read Model

API:

```http
GET /api/market-monitor/anomaly-context?trade_date=YYYY-MM-DD
```

The response is white-listed:

```ts
{
  trade_date: string;
  data_status: 'completed' | 'missing' | string;
  summary: {
    hot_industry_count: number;
    hot_stock_count: number;
    volume_spike_count: number;
    strong_move_count: number;
  };
  hot_industries: Array<{
    industry_id: string;
    industry_name: string;
    change_pct: number | null;
    amount: number | null;
    stock_count: number;
    up_count: number;
    down_count: number;
    volume_spike_count: number;
    strong_move_count: number;
    anomaly_score: number;
    explanation_bullets: string[];
  }>;
  hot_stocks: Array<{
    asset_id: string;
    symbol: string;
    name: string;
    industry_id: string;
    industry_name: string;
    change_pct: number | null;
    amount: number | null;
    amount_ratio_20d: number | null;
    turnover_rate: number | null;
    anomaly_tags: string[];
    explanation_bullets: string[];
  }>;
  warnings: string[];
}
```

## Rule Definitions

Initial P1 rule set:
- `volume_spike`: `amount_ratio_20d >= 2.0`
- `strong_up`: `change_pct >= 0.05`
- `strong_down`: `change_pct <= -0.05`
- `limit_up`: asset status says limit up
- `limit_down`: asset status says limit down
- `industry_leader`: top stock by anomaly score within a hot industry

Industry linkage score is a deterministic weighted score from:
- absolute weighted industry change
- total amount
- volume spike count
- strong move count
- breadth imbalance

## UI

Market Monitor gets a compact "异常热区解释" panel near the heatmap area. It shows:
- summary counts
- top hot industries
- top hot stocks with tags
- explanation bullets

The panel is read-only. Stock names can still open the existing Stock Workspace handoff.

## Verification

Tests cover:
- backend rule mapping and read-model filtering
- API route
- frontend client path
- Market Monitor rendering/loading/error behavior
- no write token requirement
