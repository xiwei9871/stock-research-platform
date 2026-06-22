import type {
  AdminUser,
  ApiOkResponse,
  BarPoint,
  CreateMyReviewItemPayload,
  CreateMyReviewSessionPayload,
  CreateMyWatchlistItemPayload,
  CreateUserPayload,
  CurrentUser,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
  OutcomeAnalyticsRow,
  PublicNewsRefreshResponse,
  PublicNewsResponse,
  ScoreRow,
  ShadowAnalyticsReviewRow,
  ShadowFollowUpRow,
  ShadowFollowUpResolutionRow,
  ShadowReviewDecisionRow,
  ShadowOutcomeAnalyticsRow,
  ShadowOutcomeRow,
  ShadowWatchlistRow,
  UpdateMyReviewItemPayload,
  UpdateMyReviewSessionPayload,
  UpdateMyWatchlistItemPayload,
  UserReviewItem,
  UserReviewSession,
  UserWatchlistItem,
  WatchlistSignalRow
} from './types';
import {
  deleteSessionJson,
  getJson,
  getSessionJson,
  patchSessionJson,
  postJson,
  postSessionJson
} from './http';

type OverviewParams = {
  tradeDate: string;
  scoreVersion: string;
  watchlistId: string;
  topN: number;
};

type PublicNewsParams = {
  source?: string;
  category?: string;
  q?: string;
  limit?: number;
  offset?: number;
};

export async function fetchOverview(params: OverviewParams): Promise<DashboardOverview> {
  return getJson(
    `/api/dashboard/overview?trade_date=${encodeURIComponent(params.tradeDate)}` +
      `&score_version=${encodeURIComponent(params.scoreVersion)}` +
      `&watchlist_id=${encodeURIComponent(params.watchlistId)}` +
      `&top_n=${params.topN}`
  );
}

export async function fetchPublicNews(params: PublicNewsParams = {}): Promise<PublicNewsResponse> {
  const searchParams = new URLSearchParams();
  if (params.source) searchParams.set('source', params.source);
  if (params.category) searchParams.set('category', params.category);
  if (params.q) searchParams.set('q', params.q);
  searchParams.set('limit', String(params.limit ?? 100));
  searchParams.set('offset', String(params.offset ?? 0));
  return getJson(`/api/public-news?${searchParams.toString()}`);
}

export async function refreshPublicNews(): Promise<PublicNewsRefreshResponse> {
  return postJson('/api/public-news/refresh');
}

export async function fetchCurrentUser(): Promise<CurrentUser> {
  return getSessionJson('/api/auth/me');
}

export async function login(identifier: string, password: string): Promise<CurrentUser> {
  return postSessionJson('/api/auth/login', { identifier, password });
}

export async function logout(): Promise<ApiOkResponse> {
  return postSessionJson('/api/auth/logout', undefined, { csrf: true });
}

export async function fetchDailyBars(
  assetId: string,
  startDate: string | undefined,
  endDate: string,
  options: { resolution?: string; adjustType?: string } = {}
): Promise<BarPoint[]> {
  const searchParams = new URLSearchParams();
  if (startDate) searchParams.set('start_date', startDate);
  searchParams.set('end_date', endDate);
  searchParams.set('adjust_type', options.adjustType ?? 'qfq');
  if (options.resolution) searchParams.set('resolution', options.resolution);
  const payload = await getJson<{ items: BarPoint[] }>(
    `/api/assets/${encodeURIComponent(assetId)}/bars?${searchParams.toString()}`
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

export async function fetchMyWatchlist(): Promise<UserWatchlistItem[]> {
  const payload = await getSessionJson<{ items: UserWatchlistItem[] }>('/api/my/watchlist');
  return payload.items;
}

export async function createMyWatchlistItem(
  payload: CreateMyWatchlistItemPayload
): Promise<UserWatchlistItem> {
  return postSessionJson('/api/my/watchlist/items', payload, { csrf: true });
}

export async function updateMyWatchlistItem(
  assetId: string,
  payload: UpdateMyWatchlistItemPayload
): Promise<UserWatchlistItem> {
  return patchSessionJson(`/api/my/watchlist/items/${encodeURIComponent(assetId)}`, payload, { csrf: true });
}

export async function removeMyWatchlistItem(assetId: string): Promise<ApiOkResponse> {
  return deleteSessionJson(`/api/my/watchlist/items/${encodeURIComponent(assetId)}`, { csrf: true });
}

export async function fetchMyReviewSessions(): Promise<UserReviewSession[]> {
  const payload = await getSessionJson<{ items: UserReviewSession[] }>('/api/my/reviews');
  return payload.items;
}

export async function fetchMyReviewSession(sessionId: number): Promise<UserReviewSession> {
  return getSessionJson(`/api/my/reviews/${sessionId}`);
}

export async function createMyReviewSession(
  payload: CreateMyReviewSessionPayload
): Promise<UserReviewSession> {
  return postSessionJson('/api/my/reviews', payload, { csrf: true });
}

export async function updateMyReviewSession(
  sessionId: number,
  payload: UpdateMyReviewSessionPayload
): Promise<UserReviewSession> {
  return patchSessionJson(`/api/my/reviews/${sessionId}`, payload, { csrf: true });
}

export async function createMyReviewItem(
  sessionId: number,
  payload: CreateMyReviewItemPayload
): Promise<UserReviewItem> {
  return postSessionJson(`/api/my/reviews/${sessionId}/items`, payload, { csrf: true });
}

export async function updateMyReviewItem(
  sessionId: number,
  itemId: number,
  payload: UpdateMyReviewItemPayload
): Promise<UserReviewItem> {
  return patchSessionJson(`/api/my/reviews/${sessionId}/items/${itemId}`, payload, { csrf: true });
}

export async function removeMyReviewItem(sessionId: number, itemId: number): Promise<ApiOkResponse> {
  return deleteSessionJson(`/api/my/reviews/${sessionId}/items/${itemId}`, { csrf: true });
}

export async function fetchUsers(): Promise<AdminUser[]> {
  const payload = await getSessionJson<{ items: AdminUser[] }>('/api/admin/users');
  return payload.items;
}

export async function createUser(payload: CreateUserPayload): Promise<AdminUser> {
  return postSessionJson('/api/admin/users', payload, { csrf: true });
}

export async function resetUserPassword(userId: number, password: string): Promise<ApiOkResponse> {
  return postSessionJson(`/api/admin/users/${userId}/reset-password`, { password }, { csrf: true });
}

export async function disableUser(userId: number): Promise<ApiOkResponse> {
  return postSessionJson(`/api/admin/users/${userId}/disable`, undefined, { csrf: true });
}

export async function enableUser(userId: number): Promise<ApiOkResponse> {
  return postSessionJson(`/api/admin/users/${userId}/enable`, undefined, { csrf: true });
}
