import type { DecisionEventRow } from '../api/types';

type DecisionHistoryPanelProps = {
  decisions: DecisionEventRow[];
};

export function DecisionHistoryPanel({ decisions }: DecisionHistoryPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Decision History</h2>
      {decisions.length === 0 ? (
        <p className="muted">No decision history for selected range.</p>
      ) : (
        <div className="decision-list">
          {decisions.map((decision) => (
            <article className="decision-row" key={decision.event_id}>
              <div>
                <strong>{decision.decision_label}</strong>
                <span>{decision.review_date}</span>
              </div>
              <p>{decision.notes || decision.follow_up_note || decision.evidence_artifact_id}</p>
              {decision.requires_follow_up ? <span className="risk-tag">follow up</span> : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
