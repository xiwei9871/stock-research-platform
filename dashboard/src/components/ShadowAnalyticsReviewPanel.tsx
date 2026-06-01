import type { ShadowAnalyticsReviewRow } from '../api/types';

type ShadowAnalyticsReviewPanelProps = {
  rows: ShadowAnalyticsReviewRow[];
  isLoading?: boolean;
};

export function ShadowAnalyticsReviewPanel({ rows, isLoading = false }: ShadowAnalyticsReviewPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Analytics Review</h2>
      {isLoading ? (
        <p className="muted">Loading shadow analytics review...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow analytics review rows for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => {
            const twentyDay = row.horizon_metrics['20'] ?? {};
            return (
              <article className="decision-row analytics-row" key={row.review_group_id}>
                <div>
                  <strong>{row.shadow_layer}</strong>
                  <span>{row.shadow_status}</span>
                </div>
                <div className="outcome-metrics">
                  <span>{row.review_status}</span>
                  <span>{row.review_bucket}</span>
                  <span>N {row.sample_count}</span>
                </div>
                <div className="outcome-metrics">
                  <span>Complete {row.complete_count}</span>
                  <span>Insuff {row.insufficient_data_count}</span>
                </div>
                <div className="outcome-metrics">
                  <span>20D {formatPercent(twentyDay.forward_return_mean)}</span>
                  <span>20D DD {formatPercent(twentyDay.max_low_drawdown_worst)}</span>
                </div>
                <p>{row.evidence_summary}</p>
                <p>{row.risk_notes}</p>
                <p>{row.next_research_question}</p>
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
