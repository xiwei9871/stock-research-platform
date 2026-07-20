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

export type StockPathHandoff = Pick<
  PlatformLocation,
  | 'sourceWorkspace'
  | 'query'
  | 'matchReason'
  | 'newsId'
  | 'eventKey'
  | 'reportId'
  | 'tradeDate'
  | 'monitorTab'
  | 'reportPath'
>;

const SOURCE_TOKENS = {
  home: 'home',
  reviewQueue: 'review_queue',
  dailyReview: 'daily_review',
  market: 'market',
  news: 'news',
  researchReports: 'research_reports',
  stock: 'stock',
  watchlist: 'watchlist',
  themeResearch: 'theme_research',
  techBottleneckReviewUniverse: 'tech_bottleneck_review_universe',
  dataToBriefDocling90: 'data_to_brief_docling_90',
  factors: 'factor_lab',
  strategyLab: 'strategy_lab',
  generatedReports: 'generated_reports',
  userManagement: 'user_management',
  search: 'search',
  techBottleneck: 'tech_bottleneck'
} satisfies Record<PlatformSourceWorkspace, string>;

const SOURCE_WORKSPACES: Record<string, PlatformSourceWorkspace> = {
  ...Object.fromEntries(
    Object.entries(SOURCE_TOKENS).map(([sourceWorkspace, token]) => [token, sourceWorkspace as PlatformSourceWorkspace])
  ),
  reviewQueue: 'reviewQueue',
  dailyReview: 'dailyReview',
  market_monitor: 'market',
  researchReports: 'researchReports',
  themeResearch: 'themeResearch',
  techBottleneck: 'techBottleneck',
  factors: 'factors'
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

function normalizeAssetId(assetId: string) {
  const normalized = stockCodeToAssetId(assetId);
  if (
    !normalized ||
    normalized === '.' ||
    normalized === '..' ||
    /[\/\\\u0000-\u001f\u007f]/.test(normalized)
  ) {
    return null;
  }
  return normalized;
}

function searchForHandoff(handoff: StockPathHandoff) {
  const params = new URLSearchParams();
  if (handoff.sourceWorkspace) params.set('source', SOURCE_TOKENS[handoff.sourceWorkspace]);
  if (handoff.query) params.set('q', handoff.query);
  if (handoff.matchReason) params.set('match_reason', handoff.matchReason);
  if (handoff.newsId) params.set('news_id', handoff.newsId);
  if (handoff.eventKey) params.set('event_key', handoff.eventKey);
  if (handoff.reportId) params.set('report_id', handoff.reportId);
  if (handoff.tradeDate) params.set('trade_date', handoff.tradeDate);
  if (handoff.monitorTab) params.set('monitor_tab', handoff.monitorTab);
  if (handoff.reportPath) params.set('path', handoff.reportPath);
  return params.toString();
}

export function stockPath(assetId: string, handoff: StockPathHandoff = {}) {
  const normalized = normalizeAssetId(assetId);
  if (!normalized) throw new Error('invalid_asset_id');
  const search = searchForHandoff(handoff);
  return `/stock/${encodeURIComponent(normalized)}${search ? `?${search}` : ''}`;
}

function decodePathSegment(segment: string) {
  try {
    return decodeURIComponent(segment);
  } catch {
    return null;
  }
}

function stockAssetIdFromPath(pathname: string, prefix: string) {
  if (!pathname.startsWith(prefix)) return '';
  const segment = pathname.slice(prefix.length);
  if (!segment || segment.includes('/')) return '';
  const decoded = decodePathSegment(segment);
  return decoded === null ? '' : (normalizeAssetId(decoded) ?? '');
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
