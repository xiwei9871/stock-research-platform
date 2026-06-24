import type { OpsSnapshot, OpsStageRow } from '../api/types';

type OpsSnapshotPanelProps = {
  snapshot: OpsSnapshot | null;
  stages?: OpsStageRow[];
  isLoading?: boolean;
};

export function OpsSnapshotPanel({ snapshot, stages = [], isLoading = false }: OpsSnapshotPanelProps) {
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

  const currentStage = deriveCurrentStage(snapshot, stages);
  const topPreview = snapshot.snapshot_preview.topn_preview[0] ?? null;
  const stockName = typeof topPreview?.stock_name === 'string' ? topPreview.stock_name : 'No preview asset';
  const statusList = [
    `daily ${snapshot.pipeline.daily_status ?? 'n/a'}`,
    `minute5 ${snapshot.pipeline.minute5_status ?? 'n/a'}`,
    `deps ${snapshot.pipeline.deps_status ?? 'n/a'}`
  ].join(' / ');

  return (
    <section className="inspector-section ops-panel">
      <h2>Ops Snapshot</h2>
      <div className="ops-hero-grid">
        <article className={`ops-card ops-card--${snapshot.pipeline.overall_status.toLowerCase()}`}>
          <h3>Workflow</h3>
          <strong>{snapshot.pipeline.overall_status}</strong>
          <p>Current stage: {currentStage ?? 'n/a'}</p>
          <p>Pipeline: {snapshot.pipeline.pipeline_status}</p>
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
          <span className="ops-label">Feeds</span>
          <strong>{statusList}</strong>
        </div>
        <div>
          <span className="ops-label">Published</span>
          <strong>{snapshot.snapshot_preview.published_at ?? snapshot.run_window.last_updated_at ?? 'n/a'}</strong>
        </div>
      </div>
    </section>
  );
}

function deriveCurrentStage(snapshot: OpsSnapshot, stages: OpsStageRow[]) {
  const runningStage = stages.find((stage) => normalizeStatus(stage.status) === 'running');
  if (runningStage) {
    return runningStage.stage;
  }

  const blockedStage = stages.find((stage) => normalizeStatus(stage.status) === 'failed');
  if (blockedStage) {
    return blockedStage.stage;
  }

  if (normalizeStatus(snapshot.pipeline.minute5_status) === 'running') {
    return 'minute5';
  }
  if (normalizeStatus(snapshot.pipeline.daily_status) === 'running') {
    return 'daily';
  }
  if (normalizeStatus(snapshot.pipeline.deps_status) === 'running') {
    return 'deps';
  }

  return stages.at(-1)?.stage ?? null;
}

function normalizeStatus(status: string | null | undefined) {
  return String(status ?? '').trim().toLowerCase();
}
