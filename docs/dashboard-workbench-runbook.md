# Dashboard Workbench Runbook

The dashboard workbench is a read-only UI for the existing stock research platform.

## Start API

```bash
stock-research dashboard-api --host 127.0.0.1 --port 8765
```

## Start Frontend

```bash
cd dashboard
pnpm dev
```

Open:

```text
http://127.0.0.1:5174
```

## Data Sources

- Daily bars: `market_daily_bar`
- Minute bars: `market.stock_minute_bar`
- TopN scores: `factor.stock_score_daily`
- Watchlist signals: `watchlist.watchlist_daily_signal`
- Report links: local `reports/` artifacts

## Operating Boundary

The dashboard does not create trading instructions. It only displays existing research outputs for human review.

Internal skill outputs that follow `docs/llmquant-fusion/internal-skill-template.md` are review artifacts. The dashboard may display them only after they are written as local artifacts and pass the existing review boundary. They must not mutate dashboard state, watchlist state, scores, broker/order/account/cash/position state, or production approvals.
