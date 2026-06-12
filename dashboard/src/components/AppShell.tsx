import { useState } from 'react';
import { DataExplorerWorkspace } from './DataExplorerWorkspace';
import { FactorLabWorkspace } from './FactorLabWorkspace';
import { GeneratedReportsWorkspace } from './GeneratedReportsWorkspace';
import { GlobalSearchBox } from './GlobalSearchBox';
import { HomeCockpit } from './HomeCockpit';
import { MarketMonitorWorkspace } from './MarketMonitorWorkspace';
import { NewsWorkspace } from './NewsWorkspace';
import { ResearchReportsWorkspace } from './ResearchReportsWorkspace';
import { StockWorkspace } from './StockWorkspace';
import { StrategyLabWorkspace } from './StrategyLabWorkspace';
import { WatchlistWorkspace } from './WatchlistWorkspace';
import type { GlobalSearchResult } from '../api/types';

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
  const [selectedAssetId, setSelectedAssetId] = useState('000001.SZ');
  const [newsInitialQuery, setNewsInitialQuery] = useState('');
  const [researchReportsInitialQuery, setResearchReportsInitialQuery] = useState('');
  const [generatedReportsInitialQuery, setGeneratedReportsInitialQuery] = useState('');

  function openStockWorkspace(assetId: string) {
    setSelectedAssetId(assetId);
    setWorkspaceMode('stock');
  }

  function openGlobalSearchResult(result: GlobalSearchResult) {
    const { target } = result;
    if (target.workspace === 'stock' && target.asset_id) {
      openStockWorkspace(target.asset_id);
      return;
    }

    if (target.workspace === 'news') {
      setNewsInitialQuery(target.q ?? result.title);
      setWorkspaceMode('news');
      return;
    }

    if (target.workspace === 'researchReports') {
      setResearchReportsInitialQuery(target.q ?? result.title);
      setWorkspaceMode('researchReports');
      return;
    }

    if (target.workspace === 'generatedReports') {
      setGeneratedReportsInitialQuery(target.q ?? result.title);
      setWorkspaceMode('generatedReports');
    }
  }

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
      <div className="platform-main">
        <header className="platform-topbar">
          <GlobalSearchBox onOpenResult={openGlobalSearchResult} />
        </header>
        <section className="platform-workspace">
          {workspaceMode === 'home' ? <HomeCockpit onNavigate={(mode) => setWorkspaceMode(mode)} /> : null}
          {workspaceMode === 'market' ? <MarketMonitorWorkspace /> : null}
          {workspaceMode === 'researchReports' ? (
            <ResearchReportsWorkspace initialQuery={researchReportsInitialQuery} />
          ) : null}
          {workspaceMode === 'stock' ? <StockWorkspace initialAssetId={selectedAssetId} /> : null}
          {workspaceMode === 'watchlist' ? <WatchlistWorkspace onOpenAsset={openStockWorkspace} /> : null}
          {workspaceMode === 'strategyLab' ? <StrategyLabWorkspace /> : null}
          {workspaceMode === 'generatedReports' ? (
            <GeneratedReportsWorkspace initialQuery={generatedReportsInitialQuery} />
          ) : null}
          {workspaceMode === 'data' ? <DataExplorerWorkspace /> : null}
          {workspaceMode === 'factors' ? <FactorLabWorkspace /> : null}
          {workspaceMode === 'news' ? (
            <NewsWorkspace initialQuery={newsInitialQuery} onOpenAsset={openStockWorkspace} />
          ) : null}
        </section>
      </div>
    </main>
  );
}
