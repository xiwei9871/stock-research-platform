import type {
  AssetNewsResponse,
  AssetSearchResponse,
  AdminUserActionResponse,
  AdminUsersResponse,
  AssetProfile,
  AssetThemeResearchContext,
  AssetResearchReportResponse,
  AuthMeResponse,
  BarPoint,
  BacktestJobResponse,
  BacktestRunRequest,
  BacktestRunResult,
  CreateOperatorDecisionRequest,
  CreateOperatorDecisionResponse,
  CreateAdminUserRequest,
  CreateAdminUserResponse,
  DashboardOverview,
  DailyReviewLitePayload,
  DataToBriefDocling90ReviewPayload,
  DecisionEventRow,
  DecisionOutcomeRow,
  EvidenceDigestResponse,
  EvidenceDigestSnapshot,
  EvidenceDigestSnapshotDetailResponse,
  ExperimentProposalRow,
  ExperimentReplayRow,
  FactorLibraryRow,
  FactorScorePreview,
  FactorSelection,
  GlobalSearchResponse,
  MarketAnomalyContextPayload,
  MarketMonitorPayload,
  MarketDataStatus,
  MarketOverview,
  LoginRequest,
  LoginResponse,
  SectorDetail,
  SectorFundFlowItem,
  SectorHeatmapItem,
  SectorType,
  StockHeatmapPayload,
  StockMarketContextHeatmapPayload,
  OutcomeAnalyticsRow,
  OpsStageRow,
  PlatformDisplayDate,
  PlatformReadiness,
  PlatformSummary,
  PublicNewsCollectorStatus,
  PublicNewsRefreshResponse,
  PublicNewsResponse,
  ResearchReportDocument,
  ResearchReportResponse,
  ResearchReportSummary,
  ResearchCaseDetail,
  ResearchCaseResponse,
  ResearchQueueGapsResponse,
  ResearchQueueHealth,
  ResearchPublishGate,
  ResearchPublicationPackage,
  ResearchPublicationSnapshotsResponse,
  ResearchExternalDeliveryPlan,
  ResearchExternalDeliveryAttemptsResponse,
  ResearchEvidenceResponse,
  CreateResearchReviewActionRequest,
  CreateResearchReviewActionResponse,
  ReviewItemSnapshot,
  ReviewQueueResponse,
  ScoreRow,
  SnapshotListResponse,
  ShadowAnalyticsReviewRow,
  ShadowFollowUpRow,
  ShadowFollowUpResolutionRow,
  ShadowReviewDecisionRow,
  ShadowOutcomeAnalyticsRow,
  ShadowOutcomeRow,
  ShadowWatchlistRow,
  StrategyCatalogItem,
  StrategyEvidenceArtifact,
  StrategyMetricRow,
  StrategyPositionSnapshot,
  StrategyReplayPayload,
  StrategyScoreAuditSummary,
  StrategySignal,
  StrategyTrade,
  StrategyValidationRun,
  ThemeResearchUpdatesPayload,
  UpdateOperatorDecisionRequest,
  WatchlistResponse,
  WatchlistSignalRow
} from './types';

type OverviewParams = {
  tradeDate: string;
  scoreVersion: string;
  watchlistId: string;
  topN: number;
};

type MarketMonitorParams = {
  tradeDate?: string;
  scoreVersion?: string;
  topN?: number;
};

type PublicNewsParams = {
  source?: string;
  category?: string;
  q?: string;
  startTime?: string;
  endTime?: string;
  assetId?: string;
  tsCode?: string;
  minQualityScore?: number;
  limit?: number;
  offset?: number;
};

type AssetNewsParams = {
  limit?: number;
  lookbackDays?: number;
  category?: string;
  source?: string;
};

type ResearchReportParams = {
  q?: string;
  asset_id?: string;
  ts_code?: string;
  broker?: string;
  rating?: string;
  source_name?: string;
  start_date?: string;
  end_date?: string;
  has_target_price?: boolean;
  limit?: number;
  offset?: number;
};

type EvidenceDigestParams = {
  tradeDate?: string;
  lookbackDays?: number;
  scoreVersion?: string;
};

type ReviewQueueParams = {
  tradeDate?: string;
  scoreVersion?: string;
  limit?: number;
  lookbackDays?: number;
};

type DailyReviewLiteParams = {
  tradeDate?: string;
};

type ThemeResearchUpdatesParams = {
  since?: string;
  limit?: number;
};

type ResearchCaseParams = {
  tradeDate?: string;
  status?: string;
  assetId?: string;
  limit?: number;
};

type ResearchEvidenceParams = {
  assetId?: string;
  sourceType?: string;
  limit?: number;
};

type ResearchQueueHealthParams = {
  tradeDate?: string;
};

type ResearchQueueGapsParams = {
  tradeDate?: string;
  limit?: number;
};

type ResearchPublishGateParams = {
  tradeDate?: string;
};

