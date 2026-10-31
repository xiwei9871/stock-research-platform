# Project context — stock-research-platform

Quant-research platform: A-share factor research, nightly strategy EOD
pipeline, Baostock/Tushare ingestion to Postgres (192.168.3.187), external
dashboard at stock.manqiaotechnology.com.

## Key paths
- `src/stock_research/` backend; `tests/` pytest; `dashboard/` Vite/React (pnpm)
- `scripts/` cron wrappers (sparse-heartbeat contract, D05)
- `deploy/` prod sync scripts (launchd 22:15 full deploy)
- `config/` runtime config; `docs/` runbooks + agent_governance/

## Ground rules (see AGENTS.md + DECISIONS.md)
- Canonical checkout = this path on `main`; cron must not point elsewhere
- Never touch prod without approval; protected outputs/ dirs never delete
- Baostock single-session host-wide; evening settlement window handled by
  retry-window helpers only
- `rtk` wrapper for noisy commands; keep context lean, targeted reads

## Verify (in order)
1. `python3 tools/gov/sr_gates.py all`
2. `.venv/bin/pytest` (rebuild `.venv` first — deleted 2026-10-31)
3. `cd dashboard && pnpm install && pnpm test` (node_modules deleted 2026-10-31)
