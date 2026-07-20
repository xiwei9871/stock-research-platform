import { describe, expect, it, vi } from 'vitest';
import {
  DASHBOARD_AUTH_EXPIRED_EVENT,
  fetchCurrentUser,
  fetchAdminUsers,
  createAdminUser,
  disableAdminUser,
  enableAdminUser,
  resetAdminUserPassword,
  loginDashboardUser,
  logoutDashboardUser,
  createOperatorDecision,
  fetchDailyBars,
  fetchAssetDecisions,
  fetchEvidenceDigest,
  fetchAssetNews,
  fetchAssetOutcomes,
  fetchAssetResearchReports,
  fetchAssetThemeResearchContext,
  fetchDailyReviewLite,
  fetchExperimentProposals,
  fetchExperimentReplay,
  fetchGlobalSearch,
  fetchMarketMonitorEod,
  fetchMarketOverview,
  fetchOutcomeAnalytics,
  fetchOpsStages,
  fetchOverview,
  fetchPlatformDisplayDate,
  fetchPlatformReadiness,
  fetchPublicNews,
  fetchPublicNewsStatus,
  fetchResearchReportDocument,
  fetchResearchReportSummary,
  fetchResearchReports,
  fetchResearchCases,
  fetchResearchCaseDetail,
  fetchResearchQueueHealth,
  fetchResearchPublishGate,
  fetchResearchPublicationPreview,
  fetchResearchPublicationSnapshots,
  fetchResearchExternalDeliveryPlan,
  fetchResearchExternalDeliveryAttempts,
  fetchResearchQueueGaps,
  createResearchReviewAction,
  fetchResearchEvidence,
  fetchSectorDetail,
  fetchSectorFundFlow,
  fetchSectorHeatmap,
  fetchMarketAnomalyContext,
  fetchStockHeatmap,
  fetchStockMarketContextHeatmap,
  fetchThemeResearchUpdates,
  fetchEvidenceDigestSnapshot,
  fetchEvidenceDigestSnapshots,
  fetchReviewQueue,
  fetchReviewQueueSnapshots,
  refreshPublicNews,
  fetchShadowAnalyticsReview,
  fetchShadowFollowUpQueue,
  fetchShadowFollowUpResolution,
  fetchShadowReviewDecisions,
  fetchShadowOutcomeAnalytics,
  fetchShadowOutcomes,
  fetchShadowWatchlist,
  runBacktest,
  runFreshBacktest
} from '../src/api/client';

