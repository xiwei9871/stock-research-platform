import { useEffect, useState } from 'react';
import { FactorLabWorkspace } from './FactorLabWorkspace';
import { DailyReviewLiteWorkspace } from './DailyReviewLiteWorkspace';
import { GeneratedReportsWorkspace } from './GeneratedReportsWorkspace';
import { GlobalSearchBox } from './GlobalSearchBox';
import { HomeCockpit } from './HomeCockpit';
import { MarketMonitorWorkspace } from './MarketMonitorWorkspace';
import { NewsWorkspace } from './NewsWorkspace';
import { ResearchReportsWorkspace } from './ResearchReportsWorkspace';
import { ReviewQueueWorkspace } from './ReviewQueueWorkspace';
import { StockWorkspace, type StockEntryContext } from './StockWorkspace';
import { StrategyLabWorkspace } from './StrategyLabWorkspace';
import { WatchlistWorkspace } from './WatchlistWorkspace';
import type { SectorType } from './market-monitor/mockData';
import { fetchPlatformReadiness, fetchPlatformSummary } from '../api/client';
import type { GlobalSearchResult } from '../api/types';
import { TechBottleneckWatchlistReviewPage } from '../features/techBottleneckWatchlistReview/TechBottleneckWatchlistReviewPage';
import {
  techBottleneckWorkbenchAdjacentWatchlist,
  techBottleneckWorkbenchCoreCandidates,
  techBottleneckWorkbenchEvidenceBackfillQueue,
  techBottleneckWorkbenchRejectedCandidates
} from '../features/techBottleneckWatchlistReview/techBottleneckCandidateUniverseData';
import type { TechBottleneckWorkbenchCandidate } from '../features/techBottleneckWatchlistReview/types';

type WorkspaceMode =
  | 'home'
  | 'reviewQueue'
  | 'dailyReview'
  | 'market'
  | 'news'
  | 'researchReports'
  | 'stock'
  | 'watchlist'
  | 'techBottleneckReview'
  | 'factors'
  | 'strategyLab'
  | 'generatedReports';

type WorkspaceHandoff = {
  query: string;
  tradeDate?: string;
  newsId?: string;
  assetId?: string;
  eventKey?: string;
  reportId?: string;
  path?: string;
  monitorTab?: SectorType;
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
  monitorTab?: string;
  version: number;
} & Omit<StockEntryContext, 'version'>;

function normalizeMarketMonitorTab(monitorTab?: string | null): SectorType | undefined {
  if (!monitorTab) return undefined;
  return monitorTab === 'concept' ? 'concept' : 'industry';
}

const NAV_ITEMS: Array<{ mode: WorkspaceMode; label: string; ariaLabel: string }> = [
  { mode: 'home', label: '首页', ariaLabel: 'Open Home workspace' },
  { mode: 'reviewQueue', label: '复盘队列', ariaLabel: 'Open Review Queue workspace' },
  { mode: 'dailyReview', label: '每日复盘', ariaLabel: 'Open Daily Review workspace' },
  { mode: 'market', label: '市场监控', ariaLabel: 'Open Market Monitor workspace' },
  { mode: 'news', label: '新闻', ariaLabel: 'Open News workspace' },
  { mode: 'researchReports', label: '研报', ariaLabel: 'Open Research Reports workspace' },
  { mode: 'stock', label: '个股工作台', ariaLabel: 'Open Stock Workspace workspace' },
  { mode: 'watchlist', label: '观察池', ariaLabel: 'Open Watchlist workspace' },
  {
    mode: 'techBottleneckReview',
    label: '科技卡脖子观察池',
    ariaLabel: 'Open Tech Bottleneck Watchlist Review workspace'
  },
  { mode: 'factors', label: '因子实验室', ariaLabel: 'Open Factor Lab workspace' },
  { mode: 'strategyLab', label: '策略实验室', ariaLabel: 'Open Strategy Lab workspace' },
  { mode: 'generatedReports', label: '生成报告', ariaLabel: 'Open Generated Reports workspace' }
];

const FALLBACK_DISPLAY_TRADE_DATE = '2026-06-18';
const TECH_BOTTLENECK_REVIEW_PATH = '/tech-bottleneck/watchlist-review';
const TECH_BOTTLENECK_STOCK_PREFIX = '/tech-bottleneck/stock/';

