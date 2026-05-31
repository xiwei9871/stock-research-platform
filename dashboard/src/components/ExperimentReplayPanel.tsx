import type { ExperimentReplayRow } from '../api/types';

type ExperimentReplayPanelProps = {
  rows: ExperimentReplayRow[];
  isLoading?: boolean;
};

export function ExperimentReplayPanel({ rows, isLoading = false }: ExperimentReplayPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Experiment Replay</h2>
      {isLoading ? (
        <p className="muted">Loading experiment replay...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No experiment replay results for selected range.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row analytics-row" key={row.replay_result_id}>
              <div>
                <strong>{row.proposal_id}</strong>
                <span>{row.replay_status}</span>
              </div>
              <div className="outcome-metrics">
                <span>{row.sample_count} samples</span>
                <span>{row.passed_count} pass</span>
                <span>{row.failed_count} fail</span>
              </div>
              <p>{row.source_p10_proposal_run_id}</p>
              <p>{row.source_p9_analytics_run_id}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
