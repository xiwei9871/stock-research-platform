import type {
  AssetNewsResponse,
  AssetSearchResponse,
  AssetProfile,
  AssetResearchReportResponse,
  BarPoint,
  BacktestJobResponse,
  BacktestRunRequest,
  BacktestRunResult,
  CreateOperatorDecisionRequest,
  CreateOperatorDecisionResponse,
  DashboardOverview,
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
  MarketMonitorPayload,
  OutcomeAnalyticsRow,
  PlatformReadiness,
  PlatformSummary,
  PublicNewsCollectorStatus,
  PublicNewsRefreshResponse,
  PublicNewsResponse,
  ResearchReportResponse,
  ResearchReportSummary,
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
  StrategySignal,
  StrategyTrade,
  StrategyValidationRun,
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
  startDate: string,
  endDate: string,
  adjustType = 'qfq'
): Promise<BarPoint[]> {
  const payload = await getJson<{ items: BarPoint[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/bars?start_date=${encodeURIComponent(startDate)}` +
      `&end_date=${encodeURIComponent(endDate)}&adjust_type=${encodeURIComponent(adjustType)}`
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

async function postJson<T>(url: string, request: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    throw new Error(`POST ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function patchJson<T>(url: string, request: unknown): Promise<T> {
  const response = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request)
  });
  if (!response.ok) {
    throw new Error(`PATCH ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function delay(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