function firstDate(...dates: Array<string | null | undefined>) {
  return dates.map((date) => date?.trim()).find(Boolean) ?? '';
}

function workspaceModeFromPath(pathname: string): WorkspaceMode {
  if (pathname === TECH_BOTTLENECK_REVIEW_PATH) return 'techBottleneckReview';
  if (pathname.startsWith(TECH_BOTTLENECK_STOCK_PREFIX)) return 'stock';
  return 'home';
}

function stockCodeFromTechBottleneckPath(pathname: string) {
  if (!pathname.startsWith(TECH_BOTTLENECK_STOCK_PREFIX)) return '';
  return pathname.slice(TECH_BOTTLENECK_STOCK_PREFIX.length).split('/')[0];
}

function stockCodeToAssetId(stockCode: string) {
  const normalized = stockCode.trim().toUpperCase();
  if (/^\d{6}$/.test(normalized)) {
    return `${normalized}.${normalized.startsWith('6') ? 'SH' : 'SZ'}`;
  }
  return normalized;
}

function findTechBottleneckCandidate(stockCode: string): TechBottleneckWorkbenchCandidate | undefined {
  const normalized = stockCode.trim().toUpperCase().split('.')[0];
  return [
    ...techBottleneckWorkbenchCoreCandidates,
    ...techBottleneckWorkbenchAdjacentWatchlist,
    ...techBottleneckWorkbenchEvidenceBackfillQueue,
    ...techBottleneckWorkbenchRejectedCandidates
  ].find((candidate) => candidate.stockCode === normalized);
}

function techBottleneckStockHandoffFromLocation(pathname: string, search: string): StockHandoff | null {
  const stockCode = stockCodeFromTechBottleneckPath(pathname);
  if (!stockCode) return null;
  const candidate = findTechBottleneckCandidate(stockCode);
  const assetId = stockCodeToAssetId(stockCode);
  const source = new URLSearchParams(search).get('source') ?? 'tech_bottleneck_candidate_universe_workbench_patch_v1';
  return {
    assetId,
    sourceWorkspace: 'techBottleneck',
    query: candidate?.stockName ?? stockCode,
    stockName: candidate?.stockName,
    techBottleneckSource: source,
    sourceGroup: candidate?.sourceGroup,
    previousTier: candidate?.previousTier,
    finalManualApprovalCategory: candidate?.finalManualApprovalCategory,
    industry: candidate?.industry,
    conceptTags: candidate?.conceptTags,
    evidenceCategory: candidate?.evidenceCategory,
    businessRelevanceCategory: candidate?.businessRelevanceCategory,
    researchPriorityScore: candidate?.researchPriorityScore,
    reviewPriorityRank: candidate?.reviewPriorityRank,
    evidenceStrength: candidate?.evidenceStrength,
    bottleneckRelevance: candidate?.bottleneckRelevance,
    reviewDecisionSource: candidate?.reviewDecisionSource,
    primarySourceUrl: candidate?.primarySourceUrl,
    manualApprovalRequired: candidate?.manualApprovalRequired,
    allowedForWorkbenchCandidatePool: candidate?.allowedForWorkbenchCandidatePool,
    allowedForSignal: candidate?.allowedForSignal ?? false,
    allowedForAdmission: candidate?.allowedForAdmission ?? false,
    rationale: candidate?.rationale,
    reviewStatus: candidate?.reviewStatus,
    notes: candidate?.notes,
    nextAction: candidate?.nextAction,
    evidenceExcerpt: candidate?.evidenceExcerpt,
    reportStatus: candidate?.reportStatus,
    bottleneckConfidenceScore: candidate?.bottleneckConfidenceScore,
    evidenceQualityScore: candidate?.evidenceQualityScore,
    reportReviewDecision: candidate?.reportReviewDecision,
    reportUpdatedAt: candidate?.reportUpdatedAt,
    reportMdPath: candidate?.reportMdPath,
    reportHtmlPath: candidate?.reportHtmlPath,
    reportPdfPath: candidate?.reportPdfPath,
    evidenceMatrixPath: candidate?.evidenceMatrixPath,
    reportSourcesPath: candidate?.reportSourcesPath,
    evidenceGapNote: candidate?.evidenceGapNote,
    matchReason: 'tech_bottleneck_candidate_universe_workbench_patch_v1',
    version: 0
  };
}

