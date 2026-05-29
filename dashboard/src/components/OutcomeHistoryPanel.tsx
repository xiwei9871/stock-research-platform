import type { DecisionOutcomeRow } from '../api/types';

type OutcomeHistoryPanelProps = {
  outcomes: DecisionOutcomeRow[];
};

export function OutcomeHistoryPanel({ outcomes }: OutcomeHistoryPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Outcome History</h2>
      {outcomes.length === 0 ? (
        <p className="muted">No outcome history for selected range.</p>
      ) : (
        <div className="decision-list">
          {outcomes.map((outcome) => (
            <article className="decision-row outcome-row" key={outcome.outcome_event_id}>
              <div>
                <strong>{outcome.decision_label}</strong>
                <span>{outcome.review_date}</span>
              </div>
              <div className="outcome-metrics">
                <span>1D {formatPercent(outcome.forward_returns['1'])}</span>
                <span>5D {formatPercent(outcome.forward_returns['5'])}</span>
                <span>20D {formatPercent(outcome.forward_returns['20'])}</span>
              </div>
              <p>
                {outcome.outcome_status} / {outcome.available_future_bars} future bars
              </p>
            </article>
          ))}
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
