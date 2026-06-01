import type { ShadowOutcomeRow } from '../api/types';

type ShadowOutcomesPanelProps = {
  rows: ShadowOutcomeRow[];
  isLoading?: boolean;
};

export function ShadowOutcomesPanel({ rows, isLoading = false }: ShadowOutcomesPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Outcomes</h2>
      {isLoading ? (
        <p className="muted">Loading shadow outcomes...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow outcomes for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.shadow_outcome_id}>
              <div>
                <strong>{row.stock_name || row.asset_id}</strong>
                <span>{row.outcome_status}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.shadow_status}</span>
                <span>{row.shadow_layer}</span>
                <span>{row.available_future_bars} bars</span>
              </div>
              <div className="outcome-metrics">
                <span>5D {formatPercent(row.forward_returns['5'])}</span>
                <span>20D {formatPercent(row.forward_returns['20'])}</span>
                <span>20D DD {formatPercent(row.max_low_drawdowns['20'])}</span>
              </div>
              <p>Asset {row.asset_id}</p>
              <p>{row.source_p12_shadow_run_id}</p>
              <p>{row.source_p11_replay_run_id}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function formatPercent(value: number | string | null | undefined) {
  const numericValue = typeof value === 'number' ? value : Number(value);
  if (value === null || value === undefined || !Number.isFinite(numericValue)) {
    return 'n/a';
  }
  const sign = numericValue > 0 ? '+' : '';
  return `${sign}${(numericValue * 100).toFixed(1)}%`;
}
