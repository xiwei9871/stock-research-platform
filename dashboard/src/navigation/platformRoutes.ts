export const WORKSPACE_PATHS = {
  home: '/',
  reviewQueue: '/review-queue',
  dailyReview: '/daily-review',
  market: '/market-monitor',
  news: '/news',
  researchReports: '/research-reports',
  watchlist: '/watchlist',
  themeResearch: '/theme-research',
  techBottleneckReviewUniverse: '/research/tech-bottleneck/review-universe',
  dataToBriefDocling90: '/research/data-to-brief/docling-90',
  factors: '/factor-lab',
  strategyLab: '/strategy-lab',
  generatedReports: '/generated-reports',
  userManagement: '/admin/users'
} as const;

export const LEGACY_TECH_BOTTLENECK_REVIEW_PATH = '/tech-bottleneck/watchlist-review';
export const LEGACY_TECH_BOTTLENECK_STOCK_PREFIX = '/tech-bottleneck/stock/';

export type PrimaryWorkspaceMode = keyof typeof WORKSPACE_PATHS;
export type WorkspaceMode = PrimaryWorkspaceMode | 'stock';
export type PlatformSourceWorkspace = WorkspaceMode | 'search' | 'techBottleneck';

export type PlatformLocation = {
  workspace: WorkspaceMode;
  canonicalPath: string;
  assetId?: string;
  sourceWorkspace?: PlatformSourceWorkspace;
  query?: string;
  matchReason?: string;
  newsId?: string;
  eventKey?: string;
  reportId?: string;
  tradeDate?: string;
  monitorTab?: string;
  reportPath?: string;
};

const SOURCE_WORKSPACES: Record<string, PlatformSourceWorkspace> = {
  search: 'search',
  home: 'home',
  review_queue: 'reviewQueue',
  reviewQueue: 'reviewQueue',
  daily_review: 'dailyReview',
  dailyReview: 'dailyReview',
  market: 'market',
  market_monitor: 'market',
  news: 'news',
  research_reports: 'researchReports',
  researchReports: 'researchReports',
  watchlist: 'watchlist',
  theme_research: 'themeResearch',
  themeResearch: 'themeResearch',
  tech_bottleneck: 'techBottleneck',
  techBottleneck: 'techBottleneck',
  tech_bottleneck_review_universe: 'techBottleneckReviewUniverse',
  data_to_brief_docling_90: 'dataToBriefDocling90',
  factors: 'factors',
  factor_lab: 'factors',
  strategy_lab: 'strategyLab',
  generated_reports: 'generatedReports',
  user_management: 'userManagement'
};

const QUERY_FIELDS = {
  q: 'query',
  match_reason: 'matchReason',
  news_id: 'newsId',
  event_key: 'eventKey',
  report_id: 'reportId',
  trade_date: 'tradeDate',
  monitor_tab: 'monitorTab',
  path: 'reportPath'
} as const;

export function pathForWorkspace(workspace: PrimaryWorkspaceMode) {
  return WORKSPACE_PATHS[workspace];
}

export function stockCodeToAssetId(stockCode: string) {
  const normalized = stockCode.trim().toUpperCase();
  if (/^\d{6}$/.test(normalized)) {
    return `${normalized}.${normalized.startsWith('6') ? 'SH' : 'SZ'}`;
  }
  return normalized;
}

export function stockPath(assetId: string) {
  return `/stock/${encodeURIComponent(stockCodeToAssetId(assetId))}`;
}

function decodePathSegment(segment: string) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return '';
  }
}

function stockAssetIdFromPath(pathname: string, prefix: string) {
  if (!pathname.startsWith(prefix)) return '';
  const segment = pathname.slice(prefix.length);
  if (!segment || segment.includes('/')) return '';
  return stockCodeToAssetId(decodePathSegment(segment));
}

function handoffFromSearch(search: string): Partial<PlatformLocation> {
  const params = new URLSearchParams(search);
  const handoff: Partial<PlatformLocation> = {};
  const source = params.get('source');
  if (source && SOURCE_WORKSPACES[source]) {
    handoff.sourceWorkspace = SOURCE_WORKSPACES[source];
  }
  for (const [queryField, locationField] of Object.entries(QUERY_FIELDS)) {
    const value = params.get(queryField);
    if (value !== null) {
      (handoff as Record<string, unknown>)[locationField] = value;
    }
  }
  return handoff;
}

export function parsePlatformLocation(pathname: string, search: string): PlatformLocation {
  const handoff = handoffFromSearch(search);
  if (pathname === LEGACY_TECH_BOTTLENECK_REVIEW_PATH) {
    return {
      workspace: 'techBottleneckReviewUniverse',
      canonicalPath: WORKSPACE_PATHS.techBottleneckReviewUniverse,
      ...handoff
    };
  }

  const canonicalStockAssetId = stockAssetIdFromPath(pathname, '/stock/');
  const legacyStockAssetId = stockAssetIdFromPath(pathname, LEGACY_TECH_BOTTLENECK_STOCK_PREFIX);
  const assetId = canonicalStockAssetId || legacyStockAssetId;
  if (assetId) {
    return {
      workspace: 'stock',
      assetId,
      canonicalPath: stockPath(assetId),
      ...handoff
    };
  }

  if (pathname === WORKSPACE_PATHS.themeResearch || pathname.startsWith(`${WORKSPACE_PATHS.themeResearch}/`)) {
    return { workspace: 'themeResearch', canonicalPath: pathname, ...handoff };
  }

  for (const [workspace, canonicalPath] of Object.entries(WORKSPACE_PATHS)) {
    if (pathname === canonicalPath) {
      return { workspace: workspace as PrimaryWorkspaceMode, canonicalPath, ...handoff };
    }
  }

  return { workspace: 'home', canonicalPath: WORKSPACE_PATHS.home };
}