describe('dashboard API client', () => {
  it('ignores a stale credentialed 401 after a login transition advances the auth session', async () => {
    let resolveOldRequest: ((response: { ok: boolean; status: number; json: () => Promise<{ detail: string }> }) => void) | undefined;
    const oldRequestResponse = new Promise<{ ok: boolean; status: number; json: () => Promise<{ detail: string }> }>((resolve) => {
      resolveOldRequest = resolve;
    });
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(oldRequestResponse)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          user: { user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user', is_active: true }
        })
      });
    const handleAuthExpired = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    window.addEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);

    const oldRequest = fetchAdminUsers();
    await loginDashboardUser({ username: 'analyst', password: 'secret' });
    resolveOldRequest?.({ ok: false, status: 401, json: async () => ({ detail: 'expired old session' }) });
    await expect(oldRequest).rejects.toThrow('GET /api/admin/users failed with 401');
    window.removeEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);

    expect(handleAuthExpired).not.toHaveBeenCalled();
  });

  it('dispatches exactly one expiry event when sibling current-session requests return 401', async () => {
    type ErrorResponse = { ok: boolean; status: number; json: () => Promise<{ detail: string }> };
    let resolveFirst: ((response: ErrorResponse) => void) | undefined;
    let resolveSecond: ((response: ErrorResponse) => void) | undefined;
    const firstResponse = new Promise<ErrorResponse>((resolve) => {
      resolveFirst = resolve;
    });
    const secondResponse = new Promise<ErrorResponse>((resolve) => {
      resolveSecond = resolve;
    });
    const fetchMock = vi.fn().mockReturnValueOnce(firstResponse).mockReturnValueOnce(secondResponse);
    const handleAuthExpired = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    window.addEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);

    const firstRequest = fetchAdminUsers();
    const secondRequest = fetchAdminUsers();
    resolveFirst?.({ ok: false, status: 401, json: async () => ({ detail: 'expired' }) });
    await expect(firstRequest).rejects.toThrow('GET /api/admin/users failed with 401');
    resolveSecond?.({ ok: false, status: 401, json: async () => ({ detail: 'expired' }) });
    await expect(secondRequest).rejects.toThrow('GET /api/admin/users failed with 401');
    window.removeEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);

    expect(handleAuthExpired).toHaveBeenCalledTimes(1);
  });

  it('keeps logout 401 as a logout failure without dispatching an expiry cycle', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'logout rejected' })
    });
    const handleAuthExpired = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    window.addEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);

    await expect(logoutDashboardUser()).rejects.toThrow('POST /api/auth/logout failed with 401: logout rejected');
    window.removeEventListener(DASHBOARD_AUTH_EXPIRED_EVENT, handleAuthExpired);

    expect(handleAuthExpired).not.toHaveBeenCalled();
  });

  it('uses cookie credentials for auth session endpoints and csrf for logout', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true } })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true } })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'logged_out' })
      });
    vi.stubGlobal('fetch', fetchMock);
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: 'stock_research_csrf=csrf-token'
    });

    await fetchCurrentUser();
    await loginDashboardUser({ username: 'admin', password: 'secret' });
    await logoutDashboardUser();

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/auth/me', { credentials: 'include' });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ username: 'admin', password: 'secret' })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/auth/logout',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-token' })
      })
    );
  });

  it('uses cookie credentials and csrf for admin user management endpoints', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [{ user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }] })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ user: { user_id: 'user:2', username: 'analyst', display_name: '', role: 'user', is_active: true } })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'disabled', user_id: 'user:2' })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'enabled', user_id: 'user:2' })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'password_reset', user_id: 'user:2' })
      });
    vi.stubGlobal('fetch', fetchMock);
    Object.defineProperty(document, 'cookie', {
      writable: true,
      value: 'stock_research_csrf=csrf-token'
    });

    await fetchAdminUsers();
    await createAdminUser({ username: 'analyst', password: 'secret123', role: 'user', display_name: '' });
    await disableAdminUser('user:2');
    await enableAdminUser('user:2');
    await resetAdminUserPassword('user:2', 'next-secret');

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/admin/users', { credentials: 'include' });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/admin/users',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-token' })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/admin/users/user%3A2/disable',
      expect.objectContaining({ method: 'POST', credentials: 'include', headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-token' }) })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      '/api/admin/users/user%3A2/enable',
      expect.objectContaining({ method: 'POST', credentials: 'include', headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-token' }) })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      5,
      '/api/admin/users/user%3A2/reset-password',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        headers: expect.objectContaining({ 'X-CSRF-Token': 'csrf-token' }),
        body: JSON.stringify({ password: 'next-secret' })
      })
    );
  });

  it('requests asset bars with explicit resolution and adjust type', async () => {
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

  it('omits start_date when requesting a fixed-count bars window', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ time: '2026-06-30', close: 10.5 }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchDailyBars('CN:SZ:000001', undefined, '2026-07-01', {
      resolution: '1M',
      adjustType: 'qfq'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/assets/CN%3ASZ%3A000001/bars?end_date=2026-07-01&adjust_type=qfq&resolution=1M'
    );
    expect(result[0].time).toBe('2026-06-30');
  });

  it('runs default backtests through the background job endpoint', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: 'backtest-job:1', status: 'queued' })
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: 'backtest-job:1',
          status: 'succeeded',
          result: { strategy_id: 'lhb_shortline', summary: { total_return: 0.63 } },
          error: ''
        })
      });
    vi.stubGlobal('fetch', fetchMock);

    const result = await runBacktest({
      strategy_id: 'lhb_shortline',
      start_date: '2026-01-01',
      end_date: '2026-06-08',
      score_version: 'manual_v1',
      top_n: 5,
      rebalance_frequency: 'daily',
      transaction_cost_bps: 10,
      max_positions: 20,
      adjust_type: 'hfq'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/backtests/jobs',
      expect.objectContaining({ method: 'POST' })
    );
    expect(fetchMock).toHaveBeenCalledWith('/api/backtests/jobs/backtest-job%3A1');
    expect(result.summary.total_return).toBe(0.63);
  });

  it('keeps explicit fresh backtests on the fresh endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ strategy_id: 'lhb_shortline', summary: { total_return: -0.13 } })
    });
    vi.stubGlobal('fetch', fetchMock);

    await runFreshBacktest({
      strategy_id: 'lhb_shortline',
      start_date: '2026-01-01',
      end_date: '2026-06-08',
      score_version: 'manual_v1',
      top_n: 5,
      rebalance_frequency: 'daily',
      transaction_cost_bps: 10,
      max_positions: 20,
      adjust_type: 'hfq'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/backtests/run-fresh',
      expect.objectContaining({ method: 'POST' })
    );
  });

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

  it('fetches research cases with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ case_id: 'research_case:1', title: 'Case 1' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchCases({ tradeDate: '2026-07-06', status: 'open', limit: 5 });

    expect(fetchMock).toHaveBeenCalledWith('/api/research/cases?trade_date=2026-07-06&status=open&limit=5');
    expect(result.items[0].case_id).toBe('research_case:1');
  });

  it('fetches research case detail with encoded case id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        case: { case_id: 'research_case:1', title: 'Case 1' },
        claims: [],
        evidence: [],
        summary: { claim_count: 0, evidence_count: 0, missing_or_partial_evidence_count: 0 }
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchCaseDetail('research_case:1');

    expect(fetchMock).toHaveBeenCalledWith('/api/research/cases/research_case%3A1');
    expect(result.case.case_id).toBe('research_case:1');
  });

  it('fetches research queue health with trade date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-07-07',
        status: 'healthy',
        can_review: true,
        can_publish_research_queue: false,
        summary: { case_count: 100, claim_count: 600 },
        last_refresh: null,
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchQueueHealth({ tradeDate: '2026-07-07' });

    expect(fetchMock).toHaveBeenCalledWith('/api/research/queue/health?trade_date=2026-07-07');
    expect(result.status).toBe('healthy');
  });

  it('fetches research publish gate with trade date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-07-03',
        status: 'blocked',
        research_ready_for_publication: false,
        actual_publish_enabled: false,
        internal_snapshot_enabled: false,
        external_delivery_enabled: false,
        publication_entrypoint_status: 'scaffolded',
        summary: { case_count: 15, pending_gap_count: 14 },
        blockers: [{ code: 'pending_gap', message: '14 gap cases have not been reviewed', count: 14 }],
        warnings: [],
        top_blocked_cases: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchPublishGate({ tradeDate: '2026-07-03' });

    expect(fetchMock).toHaveBeenCalledWith('/api/research/queue/publish-gate?trade_date=2026-07-03');
    expect(result.status).toBe('blocked');
    expect(result.actual_publish_enabled).toBe(false);
  });

  it('fetches research publication preview with trade date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-07-03',
        package_id: 'research_publication_package:abc',
        publishable: false,
        actual_publish_enabled: false,
        internal_snapshot_enabled: false,
        external_delivery_enabled: false,
        gate: {
          status: 'blocked',
          research_ready_for_publication: false,
          actual_publish_enabled: false,
          internal_snapshot_enabled: false,
          external_delivery_enabled: false
        },
        summary: { case_count: 15, claim_count: 90, gap_count: 15 },
        sections: [],
        warnings: [],
        blockers: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchPublicationPreview({ tradeDate: '2026-07-03' });

    expect(fetchMock).toHaveBeenCalledWith('/api/research/publication/preview?trade_date=2026-07-03');
    expect(result.publishable).toBe(false);
    expect(result.actual_publish_enabled).toBe(false);
  });

  it('fetches research publication snapshots with trade date and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
            trade_date: '2026-07-03',
            channel: 'research_queue_internal',
            title: 'Research Queue Internal Snapshot 2026-07-03',
            created_by: 'research_queue_publish',
            created_at: '2026-07-08T10:00:00+08:00',
            package_id: 'research_publication_package:abc',
            gate_status: 'research_ready',
            research_ready_for_publication: true,
            actual_external_delivery_enabled: false,
            case_count: 2,
            claim_count: 3,
            evidence_count: 4,
            gap_count: 0,
            blocker_count: 0
          }
        ]
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchPublicationSnapshots({ tradeDate: '2026-07-03', limit: 5 });

    expect(fetchMock).toHaveBeenCalledWith('/api/research/publication/snapshots?trade_date=2026-07-03&limit=5');
    expect(result.items[0].publication_snapshot_id).toBe('publication_snapshot:research_queue_internal:abc');
    expect(result.items[0].actual_external_delivery_enabled).toBe(false);
  });

  it('fetches research external delivery plan with snapshot id and channel', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        delivery_plan_id: 'research_external_delivery_plan:abc',
        publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
        trade_date: '2026-07-03',
        channel: 'feishu_preview',
        dry_run: true,
        external_send_enabled: false,
        status: 'preview_ready',
        message: {
          title: 'Research Queue Snapshot 2026-07-03',
          summary: 'Cases 2, claims 3, evidence 4, gaps 0. Gate research_ready.',
          sections: []
        },
        source: {
          package_id: 'research_publication_package:abc',
          gate_status: 'research_ready',
          snapshot_channel: 'research_queue_internal'
        },
        blockers: [],
        warnings: ['External delivery is not connected in this version.']
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchExternalDeliveryPlan({
      publicationSnapshotId: 'publication_snapshot:research_queue_internal:abc',
      channel: 'feishu_preview'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/research/publication/delivery-plan?publication_snapshot_id=publication_snapshot%3Aresearch_queue_internal%3Aabc&channel=feishu_preview'
    );
    expect(result.status).toBe('preview_ready');
    expect(result.external_send_enabled).toBe(false);
  });

  it('fetches research external delivery attempts with snapshot id and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            delivery_attempt_id: 'external_delivery_attempt:abc',
            publication_snapshot_id: 'publication_snapshot:research_queue_internal:abc',
            trade_date: '2026-07-03',
            channel: 'feishu_preview',
            mode: 'dry_run',
            status: 'preview_recorded',
            dry_run: true,
            external_send_enabled: false,
            delivery_plan_id: 'research_external_delivery_plan:abc',
            message_title: 'Research Queue Snapshot 2026-07-03',
            created_by: 'operator',
            created_at: '2026-07-08T10:00:00+08:00',
            error_code: '',
            error_message: ''
          }
        ]
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchExternalDeliveryAttempts({
      publicationSnapshotId: 'publication_snapshot:research_queue_internal:abc',
      limit: 5
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/research/publication/delivery-attempts?publication_snapshot_id=publication_snapshot%3Aresearch_queue_internal%3Aabc&limit=5'
    );
    expect(result.items[0].status).toBe('preview_recorded');
    expect(result.items[0].external_send_enabled).toBe(false);
  });

  it('fetches research queue gaps with trade date and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-07-03',
        items: [{ case_id: 'research_case:1', gap_reasons: ['partial_evidence'] }],
        summary: { gap_case_count: 1, partial_evidence_count: 1 }
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchQueueGaps({ tradeDate: '2026-07-03', limit: 5 });

    expect(fetchMock).toHaveBeenCalledWith('/api/research/queue/gaps?trade_date=2026-07-03&limit=5');
    expect(result.items[0].gap_reasons).toEqual(['partial_evidence']);
  });

  it('creates a research review action', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ review_action_id: 'review_action:abc', status: 'recorded' })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await createResearchReviewAction({
      case_id: 'research_case:1',
      action_type: 'request_more_evidence',
      gap_reasons: ['missing_evidence'],
      comment: '需要补证',
      reviewer: 'operator'
    });

    expect(fetchMock).toHaveBeenCalledWith('/api/research/review-actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        case_id: 'research_case:1',
        action_type: 'request_more_evidence',
        gap_reasons: ['missing_evidence'],
        comment: '需要补证',
        reviewer: 'operator'
      })
    });
    expect(result.review_action_id).toBe('review_action:abc');
  });

  it('fetches research evidence with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ evidence_id: 'evidence_artifact:1', title: 'Evidence 1' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchEvidence({ assetId: 'CN:SZ:000001', sourceType: 'review_item_snapshot', limit: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/research/evidence?asset_id=CN%3ASZ%3A000001&source_type=review_item_snapshot&limit=20'
    );
    expect(result.items[0].evidence_id).toBe('evidence_artifact:1');
  });

  it('fetches platform readiness with mode and checks', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        mode: 'eod_local',
        status: 'partial',
        as_of: '2026-06-15T08:30:00+08:00',
        latest_market_date: '2026-06-12',
        checks: [
          {
            key: 'market_data',
            label: 'Market data',
            status: 'ready',
            detail: 'Latest EOD data loaded'
          }
        ],
        warnings: ['News collector lagging']
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchPlatformReadiness();

    expect(fetchMock).toHaveBeenCalledWith('/api/platform/readiness');
    expect(result.mode).toBe('eod_local');
    expect(result.checks).toEqual([
      {
        key: 'market_data',
        label: 'Market data',
        status: 'ready',
        detail: 'Latest EOD data loaded'
      }
    ]);
  });

  it('fetches platform display date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        display_trade_date: '2026-06-17',
        candidate_trade_date: '2026-06-18',
        latest_market_date: '2026-06-18',
        status: 'OK',
        display_gate: { candidate_status: 'before_cutoff' },
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchPlatformDisplayDate();

    expect(fetchMock).toHaveBeenCalledWith('/api/platform/display-date');
    expect(result.display_trade_date).toBe('2026-06-17');
    expect(result.display_gate.candidate_status).toBe('before_cutoff');
  });

  it('fetches EOD market monitor with optional trade date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-06-10',
        freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
        coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
        market_breadth: { status: 'pending_source' },
        index_snapshot: [],
        sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
        unusual_moves: [],
        watchlist_alerts: [],
        strategy_signal_summary: { topn_preview_count: 0, topn_preview: [], risk_filter_counts: {} },
        generated_reports: [],
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchMarketMonitorEod({ tradeDate: '2026-06-10', topN: 3 });

    expect(fetchMock).toHaveBeenCalledWith('/api/market-monitor/eod?trade_date=2026-06-10&top_n=3');
    expect(result.freshness.is_realtime).toBe(false);
  });

  it('fetches daily review lite with the selected trade date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-06-18',
        status: 'partial',
        run: { run_id: '', source: 'fallback', report_type: 'daily_review_lite' },
        fallback: true,
        sections: [],
        artifacts: [],
        warnings: ['no registered daily review run selected']
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchDailyReviewLite({ tradeDate: '2026-06-18' });

    expect(fetchMock).toHaveBeenCalledWith('/api/daily-review-lite?trade_date=2026-06-18');
    expect(result.trade_date).toBe('2026-06-18');
  });

  it('fetches reviewed theme research context for an asset', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        asset_id: 'CN:SZ:002837',
        company_code: '002837.SZ',
        status: 'reviewed_context_available',
        themes: [],
        mappings: [],
        research_only: true,
        used_for_signal: false,
        used_for_admission: false
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchAssetThemeResearchContext('CN:SZ:002837');

    expect(fetchMock).toHaveBeenCalledWith('/api/assets/CN%3ASZ%3A002837/theme-research-context');
    expect(result.company_code).toBe('002837.SZ');
    expect(result.used_for_signal).toBe(false);
  });

  it('fetches reviewed theme research updates with bounded filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        total: 1,
        items: [{ update_id: 'review-1', object_type: 'claim' }],
        by_object_type: { claim: 1 },
        since: '2026-07-10',
        limit: 20,
        research_only: true,
        used_for_signal: false,
        used_for_admission: false,
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchThemeResearchUpdates({ since: '2026-07-10', limit: 20 });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/research/theme-decomposition/updates?since=2026-07-10&limit=20'
    );
    expect(result.total).toBe(1);
  });

  it('fetches market overview for a trade date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-06-26',
        updated_at: '2026-06-26T15:30:00+08:00',
        source: 'mock',
        data_status: 'completed',
        warnings: [],
        indices: [],
        total_amount: 1,
        up_count: 2,
        down_count: 3,
        limit_up_count: 4,
        limit_down_count: 5
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchMarketOverview('2026-06-26');

    expect(fetchMock).toHaveBeenCalledWith('/api/market-monitor/overview?trade_date=2026-06-26');
    expect(result.data_status).toBe('completed');
  });

  it('fetches sector heatmap for a trade date and sector type', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-06-26',
        updated_at: '2026-06-26T15:30:00+08:00',
        source: 'mock',
        data_status: 'completed',
        warnings: [],
        items: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchSectorHeatmap('2026-06-26', 'industry');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/market-monitor/sectors/heatmap?trade_date=2026-06-26&type=industry'
    );
    expect(result.items).toEqual([]);
  });

  it('fetches stock heatmap with P0 options', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-07-07',
        market: 'all',
        period: '1d',
        group: 'industry',
        size_by: 'amount',
        updated_at: '2026-07-07T15:30:00+08:00',
        source: 'market_daily_bar',
        data_status: 'completed',
        warnings: [],
        summary: {
          stock_count: 1,
          up_count: 1,
          flat_count: 0,
          down_count: 0,
          total_amount: 100
        },
        groups: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchStockHeatmap('2026-07-07');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/market-monitor/stocks/heatmap?trade_date=2026-07-07&market=all&period=1d&group=industry&size_by=amount'
    );
    expect(result.summary.stock_count).toBe(1);
  });

  it('fetches market anomaly context for the selected trade date', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-07-07',
        data_status: 'completed',
        summary: {
          hot_industry_count: 1,
          hot_stock_count: 1,
          volume_spike_count: 1,
          strong_move_count: 1
        },
        hot_industries: [],
        hot_stocks: [],
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchMarketAnomalyContext('2026-07-07');

    expect(fetchMock).toHaveBeenCalledWith('/api/market-monitor/anomaly-context?trade_date=2026-07-07');
    expect(result.summary.hot_stock_count).toBe(1);
  });

  it('fetches stock market context heatmap with encoded asset id', async () => {
    const payload = {
      asset_id: 'CN:SZ:000001',
      canonical_asset_id: 'CN:SZ:000001',
      trade_date: '2026-07-07',
      industry: { industry_id: 'bank', industry_name: '银行', industry_system: 'csrc' },
      selected: null,
      summary: {
        peer_count: 0,
        up_count: 0,
        flat_count: 0,
        down_count: 0,
        total_amount: 0,
        selected_in_peer_set: false
      },
      peers: [],
      data_status: 'missing',
      warnings: []
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => payload
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchStockMarketContextHeatmap('CN:SZ:000001', '2026-07-07');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/stocks/CN%3ASZ%3A000001/market-context/heatmap?trade_date=2026-07-07'
    );
    expect(result).toEqual(payload);
  });

  it('fetches sector fund flow with the default 1d period', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-06-26',
        updated_at: '2026-06-26T15:30:00+08:00',
        source: 'mock',
        data_status: 'completed',
        warnings: [],
        inflow: [],
        outflow: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchSectorFundFlow('2026-06-26', 'concept');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/market-monitor/sectors/fund-flow?trade_date=2026-06-26&type=concept&period=1d'
    );
    expect(result.outflow).toEqual([]);
  });

  it('fetches sector detail for a selected sector', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        trade_date: '2026-06-26',
        updated_at: '2026-06-26T15:30:00+08:00',
        source: 'mock',
        data_status: 'completed',
        warnings: [],
        sector_id: 'BK0428',
        sector_name: '银行',
        sector_type: 'industry',
        change_pct: 1.2,
        amount: 12345,
        up_count: 12,
        down_count: 4,
        main_net_inflow: 100,
        main_net_inflow_ratio: 0.5,
        leading_stocks: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchSectorDetail('2026-06-26', 'BK0428');

    expect(fetchMock).toHaveBeenCalledWith('/api/market-monitor/sectors/BK0428?trade_date=2026-06-26');
    expect(result.sector_id).toBe('BK0428');
  });

  it('fetches public news with db filters', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [],
          total: 0,
          limit: 10,
          offset: 2,
          summary: { total_news: 0, source_count: 0, source_counts: [], category_counts: [] },
          warnings: []
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchPublicNews({
      source: 'sina_finance',
      category: 'live',
      q: '快讯',
      startTime: '2026-06-12T00:00:00',
      endTime: '2026-06-12T23:59:59',
      assetId: 'CN:SH:600519',
      minQualityScore: 70,
      limit: 10,
      offset: 2
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/public-news?source=sina_finance&category=live&q=%E5%BF%AB%E8%AE%AF&start_time=2026-06-12T00%3A00%3A00&end_time=2026-06-12T23%3A59%3A59&asset_id=CN%3ASH%3A600519&min_quality_score=70&limit=10&offset=2'
    );
  });

  it('fetches public news collector status', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          enabled: true,
          running: false,
          interval_seconds: 1800,
          next_run_at: '2026-06-13T10:30:00'
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchPublicNewsStatus();

    expect(fetchMock).toHaveBeenCalledWith('/api/public-news/status');
    expect(result.interval_seconds).toBe(1800);
  });

  it('fetches asset news', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          asset_id: 'CN:SH:600519',
          items: [],
          summary: { news_count_1d: 0, news_count_3d: 0, news_count_7d: 0 },
          warnings: []
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchAssetNews('CN:SH:600519', { limit: 5, lookbackDays: 7 });

    expect(fetchMock).toHaveBeenCalledWith('/api/assets/CN%3ASH%3A600519/news?limit=5&lookback_days=7');
    expect(result.asset_id).toBe('CN:SH:600519');
  });

  it('fetches asset news without trailing query when params are omitted', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          asset_id: 'CN:SH:600519',
          items: [],
          summary: { news_count_1d: 0, news_count_3d: 0, news_count_7d: 0 },
          warnings: []
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    await fetchAssetNews('CN:SH:600519');

    expect(fetchMock).toHaveBeenCalledWith('/api/assets/CN%3ASH%3A600519/news');
  });

  it('fetches global search results with query and limit', async () => {
    const body = {
      query: '600519',
      groups: [
        {
          key: 'assets',
          label: 'Stocks',
          items: [
            {
              id: 'asset:CN:SH:600519',
              type: 'asset',
              title: '贵州茅台',
              subtitle: '600519 / SH',
              timestamp: '',
              target: { workspace: 'stock', asset_id: 'CN:SH:600519' },
              score: 100,
              match_reason: 'Exact code match',
              match_fields: ['symbol'],
              metadata: { symbol: '600519' }
            }
          ]
        }
      ],
      warnings: []
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => body
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchGlobalSearch('600519', 3);

    expect(fetchMock).toHaveBeenCalledWith('/api/search?q=600519&limit=3');
    expect(result).toBe(body);
  });

  it('refreshes public news through POST', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ stored: 2, items_received: 2, counts_by_category: { live: 2 }, warnings: [] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await refreshPublicNews();

    expect(fetchMock).toHaveBeenCalledWith('/api/public-news/refresh', { method: 'POST' });
    expect(result.counts_by_category.live).toBe(2);
  });

  it('fetches research report summary', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ total_reports: 57418, covered_stocks: 3367, source_counts: [] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchReportSummary();

    expect(fetchMock).toHaveBeenCalledWith('/api/research-reports/summary');
    expect(result.total_reports).toBe(57418);
  });

  it('fetches research reports with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [{ report_id: 'r1', stock_name: '贵州茅台' }],
        total: 1,
        limit: 25,
        offset: 5,
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchReports({
      q: '茅台',
      broker: '华泰',
      rating: '买入',
      source_name: 'cfi_ybyl',
      start_date: '2026-06-01',
      end_date: '2026-06-05',
      has_target_price: true,
      limit: 25,
      offset: 5
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/research-reports?q=%E8%8C%85%E5%8F%B0&broker=%E5%8D%8E%E6%B3%B0&rating=%E4%B9%B0%E5%85%A5' +
        '&source_name=cfi_ybyl&start_date=2026-06-01&end_date=2026-06-05&has_target_price=true&limit=25&offset=5'
    );
    expect(result.items[0].stock_name).toBe('贵州茅台');
  });

  it('fetches the research report document payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        report_id: 'r1',
        report_title: '贵州茅台深度报告',
        has_pdf: true,
        pdf_url: '/api/research-reports/r1/pdf',
        source_url: 'https://example.com/r1',
        file_name: 'r1.pdf',
        public_access: false,
        copyright_note: 'internal pdf',
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchResearchReportDocument('r1');

    expect(fetchMock).toHaveBeenCalledWith('/api/research-reports/r1/document');
    expect(result.pdf_url).toBe('/api/research-reports/r1/pdf');
  });

  it('fetches asset research reports', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ asset_id: '600519.SH', summary: { report_count_90d: 4 }, items: [], warnings: [] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchAssetResearchReports('600519.SH', { limit: 5, lookbackDays: 90 });

    expect(fetchMock).toHaveBeenCalledWith('/api/assets/600519.SH/research-reports?limit=5&lookback_days=90');
    expect(result.summary.report_count_90d).toBe(4);
  });

  it('fetches evidence digest with optional date and lookback', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          asset_id: '000001.SZ',
          canonical_asset_id: '000001.SZ',
          stock_code: '000001.SZ',
          stock_name: '平安银行',
          trade_date: '2026-06-12',
          latest_trade_date: '2026-06-12',
          run_id: 'eod-2026-06-12-local',
          digest_key: '2026-06-12:manual_v2:000001.SZ',
          generated_at: '2026-06-12T00:00:00+00:00',
          overall_status: 'PARTIAL',
          title: 'Mixed evidence',
          score: 62,
          bucket: 'mixed',
          sections: {
            news: {
              status: 'missing',
              as_of: '2026-06-12',
              source: 'public_news',
              item_count: 0,
              warnings: [],
              error_message: '',
              data: {},
              artifact_path: ''
            }
          },
          missing_evidence: ['news'],
          partial_evidence: [],
          lineage: { run_id: 'eod-2026-06-12-local', score_version: 'manual_v2', topn_rank: 3 },
          errors: [],
          facts: [{ kind: 'strategy', key: 'score_rank', label: 'Strategy score rank', value: 3 }],
          risk_flags: [{ key: 'strategy_risk_tags', label: 'Strategy risk tags present', severity: 'warning', value: ['gap_risk'] }],
          source_refs: { strategy_asset_id: '000001.SZ' },
          next_actions: [],
          warnings: []
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const digest = await fetchEvidenceDigest('000001.SZ', {
      tradeDate: '2026-06-12',
      lookbackDays: 30,
      scoreVersion: 'manual_v2'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/evidence-digest?asset_id=000001.SZ&trade_date=2026-06-12&lookback_days=30&score_version=manual_v2'
    );
    expect(digest.bucket).toBe('mixed');
    expect(digest.facts[0].value).toBe(3);
    expect(digest.risk_flags[0].value).toEqual(['gap_risk']);
    expect(digest.source_refs.strategy_asset_id).toBe('000001.SZ');
    expect(digest.digest_key).toBe('2026-06-12:manual_v2:000001.SZ');
    expect(digest.overall_status).toBe('PARTIAL');
    expect(digest.sections?.news?.status).toBe('missing');
    expect(digest.missing_evidence).toEqual(['news']);
  });

  it('fetchReviewQueue serializes optional filters', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          trade_date: '2026-06-08',
          score_version: 'manual_v1',
          generated_at: '2026-06-08T00:00:00+00:00',
          groups: [],
          warnings: []
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const payload = await fetchReviewQueue({
      tradeDate: '2026-06-08',
      scoreVersion: 'manual_v2',
      limit: 12,
      lookbackDays: 45
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/review-queue?trade_date=2026-06-08&score_version=manual_v2&limit=12&lookback_days=45'
    );
    expect(payload.trade_date).toBe('2026-06-08');
  });

  it('accepts backend-like review queue payloads', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          trade_date: '2026-06-08',
          score_version: 'manual_v1',
          generated_at: '2026-06-08T00:00:00+00:00',
          groups: [
            {
              bucket: 'strong',
              label: 'High Conviction',
              count: 1,
              items: [
                {
                  queue_id: '2026-06-08:manual_v1:000001.SZ',
                  asset_id: '000001.SZ',
                  canonical_asset_id: '000001.SZ',
                  trade_date: '2026-06-08',
                  latest_trade_date: '2026-06-08',
                  run_id: 'eod-2026-06-08-local',
                  generated_at: '2026-06-08T00:00:00+00:00',
                  score_version: 'manual_v1',
                  display_name: '平安银行',
                  rank: 1,
                  topn_rank: 1,
                  score: 88.5,
                  source_type: 'score_topn',
                  source_name: 'manual_v1_topn',
                  source_rank: 1,
                  score_components: { momentum: 0.8 },
                  strategy_name: null,
                  strategy_run_id: null,
                  factor_as_of: '2026-06-08',
                  digest_key: '2026-06-08:manual_v1:000001.SZ',
                  digest_url_path: '/api/evidence-digest?asset_id=000001.SZ&trade_date=2026-06-08&score_version=manual_v1',
                  stock_workspace_url_path: '/stock/000001.SZ?trade_date=2026-06-08',
                  evidence_status: 'OK',
                  missing_evidence: [],
                  partial_evidence: [],
                  missing_evidence_count: 0,
                  partial_evidence_count: 0,
                  warnings_count: 0,
                  warnings: [],
                  manifest_modules: [],
                  digest_title: 'Strong evidence',
                  bucket: 'strong',
                  source_kinds: ['strategy', 'news'],
                  risk_count: 0,
                  warning_count: 0,
                  next_action_count: 2,
                  digest: {
                    asset_id: '000001.SZ',
                    canonical_asset_id: '000001.SZ',
                    stock_code: '000001.SZ',
                    stock_name: '平安银行',
                    trade_date: '2026-06-08',
                    latest_trade_date: '2026-06-08',
                    run_id: 'eod-2026-06-08-local',
                    digest_key: '2026-06-08:manual_v1:000001.SZ',
                    generated_at: '2026-06-08T00:00:00+00:00',
                    overall_status: 'OK',
                    title: 'Strong evidence',
                    score: 82,
                    bucket: 'strong',
                    sections: {},
                    missing_evidence: [],
                    partial_evidence: [],
                    lineage: {},
                    errors: [],
                    facts: [{ kind: 'news', label: 'Recent news' }],
                    risk_flags: [],
                    source_refs: {},
                    next_actions: [
                      {
                        key: 'review_stock',
                        label: 'Review Stock',
                        workspace: 'stock',
                        asset_id: '000001.SZ'
                      }
                    ],
                    warnings: []
                  }
                }
              ]
            }
          ],
          warnings: []
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const payload = await fetchReviewQueue();

    expect(payload.groups[0].items[0].digest.facts[0].kind).toBe('news');
    expect(payload.groups[0].items[0].trade_date).toBe('2026-06-08');
    expect(payload.groups[0].items[0].source_type).toBe('score_topn');
    expect(payload.groups[0].items[0].digest_key).toBe('2026-06-08:manual_v1:000001.SZ');
    expect(payload.groups[0].items[0].missing_evidence_count).toBe(0);
  });

  it('fetches review queue snapshots with filters', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          items: [{ snapshot_id: 'review_item_snapshot:abc', run_id: 'eod-2026-06-12-local' }],
          warnings: [],
          as_of: '',
          source: 'ops.review_item_snapshot'
        }),
        { status: 200 }
      )
    );
    vi.stubGlobal('fetch', fetchMock);

    const payload = await fetchReviewQueueSnapshots({
      runId: 'eod-2026-06-12-local',
      digestKey: '2026-06-12:manual_v1:000001.SZ'
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/review-queue/snapshots?run_id=eod-2026-06-12-local&digest_key=2026-06-12%3Amanual_v1%3A000001.SZ'
    );
    expect(payload.items[0].snapshot_id).toBe('review_item_snapshot:abc');
  });

  it('fetches evidence digest snapshots and detail', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            items: [{ snapshot_id: 'evidence_digest_snapshot:def', digest_key: 'digest-1' }],
            warnings: [],
            as_of: '',
            source: 'ops.evidence_digest_snapshot'
          }),
          { status: 200 }
        )
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            item: { snapshot_id: 'evidence_digest_snapshot:def', digest_payload: { digest_key: 'digest-1' } },
            warnings: [],
            source: 'ops.evidence_digest_snapshot'
          }),
          { status: 200 }
        )
      );
    vi.stubGlobal('fetch', fetchMock);

    const listPayload = await fetchEvidenceDigestSnapshots({ digestKey: 'digest-1' });
    const detailPayload = await fetchEvidenceDigestSnapshot('evidence_digest_snapshot:def');

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/evidence-digest/snapshots?digest_key=digest-1');
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/evidence-digest/snapshots/evidence_digest_snapshot%3Adef');
    expect(listPayload.items[0].digest_key).toBe('digest-1');
    expect(detailPayload.item.snapshot_id).toBe('evidence_digest_snapshot:def');
  });

  it('fetches asset decisions with date range and limit', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [
          {
            asset_id: '000001.SZ',
            decision_label: 'candidate',
            digest_key: '2026-06-12:manual_v1:000001.SZ',
            review_item_snapshot_id: 'review_item_snapshot:abc',
            evidence_digest_snapshot_id: 'evidence_digest_snapshot:def',
            snapshot_linkage_status: 'linked'
          }
        ]
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchAssetDecisions('000001.SZ', '2026-05-01', '2026-05-30', 20);

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/assets/000001.SZ/decisions?start_date=2026-05-01&end_date=2026-05-30&limit=20'
    );
    expect(result[0].decision_label).toBe('candidate');
    expect(result[0].digest_key).toBe('2026-06-12:manual_v1:000001.SZ');
    expect(result[0].snapshot_linkage_status).toBe('linked');
  });

  it('creates operator decisions through the write endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        event_id: 'operator_decision:operator-decision-api-2026-06-12:0:abc',
        asset_id: '000001.SZ',
        stock_code: '000001.SZ',
        decision_date: '2026-06-12',
        operator_action: 'watch',
        decision_status: 'open',
        decision_label: 'observe',
        run_id: 'eod-2026-06-12-local',
        digest_key: '2026-06-12:manual_v1:000001.SZ',
        snapshot_linkage_status: 'linked',
        snapshot_linkage_warnings: [],
        warnings: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await createOperatorDecision({
      asset_id: '000001.SZ',
      stock_code: '000001.SZ',
      decision_date: '2026-06-12',
      operator_action: 'watch',
      run_id: 'eod-2026-06-12-local',
      digest_key: '2026-06-12:manual_v1:000001.SZ',
      source_context: { entry: 'review_queue' }
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/operator-decisions',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
    );
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      asset_id: '000001.SZ',
      operator_action: 'watch'
    });
    expect(result.snapshot_linkage_status).toBe('linked');
  });

  it('surfaces operator decision validation detail from failed writes', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'operator_decision_missing_evidence_linkage' })
    });
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      createOperatorDecision({
        asset_id: '000001.SZ',
        operator_action: 'watch'
      })
    ).rejects.toThrow('POST /api/operator-decisions failed with 400: operator_decision_missing_evidence_linkage');
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

  it('fetches strategy validation runs with optional strategy filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ items: [{ run_id: 'lhb_shortline:fixture:phase16', strategy_id: 'lhb_shortline' }] })
    });
    vi.stubGlobal('fetch', fetchMock);

    const { fetchStrategyValidationRuns } = await import('../src/api/client');
    const result = await fetchStrategyValidationRuns({ strategyId: 'lhb_shortline' });

    expect(fetchMock).toHaveBeenCalledWith('/api/strategy-validation/runs?strategy_id=lhb_shortline');
    expect(result[0].run_id).toBe('lhb_shortline:fixture:phase16');
  });

  it('fetches strategy validation replay with date range', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        run: { run_id: 'run-1', strategy_id: 'lhb_shortline' },
        asset_id: '000001.SZ',
        bars: [],
        signals: [],
        trades: [],
        positions: [],
        metrics: [],
        artifacts: []
      })
    });
    vi.stubGlobal('fetch', fetchMock);

    const { fetchStrategyValidationReplay } = await import('../src/api/client');
    const result = await fetchStrategyValidationReplay('run-1', '000001.SZ', '2026-06-01', '2026-06-08');

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/strategy-validation/runs/run-1/assets/000001.SZ/replay?start_date=2026-06-01&end_date=2026-06-08&adjust_type=qfq'
    );
    expect(result.asset_id).toBe('000001.SZ');
  });

  it('fetches ops stages rows from the internal ops endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [{ stage: 'daily', status: 'success' }] }), { status: 200 })
    );
    vi.stubGlobal('fetch', fetchMock);

    const result = await fetchOpsStages();

    expect(fetchMock).toHaveBeenCalledWith('/api/ops/stages');
    expect(result[0].stage).toBe('daily');
  });
});
