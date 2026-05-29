export function App() {
  return (
    <main className="workbench">
      <aside className="sidebar">
        <div className="panel-title">Stock Research</div>
      </aside>
      <section className="workspace">
        <header className="toolbar">
          <input type="date" defaultValue="2026-05-29" aria-label="trade date" />
          <input defaultValue="000001.SZ" aria-label="asset id" />
        </header>
        <section className="chart-panel">Chart loading area</section>
      </section>
      <aside className="inspector">
        <div className="panel-title">Review</div>
      </aside>
    </main>
  );
}
