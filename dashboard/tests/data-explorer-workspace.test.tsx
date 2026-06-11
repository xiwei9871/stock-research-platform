import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';
import { DataExplorerWorkspace } from '../src/components/DataExplorerWorkspace';
import type { AssetProfile } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchAssetProfile: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  fetchBacktestStrategies: vi.fn(),
  fetchMarketMonitorEod: vi.fn(),
  fetchPublicNews: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars }: { bars: unknown[] }) => <div data-testid="asset-chart">{bars.length} bars</div>
}));

function makeProfile(overrides: Partial<AssetProfile> = {}): AssetProfile {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: 'CN:SZ:000001',
    asset: {
      asset_id: '000001.SZ',
      symbol: '000001',
      name: '平安银行',
      exchange: 'SZ',
      board: 'main',
      is_active: true
    },
    bars: [
      { time: '2026-06-06', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-06-08', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1320 }
    ],
    score: {
      trade_date: '2026-06-08',
      asset_id: '000001.SZ',
      rank: 12,
      score_total: 88.5,
      score_version: 'manual_v1',
      score_components: { ret_20: 0.42 }
    },
    signals: [],
    decisions: [],
    outcomes: [],
    factor_values: [
      {
        trade_date: '2026-06-08',
        asset_id: '000001.SZ',
        factor_group: 'momentum',
        factor_name: 'ret_20',
        factor_value: 0.1234,
        calc_version: 'v1',
        source: 'unit',
        source_data_version: '20260608'
      }
    ],
    coverage: {
      daily_bars: {
        min_date: '1991-04-03',
        max_date: '2026-06-08',
        row_count: 8240
      },
      factors: {
        latest_factor_date: '2026-06-08',
        factor_count: 43
      }
    },
    ...overrides
  };
}

