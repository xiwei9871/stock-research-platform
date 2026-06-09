import type {
  BarPoint,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
  OutcomeAnalyticsRow,
  ScoreRow,
  ShadowAnalyticsReviewRow,
  ShadowFollowUpRow,
  ShadowFollowUpResolutionRow,
  ShadowReviewDecisionRow,
  ShadowOutcomeAnalyticsRow,
  ShadowOutcomeRow,
  ShadowWatchlistRow,
  StrategyEvidenceArtifact,
  StrategyMetricRow,
  StrategyPositionSnapshot,
  StrategyReplayPayload,
  StrategySignal,
  StrategyTrade,
  StrategyValidationRun,
  WatchlistSignalRow
} from './types';

type OverviewParams = {
  tradeDate: string;
  scoreVersion: string;
  watchlistId: string;
  topN: number;
};

export async function fetchOverview(params: OverviewParams): Promise<DashboardOverview> {
  return getJson(
    `/api/dashboard/overview?trade_date=${encodeURIComponent(params.tradeDate)}` +
      `&score_version=${encodeURIComponent(params.scoreVersion)}` +
      `&watchlist_id=${encodeURIComponent(params.watchlistId)}` +
      `&top_n=${params.topN}`
  );
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

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}
