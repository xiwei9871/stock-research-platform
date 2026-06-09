import type { StrategyPositionSnapshot } from '../api/types';

type StrategyPortfolioRiskPanelProps = {
  rows: StrategyPositionSnapshot[];
};

function formatValue(value: number | null) {
  return value === null ? '-' : value.toFixed(2);
}

export function StrategyPortfolioRiskPanel({ rows }: StrategyPortfolioRiskPanelProps) {
  if (rows.length === 0) {
    return <p className="muted">No position snapshots for this run.</p>;
  }

  return (
    <div className="strategy-card-grid">
      {rows.map((row) => (
        <div className="strategy-summary-card" key={`${row.run_id}-${row.asset_id}-${row.trade_date}`}>
          <strong>{row.asset_id}</strong>
          <span>Exposure {formatValue(row.exposure)}</span>
          <span>Position {formatValue(row.position_weight)}</span>
          <span>Cash {formatValue(row.cash_weight)}</span>
          {row.suppression_reason ? <small>{row.suppression_reason}</small> : <small>No suppression</small>}
        </div>
      ))}
    </div>
  );
}
