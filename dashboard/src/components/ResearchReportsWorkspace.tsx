export function ResearchReportsWorkspace() {
  return (
    <section className="workspace-stack" aria-label="Research Reports workspace">
      <header className="workspace-header">
        <h1>Research Reports</h1>
        <p className="muted">External broker and institution reports will be stock-first in Phase 3.</p>
      </header>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Planned Search Model</h2>
          <span className="status-chip neutral">stock-first</span>
        </div>
        <div className="placeholder-grid">
          <span>Stock code/name</span>
          <span>Institution</span>
          <span>Rating action</span>
          <span>Date range</span>
        </div>
      </section>
    </section>
  );
}
