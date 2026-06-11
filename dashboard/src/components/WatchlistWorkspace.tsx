export function WatchlistWorkspace() {
  return (
    <section className="workspace-stack" aria-label="Watchlist workspace">
      <header className="workspace-header">
        <h1>Watchlist</h1>
        <p className="muted">Research queue view for status, priority, signal, risk, and next action.</p>
      </header>
      <section className="workspace-panel">
        <div className="section-heading">
          <h2>Queue Model</h2>
          <span className="status-chip neutral">read-only foundation</span>
        </div>
        <div className="placeholder-grid">
          <span>Observe</span>
          <span>Candidate</span>
          <span>Holding</span>
          <span>Review</span>
        </div>
      </section>
    </section>
  );
}
