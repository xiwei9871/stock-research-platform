import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchBacktestStrategies, runBacktest } from '../api/client';
import type {
  BacktestRunRequest,
  BacktestRunResult,
  BacktestScalar,
  BacktestValue,
  StrategyCatalogItem
} from '../api/types';
import { BacktestResultDetail } from './BacktestResultDetail';

const DEFAULT_STRATEGY_ID = 'lhb_shortline';
const DEFAULT_START_DATE = '2026-01-01';
const DEFAULT_END_DATE = '2026-06-18';
const DEFAULT_COMBO_STRATEGY_IDS = new Set(['lhb_shortline', 'mid_trend', 'tech_bottleneck']);

type LHBRiskProfile = 'return_max' | 'balanced' | 'drawdown_control';
type ResultRow = Record<string, BacktestScalar>;
type ComparisonRow = {
  strategyId: string;
  strategyName: string;
  status: 'running' | 'passed' | 'failed';
  result: BacktestRunResult | null;
  error: string | null;
};
type BacktestLabWorkspaceProps = {
  embedded?: boolean;
  defaultEndDate?: string;
  initialStrategyId?: string;
};

function formatValue(value: BacktestScalar | undefined) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return value ?? '-';
}

function asScalar(value: BacktestValue | undefined): BacktestScalar | undefined {
  if (Array.isArray(value) || (value !== null && typeof value === 'object')) {
    return undefined;
  }
  return value;
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

function formatStrategyStatus(status: string) {
  return status.replace(/_/g, '-');
}

function formatPublicationPercent(value: number | null | undefined) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '-';
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function metricValue(result: BacktestRunResult | null, keys: string[]) {
  if (!result) {
    return null;
  }
  for (const key of keys) {
    const value = result.summary[key];
    if (value !== undefined) {
      return asScalar(value);
    }
  }
  return null;
}

function resultExecutionMode(result: BacktestRunResult | null) {
  if (!result) {
    return null;
  }
  if (result.execution_mode) {
    return result.execution_mode;
  }
  return result.read_only === false ? 'fresh' : 'replay';
}

function resultSource(result: BacktestRunResult | null) {
  if (!result) {
    return null;
  }
  return result.result_source ?? metricValue(result, ['result_source', 'evidence_source']);
}

function elapsedSeconds(result: BacktestRunResult | null) {
  if (!result || typeof result.elapsed_ms !== 'number') {
    return null;
  }
  return `${Number((result.elapsed_ms / 1000).toFixed(2))}s`;
}

export function BacktestLabWorkspace({
  embedded = false,
  defaultEndDate = DEFAULT_END_DATE,
  initialStrategyId
}: BacktestLabWorkspaceProps = {}) {
  const [strategies, setStrategies] = useState<StrategyCatalogItem[]>([]);
  const [strategyId, setStrategyId] = useState(DEFAULT_STRATEGY_ID);
  const [startDate, setStartDate] = useState(DEFAULT_START_DATE);
  const [endDate, setEndDate] = useState(defaultEndDate || DEFAULT_END_DATE);
  const [topN, setTopN] = useState(5);
  const [transactionCostBps, setTransactionCostBps] = useState(10);
  const [maxPositions, setMaxPositions] = useState(20);
  const [riskProfile, setRiskProfile] = useState<LHBRiskProfile>('balanced');
  const [result, setResult] = useState<BacktestRunResult | null>(null);
  const [comparisonRows, setComparisonRows] = useState<ComparisonRow[]>([]);
  const [isCatalogLoading, setIsCatalogLoading] = useState(true);
  const [isRunning, setIsRunning] = useState(false);
  const [isComparing, setIsComparing] = useState(false);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [strategySelectionError, setStrategySelectionError] = useState<string | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const mountedRef = useRef(false);
  const catalogRequestIdRef = useRef(0);
  const runRequestIdRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;
    const requestId = catalogRequestIdRef.current + 1;
    catalogRequestIdRef.current = requestId;
    setIsCatalogLoading(true);
    setCatalogError(null);
    setStrategySelectionError(null);
    setStrategies([]);
    setStrategyId('');

    fetchBacktestStrategies()
      .then((rows) => {
        if (!mountedRef.current || catalogRequestIdRef.current !== requestId) {
          return;
        }
        setStrategies(rows);
        const explicitStrategy =
          initialStrategyId === undefined
            ? null
            : rows.find(
                (row) =>
                  row.strategy_id === initialStrategyId &&
                  row.status === 'runnable' &&
                  DEFAULT_COMBO_STRATEGY_IDS.has(row.strategy_id)
              );
        if (initialStrategyId !== undefined && !explicitStrategy) {
          setStrategyId('');
          setStrategySelectionError(`未知策略 ${initialStrategyId}`);
        } else {
          setStrategyId(
            explicitStrategy?.strategy_id ??
              rows.find((row) => row.status === 'runnable' && DEFAULT_COMBO_STRATEGY_IDS.has(row.strategy_id))?.strategy_id ??
              rows.find((row) => row.status === 'runnable')?.strategy_id ??
              rows[0]?.strategy_id ??
              DEFAULT_STRATEGY_ID
          );
        }
        setIsCatalogLoading(false);
      })
      .catch((err: unknown) => {
        if (!mountedRef.current || catalogRequestIdRef.current !== requestId) {
          return;
        }
        setCatalogError(err instanceof Error ? err.message : String(err));
        setIsCatalogLoading(false);
      });

    return () => {
      mountedRef.current = false;
    };
  }, [initialStrategyId]);

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.strategy_id === strategyId) ?? null,
    [strategies, strategyId]
  );
  const runnableStrategies = useMemo(() => strategies.filter((strategy) => strategy.status === 'runnable'), [strategies]);
  const hasValidConfig =
    startDate.trim() !== '' &&
    endDate.trim() !== '' &&
    Number.isInteger(topN) &&
    topN > 0 &&
    Number.isFinite(transactionCostBps) &&
    transactionCostBps >= 0 &&
    Number.isInteger(maxPositions) &&
    maxPositions > 0 &&
    maxPositions <= 100;
  const canRun = selectedStrategy?.status === 'runnable' && hasValidConfig && !isRunning && !isComparing;
  const canCompare =
    !strategySelectionError && runnableStrategies.length > 0 && hasValidConfig && !isRunning && !isComparing;
  const completedComparisonCount = comparisonRows.filter((row) => row.status !== 'running').length;
  const runDisabledReason =
    selectedStrategy && selectedStrategy.status !== 'runnable'
      ? `${selectedStrategy.strategy_name} is ${formatStrategyStatus(
          selectedStrategy.status
        )}. Backtest Lab runs runnable research strategies only. Use Strategy Validation to inspect replay evidence.`
      : null;

  const invalidateRun = () => {
    runRequestIdRef.current += 1;
    setResult(null);
    setComparisonRows([]);
    setRunError(null);
    setIsRunning(false);
    setIsComparing(false);
  };

  const updateStrategyId = (nextStrategyId: string) => {
    setStrategyId(nextStrategyId);
    setStrategySelectionError(null);
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

  const updateTransactionCostBps = (nextTransactionCostBps: number) => {
    setTransactionCostBps(nextTransactionCostBps);
    invalidateRun();
  };

  const updateMaxPositions = (nextMaxPositions: number) => {
    setMaxPositions(nextMaxPositions);
    invalidateRun();
  };

  const updateRiskProfile = (nextRiskProfile: LHBRiskProfile) => {
    setRiskProfile(nextRiskProfile);
    invalidateRun();
  };

  const buildBacktestRequest = (nextStrategyId: string): BacktestRunRequest => ({
    strategy_id: nextStrategyId,
    start_date: startDate,
    end_date: endDate,
    score_version: 'manual_v1',
    top_n: topN,
    transaction_cost_bps: transactionCostBps,
    max_positions: null,
    max_position_weight: maxPositions / 100,
    ...(nextStrategyId === 'lhb_shortline' ? { risk_profile: riskProfile } : {}),
    adjust_type: 'hfq'
  });

  const submitBacktest = () => {
    if (!canRun) {
      return;
    }

    const requestId = runRequestIdRef.current + 1;
    runRequestIdRef.current = requestId;
    setIsRunning(true);
    setRunError(null);
    setResult(null);
    setComparisonRows([]);

    runBacktest(buildBacktestRequest(strategyId))
      .then((payload) => {
        if (!mountedRef.current || runRequestIdRef.current !== requestId) {
          return;
        }
        if (strategyId === 'lhb_shortline' && payload.result_source === 'live_vectorized_backtest') {
          throw new Error(
            `LHB Shortline must run lhb_shortline_v1, but API returned ${payload.result_source ?? 'unknown source'} for ${
              payload.strategy_id
            }.`
          );
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

  const submitComparison = () => {
    if (!canCompare) {
      return;
    }

    const requestId = runRequestIdRef.current + 1;
    runRequestIdRef.current = requestId;
    const initialRows = runnableStrategies.map((strategy) => ({
      strategyId: strategy.strategy_id,
      strategyName: strategy.strategy_name,
      status: 'running' as const,
      result: null,
      error: null
    }));
    setIsComparing(true);
    setRunError(null);
    setResult(null);
    setComparisonRows(initialRows);

    const updateComparisonRow = (nextRow: ComparisonRow) => {
      setComparisonRows((currentRows) =>
        currentRows.map((row) => (row.strategyId === nextRow.strategyId ? nextRow : row))
      );
    };

    const runs = runnableStrategies.map(async (strategy) => {
        try {
          const payload = await runBacktest(buildBacktestRequest(strategy.strategy_id));
          const nextRow = {
            strategyId: strategy.strategy_id,
            strategyName: strategy.strategy_name,
            status: 'passed' as const,
            result: payload,
            error: null
          };
          if (mountedRef.current && runRequestIdRef.current === requestId) {
            updateComparisonRow(nextRow);
          }
          return nextRow;
        } catch (err: unknown) {
          const nextRow = {
            strategyId: strategy.strategy_id,
            strategyName: strategy.strategy_name,
            status: 'failed' as const,
            result: null,
            error: err instanceof Error ? err.message : String(err)
          };
          if (mountedRef.current && runRequestIdRef.current === requestId) {
            updateComparisonRow(nextRow);
          }
          return nextRow;
        }
      });

    Promise.all(runs).then((rows) => {
      if (!mountedRef.current || runRequestIdRef.current !== requestId) {
        return;
      }
      setResult(rows.find((row) => row.status === 'passed')?.result ?? null);
      setIsComparing(false);
    });
  };

  return (
    <section className="backtest-lab-workspace" aria-label="Backtest Lab workspace">
      {embedded ? null : (
        <header className="workspace-header">
          <h1>Backtest Lab</h1>
          <p className="muted">Run validated built-in combo backtests. Custom strategy code is not supported.</p>
        </header>
      )}

      <section className="backtest-controls" aria-label="Backtest controls">
        <label>
          <span>Strategy</span>
          <select aria-label="strategy" value={strategyId} onChange={(event) => updateStrategyId(event.target.value)}>
            {strategyId === '' ? <option value="">未选择策略</option> : null}
            {strategies.length === 0 && strategyId !== '' ? (
              <option value={DEFAULT_STRATEGY_ID}>manual_v1_topn_rotation</option>
            ) : null}
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
        {strategyId === 'lhb_shortline' ? (
          <label>
            <span>Risk Profile</span>
            <select
              aria-label="risk profile"
              value={riskProfile}
              onChange={(event) => updateRiskProfile(event.target.value as LHBRiskProfile)}
            >
              <option value="return_max">收益优先</option>
              <option value="balanced">最佳平衡</option>
              <option value="drawdown_control">回撤优先</option>
            </select>
          </label>
        ) : null}
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
          <span>Max Position %</span>
          <input
            aria-label="max position percent"
            min="1"
            max="100"
            type="number"
            value={maxPositions}
            onChange={(event) => updateMaxPositions(Number(event.target.value))}
          />
        </label>
        <button type="button" disabled={!canRun} onClick={submitBacktest}>
          {isRunning ? 'Running...' : 'Run Backtest'}
        </button>
        <button type="button" disabled={!canCompare} onClick={submitComparison}>
          {isComparing ? 'Comparing...' : 'Run Comparison'}
        </button>
        {runDisabledReason ? <p className="backtest-run-note">{runDisabledReason}</p> : null}
        <p className="backtest-run-note">
          回测会提交为后台任务，页面自动等待结果；耗时较长时可先查看本页保留的最近一次结果。
        </p>
        {isRunning ? (
          <p className="backtest-run-note">
            后台回测任务已提交，正在等待结果返回。请不要重复点击或直接调用同步 run-fresh 接口。
          </p>
        ) : null}
        {result ? (
          <p className="backtest-run-note">最近一次回测结果已保留在本页，修改参数后会清空并重新运行。</p>
        ) : null}
      </section>

      {catalogError ? <p className="error-text">{catalogError}</p> : null}
      {strategySelectionError ? <p role="alert" className="error-text">{strategySelectionError}</p> : null}
      {runError ? <p className="error-text">{runError}</p> : null}

      {selectedStrategy ? (
        <section
          className="workspace-band"
          role="region"
          aria-label={`${selectedStrategy.strategy_name} 正式发布合同`}
          data-strategy-id={selectedStrategy.strategy_id}
        >
          <div className="strategy-metric-grid">
            <div>
              <span>正式合同</span>
              <strong data-testid="strategy-contract-id">{selectedStrategy.latest_metrics?.contract_id ?? '-'}</strong>
            </div>
            <div>
              <span>发布编号</span>
              <strong data-testid="strategy-publish-id">{selectedStrategy.latest_metrics?.publish_id ?? '-'}</strong>
            </div>
            <div>
              <span>产物版本</span>
              <strong>{selectedStrategy.latest_metrics?.artifact_version ?? '-'}</strong>
            </div>
            <div>
              <span>表现日期</span>
              <strong data-testid="strategy-performance-date">
                {selectedStrategy.latest_metrics?.performance_as_of_date ?? selectedStrategy.latest_metrics?.as_of_date ?? '-'}
              </strong>
            </div>
            <div>
              <span>累计收益</span>
              <strong data-testid="strategy-total-return">
                {formatPublicationPercent(selectedStrategy.latest_metrics?.total_return_pct)}
              </strong>
            </div>
            <div>
              <span>校验状态</span>
              <strong>
                {selectedStrategy.latest_metrics?.contract_status === 'success'
                  ? '通过'
                  : selectedStrategy.latest_metrics?.contract_status === 'contract_mismatch'
                    ? '合同不匹配'
                    : '未校验'}
              </strong>
            </div>
          </div>
        </section>
      ) : null}

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
              </article>
            ))}
          </div>
        ) : !isCatalogLoading && !catalogError ? (
          <p className="muted">No backtest strategies available.</p>
        ) : null}
      </section>

      {comparisonRows.length > 0 ? (
        <section className="workspace-band backtest-comparison">
          <div className="section-heading">
            <h2>Strategy Comparison</h2>
            <span className="muted">
              {completedComparisonCount} / {comparisonRows.length} completed
            </span>
          </div>
          <div className="table-scroll">
            <table className="data-table backtest-comparison-table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Status</th>
                  <th>Mode</th>
                  <th>Total Return</th>
                  <th>Max Drawdown</th>
                  <th>Turnover</th>
                  <th>Source</th>
                  <th>Elapsed</th>
                  <th>Error</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {comparisonRows.map((row) => {
                  const isSelectedResult = Boolean(row.result && result?.strategy_id === row.result.strategy_id);
                  return (
                  <tr className={isSelectedResult ? 'selected-row' : undefined} key={row.strategyId}>
                    <td>{row.strategyName}</td>
                    <td>{row.status}</td>
                    <td>{formatValue(resultExecutionMode(row.result))}</td>
                    <td>{formatValue(metricValue(row.result, ['total_return']))}</td>
                    <td>{formatValue(metricValue(row.result, ['max_drawdown']))}</td>
                    <td>{formatValue(metricValue(row.result, ['turnover', 'average_turnover']))}</td>
                    <td>{formatValue(resultSource(row.result))}</td>
                    <td>{formatValue(elapsedSeconds(row.result))}</td>
                    <td>{row.error ?? '-'}</td>
                    <td>
                      {row.result ? (
                        <button
                          type="button"
                          className="inline-button"
                          disabled={isSelectedResult}
                          onClick={() => setResult(row.result)}
                        >
                          {isSelectedResult ? 'Viewing' : 'View'}
                        </button>
                      ) : (
                        '-'
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {result ? (
        <BacktestResultDetail result={result} />
      ) : (
        <section className="workspace-band">
          <h2>Backtest Results</h2>
          <p className="muted">Run a built-in combo strategy to view summary metrics, positions, trades, and equity/drawdown rows.</p>
        </section>
      )}
    </section>
  );
}