function deferredProfile() {
  let resolve!: (profile: AssetProfile) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<AssetProfile>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

describe('DataExplorerWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchAssetProfile.mockResolvedValue(makeProfile());
    apiMocks.fetchPlatformSummary.mockResolvedValue({
      latest_market_date: '2026-06-08',
      latest_factor_date: '2026-06-08',
      latest_score_date: '2026-06-08',
      market_asset_count: 1,
      score_asset_count: 1,
      factor_count: 2,
      topn_preview: []
    });
    apiMocks.fetchStrategyCatalog.mockResolvedValue([]);
    apiMocks.fetchBacktestStrategies.mockResolvedValue([
      {
        strategy_id: 'lhb_shortline',
        strategy_name: 'LHB Shortline Combo',
        status: 'runnable',
        description: 'LHB combo',
        factor_groups: ['资金行为'],
        signal_inputs: ['龙虎榜'],
        default_parameters: { top_n: 20 },
        latest_evidence: '',
        primary_action: 'Run backtest'
      }
    ]);
    apiMocks.fetchMarketMonitorEod.mockResolvedValue({
      trade_date: '2026-06-08',
      freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
      coverage: { market_assets: 1, score_assets: 1, factor_count: 2 },
      market_breadth: {
        advancers: null,
        decliners: null,
        limit_up: null,
        limit_down: null,
        advancing_ratio: null,
        turnover_change_pct: null,
        status: 'pending_source'
      },
      index_snapshot: [],
      sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
      unusual_moves: [],
      watchlist_alerts: [],
      strategy_signal_summary: { topn_preview_count: 0, topn_preview: [], risk_filter_counts: {} },
      generated_reports: [],
      warnings: []
    });
    apiMocks.fetchPublicNews.mockResolvedValue({ items: [], warnings: [] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('initially loads the default asset profile', async () => {
    render(<DataExplorerWorkspace />);

    expect(screen.getByRole('heading', { name: 'Data Explorer' })).toBeInTheDocument();
    expect(screen.getByText('Loading asset profile...')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText('平安银行')).toBeInTheDocument());

    expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
      '000001.SZ',
      '2026-06-08',
      '2025-12-10',
      '2026-06-08',
      'manual_v1',
      'qfq'
    );
    expect(screen.getByText('CN:SZ:000001')).toBeInTheDocument();
    expect(screen.getByText('Score 88.5')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'momentum' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'ret_20' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '0.1234' })).toBeInTheDocument();
    expect(screen.queryByRole('cell', { name: 'factor_name' })).not.toBeInTheDocument();
    expect(screen.getByText('1991-04-03')).toBeInTheDocument();
    expect(screen.getByText('daily_bars.min_date')).toBeInTheDocument();
    expect(screen.getByText('factors.factor_count')).toBeInTheDocument();
    expect(screen.queryByText(/"min_date"/)).not.toBeInTheDocument();
    expect(screen.getByTestId('asset-chart')).toHaveTextContent('2 bars');
    expect(screen.getByText('Chart Range')).toBeInTheDocument();
    expect(screen.getByLabelText('chart start date')).toHaveValue('2025-12-10');
    expect(screen.getByLabelText('chart end date')).toHaveValue('2026-06-08');
    expect(screen.getByText('Factor Snapshot')).toBeInTheDocument();
    expect(screen.getByText('as of 2026-06-08')).toBeInTheDocument();
  });

  it('lets the user choose an explicit chart range for the asset profile', async () => {
    render(<DataExplorerWorkspace />);
    await waitFor(() => expect(screen.getByText('平安银行')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('chart start date'), { target: { value: '2026-01-01' } });
    fireEvent.change(screen.getByLabelText('chart end date'), { target: { value: '2026-06-01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Asset' }));

    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
        '000001.SZ',
        '2026-06-08',
        '2026-01-01',
        '2026-06-01',
        'manual_v1',
        'qfq'
      )
    );
  });

  it('loads a new asset id on request', async () => {
    render(<DataExplorerWorkspace />);
    await waitFor(() => expect(screen.getByText('平安银行')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('asset id'), { target: { value: '600000.SH' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Asset' }));

    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
        '600000.SH',
        expect.any(String),
        expect.any(String),
        expect.any(String),
        'manual_v1',
        'qfq'
      )
    );
  });

  it('shows errors and can reload after a failed request', async () => {
    apiMocks.fetchAssetProfile.mockRejectedValueOnce(new Error('profile failed')).mockResolvedValueOnce(makeProfile());

    render(<DataExplorerWorkspace />);

    await waitFor(() => expect(screen.getByText('profile failed')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Load Asset' }));

    await waitFor(() => expect(screen.getByText('平安银行')).toBeInTheDocument());
    expect(screen.queryByText('profile failed')).not.toBeInTheDocument();
  });

  it('ignores stale responses when requests resolve out of order', async () => {
    const oldRequest = deferredProfile();
    const newRequest = deferredProfile();
    apiMocks.fetchAssetProfile.mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise);

    render(<DataExplorerWorkspace />);

    fireEvent.change(screen.getByLabelText('asset id'), { target: { value: '600000.SH' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Asset' }));

    await act(async () => {
      newRequest.resolve(
        makeProfile({
          asset_id: '600000.SH',
          canonical_asset_id: 'CN:SH:600000',
          asset: {
            asset_id: '600000.SH',
            symbol: '600000',
            name: '浦发银行',
            exchange: 'SH',
            board: 'main',
            is_active: true
          },
          score: {
            trade_date: '2026-06-08',
            asset_id: '600000.SH',
            rank: 20,
            score_total: 77.1,
            score_version: 'manual_v1',
            score_components: {}
          }
        })
      );
    });

    await waitFor(() => expect(screen.getByText('浦发银行')).toBeInTheDocument());

    await act(async () => {
      oldRequest.resolve(makeProfile());
    });

    expect(screen.getByText('浦发银行')).toBeInTheDocument();
    expect(screen.getByText('CN:SH:600000')).toBeInTheDocument();
    expect(screen.queryByText('平安银行')).not.toBeInTheDocument();
  });

  it('does not update state after unmounting during a load', async () => {
    const pendingRequest = deferredProfile();
    apiMocks.fetchAssetProfile.mockReturnValueOnce(pendingRequest.promise);
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { unmount } = render(<DataExplorerWorkspace />);
    unmount();

    await act(async () => {
      pendingRequest.resolve(makeProfile());
    });

    expect(consoleErrorSpy).not.toHaveBeenCalled();
    consoleErrorSpy.mockRestore();
  });

  it('opens from AppShell Data Explorer navigation', async () => {
    render(<AppShell />);

    const navigation = screen.getByRole('complementary', { name: 'Workspace navigation' });
    fireEvent.click(within(navigation).getByRole('button', { name: 'Open Data Explorer workspace' }));

    expect(screen.getByRole('heading', { name: 'Data Explorer' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('平安银行')).toBeInTheDocument());
  });
});