type ResearchPublicationPreviewParams = {
  tradeDate?: string;
};

type ResearchPublicationSnapshotsParams = {
  tradeDate?: string;
  channel?: string;
  limit?: number;
};

type RequestOptions = {
  credentials?: RequestCredentials;
  csrfToken?: string;
};

export const DASHBOARD_AUTH_EXPIRED_EVENT = 'dashboard-auth-expired';
let dashboardAuthEpoch = 0;

function advanceDashboardAuthEpoch() {
  dashboardAuthEpoch += 1;
}

function csrfTokenFromCookie() {
  return (
    document.cookie
      .split(';')
      .map((part) => part.trim())
      .find((part) => part.startsWith('stock_research_csrf='))
      ?.split('=')
      .slice(1)
      .join('=') ?? ''
  );
}

export async function fetchCurrentUser(): Promise<AuthMeResponse> {
  return getJson<AuthMeResponse>('/api/auth/me', { credentials: 'include' });
}

export async function loginDashboardUser(request: LoginRequest): Promise<LoginResponse> {
  advanceDashboardAuthEpoch();
  return postJson<LoginResponse>('/api/auth/login', request, { credentials: 'include' });
}

export async function logoutDashboardUser(): Promise<{ status: string }> {
  advanceDashboardAuthEpoch();
  return postJson<{ status: string }>('/api/auth/logout', {}, { credentials: 'include', csrfToken: csrfTokenFromCookie() });
}

export async function fetchAdminUsers(): Promise<AdminUsersResponse> {
  return getJson<AdminUsersResponse>('/api/admin/users', { credentials: 'include' });
}

export async function createAdminUser(request: CreateAdminUserRequest): Promise<CreateAdminUserResponse> {
  return postJson<CreateAdminUserResponse>('/api/admin/users', request, {
    credentials: 'include',
    csrfToken: csrfTokenFromCookie()
  });
}

export async function disableAdminUser(userId: string): Promise<AdminUserActionResponse> {
  return postJson<AdminUserActionResponse>(`/api/admin/users/${encodeURIComponent(userId)}/disable`, {}, {
    credentials: 'include',
    csrfToken: csrfTokenFromCookie()
  });
}

export async function enableAdminUser(userId: string): Promise<AdminUserActionResponse> {
  return postJson<AdminUserActionResponse>(`/api/admin/users/${encodeURIComponent(userId)}/enable`, {}, {
    credentials: 'include',
    csrfToken: csrfTokenFromCookie()
  });
}

export async function resetAdminUserPassword(userId: string, password: string): Promise<AdminUserActionResponse> {
  return postJson<AdminUserActionResponse>(
    `/api/admin/users/${encodeURIComponent(userId)}/reset-password`,
    { password },
    {
      credentials: 'include',
      csrfToken: csrfTokenFromCookie()
    }
  );
}

type ResearchExternalDeliveryPlanParams = {
  publicationSnapshotId: string;
  channel?: string;
};

type ResearchExternalDeliveryAttemptsParams = {
  publicationSnapshotId?: string;
  tradeDate?: string;
  channel?: string;
  limit?: number;
};

type SnapshotFilters = {
  runId?: string;
  tradeDate?: string;
  assetId?: string;
  digestKey?: string;
  limit?: number;
};

function snapshotQuery(params: SnapshotFilters = {}) {
  const searchParams = new URLSearchParams();
  if (params.runId) searchParams.set('run_id', params.runId);
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.assetId) searchParams.set('asset_id', params.assetId);
  if (params.digestKey) searchParams.set('digest_key', params.digestKey);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  return searchParams.toString();
}

export async function fetchOverview(params: OverviewParams): Promise<DashboardOverview> {
  return getJson(
    `/api/dashboard/overview?trade_date=${encodeURIComponent(params.tradeDate)}` +
      `&score_version=${encodeURIComponent(params.scoreVersion)}` +
      `&watchlist_id=${encodeURIComponent(params.watchlistId)}` +
      `&top_n=${params.topN}`
  );
}

export async function fetchMarketMonitorEod(params: MarketMonitorParams = {}): Promise<MarketMonitorPayload> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.scoreVersion) searchParams.set('score_version', params.scoreVersion);
  searchParams.set('top_n', String(params.topN ?? 5));
  return getJson(`/api/market-monitor/eod?${searchParams.toString()}`);
}

export async function fetchMarketOverview(tradeDate: string): Promise<MarketOverview> {
  return getJson(`/api/market-monitor/overview?trade_date=${encodeURIComponent(tradeDate)}`);
}

export async function fetchSectorHeatmap(
  tradeDate: string,
  sectorType: SectorType
): Promise<{
  trade_date: string;
  updated_at: string | null;
  source: string;
  data_status: MarketDataStatus;
  warnings: string[];
  items: SectorHeatmapItem[];
}> {
  return getJson(
    `/api/market-monitor/sectors/heatmap?trade_date=${encodeURIComponent(tradeDate)}&type=${encodeURIComponent(sectorType)}`
  );
}

