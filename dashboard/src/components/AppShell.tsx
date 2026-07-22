import { useEffect, useState } from 'react';
import { FactorLabWorkspace } from './FactorLabWorkspace';
import { DailyReviewLiteWorkspace } from './DailyReviewLiteWorkspace';
import { DataToBriefDocling90ReviewWorkspace } from './DataToBriefDocling90ReviewWorkspace';
import { GeneratedReportsWorkspace } from './GeneratedReportsWorkspace';
import { GlobalSearchBox } from './GlobalSearchBox';
import { HomeCockpit } from './HomeCockpit';
import { MarketMonitorWorkspace } from './MarketMonitorWorkspace';
import { NewsWorkspace } from './NewsWorkspace';
import { ResearchReportsWorkspace } from './ResearchReportsWorkspace';
import { ReviewQueueWorkspace } from './ReviewQueueWorkspace';
import { StockWorkspace, type StockEntryContext } from './StockWorkspace';
import { StrategyLabWorkspace } from './StrategyLabWorkspace';
import { ThemeResearchAndIndustryCatalogWorkspace } from './ThemeResearchAndIndustryCatalogWorkspace';
import { UserManagementView } from './UserManagementView';
import { WatchlistWorkspace } from './WatchlistWorkspace';
import type { SectorType } from './market-monitor/mockData';
import { fetchPlatformReadiness, fetchPlatformSummary } from '../api/client';
import { fetchTechBottleneckReviewUniverseStock } from '../api/techBottleneckReview';
import type { CurrentUser, GlobalSearchResult } from '../api/types';
import { TechBottleneckReviewPage } from '../pages/TechBottleneckReviewPage';
import type { TechBottleneckReviewStock } from '../types/techBottleneckReview';
import {
  techBottleneckWorkbenchAdjacentWatchlist,
  techBottleneckWorkbenchCoreCandidates,
  techBottleneckWorkbenchEvidenceBackfillQueue,
  techBottleneckWorkbenchRejectedCandidates
} from '../features/techBottleneckWatchlistReview/techBottleneckCandidateUniverseData';
import type { TechBottleneckWorkbenchCandidate } from '../features/techBottleneckWatchlistReview/types';
import {
  LEGACY_TECH_BOTTLENECK_REVIEW_PATH,
  LEGACY_TECH_BOTTLENECK_STOCK_PREFIX,
  WORKSPACE_PATHS,
  parsePlatformLocation,
  pathForWorkspace,
  stockCodeToAssetId,
  stockPath,
  type PlatformLocation,
  type WorkspaceMode
} from '../navigation/platformRoutes';
import { resolvePlatformDisplayDate } from '../utils/platformDisplayDate';

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
    mode: 'themeResearch',
    label: '主题研究与产业目录',
    ariaLabel: 'Open Theme Research and Industry Catalog workspace'
  },
  {
    mode: 'dataToBriefDocling90',
    label: 'Docling报告审计',
    ariaLabel: 'Open Data-to-Brief Docling 90-stock review workspace'
  },
  {
    mode: 'techBottleneckReviewUniverse',
    label: '卡脖子复盘',
    ariaLabel: 'Open Tech Bottleneck review universe workspace'
  },
  { mode: 'factors', label: '因子实验室', ariaLabel: 'Open Factor Lab workspace' },
  { mode: 'strategyLab', label: '策略实验室', ariaLabel: 'Open Strategy Lab workspace' },
  { mode: 'generatedReports', label: '生成报告', ariaLabel: 'Open Generated Reports workspace' }
];

const ADMIN_NAV_ITEMS: Array<{ mode: WorkspaceMode; label: string; ariaLabel: string }> = [
  { mode: 'userManagement', label: '用户管理', ariaLabel: 'Open User Management workspace' }
];

const TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE = 'tech_bottleneck_review_universe_frontend_dataset_v1';

