import type { ShadowReviewDecisionRow } from '../api/types';

type ShadowReviewDecisionsPanelProps = {
  rows: ShadowReviewDecisionRow[];
  isLoading?: boolean;
};

export function ShadowReviewDecisionsPanel({ rows, isLoading = false }: ShadowReviewDecisionsPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Review Decisions</h2>
      {isLoading ? (
        <p className="muted">Loading shadow review decisions...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow review decisions for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.decision_group_id}>
              <div>
                <strong>{row.shadow_layer}</strong>
                <span>{row.shadow_status}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.decision_status}</span>
                <span>{row.decision_bucket}</span>
                <span>N {row.sample_count}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.review_status}</span>
                <span>{row.review_bucket}</span>
              </div>
              <div className="outcome-metrics">
                <span>Complete {row.complete_count}</span>
                <span>Insuff {row.insufficient_data_count}</span>
              </div>
              <p>{row.required_next_action}</p>
              <p>{row.decision_reason}</p>
              <p>{row.evidence_summary}</p>
              <p>{row.risk_notes}</p>
              <p>{row.next_research_question}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
