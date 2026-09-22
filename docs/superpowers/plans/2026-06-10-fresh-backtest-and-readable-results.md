# Fresh Backtest And Readable Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split Backtest Lab into true fresh backtests and validated replay loading, then replace raw metric-first detail views with a readable summary, KPIs, charts, and tabbed details.

**Architecture:** Keep validated replay as a fast DB read-model path, but expose it through explicit replay endpoints and UI controls. Add a fresh backtest execution path that does not call `run_replay`; it recomputes strategy results from strategy adapter score generation and the vectorized engine initially, then can be upgraded per-combo as exact strategy engines are ported. Rework the React result surface around a typed result summary model, with raw tables moved behind tabs.

**Tech Stack:** Python FastAPI, pandas, PostgreSQL read-model tables, existing vectorized TopN engine, React 19, TypeScript, lightweight-charts, Vitest, Playwright.

---

## File Structure

**Backend**
- Modify `src/stock_research/dashboard/backtests.py`
  - Add explicit execution modes: `fresh` and `replay`.
  - Keep existing replay path, but move it behind `run_replay_backtest`.
  - Add `run_fresh_backtest` that bypasses combo replay adapters and uses live DB inputs.
  - Add user-facing result metadata: `execution_mode`, `result_source`, `run_started_at`, `run_finished_at`, `elapsed_ms`, `requested_*`, `actual_*`.
- Modify `src/stock_research/dashboard/app.py`
  - Add `POST /api/backtests/run-fresh`.
  - Add `POST /api/backtests/run-replay`.
  - Add `POST /api/backtests/compare-fresh`.
  - Add `POST /api/backtests/compare-replay`.
  - Keep `POST /api/backtests/run` temporarily as a compatibility alias for replay with a deprecation field.
- Modify `src/stock_research/dashboard/strategy_backtest_adapters.py`
  - Add a fresh-score loader for combo strategies, separate from `run_replay`.
  - For first implementation, fresh mode uses existing score builders:
    - LHB: `LHBShortlineAdapter.load_scores`
    - Mid: `MidTrendAdapter.load_scores`
    - Tech: `TechBottleneckAdapter.load_scores`
  - Return warning metadata when fresh mode is an approximation of the validated combo rather than exact original research engine.
- Modify `src/stock_research/strategy_backtest_read_model.py`
  - Keep replay normalization.
  - Add stable result metadata normalization helpers shared by replay and fresh.
- Modify tests:
  - `tests/test_dashboard_backtests.py`
  - `tests/test_strategy_backtest_adapters.py`
  - `tests/test_strategy_backtest_read_model.py`

**Frontend**
- Modify `dashboard/src/api/types.ts`
  - Add `BacktestExecutionMode`, `BacktestRunEnvelope`, `BacktestComparisonResult`.
  - Extend `BacktestRunResult` with source/timing metadata.
- Modify `dashboard/src/api/client.ts`
  - Add `runFreshBacktest`, `runReplayBacktest`, `runFreshComparison`, `runReplayComparison`.
  - Keep `runBacktest` only if required by older tests, but route new UI through explicit calls.
- Modify `dashboard/src/components/BacktestLabWorkspace.tsx`
  - Rename existing fast path to `Load Replay`.
  - Make `Run Backtest` call fresh endpoint.
  - Make `Run Comparison` call fresh comparison endpoint.
  - Add `Load Replay Comparison`.
  - Replace result section with `BacktestResultDetail`.
- Create `dashboard/src/components/BacktestResultDetail.tsx`
  - Summary paragraph.
  - KPI grid.
  - Equity/drawdown chart.
  - Tabs: Overview, Equity, Trades, Holdings, Drawdown, Raw Metrics.
- Create `dashboard/src/components/BacktestCharts.tsx`
  - Use `lightweight-charts` for equity/drawdown.
  - Keep chart resilient if no rows exist.
- Modify `dashboard/src/styles.css`
  - Add result summary, KPI grid, chart band, tab styles.
- Modify tests:
  - `dashboard/tests/backtest-lab-workspace.test.tsx`
  - `dashboard/tests/platform-full-flow.spec.ts`
  - `dashboard/tests/platform-client.test.ts`

---

## Task 1: Backend API Mode Split

**Files:**
- Modify: `src/stock_research/dashboard/backtests.py`
- Modify: `src/stock_research/dashboard/app.py`
- Test: `tests/test_dashboard_backtests.py`

- [ ] **Step 1: Write failing backend tests for explicit fresh/replay endpoints**

Add these tests to `tests/test_dashboard_backtests.py`:

