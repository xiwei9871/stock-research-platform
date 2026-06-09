import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchBacktestStrategies, runBacktest } from '../api/client';
import type { BacktestRunResult, StrategyCatalogItem } from '../api/types';

const DEFAULT_STRATEGY_ID = 'manual_v1_topn_rotation';
const DEFAULT_START_DATE = '2026-01-01';
const DEFAULT_END_DATE = '2026-06-08';

type RebalanceFrequency = 'daily' | 'weekly';
type ResultRow = Record<string, number | string | null>;

function formatValue(value: number | string | null | undefined) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  }
  return value ?? '-';
}

function getStrategyInputs(strategy: StrategyCatalogItem) {
  const groups = strategy.factor_groups.length > 0 ? strategy.factor_groups.join(', ') : '';
  const signals = strategy.signal_inputs.length > 0 ? strategy.signal_inputs.join(', ') : '';
  if (groups && signals) {
    return `${groups} | ${signals}`;
  }
  return groups || signals || 'No factor groups or signal inputs listed';
}

function getTableColumns(rows: ResultRow[]) {
  const columns: string[] = [];
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!columns.includes(key)) {
        columns.push(key);
      }
    });
  });
  return columns;
}

function ResultTable({ emptyText, rows }: { emptyText: string; rows: ResultRow[] }) {
  const columns = getTableColumns(rows);

  if (rows.length === 0 || columns.length === 0) {
    return <p className="muted">{emptyText}</p>;
  }

  return (
    <div className="table-scroll">
      <table className="data-table backtest-result-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={String(row.id ?? row.date ?? row.asset_id ?? index)}>
              {columns.map((column) => (
                <td key={column}>{formatValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryTable({ summary }: { summary: BacktestRunResult['summary'] }) {
  const entries = Object.entries(summary);

  if (entries.length === 0) {
    return <p className="muted">No summary metrics returned.</p>;
  }

  return (
    <div className="table-scroll">
      <table className="data-table backtest-summary-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, value]) => (
            <tr key={key}>
              <td>{key}</td>
              <td>{formatValue(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BacktestLabWorkspace() {
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [strategyId, setStrategyId] = useState(DEFAULT_STRATEGY_ID);
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(DEFAULT_END_DATE);
  const [topN, setTopN] = useState(20);
  const [rebalanceFrequency, setRebalanceFrequency] = useState<RebalanceFrequency>('weekly');
  const [transactionCostBps, setTransactionCostBps] = useState(10);
  const [maxPositions, setMaxPositions] = useState(20);
  const [result, setResult] = useState<BacktestRunResult | null>(null);
  const [isCatalogLoading, setIsCatalogLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const runRequestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    setIsCatalogLoading(true);
    setCatalogError(null);

    fetchBacktestStrategies()
      .then((rows) => {
        if (!mountedRef.current) {
          return;
        }
        setStrategies(rows);
        setStrategyId(rows.find((row) => row.status === 'runnable')?.strategy_id ?? rows[0]?.strategy_id ?? DEFAULT_STRATEGY_ID);
        setIsCatalogLoading(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current) {
          return;
        }
        setCatalogError(err instanceof Error ? err.message : String(err));
        setIsCatalogLoading(false);
      });

    return () => {
      mountedRef.current = false;
    };
  }, []);

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.strategy_id === strategyId) ?? null,
    [strategies, strategyId]
  );
  const hasValidConfig =
    startDate.trim() !== '' &&
    endDate.trim() !== '' &&
    Number.isInteger(topN) &&
    topN > 0 &&
    Number.isFinite(transactionCostBps) &&
    transactionCostBps >= 0 &&
    Number.isInteger(maxPositions) &&
    maxPositions > 0 &&
    (rebalanceFrequency === 'daily' || rebalanceFrequency === 'weekly');
  const canRun = selectedStrategy?.status === 'runnable' && hasValidConfig && !isRunning;

  const invalidateRun = () => {
    runRequestIdRef.current += 1;
    setResult(null);
    setRunError(null);
    setIsRunning(false);
  };

  const updateStrategyId = (nextStrategyId: string) => {
    setStrategyId(nextStrategyId);
    invalidateRun();
  };

  const updateStartDate = (nextStartDate: string) => {
    setStartDate(nextStartDate);
    invalidateRun();
  };

  const updateEndDate = (nextEndDate: string) => {
    setEndDate(nextEndDate);
    invalidateRun();
  };

  const updateTopN = (nextTopN: number) => {
    setTopN(nextTopN);
    invalidateRun();
  };

  const updateRebalanceFrequency = (nextRebalanceFrequency: RebalanceFrequency) => {
    setRebalanceFrequency(nextRebalanceFrequency);
    invalidateRun();
  };

  const updateTransactionCostBps = (nextTransactionCostBps: number) => {
    setTransactionCostBps(nextTransactionCostBps);
    invalidateRun();
  };

  const updateMaxPositions = (nextMaxPositions: number) => {
    setMaxPositions(nextMaxPositions);
    invalidateRun();
  };

  const submitBacktest = () => {
    if (!canRun) {
      return;
    }

    const requestId = runRequestIdRef.current + 1;
    runRequestIdRef.current = requestId;
    setIsRunning(true);
    setRunError(null);
    setResult(null);

    runBacktest({
      strategy_id: strategyId,
      start_date: startDate,
      end_date: endDate,
      score_version: 'manual_v1',
      top_n: topN,
      rebalance_frequency: rebalanceFrequency,
      transaction_cost_bps: transactionCostBps,
      max_positions: maxPositions,
      adjust_type: 'hfq'
    })
      .then((payload) => {
        if (!mountedRef.current || runRequestIdRef.current !== requestId) {
          return;
        }
        setResult(payload);
        setIsRunning(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || runRequestIdRef.current !== requestId) {
          return;
        }
        setRunError(err instanceof Error ? err.message : String(err));
        setIsRunning(false);
      });
  };

  return (
    <section className="backtest-lab-workspace" aria-label="Backtest Lab workspace">
      <header className="workspace-header">
        <h1>Backtest Lab</h1>
        <p className="muted">
          Run built-in read-only strategy backtests. Custom strategy code is not supported.
        </p>
      </header>

      <section className="backtest-controls" aria-label="Backtest controls">
        <label>
          <span>Strategy</span>
          <select aria-label="strategy" value={strategyId} onChange={(event) => updateStrategyId(event.target.value)}>
            {strategies.length === 0 ? <option value={DEFAULT_STRATEGY_ID}>manual_v1_topn_rotation</option> : null}
            {strategies.map((strategy) => (
              <option key={strategy.strategy_id} value={strategy.strategy_id}>
                {strategy.strategy_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span>Start Date</span>
          <input
            aria-label="start date"
            type="date"
            value={startDate}
            onChange={(event) => updateStartDate(event.target.value)}
          />
        </label>
        <label>
          <span>End Date</span>
          <input aria-label="end date" type="date" value={endDate} onChange={(event) => updateEndDate(event.target.value)} />
        </label>
        <label>
          <span>Top N</span>
          <input
            aria-label="top n"
            min="1"
            type="number"
            value={topN}
            onChange={(event) => updateTopN(Number(event.target.value))}
          />
        </label>
        <label>
          <span>Rebalance</span>
          <select
            aria-label="rebalance frequency"
            value={rebalanceFrequency}
            onChange={(event) => updateRebalanceFrequency(event.target.value === 'daily' ? 'daily' : 'weekly')}
          >
            <option value="weekly">weekly</option>
            <option value="daily">daily</option>
          </select>
        </label>
        <label>
          <span>Cost Bps</span>
          <input
            aria-label="transaction cost bps"
            min="0"
            type="number"
            value={transactionCostBps}
            onChange={(event) => updateTransactionCostBps(Number(event.target.value))}
          />
        </label>
        <label>
          <span>Max Positions</span>
          <input
            aria-label="max positions"
            min="1"
            type="number"
            value={maxPositions}
            onChange={(event) => updateMaxPositions(Number(event.target.value))}
          />
        </label>
        <button type="button" disabled={!canRun} onClick={submitBacktest}>
          {isRunning ? 'Running...' : 'Run Backtest'}
        </button>
      </section>

      {catalogError ? <p className="error-text">{catalogError}</p> : null}
      {runError ? <p className="error-text">{runError}</p> : null}

      <section className="workspace-band">
        <div className="section-heading">
          <h2>Strategy Catalog</h2>
          {isCatalogLoading ? <span className="muted">Loading strategies...</span> : null}
        </div>
        {strategies.length > 0 ? (
          <div className="backtest-catalog">
            {strategies.map((strategy) => (
              <article className="backtest-catalog-row" key={strategy.strategy_id}>
                <div>
                  <strong>{strategy.strategy_name}</strong>
                  <p>{strategy.description}</p>
                  <small>{getStrategyInputs(strategy)}</small>
                </div>
                <div className="backtest-catalog-meta">
                  <span>{strategy.status}</span>
                  <small>{strategy.primary_action}</small>
                  {strategy.latest_evidence ? <small>{strategy.latest_evidence}</small> : null}
                </div>
              </article>
            ))}
          </div>
        ) : !isCatalogLoading && !catalogError ? (
          <p className="muted">No backtest strategies available.</p>
        ) : null}
      </section>

      {result ? (
        <section className="workspace-band backtest-results">
          <div className="section-heading">
            <h2>Read-only backtest</h2>
            <span className="muted">{result.strategy_name}</span>
          </div>
          <SummaryTable summary={result.summary} />

          <section className="backtest-result-section">
            <h3>Positions</h3>
            <ResultTable rows={result.positions} emptyText="No positions returned." />
          </section>

          <section className="backtest-result-section">
            <h3>Trades</h3>
            <ResultTable rows={result.trades} emptyText="No trades returned." />
          </section>

          <section className="backtest-result-section">
            <h3>Equity / Drawdown</h3>
            <ResultTable rows={result.equity_curve} emptyText="No equity curve returned." />
          </section>
        </section>
      ) : (
        <section className="workspace-band">
          <h2>Backtest Results</h2>
          <p className="muted">Run a runnable built-in strategy to view summary metrics, positions, trades, and equity/drawdown rows.</p>
        </section>
      )}
    </section>
  );
}