export async function fetchStockHeatmap(tradeDate: string): Promise<StockHeatmapPayload> {
  return getJson(
    `/api/market-monitor/stocks/heatmap?trade_date=${encodeURIComponent(tradeDate)}&market=all&period=1d&group=industry&size_by=amount`
  );
}

export async function fetchMarketAnomalyContext(tradeDate: string): Promise<MarketAnomalyContextPayload> {
  return getJson(`/api/market-monitor/anomaly-context?trade_date=${encodeURIComponent(tradeDate)}`);
}

export async function fetchStockMarketContextHeatmap(
  assetId: string,
  tradeDate: string
): Promise<StockMarketContextHeatmapPayload> {
  return getJson(
    `/api/stocks/${encodeURIComponent(assetId)}/market-context/heatmap?trade_date=${encodeURIComponent(tradeDate)}`
  );
}

export async function fetchSectorFundFlow(
  tradeDate: string,
  sectorType: SectorType
): Promise<{
  trade_date: string;
  updated_at: string | null;
  source: string;
  data_status: MarketDataStatus;
  warnings: string[];
  inflow: SectorFundFlowItem[];
  outflow: SectorFundFlowItem[];
}> {
  return getJson(
    `/api/market-monitor/sectors/fund-flow?trade_date=${encodeURIComponent(tradeDate)}&type=${encodeURIComponent(sectorType)}&period=1d`
  );
}

export async function fetchSectorDetail(tradeDate: string, sectorId: string): Promise<SectorDetail> {
  return getJson(
    `/api/market-monitor/sectors/${encodeURIComponent(sectorId)}?trade_date=${encodeURIComponent(tradeDate)}`
  );
}

export async function fetchPublicNews(params: PublicNewsParams = {}): Promise<PublicNewsResponse> {
  const searchParams = new URLSearchParams();
  if (params.source) searchParams.set('source', params.source);
  if (params.category) searchParams.set('category', params.category);
  if (params.q) searchParams.set('q', params.q);
  if (params.startTime) searchParams.set('start_time', params.startTime);
  if (params.endTime) searchParams.set('end_time', params.endTime);
  if (params.assetId) searchParams.set('asset_id', params.assetId);
  if (params.tsCode) searchParams.set('ts_code', params.tsCode);
  if (params.minQualityScore !== undefined) searchParams.set('min_quality_score', String(params.minQualityScore));
  searchParams.set('limit', String(params.limit ?? 100));
  searchParams.set('offset', String(params.offset ?? 0));
  return getJson(`/api/public-news?${searchParams.toString()}`);
}

export async function fetchPublicNewsStatus(): Promise<PublicNewsCollectorStatus> {
  return getJson('/api/public-news/status');
}

export async function fetchDataToBriefDocling90Review(): Promise<DataToBriefDocling90ReviewPayload> {
  return getJson('/api/research/data-to-brief/docling-90');
}

export async function fetchAssetNews(
  assetId: string,
  params: AssetNewsParams = {}
): Promise<AssetNewsResponse> {
  const searchParams = new URLSearchParams();
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params.lookbackDays !== undefined) searchParams.set('lookback_days', String(params.lookbackDays));
  if (params.category) searchParams.set('category', params.category);
  if (params.source) searchParams.set('source', params.source);
  const query = searchParams.toString();
  const path = `/api/assets/${encodeURIComponent(assetId)}/news`;
  return getJson(query ? `${path}?${query}` : path);
}

export async function fetchResearchReportSummary(): Promise<ResearchReportSummary> {
  return getJson('/api/research-reports/summary');
}

export async function fetchResearchReports(params: ResearchReportParams = {}): Promise<ResearchReportResponse> {
  const searchParams = new URLSearchParams();
  if (params.q) searchParams.set('q', params.q);
  if (params.asset_id) searchParams.set('asset_id', params.asset_id);
  if (params.ts_code) searchParams.set('ts_code', params.ts_code);
  if (params.broker) searchParams.set('broker', params.broker);
  if (params.rating) searchParams.set('rating', params.rating);
  if (params.source_name) searchParams.set('source_name', params.source_name);
  if (params.start_date) searchParams.set('start_date', params.start_date);
  if (params.end_date) searchParams.set('end_date', params.end_date);
  if (params.has_target_price !== undefined) searchParams.set('has_target_price', String(params.has_target_price));
  searchParams.set('limit', String(params.limit ?? 50));
  searchParams.set('offset', String(params.offset ?? 0));
  return getJson(`/api/research-reports?${searchParams.toString()}`);
}

export async function fetchResearchReportDocument(reportId: string): Promise<ResearchReportDocument> {
  return getJson(`/api/research-reports/${encodeURIComponent(reportId)}/document`);
}

