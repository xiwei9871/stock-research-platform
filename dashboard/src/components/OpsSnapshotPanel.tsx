import type { OpsSnapshot } from '../api/types';

type OpsSnapshotPanelProps = {
  snapshot: OpsSnapshot | null;
  isLoading?: boolean;
};

export function OpsSnapshotPanel({ snapshot, isLoading = false }: OpsSnapshotPanelProps) {
  if (isLoading) {
    return (
      <section className="inspector-section">
        <h2>Ops Snapshot</h2>
        <p className="muted">Loading ops snapshot...</p>
      </section>
    );
  }

  if (!snapshot) {
    return (
      <section className="inspector-section">
        <h2>Ops Snapshot</h2>
        <p className="muted">Ops snapshot unavailable.</p>
      </section>
    );
  }

  const topPreview = snapshot.snapshot_preview.topn_preview[0] ?? null;
  const stockName = typeof topPreview?.stock_name === 'string' ? topPreview.stock_name : 'No preview asset';

  return (
    <section className="inspector-section ops-panel">
      <h2>Ops Snapshot</h2>
      <div className="ops-hero-grid">
        <article className={`ops-card ops-card--${snapshot.pipeline.overall_status.toLowerCase()}`}>
          <h3>Workflow</h3>
          <strong>{snapshot.pipeline.overall_status}</strong>
          <p>Current stage: {snapshot.pipeline.current_stage ?? 'n/a'}</p>
          <p>Progress: {snapshot.pipeline.progress_pct}%</p>
        </article>
        <article className={`ops-card ops-card--${snapshot.intervention.severity.toLowerCase()}`}>
          <h3>Intervention</h3>
          <strong>{snapshot.intervention.needs_intervention ? 'Required' : 'Not required'}</strong>
          <p>{snapshot.intervention.reason_text}</p>
          <p>{snapshot.intervention.suggested_action ?? 'No action required'}</p>
        </article>
      </div>
      <div className="ops-meta-grid">
        <div>
          <span className="ops-label">Readiness</span>
          <strong>{snapshot.readiness.ready_status}</strong>
        </div>
        <div>
          <span className="ops-label">Ready trade date</span>
          <strong>{snapshot.readiness.latest_ready_trade_date ?? 'n/a'}</strong>
        </div>
        <div>
          <span className="ops-label">Preview leader</span>
          <strong>{stockName}</strong>
        </div>
        <div>
          <span className="ops-label">Published</span>
          <strong>{snapshot.snapshot_preview.published_at ?? 'n/a'}</strong>
        </div>
      </div>
    </section>
  );
}
