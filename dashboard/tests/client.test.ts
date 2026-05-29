import { describe, expect, it, vi } from 'vitest';
import { fetchOverview } from '../src/api/client';

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
});
