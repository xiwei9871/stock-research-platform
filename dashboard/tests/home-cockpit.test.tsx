import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '../src/components/AppShell';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

vi.mock('../src/api/client', () => ({
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  fetchBacktestStrategies: vi.fn(),
  fetchOverview: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchAssetProfile: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn(),
  fetchAssetDecisions: vi.fn(),
  fetchAssetOutcomes: vi.fn(),
  fetchOutcomeAnalytics: vi.fn(),
  fetchExperimentProposals: vi.fn(),
  fetchExperimentReplay: vi.fn(),
  fetchShadowWatchlist: vi.fn(),
  fetchShadowOutcomes: vi.fn(),
  fetchShadowOutcomeAnalytics: vi.fn(),
  fetchShadowAnalyticsReview: vi.fn(),
  fetchShadowReviewDecisions: vi.fn(),
  fetchShadowFollowUpQueue: vi.fn(),
  fetchShadowFollowUpResolution: vi.fn(),
  fetchStrategyValidationRuns: vi.fn(),
  fetchStrategyValidationReplay: vi.fn(),
  fetchMarketMonitorEod: vi.fn(),
  fetchPublicNews: vi.fn(),
  fetchEvidenceDigest: vi.fn(),
  fetchReviewQueue: vi.fn()
}));

import * as api from '../src/api/client';

