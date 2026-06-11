import { useState } from 'react';
import { DataExplorerWorkspace } from './DataExplorerWorkspace';
import { FactorLabWorkspace } from './FactorLabWorkspace';
import { GeneratedReportsWorkspace } from './GeneratedReportsWorkspace';
import { HomeCockpit } from './HomeCockpit';
import { MarketMonitorWorkspace } from './MarketMonitorWorkspace';
import { NewsWorkspace } from './NewsWorkspace';
import { ResearchReportsWorkspace } from './ResearchReportsWorkspace';
import { StockWorkspace } from './StockWorkspace';
import { StrategyLabWorkspace } from './StrategyLabWorkspace';
import { WatchlistWorkspace } from './WatchlistWorkspace';

type WorkspaceMode =
  | 'home'
  | 'market'
  | 'news'
  | 'researchReports'
  | 'stock'
  | 'watchlist'
  | 'factors'
  | 'strategyLab'
  | 'data'
  | 'generatedReports';
type HomeWorkspaceMode = 'data' | 'factors' | 'backtests' | 'strategy' | 'news' | 'reports';

const NAV_ITEMS: Array<{ mode: WorkspaceMode; label: string }> = [
  { mode: 'home', label: 'Home' },
  { mode: 'market', label: 'Market Monitor' },
  { mode: 'news', label: 'News' },
  { mode: 'researchReports', label: 'Research Reports' },
  { mode: 'stock', label: 'Stock Workspace' },
  { mode: 'watchlist', label: 'Watchlist' },
  { mode: 'factors', label: 'Factor Lab' },
  { mode: 'strategyLab', label: 'Strategy Lab' },
  { mode: 'data', label: 'Data Explorer' },
  { mode: 'generatedReports', label: 'Generated Reports' }
];

export function AppShell() {
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>('home');
  const handleHomeNavigate = (mode: HomeWorkspaceMode) => {
    if (mode === 'backtests' || mode === 'strategy') {
      setWorkspaceMode('strategyLab');
      return;
    }
    if (mode === 'reports') {
      setWorkspaceMode('generatedReports');
      return;
    }
    setWorkspaceMode(mode);
  };

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
        {workspaceMode === 'home' ? <HomeCockpit onNavigate={handleHomeNavigate} /> : null}
        {workspaceMode === 'market' ? <MarketMonitorWorkspace /> : null}
        {workspaceMode === 'researchReports' ? <ResearchReportsWorkspace /> : null}
        {workspaceMode === 'stock' ? <StockWorkspace /> : null}
        {workspaceMode === 'watchlist' ? <WatchlistWorkspace /> : null}
        {workspaceMode === 'strategyLab' ? <StrategyLabWorkspace /> : null}
        {workspaceMode === 'generatedReports' ? <GeneratedReportsWorkspace /> : null}
        {workspaceMode === 'data' ? <DataExplorerWorkspace /> : null}
        {workspaceMode === 'factors' ? <FactorLabWorkspace /> : null}
        {workspaceMode === 'news' ? <NewsWorkspace /> : null}
      </section>
    </main>
  );
}