function stockCodeFromTechBottleneckPath(pathname: string) {
  if (!pathname.startsWith(LEGACY_TECH_BOTTLENECK_STOCK_PREFIX)) return '';
  return pathname.slice(LEGACY_TECH_BOTTLENECK_STOCK_PREFIX.length).split('/')[0];
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
  const assetId = stockCodeToAssetId(stockCode);
  const platformLocation = parsePlatformLocation(pathname, search);
  if (platformLocation.sourceWorkspace === 'themeResearch') {
    return {
      assetId,
      sourceWorkspace: 'themeResearch',
      query: platformLocation.query,
      matchReason: platformLocation.matchReason,
      version: 0
    };
  }
  const source = new URLSearchParams(search).get('source') ?? 'tech_bottleneck_candidate_universe_workbench_patch_v1';
  if (source === TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE) {
    return {
      assetId,
      sourceWorkspace: 'techBottleneck',
      query: stockCode,
      techBottleneckSource: source,
      matchReason: TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE,
      version: 0
    };
  }
  const candidate = findTechBottleneckCandidate(stockCode);
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

function stockSourceWorkspaceFromPlatformLocation(
  sourceWorkspace: PlatformLocation['sourceWorkspace']
): StockSourceWorkspace | undefined {
  if (
    sourceWorkspace === 'search' ||
    sourceWorkspace === 'news' ||
    sourceWorkspace === 'watchlist' ||
    sourceWorkspace === 'researchReports' ||
    sourceWorkspace === 'market' ||
    sourceWorkspace === 'reviewQueue' ||
    sourceWorkspace === 'themeResearch' ||
    sourceWorkspace === 'techBottleneck'
  ) {
    return sourceWorkspace;
  }
  return undefined;
}

function stockHandoffFromLocation(pathname: string, search: string): StockHandoff | null {
  if (pathname.startsWith(LEGACY_TECH_BOTTLENECK_STOCK_PREFIX)) {
    return techBottleneckStockHandoffFromLocation(pathname, search);
  }
  const location = parsePlatformLocation(pathname, search);
  if (location.workspace !== 'stock' || !location.assetId) return null;
  return {
    assetId: location.assetId,
    sourceWorkspace: stockSourceWorkspaceFromPlatformLocation(location.sourceWorkspace),
    query: location.query,
    matchReason: location.matchReason,
    newsId: location.newsId,
    eventKey: location.eventKey,
    reportId: location.reportId,
    tradeDate: location.tradeDate,
    monitorTab: location.monitorTab,
    version: 0
  };
}

function searchQueryFromHistoryState() {
  const state = window.history.state;
  return typeof state?.searchQuery === 'string' ? state.searchQuery : '';
}

const OFFICIAL_STRATEGY_IDS = new Set(['lhb_shortline', 'mid_trend', 'tech_bottleneck']);

function strategyIdFromSearch(search: string): string | undefined {
  const params = new URLSearchParams(search);
  return params.has('strategy_id') ? (params.get('strategy_id') ?? '') : undefined;
}

function historyStateFields() {
  const state = window.history.state;
  return state && typeof state === 'object' && !Array.isArray(state) ? state : {};
}

function conceptTagsFromReviewUniverseStock(stock: TechBottleneckReviewStock) {
  if (Array.isArray(stock.concept_tags)) return stock.concept_tags;
  return String(stock.concept_tags || '')
    .split(/[;,，、|]/)
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function normalizeTechBottleneckReviewUniverseScore(value: unknown) {
  if (value === null || value === undefined || value === '') return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function techBottleneckReviewUniverseStockHandoff(stock: TechBottleneckReviewStock): StockHandoff {
  return {
    assetId: stockCodeToAssetId(stock.stock_code),
    sourceWorkspace: 'techBottleneck',
    query: stock.stock_name || stock.stock_code,
    stockName: stock.stock_name,
    techBottleneckSource: TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE,
    sourceGroup: stock.source_group || stock.review_universe_source,
    previousTier: stock.previous_tier || stock.current_layer_status,
    industry: stock.industry,
    conceptTags: conceptTagsFromReviewUniverseStock(stock),
    evidenceStrength: stock.evidence_strength,
    bottleneckRelevance: stock.bottleneck_relevance,
    bottleneckConfidenceScore:
      stock.bottleneckConfidenceScore ?? normalizeTechBottleneckReviewUniverseScore(stock.bottleneck_confidence_score),
    evidenceQualityScore:
      stock.evidenceQualityScore ?? normalizeTechBottleneckReviewUniverseScore(stock.evidence_quality_score),
    reviewStatus: stock.review_status || stock.frontend_review_status,
    allowedForSignal: false,
    allowedForAdmission: false,
    rationale: stock.evidence_summary_for_review,
    nextAction: stock.next_primary_source_to_check,
    evidenceExcerpt: stock.strongest_primary_source_claim,
    evidenceGapNote: stock.weakest_or_riskiest_claim,
    matchReason: TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE,
    version: 0
  };
}

type AppShellProps = {
  currentUser?: CurrentUser;
  onLogout?: () => void;
  logoutPending?: boolean;
  logoutError?: string;
};

function workspaceModeForCurrentUser(workspace: WorkspaceMode, currentUser?: CurrentUser): WorkspaceMode {
  if (workspace === 'userManagement' && currentUser?.role !== 'admin') return 'home';
  return workspace;
}

export function AppShell({ currentUser: _currentUser, onLogout, logoutPending = false, logoutError = '' }: AppShellProps = {}) {
  const currentUser = _currentUser;
  const navItems = currentUser?.role === 'admin' ? [...NAV_ITEMS, ...ADMIN_NAV_ITEMS] : NAV_ITEMS;
  const initialPlatformLocation =
    typeof window === 'undefined'
      ? parsePlatformLocation(WORKSPACE_PATHS.home, '')
      : parsePlatformLocation(window.location.pathname, window.location.search);
  const initialStockHandoff =
    typeof window === 'undefined' ? null : stockHandoffFromLocation(window.location.pathname, window.location.search);
  const [workspaceMode, setWorkspaceMode] = useState<WorkspaceMode>(
    workspaceModeForCurrentUser(initialPlatformLocation.workspace, currentUser)
  );
  const [globalSearchQuery, setGlobalSearchQuery] = useState(() =>
    typeof window !== 'undefined' && initialPlatformLocation.workspace === 'home'
      ? searchQueryFromHistoryState()
      : ''
  );
  const [selectedAssetId, setSelectedAssetId] = useState(initialStockHandoff?.assetId ?? '000001.SZ');
  const [newsHandoff, setNewsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [researchReportsHandoff, setResearchReportsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [generatedReportsHandoff, setGeneratedReportsHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [marketHandoff, setMarketHandoff] = useState<WorkspaceHandoff>({ query: '', version: 0 });
  const [stockHandoff, setStockHandoff] = useState<StockHandoff>(initialStockHandoff ?? { version: 0 });
  const [themeResearchPathname, setThemeResearchPathname] = useState(() =>
    typeof window !== 'undefined' && initialPlatformLocation.workspace === 'themeResearch'
      ? window.location.pathname
      : WORKSPACE_PATHS.themeResearch
  );
  const [initialStrategyId, setInitialStrategyId] = useState(() =>
    typeof window !== 'undefined' && initialPlatformLocation.workspace === 'strategyLab'
      ? strategyIdFromSearch(window.location.search)
      : undefined
  );
  const [initialReviewStrategyId, setInitialReviewStrategyId] = useState(() =>
    typeof window !== 'undefined' && initialPlatformLocation.workspace === 'reviewQueue'
      ? strategyIdFromSearch(window.location.search)
      : undefined
  );
  const [displayTradeDate, setDisplayTradeDate] = useState('');
  const [stockDefaultTradeDate, setStockDefaultTradeDate] = useState('');
  const [displayDateResolved, setDisplayDateResolved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    Promise.allSettled([fetchPlatformReadiness(), fetchPlatformSummary()]).then(([readinessResult, summaryResult]) => {
      if (cancelled) {
        return;
      }
      const readiness = readinessResult.status === 'fulfilled' ? readinessResult.value : null;
      const summary = summaryResult.status === 'fulfilled' ? summaryResult.value : null;
      const resolvedDisplayDate = resolvePlatformDisplayDate(readiness, {
        allowLegacyFallback: readinessResult.status === 'fulfilled',
        legacyFallbackDates: [summary?.latest_market_date]
      });
      setDisplayTradeDate(resolvedDisplayDate);
      setStockDefaultTradeDate(resolvedDisplayDate);
      setDisplayDateResolved(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleLocationChange = () => {
      let nextLocation = parsePlatformLocation(window.location.pathname, window.location.search);
      if (window.location.pathname === LEGACY_TECH_BOTTLENECK_REVIEW_PATH) {
        window.history.replaceState({}, '', nextLocation.canonicalPath);
        nextLocation = parsePlatformLocation(window.location.pathname, window.location.search);
      }
      if (nextLocation.workspace === 'themeResearch') {
        setThemeResearchPathname(window.location.pathname);
      }
      if (nextLocation.workspace === 'stock') {
        const nextStockHandoff = stockHandoffFromLocation(window.location.pathname, window.location.search);
        if (nextStockHandoff?.assetId) {
          setSelectedAssetId(nextStockHandoff.assetId);
          setStockHandoff((current) => ({
            ...nextStockHandoff,
            version: current.version + 1
          }));
        }
      }
      setInitialStrategyId(
        nextLocation.workspace === 'strategyLab' ? strategyIdFromSearch(window.location.search) : undefined
      );
      setInitialReviewStrategyId(
        nextLocation.workspace === 'reviewQueue' ? strategyIdFromSearch(window.location.search) : undefined
      );
      setGlobalSearchQuery(nextLocation.workspace === 'home' ? searchQueryFromHistoryState() : '');
      setWorkspaceMode(workspaceModeForCurrentUser(nextLocation.workspace, currentUser));
    };
    handleLocationChange();
    window.addEventListener('popstate', handleLocationChange);
    return () => {
      window.removeEventListener('popstate', handleLocationChange);
    };
  }, [currentUser?.role]);

  useEffect(() => {
    if (
      stockHandoff.sourceWorkspace !== 'techBottleneck' ||
      stockHandoff.techBottleneckSource !== TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE ||
      !stockHandoff.assetId
    ) {
      return;
    }

    let cancelled = false;
    const stockCode = stockHandoff.assetId.split('.')[0] ?? stockHandoff.assetId;

    fetchTechBottleneckReviewUniverseStock(stockCode)
      .then((stock) => {
        if (cancelled) return;
        const nextContext = techBottleneckReviewUniverseStockHandoff(stock);
        setStockHandoff((current) => {
          if (
            current.sourceWorkspace !== 'techBottleneck' ||
            current.techBottleneckSource !== TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE ||
            current.assetId !== nextContext.assetId
          ) {
            return current;
          }
          return {
            ...current,
            ...nextContext,
            version: current.version + 1
          };
        });
      })
      .catch(() => {
        // Keep the route-derived handoff if the read-model lookup is unavailable.
      });

    return () => {
      cancelled = true;
    };
  }, [stockHandoff.assetId, stockHandoff.sourceWorkspace, stockHandoff.techBottleneckSource]);

  function activateStockWorkspace(assetId: string, context: Omit<StockHandoff, 'assetId' | 'version'> = {}) {
    setSelectedAssetId(assetId);
    setStockHandoff((current) => ({
      ...context,
      assetId,
      version: current.version + 1
    }));
    setWorkspaceMode('stock');
  }

  function pushLocation(path: string) {
    if (`${window.location.pathname}${window.location.search}` === path) return;
    if (parsePlatformLocation(window.location.pathname, window.location.search).workspace === 'home') {
      window.history.replaceState(
        { ...historyStateFields(), searchQuery: globalSearchQuery },
        '',
        `${window.location.pathname}${window.location.search}${window.location.hash}`
      );
      setGlobalSearchQuery('');
    }
    window.history.pushState({}, '', path);
  }

  function openStockWorkspace(assetId: string, context: Omit<StockHandoff, 'assetId' | 'version'> = {}) {
    pushLocation(stockPath(assetId, context));
    activateStockWorkspace(assetId, context);
  }

  function openWorkspaceMode(mode: WorkspaceMode) {
    if (mode === 'stock') {
      openStockWorkspace(selectedAssetId);
      return;
    }
    const path = pathForWorkspace(mode);
    pushLocation(path);
    if (mode === 'themeResearch') {
      setThemeResearchPathname(path);
    }
    setWorkspaceMode(mode);
  }

  function openStrategyReviewQueue(strategyId: string) {
    if (!OFFICIAL_STRATEGY_IDS.has(strategyId)) return;
    const path = `${pathForWorkspace('reviewQueue')}?strategy_id=${encodeURIComponent(strategyId)}`;
    pushLocation(path);
    setInitialReviewStrategyId(strategyId);
    setWorkspaceMode('reviewQueue');
  }

  function navigateThemeResearch(path: string) {
    if (!path.startsWith(WORKSPACE_PATHS.themeResearch)) return;
    if (`${window.location.pathname}${window.location.search}` !== path) {
      window.history.pushState({}, '', path);
    }
    setThemeResearchPathname(window.location.pathname);
    setWorkspaceMode('themeResearch');
  }

  function openStockWorkspaceFromThemeResearch(path: string) {
    if (!path.startsWith(LEGACY_TECH_BOTTLENECK_STOCK_PREFIX)) return;
    window.history.pushState({}, '', path);
    const handoff = techBottleneckStockHandoffFromLocation(window.location.pathname, window.location.search);
    if (!handoff?.assetId) return;
    activateStockWorkspace(handoff.assetId, handoff);
  }

  function openNewsWorkspaceFromStock(context: StockEntryContext) {
    window.history.pushState({}, '', pathForWorkspace('news'));
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
    window.history.pushState({}, '', pathForWorkspace('researchReports'));
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
    window.history.pushState({}, '', pathForWorkspace('market'));
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

  function openStockWorkspaceFromTechBottleneckReviewUniverse(stock: TechBottleneckReviewStock) {
    const context = techBottleneckReviewUniverseStockHandoff(stock);
    if (!context.assetId) return;
    window.history.pushState(
      {},
      '',
      `${LEGACY_TECH_BOTTLENECK_STOCK_PREFIX}${stock.stock_code}?source=${TECH_BOTTLENECK_REVIEW_UNIVERSE_SOURCE}`
    );
    activateStockWorkspace(context.assetId, context);
  }

  function openGlobalSearchResult(result: GlobalSearchResult) {
    const { target } = result;
    if (target.workspace === 'stock' && target.asset_id) {
      const query = globalSearchQuery || target.q || result.title;
      openStockWorkspace(target.asset_id, {
        sourceWorkspace: 'search',
        query,
        matchReason: result.match_reason
      });
      return;
    }

    if (target.workspace === 'news') {
      const query = target.q ?? result.title;
      pushLocation(pathForWorkspace('news'));
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
      pushLocation(pathForWorkspace('researchReports'));
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
      pushLocation(pathForWorkspace('generatedReports'));
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
      <nav className="platform-nav" aria-label="Workspace navigation">
        <div className="panel-title">A股策略研究</div>
        {navItems.map((item) => (
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
      </nav>
      <div className="platform-main">
        <header className="platform-topbar">
          <GlobalSearchBox
            query={globalSearchQuery}
            onQueryChange={setGlobalSearchQuery}
            onOpenResult={openGlobalSearchResult}
          />
          {currentUser ? (
            <div className="platform-user-controls">
              <span>{currentUser.display_name.trim() || currentUser.username}</span>
              <button type="button" disabled={logoutPending} onClick={onLogout}>
                退出登录
              </button>
              {logoutError ? <p role="alert">{logoutError}</p> : null}
            </div>
          ) : null}
        </header>
        <section className="platform-workspace">
          {workspaceMode === 'home' ? (
            <HomeCockpit onNavigate={openWorkspaceMode} onOpenStrategy={openStrategyReviewQueue} />
          ) : null}
          {workspaceMode === 'reviewQueue' ? (
            <ReviewQueueWorkspace
              initialStrategyId={initialReviewStrategyId}
              onOpenStock={openStockWorkspaceFromReviewQueue}
              onOpenNews={openNewsWorkspaceFromStock}
              onOpenResearchReports={openResearchReportsWorkspaceFromStock}
              onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
            />
          ) : null}
          {workspaceMode === 'dailyReview' ? (
            displayDateResolved ? (
              <DailyReviewLiteWorkspace initialTradeDate={displayTradeDate} />
            ) : (
              <p className="muted" role="status">正在解析平台展示日期...</p>
            )
          ) : null}
          {workspaceMode === 'market' ? (
            marketHandoff.tradeDate || displayDateResolved ? (
              <MarketMonitorWorkspace
                key={`market:${marketHandoff.version}`}
                initialTradeDate={marketHandoff.tradeDate ?? displayTradeDate}
                initialMonitorTab={marketHandoff.monitorTab}
                initialAssetId={marketHandoff.assetId}
                emotionPresentation="panel"
                onOpenAsset={(assetId, context) =>
                  openStockWorkspace(assetId, {
                    sourceWorkspace: 'market',
                    query: context.query,
                    matchReason: context.matchReason,
                    tradeDate: context.tradeDate,
                    monitorTab: context.monitorTab
                  })
                }
              />
            ) : (
              <p className="muted" role="status">正在解析平台展示日期...</p>
            )
          ) : null}
          {workspaceMode === 'researchReports' ? (
            <ResearchReportsWorkspace
              key={`researchReports:${researchReportsHandoff.version}`}
              initialQuery={researchReportsHandoff.query}
              initialEventKey={researchReportsHandoff.eventKey}
              initialReportId={researchReportsHandoff.reportId}
              initialTradeDate={researchReportsHandoff.tradeDate ?? displayTradeDate}
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
            displayDateResolved && displayTradeDate ? (
              <StockWorkspace
                key={`stock:${stockHandoff.version}`}
                initialAssetId={stockHandoff.assetId ?? selectedAssetId}
                defaultTradeDate={displayTradeDate}
                entryContext={stockHandoff}
                onOpenNews={openNewsWorkspaceFromStock}
                onOpenResearchReports={openResearchReportsWorkspaceFromStock}
                onOpenMarketMonitor={openMarketMonitorWorkspaceFromStock}
              />
            ) : displayDateResolved ? (
              <p className="muted" role="status">平台展示日期不可用。</p>
            ) : (
              <p className="muted" role="status">正在解析平台展示日期...</p>
            )
          ) : null}
          {workspaceMode === 'watchlist' ? (
            <WatchlistWorkspace
              defaultTradeDate={displayTradeDate}
              onOpenAsset={(assetId) => openStockWorkspace(assetId, { sourceWorkspace: 'watchlist' })}
            />
          ) : null}
          {workspaceMode === 'themeResearch' ? (
            <ThemeResearchAndIndustryCatalogWorkspace
              pathname={themeResearchPathname}
              onNavigate={navigateThemeResearch}
              onOpenStock={openStockWorkspaceFromThemeResearch}
            />
          ) : null}
          {workspaceMode === 'techBottleneckReviewUniverse' ? (
            <TechBottleneckReviewPage onOpenStock={openStockWorkspaceFromTechBottleneckReviewUniverse} />
          ) : null}
          {workspaceMode === 'dataToBriefDocling90' ? <DataToBriefDocling90ReviewWorkspace /> : null}
          {workspaceMode === 'strategyLab' ? (
            <StrategyLabWorkspace defaultEndDate={displayTradeDate} initialStrategyId={initialStrategyId} />
          ) : null}
          {workspaceMode === 'generatedReports' ? (
            <GeneratedReportsWorkspace
              key={`generatedReports:${generatedReportsHandoff.version}`}
              initialQuery={generatedReportsHandoff.query}
              initialTradeDate={generatedReportsHandoff.tradeDate ?? displayTradeDate}
              initialPath={generatedReportsHandoff.path}
            />
          ) : null}
          {workspaceMode === 'userManagement' ? <UserManagementView /> : null}
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
