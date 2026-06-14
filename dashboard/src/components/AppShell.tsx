import { useState } from 'react';
import { DataExplorerWorkspace } from './DataExplorerWorkspace';
import { FactorLabWorkspace } from './FactorLabWorkspace';
import { GeneratedReportsWorkspace } from './GeneratedReportsWorkspace';
import { GlobalSearchBox } from './GlobalSearchBox';
import { HomeCockpit } from './HomeCockpit';
import { MarketMonitorWorkspace } from './MarketMonitorWorkspace';
import { NewsWorkspace } from './NewsWorkspace';
import { ResearchReportsWorkspace } from './ResearchReportsWorkspace';
import { StockWorkspace, type StockEntryContext } from './StockWorkspace';
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

type MarketMonitorTab = 'auction' | 'limit_up' | 'broken_limit_up' | 'limit_down';

type WorkspaceHandoff = {
  query: string;
  tradeDate?: string;
  newsId?: string;
  assetId?: string;
  eventKey?: string;
  reportId?: string;
  path?: string;
  monitorTab?: MarketMonitorTab;
  version: number;
};

type StockSourceWorkspace = NonNullable<StockEntryContext['sourceWorkspace']>;

type StockHandoff = {
  assetId?: string;
  sourceWorkspace?: StockSourceWorkspace;
  query?: string;
  matchReason?: string;
  newsId?: string;
  eventKey?: string;
  reportId?: string;
  tradeDate?: string;
  monitorTab?: MarketMonitorTab;
  version: number;
};

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
  const [newsHandoff, setNewsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [researchReportsHandoff, setResearchReportsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [generatedReportsHandoff, setGeneratedReportsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [marketHandoff, setMarketHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [stockHandoff, setStockHandoff] = useState<StockHandoff>({ version: 0 });

  function openStockWorkspace(assetId: string, context: Omit<StockHandoff, 'assetId' | 'version'> = {}) {
    setSelectedAssetId(assetId);
    setStockHandoff((current) => ({
      ...context,
      assetId,
      version: current.version + 1
    }));
    setWorkspaceMode('stock');
  }

  function openWorkspaceMode(mode: WorkspaceMode) {
    if (mode === 'stock') {
      openStockWorkspace(selectedAssetId);
      return;
    }
    setWorkspaceMode(mode);
  }

  function openNewsWorkspaceFromStock(context: StockEntryContext) {
    setNewsHandoff((current) => ({
      query: context.query ?? context.assetId ?? selectedAssetId,
      newsId: context.newsId,
      assetId: context.assetId ?? selectedAssetId,
      version: current.version + 1
    }));
    setWorkspaceMode('news');
  }

  function openResearchReportsWorkspaceFromStock(context: StockEntryContext) {
    setResearchReportsHandoff((current) => ({
      query: context.query ?? context.assetId ?? selectedAssetId,
      eventKey: context.eventKey,
      reportId: context.reportId,
      assetId: context.assetId ?? selectedAssetId,
      version: current.version + 1
    }));
    setWorkspaceMode('researchReports');
  }

  function openMarketMonitorWorkspaceFromStock(context: StockEntryContext) {
    setMarketHandoff((current) => ({
      query: context.query ?? context.assetId ?? selectedAssetId,
      assetId: context.assetId ?? selectedAssetId,
      tradeDate: context.tradeDate,
      monitorTab: context.monitorTab as MarketMonitorTab | undefined,
      version: current.version + 1
    }));
    setWorkspaceMode('market');
  }

  function openGlobalSearchResult(result: GlobalSearchResult) {
    const { target } = result;
    if (target.workspace === 'stock' && target.asset_id) {
      openStockWorkspace(target.asset_id, {
        sourceWorkspace: 'search',
        query: target.q ?? result.title,
        matchReason: result.match_reason
      });
      return;
    }

    if (target.workspace === 'news') {
      const query = target.q ?? result.title;
      setNewsHandoff((current) => ({
        query,
        newsId: target.news_id,
        assetId: target.asset_id,
        version: current.version + 1
      }));
      setWorkspaceMode('news');
      return;
    }

    if (target.workspace === 'researchReports') {
      const query = target.q ?? result.title;
      setResearchReportsHandoff((current) => ({
        query,
        eventKey: target.event_key,
        reportId: target.report_id,
        assetId: target.asset_id,
        version: current.version + 1
      }));
      setWorkspaceMode('researchReports');
      return;
    }

    if (target.workspace === 'generatedReports') {
      const query = target.q ?? result.title;
      setGeneratedReportsHandoff((current) => ({
        query,
        tradeDate: target.trade_date ?? result.trade_date,
        path: target.path,
        version: current.version + 1
      }));
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
            onClick={() => openWorkspaceMode(item.mode)}
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
          {workspaceMode === 'home' ? <HomeCockpit onNavigate={openWorkspaceMode} /> : null}
          {workspaceMode === 'market' ? (
            <MarketMonitorWorkspace
              key={`market:${marketHandoff.version}`}
              initialTradeDate={marketHandoff.tradeDate}
              initialMonitorTab={marketHandoff.monitorTab}
              initialAssetId={marketHandoff.assetId}
              onOpenAsset={(assetId, context) =>
                openStockWorkspace(assetId, {
                  sourceWorkspace: 'market',
                  query: context.query,
                  tradeDate: context.tradeDate,
                  monitorTab: context.monitorTab as MarketMonitorTab | undefined
                })
              }
            />
          ) : null}
          {workspaceMode === 'researchReports' ? (
            <ResearchReportsWorkspace
              key={`researchReports:${researchReportsHandoff.version}`}
              initialQuery={researchReportsHandoff.query}
              initialEventKey={researchReportsHandoff.eventKey}
              initialReportId={researchReportsHandoff.reportId}
              onOpenAsset={(assetId, context) =>
                openStockWorkspace(assetId, {
                  sourceWorkspace: 'researchReports',
                  query: context.query,
                  eventKey: context.eventKey,
                  reportId: context.reportId
                })
              }
            />
          ) : null}
          {workspaceMode === 'stock' ? (
            <StockWorkspace
              key={`stock:${stockHandoff.version}`}
              initialAssetId={stockHandoff.assetId ?? selectedAssetId}
              entryContext={stockHandoff}
              onOpenNews={openNewsWorkspaceFromStock}
              onOpenResearchReports={openResearchReportsWorkspaceFromStock}
              onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
            />
          ) : null}
          {workspaceMode === 'watchlist' ? (
            <WatchlistWorkspace
              onOpenAsset={(assetId) => openStockWorkspace(assetId, { sourceWorkspace: 'watchlist' })}
            />
          ) : null}
          {workspaceMode === 'strategyLab' ? <StrategyLabWorkspace /> : null}
          {workspaceMode === 'generatedReports' ? (
            <GeneratedReportsWorkspace
              key={`generatedReports:${generatedReportsHandoff.version}`}
              initialQuery={generatedReportsHandoff.query}
              initialTradeDate={generatedReportsHandoff.tradeDate}
              initialPath={generatedReportsHandoff.path}
            />
          ) : null}
          {workspaceMode === 'data' ? <DataExplorerWorkspace /> : null}
          {workspaceMode === 'factors' ? <FactorLabWorkspace /> : null}
          {workspaceMode === 'news' ? (
            <NewsWorkspace
              key={`news:${newsHandoff.version}`}
              initialQuery={newsHandoff.query}
              initialNewsId={newsHandoff.newsId}
              onOpenAsset={(assetId, context) =>
                openStockWorkspace(assetId, {
                  sourceWorkspace: 'news',
                  query: context.query,
                  newsId: context.newsId
                })
              }
            />
          ) : null}
        </section>
      </div>
    </main>
  );
}
