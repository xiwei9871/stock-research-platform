import type { ShadowOutcomeAnalyticsRow } from '../api/types';

type ShadowOutcomeAnalyticsPanelProps = {
  rows: ShadowOutcomeAnalyticsRow[];
  isLoading?: boolean;
};

export function ShadowOutcomeAnalyticsPanel({ rows, isLoading = false }: ShadowOutcomeAnalyticsPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Outcome Analytics</h2>
      {isLoading ? (
        <p className="muted">Loading shadow outcome analytics...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow outcome analytics for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => {
            const twentyDay = row.horizon_metrics['20'] ?? {};
            return (
              <article className="decision-row analytics-row" key={row.analytics_group_id}>
                <div>
                  <strong>{row.shadow_layer}</strong>
                  <span>{row.shadow_status}</span>
                </div>
                <div className="outcome-metrics">
                  <span>N {row.sample_count}</span>
                  <span>Complete {row.complete_count}</span>
                  <span>Insuff {row.insufficient_data_count}</span>
                </div>
                <div className="outcome-metrics">
                  <span>20D {formatPercent(twentyDay.forward_return_mean)}</span>
                  <span>Win {formatPercent(twentyDay.forward_win_rate)}</span>
                  <span>20D DD {formatPercent(twentyDay.max_low_drawdown_worst)}</span>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'n/a';
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(1)}%`;
}