describe('AppShell and HomeCockpit', () => {
  beforeEach(() => {
    vi.mocked(api.fetchPlatformSummary).mockResolvedValue({
      latest_market_date: '2026-06-08',
      latest_score_date: '2026-06-08',
      latest_factor_date: '2026-06-07',
      market_asset_count: 5207,
      score_asset_count: 5207,
      factor_count: 43,
      score_versions: ['manual_v1'],
      topn_preview: [
        {
          trade_date: '2026-06-08',
          asset_id: 'CN:SZ:300951',
          rank: 1,
          score_total: 89.9,
          score_version: 'manual_v1',
          score_components: {}
        }
      ]
    });
    vi.mocked(api.fetchStrategyCatalog).mockResolvedValue([
      {
        strategy_id: 'manual_v1_topn_rotation',
        strategy_name: 'Manual V1 TopN Rotation',
        status: 'runnable',
        description: 'TopN rotation',
        factor_groups: ['momentum'],
        signal_inputs: ['factor.stock_score_daily'],
        default_parameters: { top_n: 20 },
        latest_evidence: '',
        primary_action: 'Run backtest'
      }
    ]);
    vi.mocked(api.fetchBacktestStrategies).mockResolvedValue([
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
      },
      {
        strategy_id: 'mid_trend',
        strategy_name: 'Mid Trend Combo',
        status: 'runnable',
        description: 'Mid trend combo',
        factor_groups: ['趋势强度'],
        signal_inputs: ['趋势'],
        default_parameters: { top_n: 5 },
        latest_evidence: '',
        primary_action: 'Run backtest'
      },
      {
        strategy_id: 'tech_bottleneck',
        strategy_name: 'Tech Bottleneck Combo',
        status: 'runnable',
        description: 'Tech bottleneck combo',
        factor_groups: ['技术形态'],
        signal_inputs: ['技术'],
        default_parameters: { top_n: 5 },
        latest_evidence: '',
        primary_action: 'Run backtest'
      }
    ]);
    vi.mocked(api.fetchOverview).mockResolvedValue({
      trade_date: '2026-06-08',
      score_version: 'manual_v1',
      watchlist_id: 'default',
      top_scores: [],
      watchlist_signals: [],
      reports: [
        {
          report_type: 'daily',
          title: 'Daily Market Review',
          path: '/reports/daily-market-review.md',
          format: 'markdown',
          trade_date: '2026-06-08'
        }
      ]
    });
    vi.mocked(api.fetchAssetProfile).mockResolvedValue({
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
      bars: [],
      score: null,
      signals: [],
      decisions: [],
      outcomes: [],
      factor_values: [],
      coverage: {}
    });
    vi.mocked(api.fetchMarketMonitorEod).mockResolvedValue({
      trade_date: '2026-06-10',
      freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
      coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
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
      market_emotion: {
        summary: {
          score: 73.6,
          state: 'hot',
          risk_state: 'medium',
          style_signal_hint: 'growth_favorable',
          position_budget_hint: 'reduced',
          status: 'available'
        },
        components: [
          { key: 'breadth', label: '涨跌家数', score: 68.2 },
          { key: 'limit', label: '涨停表现', score: 75.4 },
          { key: 'relay', label: '连板接力', score: 71.1 },
          { key: 'feedback', label: '赚钱效应', score: 66.8 },
          { key: 'liquidity', label: '市场量能', score: 82.0 }
        ],
        breadth: {
          traded_count: 5207,
          up_count: 3610,
          down_count: 1492,
          strong_up_count: 269,
          strong_down_count: 55,
          status: 'available'
        },
        liquidity: { total_amount: 1280000000000, amount_ratio_5_20: 1.18, status: 'available' },
        limit_performance: {
          limit_up_count: 90,
          limit_down_count: 10,
          broken_limit_up_count: 55,
          broken_limit_up_rate: 0.3793,
          first_board_count: 58,
          second_board_count: 21,
          third_board_plus_count: 11,
          high_board_height: 6,
          status: 'available'
        },
        profit_effect: {
          limit_up_success_rate: 0.7361,
          limit_up_profit_rate: 0.026,
          limit_up_limit_down_rate: 0.026,
          relay_profit_rate: 0.018,
          relay_success_rate: 0.615,
          relay_continue_rate: 0.312,
          broken_profit_rate: 0.007,
          broken_success_rate: 0.564,
          broken_limit_down_rate: 0.073,
          status: 'available'
        },
        drawdown_pressure: {
          strong_down_count: 55,
          limit_down_count: 10,
          broken_limit_up_rate: 0.3793,
          yesterday_limit_up_limit_down_rate: 0.026,
          status: 'available'
        },
        weight_performance: { status: 'pending_source' }
      },
      emotion_stock_lists: {
        auction_status: 'pending_source',
        auction: [],
        limit_up: [
          {
            name: '金钼股份',
            asset_id: 'CN:SH:601958',
            symbol: '601958',
            amount: 3038000000,
            pct_chg: 10,
            board: '金属钼',
            tab: 'limit_up',
            limit_up_streak: 1
          }
        ],
        broken_limit_up: [],
        limit_down: []
      },
      warnings: []
    });
    vi.mocked(api.fetchPublicNews).mockResolvedValue({
      items: [
        {
          news_id: 'news-home',
          source: 'sina_finance',
          source_channel: '7x24',
          category: 'live',
          title: '首页快讯',
          summary: '',
          url: '',
          published_at: '2026-06-11 10:00:00',
          collected_at: '2026-06-11T02:00:00Z',
          raw_id: '',
          raw_payload: {},
          status: 'available'
        }
      ],
      warnings: []
    });
    vi.mocked(api.fetchEvidenceDigest).mockResolvedValue({
      asset_id: 'CN:SZ:300951',
      canonical_asset_id: 'CN:SZ:300951',
      trade_date: '2026-06-08',
      title: 'Strong evidence',
      score: 81,
      bucket: 'strong',
      facts: [],
      risk_flags: [],
      source_refs: {},
      next_actions: [],
      warnings: []
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders platform summary and strategy entry points', async () => {
    render(<AppShell />);

    expect(await screen.findByText('Research Cockpit')).toBeVisible();
    expect(screen.getByText('Market Date')).toBeVisible();
    expect(screen.getAllByText('2026-06-08')[0]).toBeVisible();
    expect(screen.getByText('Factor Date')).toBeVisible();
    expect(screen.getByText('2026-06-07')).toBeVisible();
    expect(screen.getByText('Today Focus')).toBeVisible();
    expect(screen.getByText('Market Pulse')).toBeVisible();
    expect(screen.getByText('News Flow')).toBeVisible();
    expect(screen.getByText('Strategy Health')).toBeVisible();
    expect(screen.getByText('首页快讯')).toBeVisible();
    expect(screen.getByText('LHB Shortline Combo')).toBeVisible();
    expect(screen.getByText('Mid Trend Combo')).toBeVisible();
    expect(screen.getByText('Tech Bottleneck Combo')).toBeVisible();
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
    const quickActions = within(screen.getByRole('navigation', { name: 'Quick actions' }));
    expect(quickActions.getByRole('button', { name: 'Review Queue' })).toBeVisible();
    expect(quickActions.getByRole('button', { name: 'Market Monitor' })).toBeVisible();
    expect(quickActions.getByRole('button', { name: 'Research Reports' })).toBeVisible();
    expect(quickActions.getByRole('button', { name: 'Stock Workspace' })).toBeVisible();
    expect(quickActions.getByRole('button', { name: 'Watchlist' })).toBeVisible();
    expect(quickActions.getByRole('button', { name: 'Strategy Lab' })).toBeVisible();
    expect(quickActions.getByRole('button', { name: 'Generated Reports' })).toBeVisible();
    expect(quickActions.queryByRole('button', { name: 'Backtest Lab' })).not.toBeInTheDocument();
    expect(quickActions.queryByRole('button', { name: 'Strategy Validation' })).not.toBeInTheDocument();
    expect(quickActions.queryByRole('button', { name: 'Reports' })).not.toBeInTheDocument();
  });

  it('keeps core cockpit content when optional home widgets fail', async () => {
    vi.mocked(api.fetchMarketMonitorEod).mockRejectedValueOnce(new Error('market monitor unavailable'));
    vi.mocked(api.fetchPublicNews).mockRejectedValueOnce(new Error('news unavailable'));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
    expect(screen.getByText('Market Date')).toBeVisible();
    expect(screen.getAllByText('2026-06-08')[0]).toBeVisible();
    expect(screen.getByText('Today Focus')).toBeVisible();
    expect(screen.getByText('Strategy Health')).toBeVisible();
    expect(screen.getByText('LHB Shortline Combo')).toBeVisible();
    expect(screen.getByText('Market pulse unavailable: market monitor unavailable')).toBeVisible();
    expect(screen.getByText('News flow unavailable: news unavailable')).toBeVisible();
  });

  it('shows evidence digest badges for today focus rows', async () => {
    render(<AppShell />);

    expect(await screen.findByText('Research Cockpit')).toBeVisible();
    expect(await screen.findByText('Strong evidence')).toBeVisible();
    expect(api.fetchEvidenceDigest).toHaveBeenCalledWith('CN:SZ:300951', {
      tradeDate: '2026-06-08',
      lookbackDays: 90
    });
  });

  it('keeps today focus visible when digest loading fails', async () => {
    vi.mocked(api.fetchEvidenceDigest).mockRejectedValueOnce(new Error('digest unavailable'));

    render(<AppShell />);

    expect(await screen.findByText('CN:SZ:300951')).toBeVisible();
    expect(await screen.findByText('Digest unavailable')).toBeVisible();
  });

  it('updates each top-five evidence digest row independently', async () => {
    const pendingDigest = deferred<Awaited<ReturnType<typeof api.fetchEvidenceDigest>>>();
    const focusRows = Array.from({ length: 6 }, (_, index) => ({
      trade_date: '2026-06-08',
      asset_id: `CN:SZ:00000${index + 1}`,
      rank: index + 1,
      score_total: 90 - index,
      score_version: 'manual_v1',
      score_components: {}
    }));
    vi.mocked(api.fetchPlatformSummary).mockResolvedValueOnce({
      latest_market_date: '2026-06-08',
      latest_score_date: '2026-06-08',
      latest_factor_date: '2026-06-07',
      market_asset_count: 5207,
      score_asset_count: 5207,
      factor_count: 43,
      score_versions: ['manual_v1'],
      topn_preview: focusRows
    });
    vi.mocked(api.fetchEvidenceDigest).mockImplementation((assetId) => {
      if (assetId === 'CN:SZ:000001') {
        return Promise.resolve({
          asset_id: assetId,
          canonical_asset_id: assetId,
          trade_date: '2026-06-08',
          title: 'First evidence',
          score: 81,
          bucket: 'strong',
          facts: [],
          risk_flags: [],
          source_refs: {},
          next_actions: [],
          warnings: []
        });
      }
      if (assetId === 'CN:SZ:000002') return Promise.reject(new Error('digest unavailable'));
      if (assetId === 'CN:SZ:000003') return pendingDigest.promise;
      return Promise.resolve({
        asset_id: assetId,
        canonical_asset_id: assetId,
        trade_date: '2026-06-08',
        title: `Evidence ${assetId}`,
        score: 70,
        bucket: 'mixed',
        facts: [],
        risk_flags: [],
        source_refs: {},
        next_actions: [],
        warnings: []
      });
    });

    render(<AppShell />);

    expect(await screen.findByText('CN:SZ:000001')).toBeVisible();
    await waitFor(() => expect(api.fetchEvidenceDigest).toHaveBeenCalledTimes(5));
    expect(api.fetchEvidenceDigest).toHaveBeenCalledWith('CN:SZ:000005', {
      tradeDate: '2026-06-08',
      lookbackDays: 90
    });
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalledWith('CN:SZ:000006', expect.anything());
    expect(await screen.findByText('First evidence')).toBeVisible();
    expect(await screen.findByText('Digest unavailable')).toBeVisible();
    const pendingRow = screen.getByText('CN:SZ:000003').closest('.data-table-row');
    expect(pendingRow).not.toBeNull();
    expect(within(pendingRow as HTMLElement).getByText('Digest pending')).toBeVisible();
  });

  it('does not request evidence digests when platform summary fails', async () => {
    vi.mocked(api.fetchPlatformSummary).mockRejectedValueOnce(new Error('summary unavailable'));

    render(<AppShell />);

    expect(await screen.findByText('Platform summary unavailable: summary unavailable')).toBeVisible();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
  });

  it('renders core cockpit content while optional home widgets are still pending', async () => {
    vi.mocked(api.fetchMarketMonitorEod).mockReturnValueOnce(new Promise(() => undefined));
    vi.mocked(api.fetchPublicNews).mockReturnValueOnce(new Promise(() => undefined));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
    expect(screen.getByText('Market Date')).toBeVisible();
    expect(screen.getAllByText('2026-06-08')[0]).toBeVisible();
    expect(screen.getByText('Strategy Health')).toBeVisible();
    expect(screen.getByText('LHB Shortline Combo')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Open Strategy Lab' })).toBeVisible();
  });

  it('navigates to Data Explorer from Home', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: 'Research Cockpit' });

    fireEvent.click(within(screen.getByRole('navigation', { name: 'Quick actions' })).getByRole('button', {
      name: 'Data Explorer'
    }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Data Explorer' })).toBeVisible());
  });

  it('exposes side navigation with unique accessible names and current state', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: 'Research Cockpit' });

    const sideNav = screen.getByRole('complementary', { name: 'Workspace navigation' });

    expect(within(sideNav).getByRole('button', { name: 'Open Home workspace' })).toHaveAttribute(
      'aria-current',
      'page'
    );
    expect(screen.getByRole('button', { name: 'Open Strategy Lab workspace' })).toBeVisible();
    expect(screen.getByRole('button', { name: 'Open Generated Reports workspace' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Open Strategy Validation workspace' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open Reports workspace' })).not.toBeInTheDocument();
  });

  it('navigates to Generated Reports workspace and loads reports for the default trade date', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: 'Research Cockpit' });

    const sideNav = screen.getByRole('complementary', { name: 'Workspace navigation' });
    fireEvent.click(within(sideNav).getByRole('button', { name: 'Open Generated Reports workspace' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Generated Reports', level: 1 })).toBeVisible());
    expect(screen.getByText('Local generated artifacts from TopN, risk, factor, backtest, and validation jobs.')).toBeVisible();
    expect(api.fetchOverview).toHaveBeenCalledWith({
      tradeDate: '2026-06-08',
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 5
    });
    expect(await screen.findByText('Daily Market Review')).toBeVisible();
  });

  it('loads reports for the selected report date', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: 'Research Cockpit' });

    const sideNav = screen.getByRole('complementary', { name: 'Workspace navigation' });
    fireEvent.click(within(sideNav).getByRole('button', { name: 'Open Generated Reports workspace' }));
    await screen.findByRole('heading', { name: 'Generated Reports', level: 1 });

    fireEvent.change(screen.getByLabelText('report trade date'), { target: { value: '2026-06-05' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Reports' }));

    await waitFor(() =>
      expect(api.fetchOverview).toHaveBeenLastCalledWith({
        tradeDate: '2026-06-05',
        scoreVersion: 'manual_v1',
        watchlistId: 'default',
        topN: 5
      })
    );
  });
});
