import type { ShadowFollowUpRow } from '../api/types';

type ShadowFollowUpQueuePanelProps = {
  rows: ShadowFollowUpRow[];
  isLoading?: boolean;
};

export function ShadowFollowUpQueuePanel({ rows, isLoading = false }: ShadowFollowUpQueuePanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Follow-up Queue</h2>
      {isLoading ? (
        <p className="muted">Loading shadow follow-up queue...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow follow-up queue items for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.follow_up_item_id}>
              <div>
                <strong>{row.shadow_layer}</strong>
                <span>{row.shadow_status}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.follow_up_status}</span>
                <span>{row.priority_bucket}</span>
                <span>N {row.sample_count}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.decision_status}</span>
                <span>{row.decision_bucket}</span>
              </div>
              <div className="outcome-metrics">
                <span>Complete {row.complete_count}</span>
                <span>Insuff {row.insufficient_data_count}</span>
              </div>
              <p>{row.required_input}</p>
              <p>{row.follow_up_reason}</p>
              <p>{row.required_next_action}</p>
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