export async function fetchAssetResearchReports(
  assetId: string,
  options: { limit?: number; lookbackDays?: number } = {}
): Promise<AssetResearchReportResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set('limit', String(options.limit ?? 10));
  searchParams.set('lookback_days', String(options.lookbackDays ?? 90));
  return getJson(`/api/assets/${encodeURIComponent(assetId)}/research-reports?${searchParams.toString()}`);
}

export async function fetchEvidenceDigest(
  assetId: string,
  params: EvidenceDigestParams = {}
): Promise<EvidenceDigestResponse> {
  const searchParams = new URLSearchParams();
  searchParams.set('asset_id', assetId);
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.lookbackDays !== undefined) searchParams.set('lookback_days', String(params.lookbackDays));
  if (params.scoreVersion) searchParams.set('score_version', params.scoreVersion);
  return getJson(`/api/evidence-digest?${searchParams.toString()}`);
}

export async function fetchReviewQueue(params: ReviewQueueParams = {}): Promise<ReviewQueueResponse> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.scoreVersion) searchParams.set('score_version', params.scoreVersion);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  if (params.lookbackDays !== undefined) searchParams.set('lookback_days', String(params.lookbackDays));
  const query = searchParams.toString();
  return getJson(query ? `/api/review-queue?${query}` : '/api/review-queue');
}

export async function fetchDailyReviewLite(
  params: DailyReviewLiteParams = {}
): Promise<DailyReviewLitePayload> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  const query = searchParams.toString();
  return getJson(query ? `/api/daily-review-lite?${query}` : '/api/daily-review-lite');
}

export async function fetchAssetThemeResearchContext(
  assetId: string
): Promise<AssetThemeResearchContext> {
  return getJson(`/api/assets/${encodeURIComponent(assetId)}/theme-research-context`);
}

export async function fetchThemeResearchUpdates(
  params: ThemeResearchUpdatesParams = {}
): Promise<ThemeResearchUpdatesPayload> {
  const searchParams = new URLSearchParams();
  if (params.since) searchParams.set('since', params.since);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  const query = searchParams.toString();
  return getJson(
    query
      ? `/api/research/theme-decomposition/updates?${query}`
      : '/api/research/theme-decomposition/updates'
  );
}

export async function fetchStrategyScoreAudit(tradeDate: string): Promise<StrategyScoreAuditSummary> {
  return getJson(`/api/strategy-score-audit?trade_date=${encodeURIComponent(tradeDate)}`);
}

export async function fetchReviewQueueSnapshots(
  params: SnapshotFilters = {}
): Promise<SnapshotListResponse<ReviewItemSnapshot>> {
  const query = snapshotQuery(params);
  return getJson(query ? `/api/review-queue/snapshots?${query}` : '/api/review-queue/snapshots');
}

export async function fetchEvidenceDigestSnapshots(
  params: SnapshotFilters = {}
): Promise<SnapshotListResponse<EvidenceDigestSnapshot>> {
  const query = snapshotQuery(params);
  return getJson(query ? `/api/evidence-digest/snapshots?${query}` : '/api/evidence-digest/snapshots');
}

export async function fetchEvidenceDigestSnapshot(
  snapshotId: string
): Promise<EvidenceDigestSnapshotDetailResponse> {
  return getJson(`/api/evidence-digest/snapshots/${encodeURIComponent(snapshotId)}`);
}

export async function fetchResearchCases(params: ResearchCaseParams = {}): Promise<ResearchCaseResponse> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.status) searchParams.set('status', params.status);
  if (params.assetId) searchParams.set('asset_id', params.assetId);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  const query = searchParams.toString();
  return getJson(query ? `/api/research/cases?${query}` : '/api/research/cases');
}

export async function fetchResearchCaseDetail(caseId: string): Promise<ResearchCaseDetail> {
  return getJson(`/api/research/cases/${encodeURIComponent(caseId)}`);
}

export async function fetchResearchQueueHealth(params: ResearchQueueHealthParams = {}): Promise<ResearchQueueHealth> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  const query = searchParams.toString();
  return getJson(query ? `/api/research/queue/health?${query}` : '/api/research/queue/health');
}

export async function fetchResearchQueueGaps(params: ResearchQueueGapsParams = {}): Promise<ResearchQueueGapsResponse> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  const query = searchParams.toString();
  return getJson(query ? `/api/research/queue/gaps?${query}` : '/api/research/queue/gaps');
}

export async function fetchResearchPublishGate(params: ResearchPublishGateParams = {}): Promise<ResearchPublishGate> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  const query = searchParams.toString();
  return getJson(query ? `/api/research/queue/publish-gate?${query}` : '/api/research/queue/publish-gate');
}

export async function fetchResearchPublicationPreview(
  params: ResearchPublicationPreviewParams = {}
): Promise<ResearchPublicationPackage> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  const query = searchParams.toString();
  return getJson(query ? `/api/research/publication/preview?${query}` : '/api/research/publication/preview');
}

