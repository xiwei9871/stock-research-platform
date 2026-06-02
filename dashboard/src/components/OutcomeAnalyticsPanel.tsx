import type { OutcomeAnalyticsRow } from '../api/types';

type OutcomeAnalyticsPanelProps = {
  rows: OutcomeAnalyticsRow[];
};

export function OutcomeAnalyticsPanel({ rows }: OutcomeAnalyticsPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Outcome Analytics</h2>
      {rows.length === 0 ? (
        <p className="muted">No outcome analytics for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => {
            const fiveDay = row.horizon_metrics['5'] ?? {};
            return (
              <article className="decision-row analytics-row" key={`${row.run_id}:${row.analytics_level}:${row.group_value}`}>
                <div>
                  <strong>{row.group_value}</strong>
                  <span>{row.analytics_level}</span>
                </div>
                <div className="outcome-metrics">
                  <span>N {row.sample_count}</span>
                  <span>5D {formatPercent(fiveDay.forward_return_mean)}</span>
                  <span>Win {formatPercent(fiveDay.forward_win_rate)}</span>
                </div>
                <p>
                  complete {row.complete_count} / insufficient {row.insufficient_data_count}
                </p>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function formatPercent(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return 'n/a';
  }
  const sign = value > 0 ? '+' : '';
  return `${sign}${(value * 100).toFixed(1)}%`;
}
