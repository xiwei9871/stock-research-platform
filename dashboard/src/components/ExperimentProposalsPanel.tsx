import type { ExperimentProposalRow } from '../api/types';

type ExperimentProposalsPanelProps = {
  rows: ExperimentProposalRow[];
};

export function ExperimentProposalsPanel({ rows }: ExperimentProposalsPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Experiment Proposals</h2>
      {rows.length === 0 ? (
        <p className="muted">No experiment proposals for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.proposal_id}>
              <div>
                <strong>{row.proposal_title}</strong>
                <span>{row.status}</span>
              </div>
              <p>{row.hypothesis}</p>
              <div className="outcome-metrics">
                <span>{row.review_date}</span>
                <span>{row.reviewer_id}</span>
              </div>
              <p>{row.source_p9_analytics_run_id}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
