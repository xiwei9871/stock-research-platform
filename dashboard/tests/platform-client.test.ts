import { afterEach, describe, expect, it, vi } from 'vitest';

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
        json: async () => ({ items: [{ strategy_id: 'manual_v1_topn_rotation' }] })
      } as Response);
    const { fetchPlatformSummary, fetchStrategyCatalog } = await import('../src/api/client');

    const summary = await fetchPlatformSummary();
    const catalog = await fetchStrategyCatalog();

    expect(summary.latest_market_date).toBe('2026-06-08');
    expect(catalog[0].strategy_id).toBe('manual_v1_topn_rotation');
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
    };
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
        json: async () => ({ strategy_id: 'manual_v1_topn_rotation', read_only: true })
      } as Response);
    const {
      fetchAssetProfile,
      fetchBacktestStrategies,
      fetchFactorLibrary,
      fetchFactorScorePreview,
      runBacktest
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

    expect(factorLibrary[0].factor_name).toBe('ret_20');
    expect(profile.asset_id).toBe('000001.SZ');
    expect(strategies[0].strategy_id).toBe('manual_v1_topn_rotation');
    expect(result.read_only).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(5);
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
    expect(fetchMock).toHaveBeenNthCalledWith(5, '/api/backtests/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(backtestRequest)
    });
  });
});
