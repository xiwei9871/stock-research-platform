import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockWorkspace, type StockEntryContext } from '../src/components/StockWorkspace';
import type { AssetNewsResponse, AssetProfile, AssetResearchReportResponse } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchAssetNews: vi.fn(),
  fetchAssetProfile: vi.fn(),
  fetchAssetResearchReports: vi.fn(),
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

function makeResearchReports(overrides: Partial<AssetResearchReportResponse> = {}): AssetResearchReportResponse {
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
        event_key: 'r1:000001.SZ',
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

function makeAssetNews(overrides: Partial<AssetNewsResponse> = {}): AssetNewsResponse {
  const assetId = overrides.asset_id ?? '000001.SZ';
  return {
    asset_id: assetId,
    items: [
      {
        news_id: 'news-1',
        source: 'sina_finance',
        source_channel: '公司',
        category: 'company',
        title: '平安银行相关新闻',
        summary: '',
        url: 'https://finance.sina.com.cn/doc/news.shtml',
        published_at: '2026-06-12T01:30:00+00:00',
        collected_at: '2026-06-12T01:31:00+00:00',
        raw_id: 'news-1',
        raw_payload: {},
        status: 'available',
        stocks: [{ asset_id: assetId, ts_code: '000001.SZ', stock_name: '平安银行' }]
      }
    ],
    summary: {
      news_count_1d: 1,
      news_count_3d: 1,
      news_count_7d: 1,
      latest_published_at: '2026-06-12T01:30:00+00:00',
      source_count: 1,
      category_counts: [{ name: 'company', rows: 1 }]
    },
    warnings: [],
    ...overrides
  };
}

const newsPayload = makeAssetNews();

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchAssetProfile.mockResolvedValue(makeProfile());
  apiMocks.fetchAssetResearchReports.mockResolvedValue(makeResearchReports());
  apiMocks.fetchAssetNews.mockResolvedValue(newsPayload);
  apiMocks.searchAssets.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

describe('StockWorkspace', () => {
  it('renders the source workspace and match reason for stock handoffs', async () => {
    const entryContext: StockEntryContext = { sourceWorkspace: 'search', matchReason: 'Exact code match' };

    render(
      <StockWorkspace
        initialAssetId="000001.SZ"
        entryContext={entryContext}
      />
    );

    expect(await screen.findByText('Opened from Search')).toBeInTheDocument();
    expect(screen.getByText('Exact code match')).toBeInTheDocument();
  });

  it('loads a stock dossier with factors, news, watchlist, and evidence', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(screen.getByText(/Score 82.4/)).toBeInTheDocument();
    expect(screen.getAllByText('momentum').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Score Component')).toHaveLength(2);
    expect(screen.getByText('quality')).toBeInTheDocument();
    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();
    expect(screen.getByText('candidate')).toBeInTheDocument();
    expect(screen.getByText('reports/evidence/000001.md')).toBeInTheDocument();
  });

  it('renders the stock detail evidence hub sections', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();

    [
      'Stock identity region',
      'Stock evidence summary region',
      'Price & Events',
      'Market Monitor State',
      'Strategy Signal',
      'Research Coverage',
      'Related News',
      'Research Reports',
      'Factor / Score Breakdown',
      'Review / Outcomes',
      'Evidence Timeline',
      'Search Matches'
    ].forEach((regionName) => {
      expect(screen.getByRole('region', { name: regionName })).toBeInTheDocument();
    });

    expect(screen.getByText(/Score 82.4/)).toBeInTheDocument();
    expect(screen.getAllByText('momentum').length).toBeGreaterThan(0);
    expect(screen.getByText('平安银行相关新闻')).toBeInTheDocument();
    expect(screen.getByText('candidate')).toBeInTheDocument();
    expect(screen.getByText('reports/evidence/000001.md')).toBeInTheDocument();
    expect(screen.getByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.getByText('90d reports 4')).toBeInTheDocument();
  });

  it('loads db-linked asset news for the selected stock', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(
      makeProfile({
        asset_id: 'CN:SH:600519',
        canonical_asset_id: 'CN:SH:600519',
        asset: {
          asset_id: 'CN:SH:600519',
          symbol: '600519',
          name: '贵州茅台',
          exchange: 'SH',
          board: null,
          is_active: true
        }
      })
    );
    apiMocks.fetchAssetNews.mockResolvedValueOnce(
      makeAssetNews({
        asset_id: 'CN:SH:600519',
        items: [
          {
            ...makeAssetNews().items[0],
            news_id: 'news-600519',
            title: '贵州茅台相关新闻',
            stocks: [{ asset_id: 'CN:SH:600519', ts_code: '600519.SH', stock_name: '贵州茅台' }]
          }
        ]
      })
    );

    render(<StockWorkspace initialAssetId="600519" />);

    expect(await screen.findByText('贵州茅台相关新闻')).toBeInTheDocument();
    expect(apiMocks.fetchAssetNews).toHaveBeenCalledWith('CN:SH:600519', { limit: 8, lookbackDays: 7 });
  });

  it('shows a loading state while selected stock news is loading', async () => {
    const pendingNews = deferred<AssetNewsResponse>();
    apiMocks.fetchAssetNews.mockReturnValueOnce(pendingNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    const newsSection = screen.getByRole('heading', { name: 'Related News' }).closest('article');
    expect(newsSection).not.toBeNull();
    expect(within(newsSection as HTMLElement).getByText('Loading...')).toBeInTheDocument();

    await act(async () => {
      pendingNews.resolve(newsPayload);
      await pendingNews.promise;
    });
  });

  it('shows an error when selected stock news fails to load', async () => {
    apiMocks.fetchAssetNews.mockRejectedValueOnce(new Error('news failed'));

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(await screen.findByText('news failed')).toBeInTheDocument();
    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();
  });

  it('renders warnings returned with selected stock news', async () => {
    apiMocks.fetchAssetNews.mockResolvedValueOnce(makeAssetNews({ warnings: ['partial news store coverage'] }));

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();
    expect(screen.getByText('partial news store coverage')).toBeInTheDocument();
  });

  it('does not render asset news responses for a different stock', async () => {
    apiMocks.fetchAssetNews.mockResolvedValueOnce(
      makeAssetNews({
        asset_id: '600000.SH',
        items: [
          {
            ...makeAssetNews().items[0],
            news_id: 'news-mismatch',
            title: '浦发银行不应显示的新闻',
            stocks: [{ asset_id: '600000.SH', ts_code: '600000.SH', stock_name: '浦发银行' }]
          }
        ]
      })
    );

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledWith('000001.SZ', { limit: 8, lookbackDays: 7 }));
    await waitFor(() => expect(screen.getByText('No related news found.')).toBeInTheDocument());
    expect(screen.queryByText('浦发银行不应显示的新闻')).not.toBeInTheDocument();
  });

  it('hides the previous stock news as soon as a new stock profile is visible', async () => {
    const secondNews = deferred<AssetNewsResponse>();
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

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);
    apiMocks.fetchAssetNews.mockResolvedValueOnce(makeAssetNews()).mockReturnValueOnce(secondNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行相关新闻')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenLastCalledWith('600000.SH', { limit: 8, lookbackDays: 7 }));
  });

  it('does not show stale news errors after a new stock profile is visible', async () => {
    const firstNews = deferred<AssetNewsResponse>();
    const secondNews = deferred<AssetNewsResponse>();
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

    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeProfile()).mockResolvedValueOnce(secondProfile);
    apiMocks.fetchAssetNews.mockReturnValueOnce(firstNews.promise).mockReturnValueOnce(secondNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledWith('000001.SZ', { limit: 8, lookbackDays: 7 }));

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();

    await act(async () => {
      firstNews.reject(new Error('old news failed'));
      await firstNews.promise.catch(() => undefined);
    });

    expect(screen.queryByText('old news failed')).not.toBeInTheDocument();

    await act(async () => {
      secondNews.resolve(makeAssetNews({ asset_id: '600000.SH', items: [] }));
      await secondNews.promise;
    });
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
    const firstNews = deferred<AssetNewsResponse>();
    const secondNews = deferred<AssetNewsResponse>();
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
    apiMocks.fetchAssetNews.mockReturnValueOnce(firstNews.promise).mockReturnValueOnce(secondNews.promise);

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByText('profile failed')).toBeInTheDocument();

    await act(async () => {
      firstNews.resolve(newsPayload);
      await firstNews.promise;
    });

    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    await waitFor(() => expect(apiMocks.fetchAssetNews).toHaveBeenCalledTimes(2));
    expect(screen.queryByText('平安银行相关新闻')).not.toBeInTheDocument();
  });

  it('loads research reports for the selected stock', async () => {
    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.getByText('90d reports 4')).toBeInTheDocument();
    expect(apiMocks.fetchAssetResearchReports).toHaveBeenCalledWith('000001.SZ', { limit: 5, lookbackDays: 90 });
  });

  it('clears stale research reports while loading reports for a newly selected stock', async () => {
    const secondReports = deferred<AssetResearchReportResponse>();
    let staleReportVisibleWhenSecondFetchStarted: boolean | null = null;
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
      .mockImplementationOnce(() => {
        staleReportVisibleWhenSecondFetchStarted =
          document.body.textContent?.includes('平安银行深度报告') ||
          document.body.textContent?.includes('90d reports 4') ||
          false;
        return secondReports.promise;
      });

    render(<StockWorkspace initialAssetId="000001.SZ" />);

    expect(await screen.findByText('平安银行深度报告')).toBeInTheDocument();
    expect(screen.getByText('90d reports 4')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('stock workspace asset'), { target: { value: '600000' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Stock' }));

    expect(await screen.findByRole('heading', { name: /浦发银行/ })).toBeInTheDocument();
    expect(staleReportVisibleWhenSecondFetchStarted).toBe(false);
    expect(screen.queryByText('平安银行深度报告')).not.toBeInTheDocument();
    expect(screen.queryByText('90d reports 4')).not.toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchAssetResearchReports).toHaveBeenLastCalledWith('600000.SH', {
        limit: 5,
        lookbackDays: 90
      })
    );

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
              event_key: 'r2:600000.SH',
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