export async function fetchResearchPublicationSnapshots(
  params: ResearchPublicationSnapshotsParams = {}
): Promise<ResearchPublicationSnapshotsResponse> {
  const searchParams = new URLSearchParams();
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.channel) searchParams.set('channel', params.channel);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  const query = searchParams.toString();
  return getJson(query ? `/api/research/publication/snapshots?${query}` : '/api/research/publication/snapshots');
}

export async function fetchResearchExternalDeliveryPlan(
  params: ResearchExternalDeliveryPlanParams
): Promise<ResearchExternalDeliveryPlan> {
  const searchParams = new URLSearchParams();
  searchParams.set('publication_snapshot_id', params.publicationSnapshotId);
  if (params.channel) searchParams.set('channel', params.channel);
  return getJson(`/api/research/publication/delivery-plan?${searchParams.toString()}`);
}

export async function fetchResearchExternalDeliveryAttempts(
  params: ResearchExternalDeliveryAttemptsParams = {}
): Promise<ResearchExternalDeliveryAttemptsResponse> {
  const searchParams = new URLSearchParams();
  if (params.publicationSnapshotId) searchParams.set('publication_snapshot_id', params.publicationSnapshotId);
  if (params.tradeDate) searchParams.set('trade_date', params.tradeDate);
  if (params.channel) searchParams.set('channel', params.channel);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  const query = searchParams.toString();
  return getJson(query ? `/api/research/publication/delivery-attempts?${query}` : '/api/research/publication/delivery-attempts');
}

export async function createResearchReviewAction(
  request: CreateResearchReviewActionRequest
): Promise<CreateResearchReviewActionResponse> {
  return postJson('/api/research/review-actions', request);
}

export async function fetchResearchEvidence(params: ResearchEvidenceParams = {}): Promise<ResearchEvidenceResponse> {
  const searchParams = new URLSearchParams();
  if (params.assetId) searchParams.set('asset_id', params.assetId);
  if (params.sourceType) searchParams.set('source_type', params.sourceType);
  if (params.limit !== undefined) searchParams.set('limit', String(params.limit));
  const query = searchParams.toString();
  return getJson(query ? `/api/research/evidence?${query}` : '/api/research/evidence');
}

export async function searchAssets(q: string, limit = 10) {
  const payload = await getJson<AssetSearchResponse>(
    `/api/assets/search?q=${encodeURIComponent(q)}&limit=${limit}`
  );
  return payload.items;
}

export async function fetchGlobalSearch(q: string, limit = 5): Promise<GlobalSearchResponse> {
  return getJson(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`);
}

export async function fetchWatchlistSignals(watchlistId: string, tradeDate: string): Promise<WatchlistSignalRow[]> {
  const payload = await getJson<WatchlistResponse>(
    `/api/watchlists/${encodeURIComponent(watchlistId)}?trade_date=${encodeURIComponent(tradeDate)}`
  );
  return payload.items;
}

export async function refreshPublicNews(): Promise<PublicNewsRefreshResponse> {
  const response = await fetch('/api/public-news/refresh', { method: 'POST' });
  if (!response.ok) {
    throw new Error(`POST /api/public-news/refresh failed with ${response.status}`);
  }
  return response.json() as Promise<PublicNewsRefreshResponse>;
}

export async function fetchDailyBars(
  assetId: string,
  startDate: string | undefined,
  endDate: string,
  options: string | { resolution?: string; adjustType?: string } = 'qfq'
): Promise<BarPoint[]> {
  const adjustType = typeof options === 'string' ? options : options.adjustType ?? 'qfq';
  const resolution = typeof options === 'string' ? undefined : options.resolution;
  const queryParts = [
    ...(startDate ? [`start_date=${encodeURIComponent(startDate)}`] : []),
    `end_date=${encodeURIComponent(endDate)}`,
    `adjust_type=${encodeURIComponent(adjustType)}`
  ];
  if (resolution) queryParts.push(`resolution=${encodeURIComponent(resolution)}`);
  const payload = await getJson<{ items: BarPoint[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/bars?${queryParts.join('&')}`
  );
  return payload.items;
}

export async function fetchAssetScore(
  assetId: string,
  tradeDate: string,
  scoreVersion = 'manual_v1'
): Promise<ScoreRow | null> {
  const payload = await getJson<{ item: ScoreRow | null }>(
    `/api/assets/${encodeURIComponent(assetId)}/scores?trade_date=${encodeURIComponent(tradeDate)}` +
      `&score_version=${encodeURIComponent(scoreVersion)}`
  );
  return payload.item;
}