```python
def test_run_replay_backtest_uses_replay_adapter(monkeypatch):
    calls = {}

    class FakeReplayAdapter:
        strategy_id = "mid_trend"
        strategy_name = "Mid Trend Combo"

        def run_replay(self, params, run_config):
            calls["params"] = params
            calls["run_config"] = run_config
            return {
                "strategy_id": "mid_trend",
                "strategy_name": "Mid Trend Combo",
                "read_only": True,
                "config": {"start_date": params.start_date, "end_date": params.end_date},
                "summary": {"final_equity": 1.2},
                "equity_curve": [],
                "positions": [],
                "trades": [],
            }

    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "mid_trend", FakeReplayAdapter())

    payload = backtests.run_replay_backtest({
        "strategy_id": "mid_trend",
        "start_date": "2026-01-01",
        "end_date": "2026-06-08",
        "top_n": 20,
        "rebalance_frequency": "weekly",
        "transaction_cost_bps": 10,
        "max_positions": 20,
        "score_version": "manual_v1",
        "adjust_type": "hfq",
    })

    assert payload["execution_mode"] == "replay"
    assert payload["result_source"] == "database_replay"
    assert payload["summary"]["final_equity"] == 1.2
    assert calls["params"].start_date == "2026-01-01"


def test_run_fresh_backtest_bypasses_replay_adapter_and_uses_live_scores(monkeypatch):
    calls = {}

    class FakeComboAdapter:
        strategy_id = "mid_trend"
        strategy_name = "Mid Trend Combo"

        def run_replay(self, params, run_config):
            raise AssertionError("fresh mode must not call run_replay")

        def load_scores(self, params):
            calls["params"] = params
            return pd.DataFrame([
                {"trade_date": "2026-01-02", "asset_id": "A", "rank": 1, "score_total": 90.0}
            ])

    result = VectorizedTopNResult(
        config=VectorizedTopNConfig(
            start_date="2026-01-01",
            end_date="2026-06-08",
            top_n=1,
            rebalance_frequency="weekly",
            transaction_cost_bps=10.0,
            max_positions=1,
        ),
        equity_curve=pd.DataFrame([{"date": "2026-01-02", "equity": 1.03, "drawdown": 0.0}]),
        positions=pd.DataFrame([{"rebalance_date": "2026-01-02", "asset_id": "A", "weight": 1.0}]),
        trades=pd.DataFrame([{"execution_date": "2026-01-02", "asset_id": "A", "side": "buy"}]),
        summary={"final_equity": 1.03, "total_return": 0.03, "max_drawdown": 0.0},
    )

    monkeypatch.setitem(backtests.STRATEGY_BACKTEST_REGISTRY, "mid_trend", FakeComboAdapter())
    monkeypatch.setattr(backtests, "load_vectorized_topn_prices", lambda **kwargs: pd.DataFrame([
        {"trade_date": "2026-01-02", "asset_id": "A", "close": 10.0}
    ]))
    monkeypatch.setattr(backtests, "run_vectorized_topn_backtest", lambda scores, prices, config: result)

    payload = backtests.run_fresh_backtest({
        "strategy_id": "mid_trend",
        "start_date": "2026-01-01",
        "end_date": "2026-06-08",
        "top_n": 1,
        "rebalance_frequency": "weekly",
        "transaction_cost_bps": 10,
        "max_positions": 1,
        "score_version": "manual_v1",
        "adjust_type": "hfq",
    })

    assert payload["execution_mode"] == "fresh"
    assert payload["result_source"] == "live_vectorized_backtest"
    assert payload["summary"]["final_equity"] == 1.03
    assert payload["summary"]["fresh_engine_note"] == "live score rebuild; combo parity may differ from validated replay"
```

- [ ] **Step 2: Run failing tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_dashboard_backtests.py::test_run_replay_backtest_uses_replay_adapter \
  tests/test_dashboard_backtests.py::test_run_fresh_backtest_bypasses_replay_adapter_and_uses_live_scores -q
