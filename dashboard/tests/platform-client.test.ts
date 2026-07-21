import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchWatchlistSignals, searchAssets } from '../src/api/client';

describe('platform API clients', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('fetches platform summary and strategy catalog', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ latest_market_date: '2026-06-08' })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              strategy_id: 'manual_v1_topn_rotation',
              latest_metrics: {
                publish_id: 'publish-20260720',
                publish_started_at: '2026-07-20T12:30:00.000000+00:00'
              }
            }
          ]
        })
      } as Response);
    const { fetchPlatformSummary, fetchStrategyCatalog } = await import('../src/api/client');

    const summary = await fetchPlatformSummary();
    const catalog = await fetchStrategyCatalog();

    expect(summary.latest_market_date).toBe('2026-06-08');
    expect(catalog[0].strategy_id).toBe('manual_v1_topn_rotation');
    expect(catalog[0].latest_metrics?.publish_id).toBe('publish-20260720');
    expect(catalog[0].latest_metrics?.publish_started_at).toBe(
      '2026-07-20T12:30:00.000000+00:00'
    );
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/platform/summary');
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/strategies/catalog');
  });

  it('fetches factor library, score preview, asset profile, and backtest APIs', async () => {
    const backtestRequest = {
      strategy_id: 'manual_v1_topn_rotation',
      start_date: '2026-06-01',
      end_date: '2026-06-08',
      top_n: 20,
      rebalance_frequency: 'weekly',
      transaction_cost_bps: 10,
      max_positions: 20,
      score_version: 'manual_v1',
      adjust_type: 'hfq'
    } as const;
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [{ factor_name: 'ret_20' }] })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [{ asset_id: 'A' }], selected_factors: [] })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ asset_id: '000001.SZ', bars: [] })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ items: [{ strategy_id: 'manual_v1_topn_rotation' }] })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ job_id: 'backtest-job:1', status: 'queued' })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          job_id: 'backtest-job:1',
          status: 'succeeded',
          result: { strategy_id: 'manual_v1_topn_rotation', read_only: false, execution_mode: 'fresh' },
          error: ''
        })
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ strategy_id: 'manual_v1_topn_rotation', read_only: false, execution_mode: 'fresh' })
      } as Response);
    const {
      fetchAssetProfile,
      fetchBacktestStrategies,
      fetchFactorLibrary,
      fetchFactorScorePreview,
      runBacktest,
      runFreshBacktest
    } = await import('../src/api/client');

    const factorLibrary = await fetchFactorLibrary();
    await fetchFactorScorePreview(
      '2026-06-08',
      [
        { factor_name: 'ret_20', direction: 'higher', weight: 1 },
        { factor_name: 'volatility 20', direction: 'lower', weight: 0.5 }
      ],
      10
    );
    const profile = await fetchAssetProfile('000001.SZ', '2026-06-08', '2026-06-01', '2026-06-08');
    const strategies = await fetchBacktestStrategies();
    const result = await runBacktest(backtestRequest);
    const freshResult = await runFreshBacktest(backtestRequest);

    expect(factorLibrary[0].factor_name).toBe('ret_20');
    expect(profile.asset_id).toBe('000001.SZ');
    expect(strategies[0].strategy_id).toBe('manual_v1_topn_rotation');
    expect(result.execution_mode).toBe('fresh');
    expect(freshResult.execution_mode).toBe('fresh');
    expect(fetchMock).toHaveBeenCalledTimes(7);
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/factors/library');
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/factors/score-preview?trade_date=2026-06-08&factors=ret_20%3Ahigher%3A1%2Cvolatility%2020%3Alower%3A0.5&top_n=10'
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      '/api/assets/000001.SZ/profile?trade_date=2026-06-08&start_date=2026-06-01&end_date=2026-06-08&score_version=manual_v1&adjust_type=qfq'
    );
    expect(fetchMock).toHaveBeenNthCalledWith(4, '/api/backtests/strategies');
    expect(fetchMock).toHaveBeenNthCalledWith(5, '/api/backtests/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(backtestRequest)
    });
    expect(fetchMock).toHaveBeenNthCalledWith(6, '/api/backtests/jobs/backtest-job%3A1');
    expect(fetchMock).toHaveBeenNthCalledWith(7, '/api/backtests/run-fresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(backtestRequest)
    });
  });

  it('searches assets through the dashboard API', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [{ asset_id: '000001.SZ', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true }]
      })
    } as Response);

    const items = await searchAssets('平安', 5);

    expect(fetchMock).toHaveBeenCalledWith('/api/assets/search?q=%E5%B9%B3%E5%AE%89&limit=5');
    expect(items).toEqual([
      { asset_id: '000001.SZ', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true }
    ]);
  });

  it('fetches watchlist signal rows for an EOD date', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        watchlist_id: 'default',
        trade_date: '2026-06-08',
        items: [
          {
            watchlist_id: 'default',
            trade_date: '2026-06-08',
            asset_id: '000001.SZ',
            stock_code: '000001',
            stock_name: '平安银行',
            priority: 8,
            signal_score: 82.4,
            primary_signal: 'candidate',
            signal_tags: ['momentum'],
            risk_tags: ['earnings'],
            must_watch: true,
            reason_json: { next_action: 'review close above 10d high' }
          }
        ]
      })
    } as Response);

    const items = await fetchWatchlistSignals('default', '2026-06-08');

    expect(fetchMock).toHaveBeenCalledWith('/api/watchlists/default?trade_date=2026-06-08');
    expect(items[0].asset_id).toBe('000001.SZ');
  });
});