export function AppShell() {
  const initialTechBottleneckStockHandoff =
    typeof window === 'undefined' ? null : techBottleneckStockHandoffFromLocation(window.location.pathname, window.location.search);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(() =>
    typeof window === 'undefined' ? 'home' : workspaceModeFromPath(window.location.pathname)
  );
  const [selectedAssetId, setSelectedAssetId] = useState(initialTechBottleneckStockHandoff?.assetId ?? '000001.SZ');
  const [newsHandoff, setNewsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [researchReportsHandoff, setResearchReportsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [generatedReportsHandoff, setGeneratedReportsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [marketHandoff, setMarketHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [stockHandoff, setStockHandoff] = useState<StockHandoff>(initialTechBottleneckStockHandoff ?? { version: 0 });
  const [displayTradeDate, setDisplayTradeDate] = useState(FALLBACK_DISPLAY_TRADE_DATE);
  const [stockDefaultTradeDate, setStockDefaultTradeDate] = useState(FALLBACK_DISPLAY_TRADE_DATE);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([fetchPlatformReadiness(), fetchPlatformSummary()]).then(([readinessResult, summaryResult]) => {
      if (cancelled) {
        return;
      }
      const readiness = readinessResult.status === 'fulfilled' ? readinessResult.value : null;
      const summary = summaryResult.status === 'fulfilled' ? summaryResult.value : null;
      const latestAvailableDate = firstDate(readiness?.latest_market_date, summary?.latest_market_date, readiness?.latest_trade_date);
      const readinessDate = firstDate(latestAvailableDate, readiness?.display_trade_date);
      const summaryDate = summaryResult.status === 'fulfilled' ? summaryResult.value.latest_market_date : undefined;
      setDisplayTradeDate(readinessDate || summaryDate || FALLBACK_DISPLAY_TRADE_DATE);
      setStockDefaultTradeDate(
        firstDate(readiness?.latest_market_date, readiness?.latest_trade_date, summary?.latest_market_date, readinessDate) ||
          FALLBACK_DISPLAY_TRADE_DATE
      );
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleLocationChange = () => {
      const nextMode = workspaceModeFromPath(window.location.pathname);
      if (window.location.pathname.startsWith(TECH_BOTTLENECK_STOCK_PREFIX)) {
        const techBottleneckHandoff = techBottleneckStockHandoffFromLocation(window.location.pathname, window.location.search);
        if (techBottleneckHandoff?.assetId) {
          setSelectedAssetId(techBottleneckHandoff.assetId);
          setStockHandoff((current) => ({
            ...techBottleneckHandoff,
            version: current.version + 1
          }));
        }
      }
      setWorkspaceMode(nextMode);
    };
    window.addEventListener('popstate', handleLocationChange);
    return () => {
      window.removeEventListener('popstate', handleLocationChange);
    };
  }, []);

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
    if (mode === 'techBottleneckReview' && window.location.pathname !== TECH_BOTTLENECK_REVIEW_PATH) {
      window.history.pushState({}, '', TECH_BOTTLENECK_REVIEW_PATH);
    } else if (
      mode !== 'techBottleneckReview' &&
      (window.location.pathname === TECH_BOTTLENECK_REVIEW_PATH || window.location.pathname.startsWith(TECH_BOTTLENECK_STOCK_PREFIX))
    ) {
      window.history.pushState({}, '', '/');
    }
    setWorkspaceMode(mode);
  }

  function openNewsWorkspaceFromStock(context: StockEntryContext) {
    setNewsHandoff((current) => ({
      query: context.query ?? context.assetId ?? selectedAssetId,
      newsId: context.newsId,
      assetId: context.assetId ?? selectedAssetId,
      tradeDate: context.tradeDate,
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
      tradeDate: context.tradeDate,
      version: current.version + 1
    }));
    setWorkspaceMode('researchReports');
  }

  function openMarketMonitorWorkspaceFromStock(context: StockEntryContext) {
    setMarketHandoff((current) => ({
      query: context.query ?? context.assetId ?? selectedAssetId,
      assetId: context.assetId ?? selectedAssetId,
      tradeDate: context.tradeDate,
      monitorTab: normalizeMarketMonitorTab(context.monitorTab),
      version: current.version + 1
    }));
    setWorkspaceMode('market');
  }

function openStockWorkspaceFromReviewQueue(assetId: string, context?: StockEntryContext) {
  openStockWorkspace(assetId, {
    ...context
  });
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
        <div className="panel-title">A股策略研究</div>
        {NAV_ITEMS.map((item) => (
          <button
            type="button"
            key={item.mode}
            aria-current={workspaceMode === item.mode ? 'page' : undefined}
            aria-label={item.ariaLabel}
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
          {workspaceMode === 'reviewQueue' ? (
            <ReviewQueueWorkspace
              onOpenStock={openStockWorkspaceFromReviewQueue}
              onOpenNews={openNewsWorkspaceFromStock}
              onOpenResearchReports={openResearchReportsWorkspaceFromStock}
              onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
            />
          ) : null}
          {workspaceMode === 'dailyReview' ? <DailyReviewLiteWorkspace initialTradeDate={displayTradeDate} /> : null}
          {workspaceMode === 'market' ? (
            <MarketMonitorWorkspace
              key={`market:${marketHandoff.version}`}
              initialTradeDate={marketHandoff.tradeDate}
              initialMonitorTab={marketHandoff.monitorTab}
              initialAssetId={marketHandoff.assetId}
              emotionPresentation="panel"
              onOpenAsset={(assetId, context) =>
                openStockWorkspace(assetId, {
                  sourceWorkspace: 'market',
                  query: context.query,
                  tradeDate: context.tradeDate,
                  monitorTab: normalizeMarketMonitorTab(context.monitorTab)
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
              initialTradeDate={researchReportsHandoff.tradeDate}
              onOpenAsset={(assetId, context) =>
                openStockWorkspace(assetId, {
                  sourceWorkspace: 'researchReports',
                  query: context.query,
                  eventKey: context.eventKey,
                  reportId: context.reportId,
                  tradeDate: context.tradeDate
                })
              }
            />
          ) : null}
          {workspaceMode === 'stock' ? (
            <StockWorkspace
              key={`stock:${stockHandoff.version}`}
              initialAssetId={stockHandoff.assetId ?? selectedAssetId}
              defaultTradeDate={stockDefaultTradeDate}
              entryContext={stockHandoff}
              onOpenNews={openNewsWorkspaceFromStock}
              onOpenResearchReports={openResearchReportsWorkspaceFromStock}
              onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
            />
          ) : null}
          {workspaceMode === 'watchlist' ? (
            <WatchlistWorkspace
              defaultTradeDate={displayTradeDate}
              onOpenAsset={(assetId) => openStockWorkspace(assetId, { sourceWorkspace: 'watchlist' })}
            />
          ) : null}
          {workspaceMode === 'techBottleneckReview' ? <TechBottleneckWatchlistReviewPage /> : null}
          {workspaceMode === 'strategyLab' ? <StrategyLabWorkspace defaultEndDate={displayTradeDate} /> : null}
          {workspaceMode === 'generatedReports' ? (
            <GeneratedReportsWorkspace
              key={`generatedReports:${generatedReportsHandoff.version}`}
              initialQuery={generatedReportsHandoff.query}
              initialTradeDate={generatedReportsHandoff.tradeDate ?? displayTradeDate}
              initialPath={generatedReportsHandoff.path}
            />
          ) : null}
          {workspaceMode === 'factors' ? <FactorLabWorkspace defaultTradeDate={displayTradeDate} /> : null}
          {workspaceMode === 'news' ? (
            <NewsWorkspace
              key={`news:${newsHandoff.version}`}
              initialQuery={newsHandoff.query}
              initialNewsId={newsHandoff.newsId}
              initialTradeDate={newsHandoff.tradeDate}
              onOpenAsset={(assetId, context) =>
                openStockWorkspace(assetId, {
                  sourceWorkspace: 'news',
                  query: context.query,
                  newsId: context.newsId,
                  tradeDate: context.tradeDate
                })
              }
            />
          ) : null}
        </section>
      </div>
    </main>
  );
}
