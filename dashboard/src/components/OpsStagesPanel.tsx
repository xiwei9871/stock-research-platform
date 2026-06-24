import type { OpsStageRow } from '../api/types';

type OpsStagesPanelProps = {
  rows: OpsStageRow[];
  isLoading?: boolean;
};

export function OpsStagesPanel({ rows, isLoading = false }: OpsStagesPanelProps) {
  return (
    <section className="inspector-section">
      <h2>Stage Status</h2>
      {isLoading ? (
        <p className="muted">Loading stage status...</p>
      ) : rows.length === 0 ? (
        <p className="muted">No stage rows available.</p>
      ) : (
        <div className="decision-list">
          {rows.map((row) => (
            <article className="decision-row ops-stage-row" key={`${row.stage}:${row.started_at ?? row.updated_at ?? row.status}`}>
              <div>
                <strong>{row.stage}</strong>
                <span>{row.status}</span>
              </div>
              <p>{row.error_summary ?? row.updated_at ?? row.started_at ?? 'No stage details reported.'}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
