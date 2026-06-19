import type { BacktestRunResult, BacktestScalar, BacktestValue } from '../api/types';
import { BacktestCharts } from './BacktestCharts';

type ResultRow = Record<string, BacktestScalar>;

type BacktestResultDetailProps = {
  result: BacktestRunResult;
};

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false';
  }
  if (Array.isArray(value) || (value !== null && typeof value === 'object')) {
    return JSON.stringify(value);
  }
  return value === undefined || value === null ? '-' : String(value);
}

function formatPercent(value: unknown) {
  const numberValue = asNumber(value);
  if (numberValue === null) {
    return '-';
  }
  const sign = numberValue > 0 ? '+' : '';
  return `${sign}${(numberValue * 100).toFixed(2)}%`;
}

function formatUnsignedPercent(value: unknown) {
  const numberValue = asNumber(value);
  return numberValue === null ? '-' : `${(numberValue * 100).toFixed(2)}%`;
}

function formatWeight(value: unknown) {
  const numberValue = asNumber(value);
  if (numberValue === null) {
    return '-';
  }
  return Math.abs(numberValue) <= 1 ? formatUnsignedPercent(numberValue) : formatValue(numberValue);
}

function formatSignedWeight(value: unknown) {
  const numberValue = asNumber(value);
  if (numberValue === null) {
    return '-';
  }
  if (Math.abs(numberValue) <= 1) {
    const sign = numberValue > 0 ? '+' : '';
    return `${sign}${(numberValue * 100).toFixed(2)}%`;
  }
  return formatValue(numberValue);
}

function formatMultiple(value: unknown) {
  const numberValue = asNumber(value);
  return numberValue === null ? '-' : `${Number(numberValue.toFixed(4))}x`;
}

function formatInteger(value: unknown) {
  const numberValue = asNumber(value);
  return numberValue === null ? '-' : String(Math.round(numberValue));
}

function formatBps(value: unknown) {
  const numberValue = asNumber(value);
  return numberValue === null ? '-' : `${Number(numberValue.toFixed(2))} bps`;
}

