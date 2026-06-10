import type { BacktestRunResult, BacktestScalar } from '../api/types';
import { BacktestCharts } from './BacktestCharts';

type ResultRow = Record<string, BacktestScalar>;

type BacktestResultDetailProps = {
  result: BacktestRunResult;
};

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatValue(value: BacktestScalar | undefined) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  return value ?? '-';
}

function formatPercent(value: unknown) {
  const numberValue = asNumber(value);
  if (numberValue === null) {
    return '-';
  }
  const sign = numberValue > 0 ? '+' : '';
  return `${sign}${(numberValue * 100).toFixed(2)}%`;
}

function formatMultiple(value: unknown) {
  const numberValue = asNumber(value);
  return numberValue === null ? '-' : `${Number(numberValue.toFixed(4))}x`;
}

function getMetric(result: BacktestRunResult, keys: string[]) {
  for (const key of keys) {
    const value = result.summary[key];
    if (value !== undefined && value !== null) {
      return value;
    }
  }
  return null;
}

function getLatestEquity(result: BacktestRunResult) {
  for (let index = result.equity_curve.length - 1; index >= 0; index -= 1) {
    const row = result.equity_curve[index];
    const value = row.equity ?? row.account_equity ?? row.final_equity;
    if (asNumber(value) !== null) {
      return value;
    }
  }
  return null;
}

function getResultHeading(result: BacktestRunResult) {
  if (result.execution_mode === 'validated') {
    return 'Validated backtest';
  }
  if (result.execution_mode === 'fresh' || result.read_only === false) {
    return 'Fresh backtest';
  }
  return 'Replay backtest';
}

function getExecutionLabel(result: BacktestRunResult) {
  if (result.execution_mode === 'validated') {
    return 'Validated combo';
  }
  if (result.execution_mode === 'fresh' || result.read_only === false) {
    return 'Fresh execution';
  }
  return 'Replay';
}

function hasRiskMetricCaveat(result: BacktestRunResult) {
  return (
    result.strategy_id === 'lhb_shortline' &&
    (result.summary.detail_source === 'phase16c_rebuilt_cash_account' || result.summary.mark_to_market === false)
  );
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

function resultRowKey(row: ResultRow, index: number) {
  return [
    index,
    row.id,
    row.date,
    row.rebalance_date,
    row.signal_date,
    row.execution_date,
    row.asset_id,
    row.side
  ]
    .filter((value) => value !== undefined && value !== null && value !== '')
    .map(String)
    .join('|');
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
            <tr key={resultRowKey(row, index)}>
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

export function BacktestResultDetail({ result }: BacktestResultDetailProps) {
  const totalReturn = getMetric(result, ['total_return']);
  const finalEquity = getMetric(result, ['final_equity', 'account_final_equity']) ?? getLatestEquity(result);
  const maxDrawdown = getMetric(result, ['max_drawdown', 'account_max_drawdown']);
  const sharpeRatio = getMetric(result, ['sharpe_ratio', 'sharpe']);
  const startDate = getMetric(result, ['start_date']) ?? result.config.start_date;
  const endDate = getMetric(result, ['end_date']) ?? result.config.end_date;
  const actualStartDate = getMetric(result, ['actual_start_date']);
  const actualEndDate = getMetric(result, ['actual_end_date']);
  const source = result.result_source ?? String(getMetric(result, ['evidence_source']) ?? 'strategy result');

  return (
    <section className="workspace-band backtest-results">
      <div className="section-heading">
        <h2>{getResultHeading(result)}</h2>
        <span className="muted">{result.strategy_name}</span>
      </div>

      <section className="backtest-readable-summary" aria-label="Readable backtest summary">
        <div>
          <h3>Result Summary</h3>
          <p>
            {result.strategy_name} returned {formatPercent(totalReturn)} over {String(startDate ?? '-')} to{' '}
            {String(endDate ?? '-')}, with max drawdown {formatPercent(maxDrawdown)} and {result.trades.length} trade rows.
          </p>
        </div>
        <span className="backtest-mode-pill">{getExecutionLabel(result)}</span>
      </section>

      {hasRiskMetricCaveat(result) ? (
        <section className="backtest-risk-caveat" aria-label="Risk metric caveat">
          <strong>Risk metric caveat</strong>
          <p>
            This LHB lifecycle cash replay is not daily marked to market. Interim holding drawdowns, Sharpe, and turnover
            may be understated or unavailable until a daily mark-to-market backtest is wired in.
          </p>
        </section>
      ) : null}

      <div className="backtest-kpi-grid">
        <article>
          <span>Total Return</span>
          <strong>{formatPercent(totalReturn)}</strong>
        </article>
        <article>
          <span>Final Equity</span>
          <strong>{formatMultiple(finalEquity)}</strong>
        </article>
        <article>
          <span>Max Drawdown</span>
          <strong>{formatPercent(maxDrawdown)}</strong>
        </article>
        <article>
          <span>Sharpe</span>
          <strong>{formatValue(sharpeRatio)}</strong>
        </article>
        <article>
          <span>Actual Range</span>
          <strong>
            {String(actualStartDate ?? startDate ?? '-')} / {String(actualEndDate ?? endDate ?? '-')}
          </strong>
        </article>
        <article>
          <span>Source</span>
          <strong>{source}</strong>
        </article>
      </div>

      <section className="backtest-result-section">
        <h3>Equity / Drawdown Chart</h3>
        <BacktestCharts result={result} />
      </section>

      <section className="backtest-result-section">
        <h3>Raw Summary</h3>
        <SummaryTable summary={result.summary} />
      </section>

      <section className="backtest-result-section">
        <h3>Positions</h3>
        <ResultTable rows={result.positions} emptyText="No positions returned." />
      </section>

      <section className="backtest-result-section">
        <h3>Trades</h3>
        <ResultTable rows={result.trades} emptyText="No trades returned." />
      </section>

      <section className="backtest-result-section">
        <h3>Equity / Drawdown Rows</h3>
        <ResultTable rows={result.equity_curve} emptyText="No equity curve returned." />
      </section>
    </section>
  );
}