export async function fetchAssetSignals(assetId: string, tradeDate: string): Promise<WatchlistSignalRow[]> {
  const payload = await getJson<{ items: WatchlistSignalRow[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/signals?trade_date=${encodeURIComponent(tradeDate)}`
  );
  return payload.items;
}

export async function fetchAssetDecisions(
  assetId: string,
  startDate: string,
  endDate: string,
  limit = 20
): Promise<DecisionEventRow[]> {
  const payload = await getJson<{ items: DecisionEventRow[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/decisions?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}`
  );
  return payload.items;
}

export async function createOperatorDecision(
  request: CreateOperatorDecisionRequest
): Promise<CreateOperatorDecisionResponse> {
  return postJson('/api/operator-decisions', request);
}

export async function updateOperatorDecision(
  eventId: string,
  request: UpdateOperatorDecisionRequest
): Promise<DecisionEventRow> {
  const payload = await patchJson<{ item: DecisionEventRow }>(
    `/api/operator-decisions/${encodeURIComponent(eventId)}`,
    request
  );
  return payload.item;
}

export async function fetchAssetOutcomes(
  assetId: string,
  startDate: string,
  endDate: string,
  options: { reviewSessionId?: string; limit?: number } = {}
): Promise<DecisionOutcomeRow[]> {
  const limit = options.limit ?? 20;
  const reviewSession = options.reviewSessionId
    ? `&review_session_id=${encodeURIComponent(options.reviewSessionId)}`
    : '';
  const payload = await getJson<{ items: DecisionOutcomeRow[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/outcomes?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}${reviewSession}`
  );
  return payload.items;
}

export async function fetchOutcomeAnalytics(
  startDate: string,
  endDate: string,
  options: { reviewSessionId?: string; limit?: number } = {}
): Promise<OutcomeAnalyticsRow[]> {
  const limit = options.limit ?? 20;
  const reviewSession = options.reviewSessionId
    ? `&review_session_id=${encodeURIComponent(options.reviewSessionId)}`
    : '';
  const payload = await getJson<{ items: OutcomeAnalyticsRow[] }>(
    `/api/outcome-analytics?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}${reviewSession}`
  );
  return payload.items;
}

export async function fetchExperimentProposals(
  startDate: string,
  endDate: string,
  options: { status?: string; limit?: number } = {}
): Promise<ExperimentProposalRow[]> {
  const limit = options.limit ?? 20;
  const status = options.status ? `&status=${encodeURIComponent(options.status)}` : '';
  const payload = await getJson<{ items: ExperimentProposalRow[] }>(
    `/api/experiment-proposals?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}${status}`
  );
  return payload.items;
}

export async function fetchExperimentReplay(
  startDate: string,
  endDate: string,
  options: { status?: string; limit?: number } = {}
): Promise<ExperimentReplayRow[]> {
  const limit = options.limit ?? 20;
  const status = options.status ? `&status=${encodeURIComponent(options.status)}` : '';
  const payload = await getJson<{ items: ExperimentReplayRow[] }>(
    `/api/experiment-replay?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}${status}`
  );
  return payload.items;
}

export async function fetchShadowWatchlist(
  startDate: string,
  endDate: string,
  options: { status?: string; limit?: number } = {}
): Promise<ShadowWatchlistRow[]> {
  const limit = options.limit ?? 20;
  const status = options.status ? `&status=${encodeURIComponent(options.status)}` : '';
  const payload = await getJson<{ items: ShadowWatchlistRow[] }>(
    `/api/shadow-watchlist?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}${status}`
  );
  return payload.items;
}

export async function fetchShadowOutcomes(
  startDate: string,
  endDate: string,
  options: { outcomeStatus?: string; limit?: number } = {}
): Promise<ShadowOutcomeRow[]> {
  const limit = options.limit ?? 20;
  const status = options.outcomeStatus ? `&outcome_status=${encodeURIComponent(options.outcomeStatus)}` : '';
  const payload = await getJson<{ items: ShadowOutcomeRow[] }>(
    `/api/shadow-outcomes?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}${status}`
  );
  return payload.items;
}

export async function fetchShadowOutcomeAnalytics(
  startDate: string,
  endDate: string,
  options: { limit?: number } = {}
): Promise<ShadowOutcomeAnalyticsRow[]> {
  const limit = options.limit ?? 20;
  const payload = await getJson<{ items: ShadowOutcomeAnalyticsRow[] }>(
    `/api/shadow-outcome-analytics?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}`
  );
  return payload.items;
}

export async function fetchShadowAnalyticsReview(
  startDate: string,
  endDate: string,
  options: { limit?: number } = {}
): Promise<ShadowAnalyticsReviewRow[]> {
  const limit = options.limit ?? 20;
  const payload = await getJson<{ items: ShadowAnalyticsReviewRow[] }>(
    `/api/shadow-analytics-review?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}`
  );
  return payload.items;
}

export async function fetchShadowReviewDecisions(
  startDate: string,
  endDate: string,
  options: { limit?: number } = {}
): Promise<ShadowReviewDecisionRow[]> {
  const limit = options.limit ?? 20;
  const payload = await getJson<{ items: ShadowReviewDecisionRow[] }>(
    `/api/shadow-review-decisions?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}`
  );
  return payload.items;
}

export async function fetchShadowFollowUpQueue(
  startDate: string,
  endDate: string,
  options: { limit?: number } = {}
): Promise<ShadowFollowUpRow[]> {
  const limit = options.limit ?? 20;
  const payload = await getJson<{ items: ShadowFollowUpRow[] }>(
    `/api/shadow-follow-up-queue?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}`
  );
  return payload.items;
}

export async function fetchShadowFollowUpResolution(
  startDate: string,
  endDate: string,
  options: { limit?: number } = {}
): Promise<ShadowFollowUpResolutionRow[]> {
  const limit = options.limit ?? 20;
  const payload = await getJson<{ items: ShadowFollowUpResolutionRow[] }>(
    `/api/shadow-follow-up-resolution?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&limit=${limit}`
  );
  return payload.items;
}

export async function fetchStrategyValidationRuns(
  options: { strategyId?: string } = {}
): Promise<StrategyValidationRun[]> {
  const strategy = options.strategyId ? `?strategy_id=${encodeURIComponent(options.strategyId)}` : '';
  const payload = await getJson<{ items: StrategyValidationRun[] }>(`/api/strategy-validation/runs${strategy}`);
  return payload.items;
}

export async function fetchStrategyValidationSignals(
  runId: string,
  options: { assetId?: string; signalBucket?: string; riskBucket?: string } = {}
): Promise<StrategySignal[]> {
  const params = new URLSearchParams();
  if (options.assetId) params.set('asset_id', options.assetId);
  if (options.signalBucket) params.set('signal_bucket', options.signalBucket);
  if (options.riskBucket) params.set('risk_bucket', options.riskBucket);
  const suffix = params.toString() ? `?${params.toString()}` : '';
  const payload = await getJson<{ items: StrategySignal[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/signals${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationTrades(
  runId: string,
  options: { assetId?: string } = {}
): Promise<StrategyTrade[]> {
  const suffix = options.assetId ? `?asset_id=${encodeURIComponent(options.assetId)}` : '';
  const payload = await getJson<{ items: StrategyTrade[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/trades${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationPositions(
  runId: string,
  options: { assetId?: string } = {}
): Promise<StrategyPositionSnapshot[]> {
  const suffix = options.assetId ? `?asset_id=${encodeURIComponent(options.assetId)}` : '';
  const payload = await getJson<{ items: StrategyPositionSnapshot[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/positions${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationMetrics(
  runId: string,
  options: { metricLevel?: string } = {}
): Promise<StrategyMetricRow[]> {
  const suffix = options.metricLevel ? `?metric_level=${encodeURIComponent(options.metricLevel)}` : '';
  const payload = await getJson<{ items: StrategyMetricRow[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/metrics${suffix}`
  );
  return payload.items;
}

