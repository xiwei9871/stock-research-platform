import { useState } from 'react';
import { HomeCockpit } from './HomeCockpit';
import { StrategyValidationWorkspace } from './StrategyValidationWorkspace';

type WorkspaceMode = 'home' | 'data' | 'factors' | 'backtests' | 'strategy' | 'reports';

const NAV_ITEMS: Array<{ mode: WorkspaceMode; label: string }> = [
  { mode: 'home', label: 'Home' },
  { mode: 'data', label: 'Data Explorer' },
  { mode: 'factors', label: 'Factor Lab' },
  { mode: 'backtests', label: 'Backtest Lab' },
  { mode: 'strategy', label: 'Strategy Validation' },
  { mode: 'reports', label: 'Reports' }
];

function PlaceholderWorkspace({ title }: { title: string }) {
  return (
    <section className="placeholder-workspace">
      <h1>{title}</h1>
    </section>
  );
}

export function AppShell() {
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('home');

  return (
    <main className="platform-shell">
      <aside className="platform-nav" aria-label="Workspace navigation">
        <div className="panel-title">Stock Research</div>
        {NAV_ITEMS.map((item) => (
          <button
            type="button"
            key={item.mode}
            className={workspaceMode === item.mode ? 'active' : ''}
            onClick={() => setWorkspaceMode(item.mode)}
          >
            {item.label}
          </button>
        ))}
      </aside>
      <section className="platform-workspace">
        {workspaceMode === 'home' ? <HomeCockpit onNavigate={setWorkspaceMode} /> : null}
        {workspaceMode === 'data' ? <PlaceholderWorkspace title="Data Explorer" /> : null}
        {workspaceMode === 'factors' ? <PlaceholderWorkspace title="Factor Lab" /> : null}
        {workspaceMode === 'backtests' ? <PlaceholderWorkspace title="Backtest Lab" /> : null}
        {workspaceMode === 'strategy' ? <StrategyValidationWorkspace /> : null}
        {workspaceMode === 'reports' ? <PlaceholderWorkspace title="Reports" /> : null}
      </section>
    </main>
  );
}
