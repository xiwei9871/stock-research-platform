import { useState } from 'react';
import { BacktestLabWorkspace } from './BacktestLabWorkspace';
import { DataExplorerWorkspace } from './DataExplorerWorkspace';
import { FactorLabWorkspace } from './FactorLabWorkspace';
import { HomeCockpit } from './HomeCockpit';
import { NewsWorkspace } from './NewsWorkspace';
import { ReportsWorkspace } from './ReportsWorkspace';
import { StrategyValidationWorkspace } from './StrategyValidationWorkspace';

type WorkspaceMode = 'home' | 'data' | 'factors' | 'backtests' | 'strategy' | 'news' | 'reports';

const NAV_ITEMS: Array<{ mode: WorkspaceMode; label: string }> = [
  { mode: 'home', label: 'Home' },
  { mode: 'data', label: 'Data Explorer' },
  { mode: 'factors', label: 'Factor Lab' },
  { mode: 'backtests', label: 'Backtest Lab' },
  { mode: 'strategy', label: 'Strategy Validation' },
  { mode: 'news', label: 'News' },
  { mode: 'reports', label: 'Reports' }
];

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
            aria-current={workspaceMode === item.mode ? 'page' : undefined}
            aria-label={`Open ${item.label} workspace`}
            className={workspaceMode === item.mode ? 'active' : ''}
            onClick={() => setWorkspaceMode(item.mode)}
          >
            {item.label}
          </button>
        ))}
      </aside>
      <section className="platform-workspace">
        {workspaceMode === 'home' ? <HomeCockpit onNavigate={setWorkspaceMode} /> : null}
        {workspaceMode === 'data' ? <DataExplorerWorkspace /> : null}
        {workspaceMode === 'factors' ? <FactorLabWorkspace /> : null}
        {workspaceMode === 'backtests' ? <BacktestLabWorkspace /> : null}
        {workspaceMode === 'strategy' ? <StrategyValidationWorkspace /> : null}
        {workspaceMode === 'news' ? <NewsWorkspace /> : null}
        {workspaceMode === 'reports' ? <ReportsWorkspace /> : null}
      </section>
    </main>
  );
}
