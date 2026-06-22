import { describe, expect, it, vi } from 'vitest';
import {
  createMyReviewItem,
  createMyWatchlistItem,
  createUser,
  fetchDailyBars,
  fetchAssetDecisions,
  fetchCurrentUser,
  fetchMyReviewSession,
  fetchAssetOutcomes,
  fetchExperimentProposals,
  fetchExperimentReplay,
  login,
  logout,
  fetchOutcomeAnalytics,
  fetchOverview,
  fetchPublicNews,
  refreshPublicNews,
  fetchShadowAnalyticsReview,
  fetchShadowFollowUpQueue,
  fetchShadowFollowUpResolution,
  fetchShadowReviewDecisions,
  fetchShadowOutcomeAnalytics,
  fetchShadowOutcomes,
  fetchShadowWatchlist,
  updateMyReviewItem,
  updateMyReviewSession
} from '../src/api/client';
import { deleteSessionJson, setCsrfCookieName } from '../src/api/http';

describe('dashboard API client', () => {
  it('fetches overview with query params', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ trade_date: '2026-05-29', top_scores: [], watchlist_signals: [], reports: [] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchOverview({
      tradeDate: '2026-05-29',
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 20
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/dashboard/overview?trade_date=2026-05-29&score_version=manual_v1&watchlist_id=default&top_n=20'
    );
    expect(result.trade_date).toBe('2026-05-29');
  });

  it('fetches public news with filters and pagination', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ news_id: 'news-1', title: '全球快讯' }], warnings: [] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchPublicNews({
      source: 'sina_finance',
      category: 'live',
      q: '快讯',
      limit: 10,
      offset: 2
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/public-news?source=sina_finance&category=live&q=%E5%BF%AB%E8%AE%AF&limit=10&offset=2'
    );
    expect(result.items[0].title).toBe('全球快讯');
  });

  it('refreshes public news through POST', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ stored: 2, counts_by_category: { live: 2 }, warnings: [] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await refreshPublicNews();

    expect(fetchMock).toHaveBeenCalledWith('/api/public-news/refresh', { method: 'POST' });
    expect(result.counts_by_category.live).toBe(2);
  });

  it('fetches asset bars with an explicit resolution', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ time: '2026-05-29 10:00:00', close: 10.5 }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchDailyBars('000001.SZ', '2026-05-29', '2026-05-29', {
      resolution: '30m',
      adjustType: 'raw'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/assets/000001.SZ/bars?start_date=2026-05-29&end_date=2026-05-29&adjust_type=raw&resolution=30m'
    );
    expect(result[0].time).toBe('2026-05-29 10:00:00');
  });

  it('fetches asset decisions with date range and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ asset_id: '000001.SZ', decision_label: 'candidate' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchAssetDecisions('000001.SZ', '2026-05-01', '2026-05-30', 20);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/assets/000001.SZ/decisions?start_date=2026-05-01&end_date=2026-05-30&limit=20'
    );
    expect(result[0].decision_label).toBe('candidate');
  });

  it('fetches asset outcomes with optional review session and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ asset_id: '000001.SZ', outcome_status: 'complete' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchAssetOutcomes('000001.SZ', '2026-05-01', '2026-05-30', {
      reviewSessionId: 'morning-review',
      limit: 10
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/assets/000001.SZ/outcomes?start_date=2026-05-01&end_date=2026-05-30' +
        '&limit=10&review_session_id=morning-review'
    );
    expect(result[0].outcome_status).toBe('complete');
  });

  it('fetches outcome analytics summary with optional review session and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ analytics_level: 'decision_label', group_value: 'candidate' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchOutcomeAnalytics('2026-05-01', '2026-06-30', {
      reviewSessionId: 'morning-review',
      limit: 12
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/outcome-analytics?start_date=2026-05-01&end_date=2026-06-30' +
        '&limit=12&review_session_id=morning-review'
    );
    expect(result[0].group_value).toBe('candidate');
  });

  it('fetches experiment proposal summary with optional status and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ proposal_id: 'p10-proposal:001', status: 'approved_for_experiment' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchExperimentProposals('2026-05-01', '2026-06-30', {
      status: 'approved_for_experiment',
      limit: 12
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/experiment-proposals?start_date=2026-05-01&end_date=2026-06-30' +
        '&limit=12&status=approved_for_experiment'
    );
    expect(result[0].proposal_id).toBe('p10-proposal:001');
  });

  it('fetches experiment replay summary with optional status and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ replay_result_id: 'p11-replay:001', replay_status: 'passed_offline_replay' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchExperimentReplay('2026-01-01', '2026-06-30', {
      status: 'passed_offline_replay',
      limit: 12
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/experiment-replay?start_date=2026-01-01&end_date=2026-06-30' +
        '&limit=12&status=passed_offline_replay'
    );
    expect(result[0].replay_result_id).toBe('p11-replay:001');
  });

  it('fetches shadow watchlist summary with optional status and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ shadow_candidate_id: 'p12-shadow:001', status: 'shadow_ready' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchShadowWatchlist('2026-06-01', '2026-06-30', {
      status: 'shadow_ready',
      limit: 12
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shadow-watchlist?start_date=2026-06-01&end_date=2026-06-30' +
        '&limit=12&status=shadow_ready'
    );
    expect(result[0].shadow_candidate_id).toBe('p12-shadow:001');
  });

  it('fetches shadow outcomes summary with optional status and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ shadow_candidate_id: 'p12-shadow:001', outcome_status: 'complete' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchShadowOutcomes('2026-06-01', '2026-07-31', {
      outcomeStatus: 'complete',
      limit: 12
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shadow-outcomes?start_date=2026-06-01&end_date=2026-07-31' +
        '&limit=12&outcome_status=complete'
    );
    expect(result[0].shadow_candidate_id).toBe('p12-shadow:001');
  });

  it('fetches shadow outcome analytics summary with limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ group_key: 'trend_shadow|shadow_ready' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchShadowOutcomeAnalytics('2026-06-01', '2026-08-31', { limit: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shadow-outcome-analytics?start_date=2026-06-01&end_date=2026-08-31&limit=20'
    );
    expect(result[0].group_key).toBe('trend_shadow|shadow_ready');
  });

  it('fetches shadow analytics review summary with limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ review_status: 'research_follow_up_candidate' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchShadowAnalyticsReview('2026-06-01', '2026-08-31', { limit: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shadow-analytics-review?start_date=2026-06-01&end_date=2026-08-31&limit=20'
    );
    expect(result[0].review_status).toBe('research_follow_up_candidate');
  });

  it('fetches shadow review decisions summary with limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ decision_status: 'open_research_follow_up' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchShadowReviewDecisions('2026-06-01', '2026-08-31', { limit: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shadow-review-decisions?start_date=2026-06-01&end_date=2026-08-31&limit=20'
    );
    expect(result[0].decision_status).toBe('open_research_follow_up');
  });

  it('fetches shadow follow-up queue summary with limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ follow_up_status: 'collect_more_evidence' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchShadowFollowUpQueue('2026-06-01', '2026-08-31', { limit: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shadow-follow-up-queue?start_date=2026-06-01&end_date=2026-08-31&limit=20'
    );
    expect(result[0].follow_up_status).toBe('collect_more_evidence');
  });

  it('fetches shadow follow-up resolution summary with limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ resolution_status: 'stale_unresolved' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchShadowFollowUpResolution('2026-06-01', '2026-08-31', { limit: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/shadow-follow-up-resolution?start_date=2026-06-01&end_date=2026-08-31&limit=20'
    );
    expect(result[0].resolution_status).toBe('stale_unresolved');
  });

  it('sends credentials on auth requests', async () => {
    Object.defineProperty(document, 'cookie', {
      value: 'stock_research_csrf=csrf-1',
      configurable: true
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 1,
        username: 'xiwei',
        display_name: 'Xiwei',
        role: 'admin',
        is_active: true
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    await fetchCurrentUser();
    await login('xiwei', 'secret123');
    await logout();

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/auth/me', { credentials: 'include' });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ identifier: 'xiwei', password: 'secret123' })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/auth/logout',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include'
      })
    );
    const logoutHeaders = new Headers(fetchMock.mock.calls[2][1]?.headers);
    expect(logoutHeaders.get('X-CSRF-Token')).toBe('csrf-1');
  });

  it('adds csrf headers to mutating watchlist and review item create requests', async () => {
    Object.defineProperty(document, 'cookie', {
      value: 'theme=light; stock_research_csrf=csrf-1',
      configurable: true
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 34 })
    });
    vi.stubGlobal('fetch', fetchMock);

    await createMyWatchlistItem({
      asset_id: 'CN:SZ:000001',
      source: 'manual',
      notes: 'relative strength'
    });
    await createMyReviewItem(12, {
      asset_id: 'CN:SZ:000001',
      decision: 'watch',
      conviction: 'medium',
      tags: [],
      notes: '',
      follow_up_required: false
    });

    const watchlistHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      '/api/my/watchlist/items',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({
          asset_id: 'CN:SZ:000001',
          source: 'manual',
          notes: 'relative strength'
        })
      })
    );
    expect(watchlistHeaders.get('Content-Type')).toBe('application/json');
    expect(watchlistHeaders.get('X-CSRF-Token')).toBe('csrf-1');

    const reviewHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/my/reviews/12/items',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({
          asset_id: 'CN:SZ:000001',
          decision: 'watch',
          conviction: 'medium',
          tags: [],
          notes: '',
          follow_up_required: false
        })
      })
    );
    expect(reviewHeaders.get('Content-Type')).toBe('application/json');
    expect(reviewHeaders.get('X-CSRF-Token')).toBe('csrf-1');
  });

  it('supports an explicit csrf cookie-name override for admin mutations', async () => {
    Object.defineProperty(document, 'cookie', {
      value: 'theme=light; dashboard_csrf=override-1; session=value',
      configurable: true
    });
    setCsrfCookieName('dashboard_csrf');
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 12,
        username: 'analyst',
        email: 'analyst@example.com',
        display_name: 'Analyst',
        role: 'user',
        is_active: true,
        disabled_at: null
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    try {
      await createUser({
        username: 'analyst',
        email: 'analyst@example.com',
        display_name: 'Analyst',
        password: 'secret123',
        role: 'user'
      });

      const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/admin/users',
        expect.objectContaining({
          method: 'POST',
          credentials: 'include'
        })
      );
      expect(headers.get('X-CSRF-Token')).toBe('override-1');
    } finally {
      setCsrfCookieName('stock_research_csrf');
    }
  });

  it('propagates backend error detail from shared requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      headers: new Headers({ 'Content-Type': 'application/json' }),
      text: async () => JSON.stringify({ detail: 'invalid session' })
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(fetchCurrentUser()).rejects.toThrow('GET /api/auth/me failed with 401: invalid session');
  });

  it('supports successful empty-body responses in the shared transport layer', async () => {
    Object.defineProperty(document, 'cookie', {
      value: 'stock_research_csrf=csrf-1',
      configurable: true
    });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      headers: new Headers(),
      text: async () => ''
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await deleteSessionJson('/api/test-empty', { csrf: true });

    expect(result).toBeUndefined();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/test-empty',
      expect.objectContaining({
        method: 'DELETE',
        credentials: 'include'
      })
    );
  });

  it('fetches a review session from the dedicated session route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 31,
        user_id: 7,
        trade_date: '2026-06-21',
        title: 'Morning review',
        summary: '',
        market_view: '',
        position_view: '',
        next_action: '',
        created_at: '2026-06-21T09:00:00Z',
        updated_at: '2026-06-21T09:00:00Z',
        items: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchMyReviewSession(31);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith('/api/my/reviews/31', { credentials: 'include' });
    expect(result.id).toBe(31);
  });

  it('updates a review session through the dedicated session route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 31,
        user_id: 7,
        trade_date: '2026-06-21',
        title: 'Updated title',
        summary: 'Revised summary',
        market_view: '',
        position_view: '',
        next_action: '',
        created_at: '2026-06-21T09:00:00Z',
        updated_at: '2026-06-21T10:00:00Z',
        items: []
      })
    });
    Object.defineProperty(document, 'cookie', {
      value: 'stock_research_csrf=csrf-1',
      configurable: true
    });
    vi.stubGlobal('fetch', fetchMock);

    await updateMyReviewSession(31, {
      title: 'Updated title',
      summary: 'Revised summary'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/my/reviews/31',
      expect.objectContaining({
        method: 'PATCH',
        credentials: 'include',
        body: JSON.stringify({
          title: 'Updated title',
          summary: 'Revised summary'
        })
      })
    );
    const headers = new Headers(fetchMock.mock.calls[0][1]?.headers);
    expect(headers.get('Content-Type')).toBe('application/json');
    expect(headers.get('X-CSRF-Token')).toBe('csrf-1');
  });

  it('updates review items through the existing item route', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: 34,
        session_id: 12,
        user_id: 7,
        asset_id: 'CN:SZ:000001',
        decision: 'watch',
        conviction: 'medium',
        tags: [],
        notes: '',
        follow_up_required: false,
        created_at: '2026-06-21T09:00:00Z',
        updated_at: '2026-06-21T10:00:00Z'
      })
    });
    Object.defineProperty(document, 'cookie', {
      value: 'stock_research_csrf=csrf-1',
      configurable: true
    });
    vi.stubGlobal('fetch', fetchMock);

    await updateMyReviewItem(12, 34, {
      decision: 'watch',
      conviction: 'medium',
      tags: [],
      notes: '',
      follow_up_required: false
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/my/reviews/12/items/34',
      expect.objectContaining({
        method: 'PATCH',
        credentials: 'include',
        body: JSON.stringify({
          decision: 'watch',
          conviction: 'medium',
          tags: [],
          notes: '',
          follow_up_required: false
        })
      })
    );
  });
});