export async function fetchStrategyValidationArtifacts(runId: string): Promise<StrategyEvidenceArtifact[]> {
  const payload = await getJson<{ items: StrategyEvidenceArtifact[] }>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}/artifacts`
  );
  return payload.items;
}

export async function fetchStrategyValidationReplay(
  runId: string,
  assetId: string,
  startDate: string,
  endDate: string,
  adjustType = 'qfq'
): Promise<StrategyReplayPayload> {
  return getJson<StrategyReplayPayload>(
    `/api/strategy-validation/runs/${encodeURIComponent(runId)}` +
      `/assets/${encodeURIComponent(assetId)}/replay?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&adjust_type=${encodeURIComponent(adjustType)}`
  );
}

export async function fetchPlatformSummary(): Promise<PlatformSummary> {
  return getJson<PlatformSummary>('/api/platform/summary');
}

export async function fetchPlatformReadiness(): Promise<PlatformReadiness> {
  return getJson<PlatformReadiness>('/api/platform/readiness');
}

export async function fetchPlatformDisplayDate(): Promise<PlatformDisplayDate> {
  return getJson<PlatformDisplayDate>('/api/platform/display-date');
}

export async function fetchOpsStages(): Promise<OpsStageRow[]> {
  const payload = await getJson<{ items: OpsStageRow[] }>('/api/ops/stages');
  return payload.items;
}

export async function fetchStrategyCatalog(): Promise<StrategyCatalogItem[]> {
  const payload = await getJson<{ items: StrategyCatalogItem[] }>('/api/strategies/catalog');
  return payload.items;
}

export async function fetchFactorLibrary(): Promise<FactorLibraryRow[]> {
  const payload = await getJson<{ items: FactorLibraryRow[] }>('/api/factors/library');
  return payload.items;
}

export async function fetchFactorScorePreview(
  tradeDate: string,
  factors: FactorSelection[],
  topN: number
): Promise<FactorScorePreview> {
  const encodedFactors = factors
    .map((factor) => `${factor.factor_name}:${factor.direction}:${factor.weight}`)
    .join(',');
  return getJson<FactorScorePreview>(
    `/api/factors/score-preview?trade_date=${encodeURIComponent(tradeDate)}` +
      `&factors=${encodeURIComponent(encodedFactors)}&top_n=${topN}`
  );
}

export async function fetchAssetProfile(
  assetId: string,
  tradeDate: string,
  startDate: string,
  endDate: string,
  scoreVersion = 'manual_v1',
  adjustType = 'qfq'
): Promise<AssetProfile> {
  return getJson<AssetProfile>(
    `/api/assets/${encodeURIComponent(assetId)}/profile?trade_date=${encodeURIComponent(tradeDate)}` +
      `&start_date=${encodeURIComponent(startDate)}&end_date=${encodeURIComponent(endDate)}` +
      `&score_version=${encodeURIComponent(scoreVersion)}&adjust_type=${encodeURIComponent(adjustType)}`
  );
}

export async function fetchBacktestStrategies(): Promise<StrategyCatalogItem[]> {
  const payload = await getJson<{ items: StrategyCatalogItem[] }>('/api/backtests/strategies');
  return payload.items;
}

export async function runBacktest(request: BacktestRunRequest): Promise<BacktestRunResult> {
  const job = await submitBacktestJob(request);
  return waitForBacktestJob(job.job_id);
}

export async function runFreshBacktest(request: BacktestRunRequest): Promise<BacktestRunResult> {
  return postBacktest('/api/backtests/run-fresh', request);
}

export async function submitBacktestJob(request: BacktestRunRequest): Promise<BacktestJobResponse> {
  return postJson('/api/backtests/jobs', request);
}

export async function fetchBacktestJob(jobId: string): Promise<BacktestJobResponse> {
  return getJson(`/api/backtests/jobs/${encodeURIComponent(jobId)}`);
}

async function waitForBacktestJob(jobId: string): Promise<BacktestRunResult> {
  for (let attempt = 0; attempt < 360; attempt += 1) {
    const job = await fetchBacktestJob(jobId);
    if (job.status === 'succeeded' && job.result) {
      return job.result;
    }
    if (job.status === 'failed') {
      throw new Error(job.error || `Backtest job ${jobId} failed`);
    }
    await delay(1000);
  }
  throw new Error(`Backtest job ${jobId} timed out`);
}

async function postBacktest(url: string, request: BacktestRunRequest): Promise<BacktestRunResult> {
  return postJson(url, request);
}

async function postJson<T>(url: string, request: unknown, options: RequestOptions = {}): Promise<T> {
  const authEpoch = authEpochForRequest(url, options);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (options.csrfToken) {
    headers['X-CSRF-Token'] = options.csrfToken;
  }
  const response = await fetch(url, {
    method: 'POST',
    headers,
    credentials: options.credentials,
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    notifyAuthExpired(url, response.status, options, authEpoch);
    const detail = await responseErrorDetail(response);
    throw new Error(`POST ${url} failed with ${response.status}${detail ? `: ${detail}` : ''}`);
  }
  return response.json() as Promise<T>;
}

async function responseErrorDetail(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === 'string') return payload.detail;
    if (payload.detail) return JSON.stringify(payload.detail);
  } catch {
    return '';
  }
  return '';
}

async function patchJson<T>(url: string, request: unknown, options: RequestOptions = {}): Promise<T> {
  const authEpoch = authEpochForRequest(url, options);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (options.csrfToken) {
    headers['X-CSRF-Token'] = options.csrfToken;
  }
  const response = await fetch(url, {
    method: 'PATCH',
    headers,
    credentials: options.credentials,
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    notifyAuthExpired(url, response.status, options, authEpoch);
    throw new Error(`PATCH ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function getJson<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const authEpoch = authEpochForRequest(url, options);
  const response = options.credentials ? await fetch(url, { credentials: options.credentials }) : await fetch(url);
  if (!response.ok) {
    notifyAuthExpired(url, response.status, options, authEpoch);
    throw new Error(`GET ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function authEpochForRequest(url: string, options: RequestOptions) {
  if (options.credentials !== 'include') return null;
  if (typeof window === 'undefined') return url.startsWith('/') ? dashboardAuthEpoch : null;
  const requestUrl = new URL(url, window.location.href);
  return requestUrl.origin === window.location.origin ? dashboardAuthEpoch : null;
}

function notifyAuthExpired(url: string, status: number, options: RequestOptions, requestAuthEpoch: number | null) {
  if (
    status !== 401 ||
    options.credentials !== 'include' ||
    url === '/api/auth/login' ||
    url === '/api/auth/logout' ||
    requestAuthEpoch === null ||
    requestAuthEpoch !== dashboardAuthEpoch
  ) {
    return;
  }
  if (typeof window === 'undefined') {
    return;
  }
  advanceDashboardAuthEpoch();
  window.dispatchEvent(new CustomEvent(DASHBOARD_AUTH_EXPIRED_EVENT));
}