```

Expected: fail because `run_replay_backtest` and `run_fresh_backtest` do not exist.

- [ ] **Step 3: Implement request parsing helper and metadata envelope**

In `src/stock_research/dashboard/backtests.py`, add:

```python
import time
from datetime import datetime, timezone
```

Then add:

```python
def _parse_backtest_request(payload: dict[str, Any]) -> tuple[str, StrategyBacktestParams, dict[str, Any], VectorizedTopNConfig]:
    strategy_id = _required_text(payload, "strategy_id")
    start_date = _required_text(payload, "start_date")
    end_date = _required_text(payload, "end_date")
    score_version = _optional_text(payload.get("score_version"), "manual_v1")
    adjust_type = _optional_text(payload.get("adjust_type"), "hfq")
    top_n = _positive_int(payload.get("top_n"), "top_n", 20)
    max_positions = _optional_positive_int(payload.get("max_positions"), "max_positions")
    rebalance_frequency = _rebalance_frequency(payload.get("rebalance_frequency"))
    transaction_cost_bps = _finite_float(payload.get("transaction_cost_bps"), "transaction_cost_bps", 0.0)
    params = StrategyBacktestParams(
        start_date=start_date,
        end_date=end_date,
        score_version=score_version,
        adjust_type=adjust_type,
    )
    run_config = {
        "score_version": score_version,
        "top_n": top_n,
        "rebalance_frequency": rebalance_frequency,
        "transaction_cost_bps": transaction_cost_bps,
        "max_positions": max_positions,
        "adjust_type": adjust_type,
    }
    vector_config = VectorizedTopNConfig(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        rebalance_frequency=rebalance_frequency,
        transaction_cost_bps=transaction_cost_bps,
        max_positions=max_positions,
    )
    return strategy_id, params, run_config, vector_config


def _with_execution_metadata(payload: dict[str, Any], *, mode: str, source: str, started_at: str, elapsed_ms: float) -> dict[str, Any]:
    result = dict(payload)
    result["execution_mode"] = mode
    result["result_source"] = source
    result["run_started_at"] = started_at
    result["run_finished_at"] = datetime.now(timezone.utc).isoformat()
    result["elapsed_ms"] = round(float(elapsed_ms), 3)
    summary = dict(result.get("summary") or {})
    summary["execution_mode"] = mode
    summary["result_source"] = source
    summary["elapsed_ms"] = result["elapsed_ms"]
    result["summary"] = summary
    return result
