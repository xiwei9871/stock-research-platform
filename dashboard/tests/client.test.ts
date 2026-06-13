import { describe, expect, it, vi } from 'vitest';
import {
  fetchAssetDecisions,
  fetchAssetNews,
  fetchAssetOutcomes,
  fetchAssetResearchReports,
  fetchExperimentProposals,
  fetchExperimentReplay,
  fetchGlobalSearch,
  fetchMarketMonitorEod,
  fetchOutcomeAnalytics,
  fetchOverview,
  fetchPublicNews,
  fetchPublicNewsStatus,
  fetchResearchReportSummary,
  fetchResearchReports,
  refreshPublicNews,
  fetchShadowAnalyticsReview,
  fetchShadowFollowUpQueue,
  fetchShadowFollowUpResolution,
  fetchShadowReviewDecisions,
  fetchShadowOutcomeAnalytics,
  fetchShadowOutcomes,
  fetchShadowWatchlist
} from '../src/api/client';

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
});
