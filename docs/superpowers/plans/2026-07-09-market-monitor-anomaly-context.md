# Market Monitor Anomaly Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only EOD anomaly explanations, industry linkage ranking, and volume/change tags to Market Monitor.

**Architecture:** Create a backend dashboard read model and API, then add frontend client/types and a compact Market Monitor panel. The feature uses existing tables and carries no write, trading, publication, realtime, Agent, or RAG behavior.

**Tech Stack:** FastAPI, PostgreSQL read model, React, TypeScript, Vitest, pytest.

---

### Task 1: Backend Read Model

**Files:**
- Create: `src/stock_research/dashboard/market_anomaly_context.py`
- Create: `tests/test_dashboard_market_anomaly_context.py`
- Modify: `src/stock_research/dashboard/app.py`

- [ ] Write failing pytest coverage for rule mapping, white-listed read model, missing data, and API route.
- [ ] Implement `build_market_anomaly_context(trade_date, service=...)`.
- [ ] Implement `market_anomaly_context_read_model(payload)`.
- [ ] Add `GET /api/market-monitor/anomaly-context`.
- [ ] Run `rtk .venv/bin/pytest tests/test_dashboard_market_anomaly_context.py -q`.

### Task 2: Frontend API And Types

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Modify: `dashboard/tests/client.test.ts`

- [ ] Write failing Vitest coverage for `fetchMarketAnomalyContext`.
- [ ] Add `MarketAnomalyContextPayload` types.
- [ ] Add API client function for `/api/market-monitor/anomaly-context`.
- [ ] Run frontend tests.

### Task 3: Market Monitor UI

**Files:**
- Create: `dashboard/src/components/market-monitor/MarketAnomalyContextPanel.tsx`
- Modify: `dashboard/src/components/MarketMonitorWorkspace.tsx`
- Modify: `dashboard/tests/market-monitor-workspace.test.tsx`
- Modify: `dashboard/src/styles.css`

- [ ] Write failing UI test for "异常热区解释".
- [ ] Fetch anomaly context for the active trade date.
- [ ] Render loading, empty, error, hot industry, and hot stock states.
- [ ] Keep stock click-through read-only and context-aware.

### Task 4: Verification

**Commands:**

```bash
rtk .venv/bin/pytest tests/test_dashboard_market_anomaly_context.py tests/test_dashboard_app.py -q
rtk pnpm --dir dashboard test
rtk pnpm --dir dashboard build
```

Expected:
- backend targeted tests pass
- frontend Vitest passes
- dashboard build passes with only the existing Vite chunk warning
