import type { ShadowFollowUpResolutionRow } from '../api/types';

type ShadowFollowUpResolutionPanelProps = {
  rows: ShadowFollowUpResolutionRow[];
  isLoading?: boolean;
};

export function ShadowFollowUpResolutionPanel({
  rows,
  isLoading = false
}: ShadowFollowUpResolutionPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Shadow Follow-up Resolution</h2>
      {isLoading ? (
        <p className="muted">Loading shadow follow-up resolution...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No shadow follow-up resolution items for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.resolution_item_id}>
              <div>
                <strong>{row.shadow_layer}</strong>
                <span>{row.shadow_status}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.resolution_status}</span>
                <span>{row.resolution_bucket}</span>
                <span>{row.priority_bucket}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.follow_up_status}</span>
                <span>N {row.sample_count}</span>
              </div>
              <div className="outcome-metrics">
                <span>Complete {row.complete_count}</span>
                <span>Insuff {row.insufficient_data_count}</span>
              </div>
              <p>{row.recommended_resolution_action}</p>
              <p>{row.resolution_reason}</p>
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