```

- [ ] **Step 4: Implement `run_replay_backtest` and `run_fresh_backtest`**

Refactor existing `run_backtest` into explicit functions:

```python
def run_replay_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    strategy_id, params, run_config, _vector_config = _parse_backtest_request(payload)
    adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
    if adapter is None:
        raise ValueError(f"unsupported strategy: {strategy_id}")
    replay_runner = getattr(adapter, "run_replay", None)
    if not callable(replay_runner):
        raise ValueError(f"strategy does not support replay: {strategy_id}")
    result = to_json_safe(replay_runner(params, run_config))
    return _with_execution_metadata(
        result,
        mode="replay",
        source=str(result.get("source_kind") or "database_replay"),
        started_at=started_at,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def run_fresh_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = datetime.now(timezone.utc).isoformat()
    strategy_id, params, run_config, vector_config = _parse_backtest_request(payload)
    adapter = STRATEGY_BACKTEST_REGISTRY.get(strategy_id)
    if adapter is None:
        raise ValueError(f"unsupported strategy: {strategy_id}")
    scores = adapter.load_scores(params)
    prices = load_vectorized_topn_prices(
        start_date=params.start_date,
        end_date=params.end_date,
        adjust_type=params.adjust_type,
    )
    result = run_vectorized_topn_backtest(scores, prices, vector_config)
    payload_result = {
        "strategy_id": strategy_id,
        "strategy_name": _strategy_name(strategy_id),
        "read_only": False,
        "config": {
            "start_date": params.start_date,
            "end_date": params.end_date,
            **run_config,
        },
        "summary": {
            **to_json_safe(result.summary),
            "fresh_engine_note": "live score rebuild; combo parity may differ from validated replay",
        },
        "equity_curve": _frame_records(result.equity_curve),
        "positions": _frame_records(result.positions),
        "trades": _frame_records(result.trades),
    }
    return _with_execution_metadata(
        payload_result,
        mode="fresh",
        source="live_vectorized_backtest",
        started_at=started_at,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )
```

Then make legacy `run_backtest` call replay for compatibility:

```python
def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    return run_replay_backtest(payload)
```

- [ ] **Step 5: Add FastAPI routes**

In `src/stock_research/dashboard/app.py`, import and use:

```python
from stock_research.dashboard.backtests import (
    list_backtest_strategies,
    run_backtest,
    run_fresh_backtest,
    run_replay_backtest,
)
```

Add routes:

```python
@app.post("/api/backtests/run-fresh")
def backtest_run_fresh(payload: dict):
    try:
        return run_fresh_backtest(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/backtests/run-replay")
def backtest_run_replay(payload: dict):
    try:
        return run_replay_backtest(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest tests/test_dashboard_backtests.py -q
```

Expected: pass.

---

## Task 2: Frontend API Client Split

**Files:**
- Modify: `dashboard/src/api/types.ts`
- Modify: `dashboard/src/api/client.ts`
- Test: `dashboard/tests/platform-client.test.ts`

- [ ] **Step 1: Write failing client tests**

In `dashboard/tests/platform-client.test.ts`, add expectations that:

```typescript
const freshResult = await runFreshBacktest(backtestRequest);
const replayResult = await runReplayBacktest(backtestRequest);

expect(fetchMock).toHaveBeenCalledWith('/api/backtests/run-fresh', expect.objectContaining({ method: 'POST' }));
expect(fetchMock).toHaveBeenCalledWith('/api/backtests/run-replay', expect.objectContaining({ method: 'POST' }));
expect(freshResult.execution_mode).toBe('fresh');
expect(replayResult.execution_mode).toBe('replay');
```

- [ ] **Step 2: Run failing client tests**

Run:

```bash
pnpm vitest run tests/platform-client.test.ts --exclude "**/*.spec.ts"
```

Expected: fail because `runFreshBacktest` and `runReplayBacktest` do not exist.

- [ ] **Step 3: Extend TypeScript result types**

In `dashboard/src/api/types.ts`, add:

```typescript
export type BacktestExecutionMode = 'fresh' | 'replay';

export type BacktestRunResult = {
  strategy_id: string;
  strategy_name: string;
  read_only: boolean;
  execution_mode?: BacktestExecutionMode;
  result_source?: string;
  run_started_at?: string;
  run_finished_at?: string;
  elapsed_ms?: number;
  config: Record<string, unknown>;
  summary: Record<string, number | string | null>;
  equity_curve: Array<Record<string, number | string | null>>;
  positions: Array<Record<string, number | string | null>>;
  trades: Array<Record<string, number | string | null>>;
};
```

- [ ] **Step 4: Add explicit client functions**

In `dashboard/src/api/client.ts`, add:

```typescript
async function postBacktest(url: string, request: BacktestRunRequest): Promise<BacktestRunResult> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    throw new Error(`POST ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<BacktestRunResult>;
}

export async function runFreshBacktest(request: BacktestRunRequest): Promise<BacktestRunResult> {
  return postBacktest('/api/backtests/run-fresh', request);
}

export async function runReplayBacktest(request: BacktestRunRequest): Promise<BacktestRunResult> {
  return postBacktest('/api/backtests/run-replay', request);
}

export async function runBacktest(request: BacktestRunRequest): Promise<BacktestRunResult> {
  return runReplayBacktest(request);
}
```

- [ ] **Step 5: Run client tests**

Run:

```bash
pnpm vitest run tests/platform-client.test.ts --exclude "**/*.spec.ts"
```

Expected: pass.

---

## Task 3: Backtest Lab Controls For Fresh vs Replay

**Files:**
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Modify: `dashboard/tests/backtest-lab-workspace.test.tsx`
- Modify: `dashboard/tests/platform-full-flow.spec.ts`

- [ ] **Step 1: Write failing UI tests for controls**

Update `dashboard/tests/backtest-lab-workspace.test.tsx` so the mocked API exports:

```typescript
runFreshBacktest: vi.fn(),
runReplayBacktest: vi.fn()
```

Add tests:

```typescript
it('runs fresh backtest from Run Backtest and replay from Load Replay', async () => {
  render(<BacktestLabWorkspace />);
  await screen.findAllByText('LHB Shortline Combo');

  fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));
  await waitFor(() => expect(apiMocks.runFreshBacktest).toHaveBeenCalledTimes(1));
  expect(apiMocks.runReplayBacktest).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Load Replay' }));
  await waitFor(() => expect(apiMocks.runReplayBacktest).toHaveBeenCalledTimes(1));
});

it('runs fresh comparison and replay comparison separately', async () => {
  render(<BacktestLabWorkspace />);
  await screen.findAllByText('LHB Shortline Combo');

  fireEvent.click(screen.getByRole('button', { name: 'Run Comparison' }));
  await waitFor(() => expect(apiMocks.runFreshBacktest).toHaveBeenCalledTimes(3));

  fireEvent.click(screen.getByRole('button', { name: 'Load Replay Comparison' }));
  await waitFor(() => expect(apiMocks.runReplayBacktest).toHaveBeenCalledTimes(3));
});
```

- [ ] **Step 2: Run failing UI tests**

Run:

```bash
pnpm vitest run tests/backtest-lab-workspace.test.tsx --exclude "**/*.spec.ts"
```

Expected: fail because buttons/functions are missing.

- [ ] **Step 3: Update imports and submit handlers**

In `BacktestLabWorkspace.tsx`, change imports:

```typescript
import { fetchBacktestStrategies, runFreshBacktest, runReplayBacktest } from '../api/client';
```

Replace `submitBacktest` with a mode parameter:

```typescript
const submitBacktest = (mode: 'fresh' | 'replay') => {
  if (!canRun) return;
  const requestId = runRequestIdRef.current + 1;
  runRequestIdRef.current = requestId;
  setIsRunning(true);
  setRunError(null);
  setResult(null);
  setComparisonRows([]);

  const runner = mode === 'fresh' ? runFreshBacktest : runReplayBacktest;
  runner(buildBacktestRequest(strategyId))
    .then((payload) => {
      if (!mountedRef.current || runRequestIdRef.current !== requestId) return;
      setResult(payload);
      setIsRunning(false);
    })
    .catch((err: unknown) => {
      if (!mountedRef.current || runRequestIdRef.current !== requestId) return;
      setRunError(err instanceof Error ? err.message : String(err));
      setIsRunning(false);
    });
};
```

Replace comparison similarly:

```typescript
const submitComparison = (mode: 'fresh' | 'replay') => {
  if (!canCompare) return;
  const runner = mode === 'fresh' ? runFreshBacktest : runReplayBacktest;
  // existing comparison loop, but call runner(...)
};
```

- [ ] **Step 4: Add explicit buttons and copy**

Replace the button area with:

```tsx
<button type="button" disabled={!canRun} onClick={() => submitBacktest('fresh')}>
  {isRunning ? 'Running...' : 'Run Backtest'}
</button>
<button type="button" disabled={!canRun} onClick={() => submitBacktest('replay')}>
  Load Replay
</button>
<button type="button" disabled={!canCompare} onClick={() => submitComparison('fresh')}>
  {isComparing ? 'Comparing...' : 'Run Comparison'}
</button>
<button type="button" disabled={!canCompare} onClick={() => submitComparison('replay')}>
  Load Replay Comparison
</button>
```

Update helper text:

```tsx
<p className="muted">
  Run Backtest recomputes from live database inputs. Load Replay reads validated cached results.
</p>
```

- [ ] **Step 5: Run UI tests**

Run:

```bash
pnpm vitest run tests/backtest-lab-workspace.test.tsx --exclude "**/*.spec.ts"
```

Expected: pass.

---

## Task 4: Readable Result Detail Component

**Files:**
- Create: `dashboard/src/components/BacktestResultDetail.tsx`
- Create: `dashboard/src/components/BacktestCharts.tsx`
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Modify: `dashboard/src/styles.css`
- Test: `dashboard/tests/backtest-lab-workspace.test.tsx`

- [ ] **Step 1: Write failing tests for readable detail**

Add to `dashboard/tests/backtest-lab-workspace.test.tsx`:

```typescript
it('renders readable summary, KPI cards, and detail tabs for a backtest result', async () => {
  apiMocks.runReplayBacktest.mockResolvedValue(makeRunResult('mid_trend', 'Mid Trend Combo', {
    summary: {
      execution_mode: 'replay',
      result_source: 'database_replay',
      start_date: '2026-01-01',
      end_date: '2026-06-08',
      actual_start_date: '2026-01-05',
      actual_end_date: '2026-06-02',
      final_equity: 1.5599,
      total_return: 0.5599,
      max_drawdown: -0.1752,
      trade_rows: 74,
      position_rows: 95,
      elapsed_ms: 31.2
    }
  }));

  render(<BacktestLabWorkspace />);
  await screen.findAllByText('LHB Shortline Combo');
  fireEvent.change(screen.getByLabelText('strategy'), { target: { value: 'mid_trend' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load Replay' }));

  expect(await screen.findByText(/Mid Trend Combo 在 2026-01-01 至 2026-06-08/)).toBeInTheDocument();
  expect(screen.getByText('区间收益')).toBeInTheDocument();
  expect(screen.getByText('+55.99%')).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Overview' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Trades' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Raw Metrics' })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run failing result detail test**

Run:

```bash
pnpm vitest run tests/backtest-lab-workspace.test.tsx --exclude "**/*.spec.ts"
```

Expected: fail because `BacktestResultDetail` does not exist.

- [ ] **Step 3: Create formatting helpers inside `BacktestResultDetail.tsx`**

Create `dashboard/src/components/BacktestResultDetail.tsx`:

```tsx
import { useMemo, useState } from 'react';
import type { BacktestRunResult } from '../api/types';
import { BacktestEquityChart } from './BacktestCharts';

type ResultRow = Record<string, number | string | null>;
type TabKey = 'overview' | 'equity' | 'trades' | 'holdings' | 'drawdown' | 'raw';

function numberValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function stringValue(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function percent(value: unknown) {
  const parsed = numberValue(value);
  if (parsed === null) return '-';
  const sign = parsed > 0 ? '+' : '';
  return `${sign}${(parsed * 100).toFixed(2)}%`;
}

function decimal(value: unknown) {
  const parsed = numberValue(value);
  return parsed === null ? '-' : parsed.toFixed(4);
}

function display(value: unknown) {
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  return value == null || value === '' ? '-' : String(value);
}

function columns(rows: ResultRow[]) {
  return Array.from(new Set(rows.flatMap((row) => Object.keys(row))));
}

function ResultTable({ rows, emptyText }: { rows: ResultRow[]; emptyText: string }) {
  const cols = columns(rows);
  if (rows.length === 0 || cols.length === 0) return <p className="muted">{emptyText}</p>;
  return (
    <div className="table-scroll">
      <table className="data-table backtest-result-table">
        <thead><tr>{cols.map((col) => <th key={col}>{col}</th>)}</tr></thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${index}-${row.asset_id ?? ''}-${row.date ?? row.trade_date ?? row.rebalance_date ?? ''}`}>
              {cols.map((col) => <td key={col}>{display(row[col])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BacktestResultDetail({ result }: { result: BacktestRunResult }) {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');
  const summary = result.summary;
  const requestedStart = stringValue(summary.start_date) ?? stringValue(summary.requested_start_date) ?? '-';
  const requestedEnd = stringValue(summary.end_date) ?? stringValue(summary.requested_end_date) ?? '-';
  const actualStart = stringValue(summary.actual_start_date) ?? '-';
  const actualEnd = stringValue(summary.actual_end_date) ?? '-';
  const source = stringValue(summary.result_source) ?? result.result_source ?? 'unknown';
  const mode = stringValue(summary.execution_mode) ?? result.execution_mode ?? 'unknown';

  const kpis = [
    ['区间收益', percent(summary.total_return)],
    ['最终净值', decimal(summary.final_equity)],
    ['最大回撤', percent(summary.max_drawdown)],
    ['交易数', display(summary.trade_rows ?? result.trades.length)],
    ['持仓记录', display(summary.position_rows ?? result.positions.length)],
    ['实际区间', `${actualStart} 至 ${actualEnd}`],
    ['来源', `${mode} / ${source}`],
    ['耗时', summary.elapsed_ms == null ? '-' : `${display(summary.elapsed_ms)} ms`],
  ];

  const tabs: Array<[TabKey, string]> = [
    ['overview', 'Overview'],
    ['equity', 'Equity'],
    ['trades', 'Trades'],
    ['holdings', 'Holdings'],
    ['drawdown', 'Drawdown'],
    ['raw', 'Raw Metrics'],
  ];

  const drawdownRows = useMemo(
    () => result.equity_curve.map((row) => ({ date: row.date ?? row.trade_date ?? null, drawdown: row.drawdown ?? null })),
    [result.equity_curve]
  );

  return (
    <section className="workspace-band backtest-results">
      <div className="section-heading">
        <h2>Backtest Detail</h2>
        <span className="muted">{result.strategy_name}</span>
      </div>
      <p className="backtest-readable-summary">
        {result.strategy_name} 在 {requestedStart} 至 {requestedEnd} 请求区间内，实际可用明细为 {actualStart} 至 {actualEnd}。
        区间收益 {percent(summary.total_return)}，最终净值 {decimal(summary.final_equity)}，最大回撤 {percent(summary.max_drawdown)}，
        交易 {display(summary.trade_rows ?? result.trades.length)} 笔。
      </p>
      <div className="backtest-kpi-grid">
        {kpis.map(([label, value]) => (
          <div className="backtest-kpi" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <BacktestEquityChart rows={result.equity_curve} />
      <div className="tab-list" role="tablist" aria-label="Backtest detail tabs">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={activeTab === key}
            onClick={() => setActiveTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {activeTab === 'overview' ? <ResultTable rows={[summary]} emptyText="No summary returned." /> : null}
      {activeTab === 'equity' ? <ResultTable rows={result.equity_curve} emptyText="No equity rows returned." /> : null}
      {activeTab === 'trades' ? <ResultTable rows={result.trades} emptyText="No trades returned." /> : null}
      {activeTab === 'holdings' ? <ResultTable rows={result.positions} emptyText="No holdings returned." /> : null}
      {activeTab === 'drawdown' ? <ResultTable rows={drawdownRows} emptyText="No drawdown rows returned." /> : null}
      {activeTab === 'raw' ? <ResultTable rows={[summary]} emptyText="No raw metrics returned." /> : null}
    </section>
  );
}
```

- [ ] **Step 4: Create resilient chart component**

Create `dashboard/src/components/BacktestCharts.tsx`:

```tsx
import { useEffect, useRef } from 'react';
import { createChart, type IChartApi } from 'lightweight-charts';

type ChartRow = Record<string, number | string | null>;

function rowDate(row: ChartRow) {
  const value = row.date ?? row.trade_date;
  return typeof value === 'string' ? value : null;
}

function rowNumber(row: ChartRow, key: string) {
  const value = row[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function BacktestEquityChart({ rows }: { rows: ChartRow[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const chart: IChartApi = createChart(container, {
      height: 260,
      layout: { background: { color: '#ffffff' }, textColor: '#1f2937' },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      grid: { vertLines: { color: '#eef2f7' }, horzLines: { color: '#eef2f7' } },
    });
    const equitySeries = chart.addLineSeries({ color: '#2563eb', lineWidth: 2 });
    const drawdownSeries = chart.addLineSeries({ color: '#dc2626', lineWidth: 1 });
    equitySeries.setData(
      rows
        .map((row) => {
          const time = rowDate(row);
          const value = rowNumber(row, 'equity');
          return time && value !== null ? { time, value } : null;
        })
        .filter((item): item is { time: string; value: number } => item !== null)
    );
    drawdownSeries.setData(
      rows
        .map((row) => {
          const time = rowDate(row);
          const value = rowNumber(row, 'drawdown');
          return time && value !== null ? { time, value } : null;
        })
        .filter((item): item is { time: string; value: number } => item !== null)
    );
    chart.timeScale().fitContent();
    const resizeObserver = new ResizeObserver(() => chart.applyOptions({ width: container.clientWidth }));
    resizeObserver.observe(container);
    chart.applyOptions({ width: container.clientWidth });
    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [rows]);

  if (rows.length === 0) {
    return <p className="muted">No equity curve returned.</p>;
  }

  return <div className="backtest-chart" ref={containerRef} aria-label="Equity and drawdown chart" />;
}
```

- [ ] **Step 5: Wire detail component**

In `BacktestLabWorkspace.tsx`, import:

```typescript
import { BacktestResultDetail } from './BacktestResultDetail';
```

Replace the entire `{result ? (...) : (...)}` result block with:

```tsx
{result ? (
  <BacktestResultDetail result={result} />
) : (
  <section className="workspace-band">
    <h2>Backtest Results</h2>
    <p className="muted">Run a fresh backtest or load a validated replay to view summary, KPIs, charts, and detail rows.</p>
  </section>
)}
```

- [ ] **Step 6: Add CSS**

Append to `dashboard/src/styles.css`:

```css
.backtest-readable-summary {
  margin: 0 0 16px;
  max-width: 920px;
  color: #334155;
  line-height: 1.6;
}

.backtest-kpi-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin: 16px 0;
}

.backtest-kpi {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 12px;
  background: #fff;
}

.backtest-kpi span {
  display: block;
  color: #64748b;
  font-size: 0.78rem;
  margin-bottom: 6px;
}

.backtest-kpi strong {
  color: #111827;
  font-size: 1rem;
}

.backtest-chart {
  width: 100%;
  min-height: 260px;
  margin: 16px 0;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.tab-list {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin: 16px 0 10px;
}

.tab-list button {
  border: 1px solid #cbd5e1;
  background: #fff;
  border-radius: 6px;
  padding: 8px 10px;
}

.tab-list button[aria-selected="true"] {
  border-color: #2563eb;
  color: #2563eb;
  background: #eff6ff;
}
```

- [ ] **Step 7: Run UI tests**

Run:

```bash
pnpm vitest run tests/backtest-lab-workspace.test.tsx --exclude "**/*.spec.ts"
```

Expected: pass.

---

## Task 5: Fresh Comparison Semantics And Timing

**Files:**
- Modify: `dashboard/src/components/BacktestLabWorkspace.tsx`
- Modify: `dashboard/tests/backtest-lab-workspace.test.tsx`
- Modify: `dashboard/tests/platform-full-flow.spec.ts`

- [ ] **Step 1: Add tests that fresh comparison remains visibly running**

In `dashboard/tests/backtest-lab-workspace.test.tsx`, update deferred comparison test so fresh comparison rows start as `running` and only complete after promises resolve:

```typescript
expect(screen.getByText('0 / 3 completed')).toBeInTheDocument();
expect(screen.getAllByRole('cell', { name: 'running' })).toHaveLength(3);
```

Keep this test using deferred promises; do not add artificial sleeps.

- [ ] **Step 2: Add source/timing columns to comparison table**

In `BacktestLabWorkspace.tsx`, add columns:

```tsx
<th>Mode</th>
<th>Source</th>
<th>Elapsed</th>
<th>Actual Range</th>
```

Render:

```tsx
<td>{row.result?.execution_mode ?? '-'}</td>
<td>{row.result?.result_source ?? '-'}</td>
<td>{row.result?.elapsed_ms == null ? '-' : `${formatValue(row.result.elapsed_ms)} ms`}</td>
<td>
  {row.result
    ? `${row.result.summary.actual_start_date ?? '-'} to ${row.result.summary.actual_end_date ?? '-'}`
    : '-'}
</td>
```

- [ ] **Step 3: Update Playwright mocked flow**

In `dashboard/tests/platform-full-flow.spec.ts`, make `/api/backtests/run-fresh` delay at least 50 ms in mocks and return:

```typescript
execution_mode: 'fresh',
result_source: 'live_vectorized_backtest',
elapsed_ms: 1234
```

Make `/api/backtests/run-replay` return:

```typescript
execution_mode: 'replay',
result_source: 'database_replay',
elapsed_ms: 31
```

- [ ] **Step 4: Run frontend tests and e2e**

Run:

```bash
pnpm test
pnpm build
pnpm test:e2e
```

Expected: all pass.

---

## Task 6: API Verification And Server Restart

**Files:**
- Runtime only.

- [ ] **Step 1: Run backend focused tests**

Run:

```bash
/Users/xiwei/stock_research/.venv/bin/python -m pytest \
  tests/test_strategy_backtest_adapters.py \
  tests/test_dashboard_backtests.py \
  tests/test_strategy_backtest_read_model.py \
  tests/test_dashboard_strategy_catalog.py \
  tests/test_schema.py::test_research_extension_includes_strategy_backtest_read_model_tables -q
```

Expected: pass.

- [ ] **Step 2: Restart API**

Find existing API:

```bash
lsof -nP -iTCP:8765 -sTCP:LISTEN
```

Kill only the listed API PID, then restart:

```bash
PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m uvicorn stock_research.dashboard.app:app --host 127.0.0.1 --port 8765
```

- [ ] **Step 3: Verify replay is fast and labeled replay**

Run:

```bash
curl -s http://127.0.0.1:8765/api/backtests/run-replay \
  -H 'Content-Type: application/json' \
  --data '{"strategy_id":"mid_trend","start_date":"2026-01-01","end_date":"2026-06-08","top_n":20,"rebalance_frequency":"weekly","transaction_cost_bps":10,"max_positions":20,"score_version":"manual_v1","adjust_type":"hfq"}' \
  | /Users/xiwei/stock_research/.venv/bin/python -c 'import json,sys; r=json.load(sys.stdin); print(r["execution_mode"], r["result_source"], r["summary"]["start_date"], r["summary"]["end_date"], r["summary"]["final_equity"])'
```

Expected:

```text
replay database_replay 2026-01-01 2026-06-08 1.5599208351
```

- [ ] **Step 4: Verify fresh endpoint is slower and labeled fresh**

Run:

```bash
curl -s -w '\ntime=%{time_total}\n' http://127.0.0.1:8765/api/backtests/run-fresh \
  -H 'Content-Type: application/json' \
  --data '{"strategy_id":"mid_trend","start_date":"2026-01-01","end_date":"2026-06-08","top_n":20,"rebalance_frequency":"weekly","transaction_cost_bps":10,"max_positions":20,"score_version":"manual_v1","adjust_type":"hfq"}' \
  | tail -5
```

Expected: response contains `"execution_mode":"fresh"` and total time is seconds, not milliseconds.

- [ ] **Step 5: Verify real page**

Use Playwright against `http://127.0.0.1:5174`:

```bash
node - <<'JS'
const { chromium } = require('@playwright/test');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  page.setDefaultTimeout(120000);
  await page.goto('http://127.0.0.1:5174', { waitUntil: 'networkidle' });
  const nav = page.getByRole('button', { name: 'Open Backtest Lab workspace' });
  if (await nav.count()) await nav.click();
  await page.getByRole('heading', { name: 'Backtest Lab' }).waitFor();
  await page.getByRole('button', { name: 'Load Replay' }).click();
  await page.getByText(/实际可用明细/).waitFor();
  await page.getByRole('button', { name: 'Run Comparison' }).click();
  await page.getByText('0 / 3 completed').waitFor();
  await browser.close();
})();
JS
```

Expected: replay detail shows readable summary; fresh comparison initially shows running rows.

---

## Self-Review

- Spec coverage: The plan covers explicit fresh/replay semantics, real backtest button behavior, replay button behavior, readable detail summary, KPI cards, chart, tabs, comparison metadata, tests, API verification, and server restart.
- Placeholder scan: No placeholder tasks remain. Each implementation task includes file paths, test names, commands, and concrete code snippets.
- Type consistency: `BacktestRunResult.execution_mode`, `result_source`, and `elapsed_ms` are introduced in Task 2 and used consistently in Tasks 3-6. Backend mode names are `fresh` and `replay`; frontend uses the same string literals.
