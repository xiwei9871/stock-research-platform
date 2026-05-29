import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';

const apiMocks = vi.hoisted(() => ({
  fetchOverview: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars }: { bars: unknown[] }) => <div data-testid="asset-chart">{bars.length} bars</div>
}));

describe('dashboard app shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.fetchOverview.mockResolvedValue({
      trade_date: '2026-05-29',
      score_version: 'manual_v1',
      watchlist_id: 'default',
      top_scores: [
        {
          trade_date: '2026-05-29',
          asset_id: '000001.SZ',
          rank: 1,
          score_total: 91.2,
          score_version: 'manual_v1',
          score_components: {}
        }
      ],
      watchlist_signals: [
        {
          watchlist_id: 'default',
          trade_date: '2026-05-29',
          asset_id: '000002.SZ',
          stock_code: '000002',
          stock_name: 'Vanke',
          priority: 5,
          signal_score: 72,
          primary_signal: 'observe',
          signal_tags: ['trend_ok'],
          risk_tags: ['high_volatility'],
          must_watch: true,
          reason_json: {}
        }
      ],
      reports: [
        {
          report_type: 'daily',
          title: 'Daily Review',
          path: '/reports/daily.html',
          format: 'html',
          trade_date: '2026-05-29'
        }
      ]
    });
    apiMocks.fetchDailyBars.mockResolvedValue([
      { time: '2026-05-29', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
    ]);
    apiMocks.fetchAssetScore.mockResolvedValue({
      trade_date: '2026-05-29',
      asset_id: '000001.SZ',
      rank: 1,
      score_total: 91.2,
      score_version: 'manual_v1',
      score_components: {}
    });
    apiMocks.fetchAssetSignals.mockResolvedValue([
      {
        watchlist_id: 'default',
        trade_date: '2026-05-29',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: 'Ping An Bank',
        priority: 10,
        signal_score: 80,
        primary_signal: 'watch',
        signal_tags: [],
        risk_tags: ['gap_risk'],
        must_watch: false,
        reason_json: {}
      }
    ]);
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the stock research shell title', async () => {
    render(<App />);

    expect(screen.getByText('Stock Research')).toBeVisible();
    await screen.findByText('TopN');
  });

  it('loads overview, selected asset review, and chart data', async () => {
    render(<App />);

    expect(await screen.findByText('000001.SZ')).toBeVisible();
    expect(screen.getAllByText('91.2')).toHaveLength(2);
    expect(screen.getByText('必看')).toBeVisible();
    expect(screen.getByText('Daily Review')).toBeVisible();
    expect(screen.getByTestId('asset-chart')).toHaveTextContent('1 bars');
    expect(apiMocks.fetchOverview).toHaveBeenCalledWith({
      tradeDate: '2026-05-29',
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 30
    });
  });

  it('selects an asset from the watchlist', async () => {
    render(<App />);

    fireEvent.click(await screen.findByText('Vanke'));

    await waitFor(() => {
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000002.SZ', expect.any(String), '2026-05-29');
    });
  });
});
