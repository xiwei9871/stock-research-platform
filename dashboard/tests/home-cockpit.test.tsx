import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AppShell } from '../src/components/AppShell';

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
  fetchPublicNews: vi.fn()
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