function formatSeconds(value: unknown) {
  const numberValue = asNumber(value);
  return numberValue === null ? '-' : `${Number((numberValue / 1000).toFixed(1))}s`;
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

function asRecord(value: unknown): Record<string, BacktestValue> | null {
  if (value === null || Array.isArray(value) || typeof value !== 'object') {
    return null;
  }
  return value as Record<string, BacktestValue>;
}

function getFirstValue(row: ResultRow, keys: string[]) {
  for (const key of keys) {
    const value = row[key];
    if (value !== undefined && value !== null && value !== '') {
      return value;
    }
  }
  return null;
}

const EXIT_REASON_LABELS: Record<string, string> = {
  intraday_high_near_limit_but_failed_close_below_vwap: '冲高接近涨停后回落，收盘跌破均价',
  close_below_vwap_after_intraday_fade: '盘中走弱，价格跌破均价',
  close_below_entry_price_after_t1: 'T+1 后跌破买入价',
  no_lifecycle_exit_signal_before_max_hold: '未触发风控信号，到期卖出',
  target_reached: '达到止盈目标',
  take_profit: '达到止盈目标',
  max_hold_days: '达到最长持有天数',
  max_hold_exit: '达到最长持有天数',
  signal_exit: '触发卖出信号',
  break_entry_price: '跌破买入价',
  limit_break_failed: '冲板失败后回落',
  vwap_break_with_distribution: '跌破均价并放量走弱',
  not_filled: '未成交',
  no_exit_data: '缺少卖出数据',
  no_post_entry_bars: '买入后缺少行情数据',
  locked_limit_down: '跌停无法卖出',
  normal_exit: '常规卖出'
};

const REBALANCE_REASON_LABELS: Record<string, string> = {
  rebalance: '定期调仓',
  risk_exit: '风险退出',
  rank_exit: '排名退出',
  buy: '买入',
  sell: '卖出'
};

const SIDE_LABELS: Record<string, string> = {
  buy: '买入',
  sell: '卖出',
  hold: '持有'
};

function formatExitReason(value: unknown) {
  if (value === undefined || value === null || value === '') {
    return { label: '-', title: undefined };
  }
  const raw = String(value);
  const parts = raw
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
  const labels = parts.map((part) => EXIT_REASON_LABELS[part] ?? '其他卖出原因');
  return {
    label: labels.length > 0 ? Array.from(new Set(labels)).join('，') : '其他卖出原因',
    title: raw
  };
}

function formatRebalanceReason(value: unknown) {
  if (value === undefined || value === null || value === '') {
    return { label: '-', title: undefined };
  }
  const raw = String(value);
  const label = REBALANCE_REASON_LABELS[raw] ?? raw;
  return { label, title: label === raw ? undefined : raw };
}

function formatSide(value: unknown) {
  if (value === undefined || value === null || value === '') {
    return '-';
  }
  const raw = String(value);
  return SIDE_LABELS[raw] ?? raw;
}

function hasRebalanceTradeShape(rows: ResultRow[]) {
  return rows.some(
    (row) =>
      getFirstValue(row, ['side']) !== null &&
      (getFirstValue(row, ['previous_weight', 'target_weight', 'delta_weight', 'turnover_contribution']) !== null ||
        getFirstValue(row, ['reason']) !== null)
  );
}

function getDeltaWeight(row: ResultRow) {
  const explicitDelta = getFirstValue(row, ['delta_weight']);
  if (explicitDelta !== null) {
    return explicitDelta;
  }
  const previousWeight = asNumber(getFirstValue(row, ['previous_weight']));
  const targetWeight = asNumber(getFirstValue(row, ['target_weight', 'weight']));
  if (previousWeight === null || targetWeight === null) {
    return null;
  }
  return targetWeight - previousWeight;
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

function TradeLedgerTable({ positions, trades }: { positions: ResultRow[]; trades: ResultRow[] }) {
  if (trades.length === 0 && positions.length === 0) {
    return <p className="muted">No trades or positions returned.</p>;
  }

  const rows = trades.length > 0 ? trades : positions;
  if (hasRebalanceTradeShape(rows)) {
    return <RebalanceTradeTable rows={rows} />;
  }

  return (
    <div className="table-scroll">
      <table className="data-table backtest-result-table">
        <thead>
          <tr>
            <th>Signal Date</th>
            <th>Stock</th>
            <th>Entry Date</th>
            <th>Entry Time</th>
            <th>Entry Price</th>
            <th>Exit Date</th>
            <th>Exit Time</th>
            <th>Exit Price</th>
            <th>Position</th>
            <th>Return</th>
            <th>Exit Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const asset = getFirstValue(row, ['asset_id', 'ts_code', 'symbol', 'stock_code', 'code']);
            const exitReason = formatExitReason(getFirstValue(row, ['exit_reason', 'exit_signal', 'exit_status', 'skip_reason']));
            return (
              <tr key={resultRowKey(row, index)}>
                <td>{formatValue(getFirstValue(row, ['signal_date', 'trade_date', 'date']))}</td>
                <td>{formatValue(asset)}</td>
                <td>{formatValue(getFirstValue(row, ['entry_trade_date', 'entry_date', 'execution_date']))}</td>
                <td>{formatValue(getFirstValue(row, ['entry_time']))}</td>
                <td>{formatValue(getFirstValue(row, ['entry_price', 'execution_price', 'price']))}</td>
                <td>{formatValue(getFirstValue(row, ['exit_trade_date', 'exit_date']))}</td>
                <td>{formatValue(getFirstValue(row, ['exit_time']))}</td>
                <td>{formatValue(getFirstValue(row, ['exit_price']))}</td>
                <td>{formatWeight(getFirstValue(row, ['position_notional', 'position_weight', 'weight', 'target_weight', 'notional_pct']))}</td>
                <td>{formatPercent(getFirstValue(row, ['return', 'trade_return', 'pnl_pct', 'realized_return']))}</td>
                <td title={exitReason.title}>{exitReason.label}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RebalanceTradeTable({ rows }: { rows: ResultRow[] }) {
  return (
    <div className="table-scroll">
      <table className="data-table backtest-result-table">
        <thead>
          <tr>
            <th>Trade Date</th>
            <th>Stock</th>
            <th>Side</th>
            <th>Previous Weight</th>
            <th>Target Weight</th>
            <th>Delta Weight</th>
            <th>Turnover</th>
            <th>Cost</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => {
            const reason = formatRebalanceReason(getFirstValue(row, ['reason', 'exit_reason']));
            return (
              <tr key={resultRowKey(row, index)}>
                <td>{formatValue(getFirstValue(row, ['trade_date', 'rebalance_date', 'date']))}</td>
                <td>{formatValue(getFirstValue(row, ['asset_id', 'ts_code', 'symbol', 'stock_code', 'code']))}</td>
                <td>{formatSide(getFirstValue(row, ['side']))}</td>
                <td>{formatWeight(getFirstValue(row, ['previous_weight']))}</td>
                <td>{formatWeight(getFirstValue(row, ['target_weight', 'weight']))}</td>
                <td>{formatSignedWeight(getDeltaWeight(row))}</td>
                <td>{formatWeight(getFirstValue(row, ['turnover_contribution', 'turnover']))}</td>
                <td>{formatValue(getFirstValue(row, ['transaction_cost', 'cost']))}</td>
                <td title={reason.title}>{reason.label}</td>
              </tr>
            );
          })}
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
  const hasSharpeRatio = asNumber(sharpeRatio) !== null;
  const startDate = getMetric(result, ['start_date']) ?? result.config.start_date;
  const endDate = getMetric(result, ['end_date']) ?? result.config.end_date;
  const actualStartDate = getMetric(result, ['actual_start_date']);
  const actualEndDate = getMetric(result, ['actual_end_date']);
  const filledTradeCount = getMetric(result, ['filled_trade_count', 'closed_trade_count', 'trade_rows']);
  const winRate = getMetric(result, ['win_rate']);
  const avgTradeReturn = getMetric(result, ['avg_trade_return']);
  const topN = getMetric(result, ['top_n', 'phase18c_top_n']) ?? result.config.top_n;
  const positionPct = getMetric(result, ['position_pct', 'max_position_weight']) ?? result.config.max_position_weight;
  const maxHoldings = getMetric(result, ['phase18c_max_positions']) ?? result.config.max_positions ?? topN;
  const transactionCostBps = getMetric(result, ['transaction_cost_bps']) ?? result.config.transaction_cost_bps;
  const elapsedMs = result.elapsed_ms ?? getMetric(result, ['elapsed_ms']);
  const riskProfileLabel = getMetric(result, ['risk_profile_label']);

  return (
    <section className="workspace-band backtest-results">
      <div className="section-heading">
        <h2>{getResultHeading(result)}</h2>
        <span className="muted">
          {result.strategy_name} ({result.strategy_id})
        </span>
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

      <section className="backtest-result-section">
        <h3>Performance</h3>
        <div className="backtest-kpi-grid">
          <article>
            <span>Final Equity</span>
            <strong>{formatMultiple(finalEquity)}</strong>
          </article>
          <article>
            <span>Total Return</span>
            <strong>{formatPercent(totalReturn)}</strong>
          </article>
          <article>
            <span>Max Drawdown</span>
            <strong>{formatPercent(maxDrawdown)}</strong>
          </article>
          <article>
            <span>Win Rate</span>
            <strong>{formatPercent(winRate)}</strong>
          </article>
          <article>
            <span>Trades</span>
            <strong>{formatInteger(filledTradeCount)}</strong>
          </article>
          <article>
            <span>Avg Trade Return</span>
            <strong>{formatPercent(avgTradeReturn)}</strong>
          </article>
          <article>
            <span>Actual Range</span>
            <strong>
              {String(actualStartDate ?? startDate ?? '-')} / {String(actualEndDate ?? endDate ?? '-')}
            </strong>
          </article>
          {hasSharpeRatio ? (
            <article>
              <span>Sharpe</span>
              <strong>{formatValue(sharpeRatio)}</strong>
            </article>
          ) : null}
        </div>
      </section>

      <section className="backtest-result-section">
        <h3>Strategy Setup</h3>
        <div className="backtest-kpi-grid">
          <article>
            <span>Strategy</span>
            <strong>{result.strategy_id}</strong>
          </article>
          <article>
            <span>Top N</span>
            <strong>{formatValue(topN)}</strong>
          </article>
          <article>
            <span>Max Weight Per Stock</span>
            <strong>{formatUnsignedPercent(positionPct)}</strong>
          </article>
          <article>
            <span>Max Holdings</span>
            <strong>{formatValue(maxHoldings)}</strong>
          </article>
          {riskProfileLabel ? (
            <article>
              <span>Risk Profile</span>
              <strong>{formatValue(riskProfileLabel)}</strong>
            </article>
          ) : null}
          <article>
            <span>Cost</span>
            <strong>{formatBps(transactionCostBps)}</strong>
          </article>
          <article>
            <span>Runtime</span>
            <strong>{formatSeconds(elapsedMs)}</strong>
          </article>
        </div>
      </section>

      <section className="backtest-result-section">
        <h3>Equity / Drawdown Chart</h3>
        <BacktestCharts result={result} />
      </section>

      <details className="backtest-result-section backtest-technical-details">
        <summary>Technical Details</summary>
        <strong>Summary</strong>
        <SummaryTable summary={result.summary} />
        <strong>Raw Positions</strong>
        <ResultTable rows={result.positions} emptyText="No positions returned." />
        <strong>Raw Trades</strong>
        <ResultTable rows={result.trades} emptyText="No trades returned." />
        <strong>Raw Equity Curve</strong>
        <ResultTable rows={result.equity_curve} emptyText="No equity curve returned." />
      </details>

      <section className="backtest-result-section">
        <h3>{hasRebalanceTradeShape(result.trades) ? 'Rebalance Trades' : 'Completed Trades'}</h3>
        <TradeLedgerTable positions={result.positions} trades={result.trades} />
      </section>
    </section>
  );
}
