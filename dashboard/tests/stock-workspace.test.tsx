import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockWorkspace } from '../src/components/StockWorkspace';
import type { AssetProfile, AssetResearchReportResponse, PublicNewsResponse } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchAssetProfile: vi.fn(),
  fetchAssetResearchReports: vi.fn(),
  fetchPublicNews: vi.fn(),
  searchAssets: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars }: { bars: unknown[] }) => <div data-testid="asset-chart">{bars.length} bars</div>
}));

function makeProfile(overrides: Partial<AssetProfile> = {}): AssetProfile {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    asset: { asset_id: '000001.SZ', symbol: '000001', name: '平安银行', exchange: 'SZ', board: null, is_active: true },
    bars: [
      { time: '2026-06-05', open: 10, high: 11, low: 9.8, close: 10.6, volume: 1000, amount: 10600 },
      { time: '2026-06-08', open: 10.6, high: 11.2, low: 10.4, close: 11, volume: 1300, amount: 14300 }
    ],
    score: {
      trade_date: '2026-06-08',
      asset_id: '000001.SZ',
      rank: 3,
      score_total: 82.4,
      score_version: 'manual_v1',
      score_components: { momentum: 31.2, quality: 18.4 }
    },
    signals: [
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
    ],
    decisions: [
      {
        review_date: '2026-06-08',
        review_session_id: 'session-1',
        event_id: 'event-1',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: '平安银行',
        decision_label: 'watch',
        evidence_artifact_id: 'artifact-1',
        evidence_path: 'reports/evidence/000001.md',
        source_context: 'strategy_lab',
        requires_follow_up: true,
        follow_up_note: 'check next close',
        notes: 'strong score',
        manual_review_required: true,
        auto_trade_enabled: false
      }
    ],
    outcomes: [],
    factor_values: [{ factor_name: 'momentum_20d', factor_group: 'momentum', factor_value: 0.21 }],
    coverage: { bars: { start: '2026-06-05', end: '2026-06-08' } },
    ...overrides
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function makeResearchReports(
  overrides: Partial<AssetResearchReportResponse> = {}
): AssetResearchReportResponse {
  return {
    asset_id: '000001.SZ',
    summary: {
      report_count_30d: 2,
      report_count_90d: 4,
      broker_coverage_count_90d: 3,
      latest_report_date: '2026-06-03',
      latest_rating: '买入',
      latest_target_price: 19.5
    },
    items: [
      {
        report_id: 'r1',
        asset_id: '000001.SZ',
        ts_code: '000001.SZ',
        stock_name: '平安银行',
        industry_name: '银行',
        report_title: '平安银行深度报告',
        publish_date: '2026-06-03',
        report_date: '2026-06-03',
        broker: '华泰证券',
        analyst: '',
        rating: '买入',
        rating_change: '',
        target_price: 19.5,
        target_upside: null,
        source_type: 'public_web_search_result',
        source_name: 'cfi_ybyl',
        source_confidence: 0.8,
        public_access: true,
        copyright_note: 'metadata only',
        source_url: 'https://example.com/r1',
        raw_summary: '',
        company_view: '',
        industry_view: '',
        risk_summary: '',
        metadata: {}
      }
    ],
    warnings: [],
    ...overrides
  };
}

const newsPayload: PublicNewsResponse = {
  warnings: [],
  items: [
    {
      news_id: 'n1',
      source: 'sina_finance',
      source_channel: 'company',
      category: 'company',
      title: '000001 平安银行公告',
      summary: '公司新闻',
      url: 'https://example.com/news/1',
      published_at: '2026-06-08T09:30:00',
      collected_at: '2026-06-08T09:31:00',
      raw_id: 'n1',
      raw_payload: {},
      status: 'active'
    }
  ]
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchAssetProfile.mockResolvedValue(makeProfile());
  apiMocks.fetchAssetResearchReports.mockResolvedValue(makeResearchReports());
  apiMocks.fetchPublicNews.mockResolvedValue(newsPayload);
  apiMocks.searchAssets.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

describe('StockWorkspace', () => {
  it('loads a stock dossier with factors, news, watchlist, and evidence', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(screen.getByText(/Score 82.4/)).toBeInTheDocument();
    expect(screen.getAllByText('momentum').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Score Component')).toHaveLength(2);
    expect(screen.getByText('quality')).toBeInTheDocument();
    expect(await screen.findByText('000001 平安银行公告')).toBeInTheDocument();
    expect(screen.getByText('candidate')).toBeInTheDocument();
    expect(screen.getByText('reports/evidence/000001.md')).toBeInTheDocument();
  });

  it('normalizes six digit stock input before loading', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    await screen.findByRole('heading', { name: /平安银行/ });
    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    await waitFor(() => {
      expect(apiMocks.fetchAssetProfile).toHaveBeenLastCalledWith(
        '600000.SH',
        '2026-06-08',
        '2025-12-10',
        '2026-06-08',
        'manual_v1',
        'qfq'
      );
    });
  });

  it('searches asset matches only after loading a submitted stock', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    await screen.findByRole('heading', { name: /平安银行/ });
    await waitFor(() => {
      expect(apiMocks.searchAssets).toHaveBeenCalledWith('000001.SZ', 8);
    });
    const initialSearchCallCount = apiMocks.searchAssets.mock.calls.length;

    const assetInput = screen.getByLabelText('stock workspace asset');
    fireEvent.change(assetInput, { target: { value: '' } });
    fireEvent.change(assetInput, { target: { value: '6' } });
    fireEvent.change(assetInput, { target: { value: '60' } });
    fireEvent.change(assetInput, { target: { value: '600' } });
    fireEvent.change(assetInput, { target: { value: '6000' } });
    fireEvent.change(assetInput, { target: { value: '60000' } });
    fireEvent.change(assetInput, { target: { value: '600000' } });

    expect(apiMocks.searchAssets).toHaveBeenCalledTimes(initialSearchCallCount);

    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    await waitFor(() => {
      expect(apiMocks.searchAssets).toHaveBeenCalledWith('600000.SH', 8);
    });
  });

  it('does not show stale news after a later profile load clears the profile', async () => {
    const firstNews = deferred<PublicNewsResponse>();
    const secondNews = deferred<PublicNewsResponse>();
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: {
        asset_id: '600000.SH',
        symbol: '600000',
        name: '浦发银行',
        exchange: 'SH',
        board: null,
        is_active: true
      },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile
      .mockResolvedValueOnce(makeProfile())
      .mockRejectedValueOnce(new Error('profile failed'))
      .mockResolvedValueOnce(secondProfile);
    apiMocks.fetchPublicNews.mockReturnValueOnce(firstNews.promise).mockReturnValueOnce(secondNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchPublicNews).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByText('profile failed')).toBeInTheDocument();

    await act(async () => {
      firstNews.resolve(newsPayload);
      await firstNews.promise;
    });

    expect(screen.queryByText('000001 平安银行公告')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchPublicNews).toHaveBeenCalledTimes(2));
    expect(screen.queryByText('000001 平安银行公告')).not.toBeInTheDocument();
  });

  it('loads research reports for the selected stock', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.getByText('90d reports 4')).toBeInTheDocument();
    expect(apiMocks.fetchAssetResearchReports).toHaveBeenCalledWith('000001.SZ', { limit: 5, lookbackDays: 90 });
  });

  it('clears stale research reports while loading reports for a newly selected stock', async () => {
    const secondReports = deferred<AssetResearchReportResponse>();
    const secondProfile = makeProfile({
      asset_id: '600000.SH',
      canonical_asset_id: '600000.SH',
      asset: { asset_id: '600000.SH', symbol: '600000', name: '浦发银行', exchange: 'SH', board: null, is_active: true },
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: []
    });

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);
    apiMocks.fetchAssetResearchReports
      .mockResolvedValueOnce(makeResearchReports())
      .mockReturnValueOnce(secondReports.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.getByText('90d reports 4')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchAssetResearchReports).toHaveBeenLastCalledWith('600000.SH', {
        limit: 5,
        lookbackDays: 90
      })
    );

    expect(screen.queryByText('平安银行深度报告')).not.toBeInTheDocument();
    expect(screen.queryByText('90d reports 4')).not.toBeInTheDocument();

    await act(async () => {
      secondReports.resolve(
        makeResearchReports({
          asset_id: '600000.SH',
          summary: {
            report_count_30d: 1,
            report_count_90d: 2,
            broker_coverage_count_90d: 1,
            latest_report_date: '2026-06-04',
            latest_rating: '增持',
            latest_target_price: 12.3
          },
          items: [
            {
              ...makeResearchReports().items[0],
              report_id: 'r2',
              asset_id: '600000.SH',
              ts_code: '600000.SH',
              stock_name: '浦发银行',
              report_title: '浦发银行跟踪报告',
              broker: '中信证券',
              source_url: 'https://example.com/r2'
            }
          ]
        })
      );
      await secondReports.promise;
    });

    expect(await screen.findByText('浦发银行跟踪报告')).toBeInTheDocument();
  });

  it('does not show stale research reports after a later profile load clears the profile', async () => {
    const firstReports = deferred<AssetResearchReportResponse>();
    apiMocks.fetchAssetResearchReports.mockReturnValueOnce(firstReports.promise);
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockRejectedValueOnce(new Error('not found'));

    render(<StockWorkspace initialAssetId="000001.SZ" />);
    await screen.findByRole('heading', { name: /平安银行/ });

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    await screen.findByText('not found');

    await act(async () => {
      firstReports.resolve({
        asset_id: '000001.SZ',
        summary: {
          report_count_30d: 2,
          report_count_90d: 4,
          broker_coverage_count_90d: 3,
          latest_report_date: '2026-06-03',
          latest_rating: '买入',
          latest_target_price: 19.5
        },
        items: [],
        warnings: []
      });
    });

    expect(screen.queryByText('90d reports 4')).not.toBeInTheDocument();
  });
});
