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
  fetchPlatformReadiness: vi.fn(),
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
    vi.mocked(api.fetchPlatformReadiness).mockResolvedValue({
      mode: 'eod_local',
      status: 'PARTIAL',
      as_of: '2026-06-15T08:30:00+08:00',
      latest_market_date: '2026-06-12',
      latest_trade_date: '2026-06-12',
      display_trade_date: '2026-06-08',
      candidate_trade_date: '2026-06-12',
      checks: [
        {
          key: 'market_data',
          label: 'Market data',
          status: 'ready',
          detail: 'Latest EOD data loaded'
        },
        {
          key: 'news_flow',
          label: 'News flow',
          status: 'partial',
          detail: 'Collector is lagging'
        }
      ],
      warnings: ['Generated Reports unavailable']
    });
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
        latest_evidence: 'Top5/20%/10bps 净值约 2.6069，最大回撤约 -5.32%。',
        latest_metrics: {
          as_of_date: '2026-06-08',
          total_return_pct: 160.7,
          max_drawdown_pct: -5.3,
          latest_day_return_pct: 1.2,
          latest_day_drawdown_pct: -0.4,
          signal_status: 'no_position_rows',
          signal_count: null
        },
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
        latest_evidence: '2026区间净值 1.5599，最大回撤 -17.52%。',
        latest_metrics: {
          as_of_date: '2026-06-02',
          total_return_pct: 56.0,
          max_drawdown_pct: -17.5,
          latest_day_return_pct: -2.1,
          latest_day_drawdown_pct: -2.7,
          signal_status: 'connected',
          signal_count: 5
        },
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
        latest_evidence: '2026-01-01 至 2026-06-08 净值约 1.6007，最大回撤约 -8.30%。',
        latest_metrics: {
          as_of_date: '2026-06-08',
          total_return_pct: 60.1,
          max_drawdown_pct: -8.3,
          latest_day_return_pct: 0.8,
          latest_day_drawdown_pct: -0.5,
          signal_status: 'connected',
          signal_count: 5
        },
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

  it('renders a strategy-centered command center', async () => {
    render(<AppShell />);

    expect(await screen.findByText('策略指挥中心')).toBeVisible();
    expect(screen.getByText('启用策略表现')).toBeVisible();
    expect(screen.getByText('策略持仓状态')).toBeVisible();
    expect(screen.getByText('市场环境')).toBeVisible();
    expect(screen.getByText('高质量新闻')).toBeVisible();
    expect(within(screen.getByRole('region', { name: '首页状态' })).getByText('部分可用')).toBeVisible();
    expect(screen.getByText('生成报告不可用')).toBeVisible();
    expect(screen.queryByText('Strategy Health')).not.toBeInTheDocument();
    expect(screen.queryByText('Market Pulse')).not.toBeInTheDocument();
    expect(screen.queryByText('Today Focus')).not.toBeInTheDocument();
    expect(screen.queryByText('Today Actions')).not.toBeInTheDocument();
    expect(screen.queryByText('CN:SZ:300951')).not.toBeInTheDocument();

    const strategyPerformance = within(screen.getByRole('region', { name: '启用策略表现' }));
    expect(strategyPerformance.getByText('LHB Shortline Combo')).toBeVisible();
    expect(strategyPerformance.getByText('+160.7%')).toBeVisible();
    expect(strategyPerformance.getByText('-5.3%')).toBeVisible();
    expect(strategyPerformance.getByText('+1.2%')).toBeVisible();
    expect(strategyPerformance.getAllByText('正常')).toHaveLength(2);
    expect(strategyPerformance.getByText('Mid Trend Combo')).toBeVisible();
    expect(strategyPerformance.getByText('+56.0%')).toBeVisible();
    expect(strategyPerformance.getByText('-17.5%')).toBeVisible();
    expect(strategyPerformance.getByText('-2.1%')).toBeVisible();
    expect(strategyPerformance.getByText('复盘')).toBeVisible();
    expect(strategyPerformance.getByText('Tech Bottleneck Combo')).toBeVisible();
    expect(strategyPerformance.getByText('+60.1%')).toBeVisible();
    expect(strategyPerformance.getByText('-8.3%')).toBeVisible();
    expect(strategyPerformance.getByText('+0.8%')).toBeVisible();
    expect(strategyPerformance.getByText('持仓明细暂无')).toBeVisible();
    expect(strategyPerformance.getAllByText('最新持仓 5')).toHaveLength(2);
    expect(strategyPerformance.getAllByText('截至 2026-06-08')).toHaveLength(2);

    const marketRegime = within(screen.getByRole('region', { name: '市场环境' }));
    expect(marketRegime.getByText('73.6')).toBeVisible();
    expect(marketRegime.getByText('偏热')).toBeVisible();
    expect(marketRegime.getByText('涨跌家数')).toBeVisible();
    expect(marketRegime.getByText('3,610 / 1,492')).toBeVisible();
    expect(marketRegime.getByText(/强涨 269，强跌 55/)).toBeVisible();
    expect(marketRegime.getByText('涨停 / 跌停')).toBeVisible();
    expect(marketRegime.getByText('90 / 10')).toBeVisible();
    expect(marketRegime.getAllByText(/炸板 55，炸板率 37.9%/).length).toBeGreaterThan(0);
    expect(marketRegime.getByText('首板 / 二板')).toBeVisible();
    expect(marketRegime.getByText('58 / 21')).toBeVisible();
    expect(marketRegime.getByText('三板以上 / 高度')).toBeVisible();
    expect(marketRegime.getByText('11 / 6')).toBeVisible();
    expect(marketRegime.getByText('连板数量')).toBeVisible();
    expect(marketRegime.getByText('二板数量')).toBeVisible();
    expect(marketRegime.getByText('三板以上')).toBeVisible();
    expect(marketRegime.getByText('金钼股份')).toBeVisible();
    expect(marketRegime.getAllByText('股票列表未接入')).toHaveLength(1);
    expect(marketRegime.getByText('涨跌广度评分')).toBeVisible();
    expect(marketRegime.getByText('权重 25%：上涨/下跌比例 + 强涨/强跌比例')).toBeVisible();
    expect(marketRegime.getByText('涨停表现评分')).toBeVisible();
    expect(marketRegime.getByText('连板接力评分')).toBeVisible();
    expect(marketRegime.getByText('权重 25%：涨停数量加分，跌停和炸板率扣分')).toBeVisible();
    expect(marketRegime.getByText('权重 20%：最高连板高度 + 二板以上占涨停比例')).toBeVisible();
    expect(marketRegime.getByText('赚钱效应评分')).toBeVisible();
    expect(marketRegime.getByText('66.8 分')).toBeVisible();
    expect(marketRegime.getByText(/情绪偏强但需要看炸板压力/)).toBeVisible();

    const strategySignals = within(screen.getByRole('region', { name: '策略持仓状态' }));
    expect(strategySignals.getByText('LHB Shortline Combo')).toBeVisible();
    expect(strategySignals.getByText('Mid Trend Combo')).toBeVisible();
    expect(strategySignals.getByText('Tech Bottleneck Combo')).toBeVisible();
    expect(strategySignals.getByText('持仓明细暂无')).toBeVisible();
    expect(strategySignals.getAllByText('最新持仓 5')).toHaveLength(2);
    expect(strategySignals.getByText('非买卖建议')).toBeVisible();
    expect(strategySignals.getByText(/最新回测持仓数量/)).toBeVisible();

    const qualityNews = within(screen.getByRole('region', { name: '高质量新闻' }));
    expect(qualityNews.getByText('首页快讯')).toBeVisible();
    expect(qualityNews.getByText('1')).toBeVisible();
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
    expect(api.fetchPublicNews).toHaveBeenCalledWith(
      expect.objectContaining({ limit: 5, minQualityScore: 65 })
    );
    expect(screen.queryByRole('navigation', { name: 'Quick actions' })).not.toBeInTheDocument();
  });

  it('keeps core cockpit content when platform readiness fails', async () => {
    vi.mocked(api.fetchPlatformReadiness).mockRejectedValueOnce(new Error('readiness unavailable'));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('平台就绪状态不可用：readiness unavailable')).toBeVisible();
    expect(screen.getByText('策略持仓状态')).toBeVisible();
    expect(screen.getByText('市场环境')).toBeVisible();
  });

  it('keeps core cockpit content when optional home widgets fail', async () => {
    vi.mocked(api.fetchMarketMonitorEod).mockRejectedValueOnce(new Error('market monitor unavailable'));
    vi.mocked(api.fetchPublicNews).mockRejectedValueOnce(new Error('news unavailable'));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('平台日期')).toBeVisible();
    expect(screen.getAllByText('2026-06-08')[0]).toBeVisible();
    expect(screen.getByText('策略持仓状态')).toBeVisible();
    expect(screen.getByText('启用策略表现')).toBeVisible();
    expect(screen.getAllByText('LHB Shortline Combo')[0]).toBeVisible();
    expect(screen.getByText('市场环境不可用：market monitor unavailable')).toBeVisible();
    expect(screen.getByText('新闻流不可用：news unavailable')).toBeVisible();
  });

  it('does not load manual v1 evidence digest rows on the home page', async () => {
    render(<AppShell />);

    expect(await screen.findByText('策略指挥中心')).toBeVisible();
    expect(screen.queryByText('Strong evidence')).not.toBeInTheDocument();
    expect(screen.queryByText('CN:SZ:300951')).not.toBeInTheDocument();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
  });

  it('ignores manual v1 topn rows even when platform summary has them', async () => {
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

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.queryByText('CN:SZ:000001')).not.toBeInTheDocument();
    expect(screen.queryByText('CN:SZ:000006')).not.toBeInTheDocument();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
  });

  it('does not request evidence digests when platform summary fails', async () => {
    vi.mocked(api.fetchPlatformSummary).mockRejectedValueOnce(new Error('summary unavailable'));

    render(<AppShell />);

    expect(await screen.findByText('平台摘要不可用：summary unavailable')).toBeVisible();
    expect(api.fetchEvidenceDigest).not.toHaveBeenCalled();
  });

  it('renders core cockpit content while optional home widgets are still pending', async () => {
    vi.mocked(api.fetchMarketMonitorEod).mockReturnValueOnce(new Promise(() => undefined));
    vi.mocked(api.fetchPublicNews).mockReturnValueOnce(new Promise(() => undefined));

    render(<AppShell />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('平台日期')).toBeVisible();
    expect(screen.getAllByText('2026-06-08')[0]).toBeVisible();
    expect(screen.getByText('启用策略表现')).toBeVisible();
    expect(screen.getAllByText('LHB Shortline Combo')[0]).toBeVisible();
    expect(screen.getByRole('button', { name: '打开策略实验室' })).toBeVisible();
  });

  it('navigates to Data Explorer from Home', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '策略指挥中心' });

    const sideNav = screen.getByRole('complementary', { name: 'Workspace navigation' });
    fireEvent.click(within(sideNav).getByRole('button', { name: 'Open Data Explorer workspace' }));

    await waitFor(() => expect(screen.getByRole('heading', { name: 'Data Explorer' })).toBeVisible());
  });

  it('exposes side navigation with unique accessible names and current state', async () => {
    render(<AppShell />);
    await screen.findByRole('heading', { name: '策略指挥中心' });

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
    await screen.findByRole('heading', { name: '策略指挥中心' });

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
    await screen.findByRole('heading', { name: '策略指挥中心' });

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
