import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';
import { buildBacktestChartPoints, formatBacktestChartTooltip } from '../src/components/BacktestCharts';
import { BacktestLabWorkspace } from '../src/components/BacktestLabWorkspace';
import { BacktestResultDetail } from '../src/components/BacktestResultDetail';
import type { BacktestRunResult, PlatformSummary, StrategyCatalogItem } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchBacktestStrategies: vi.fn(),
  fetchPlatformReadiness: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  fetchMarketMonitorEod: vi.fn(),
  fetchPublicNews: vi.fn(),
  runBacktest: vi.fn(),
  runFreshBacktest: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeStrategies(): StrategyCatalogItem[] {
  return [
    {
      strategy_id: 'lhb_shortline',
      strategy_name: 'LHB Shortline Combo',
      status: 'runnable',
      description: 'Phase15 cash account plus Phase16C delayed exit.',
      factor_groups: ['lhb', 'auction', 'position_control'],
      signal_inputs: ['Phase14C lifecycle entry/exit', 'Phase15 cash account', 'Phase16C limit-break-failed delayed exit'],
      default_parameters: { top_n: 5 },
      latest_evidence: 'lhb_shortline_v1 DB recompute benchmark final_equity=2.7640',
      primary_action: 'Run backtest'
    },
    {
      strategy_id: 'mid_trend',
      strategy_name: 'Mid Trend Combo',
      status: 'runnable',
      description: 'report_mild_bonus plus Top5 weekly max2 selective trend holding protection.',
      factor_groups: ['trend', 'research_overlay'],
      signal_inputs: ['mid_trend funnel', 'report_mild_bonus', 'C2 stock protection'],
      default_parameters: { top_n: 5 },
      latest_evidence: 'report_mild_bonus final_equity=4.2056',
      primary_action: 'Run backtest'
    },
    {
      strategy_id: 'tech_bottleneck',
      strategy_name: 'Tech Bottleneck Combo',
      status: 'runnable',
      description: 'tech_hard_filter plus top5_adaptive_daily_check_max2_v1.',
      factor_groups: ['tech_bottleneck', 'trend'],
      signal_inputs: ['tech_hard_filter', 'top5_adaptive_daily_check_max2_v1'],
      default_parameters: { top_n: 5 },
      latest_evidence: 'tech_hard_filter final_equity=3.4973',
      primary_action: 'Run backtest'
    }
  ];
}

function makeSummary(): PlatformSummary {
  return {
    latest_market_date: '2026-06-08',
    latest_factor_date: '2026-06-08',
    latest_score_date: '2026-06-08',
    market_asset_count: 1,
    score_asset_count: 1,
    factor_count: 2,
    score_versions: ['manual_v1'],
    topn_preview: []
  };
}

function makeRunResult(
  strategyId = 'lhb_shortline',
  strategyName = 'LHB Shortline Combo'
): BacktestRunResult {
  const summary: BacktestRunResult['summary'] = {
    final_equity: 1.12,
    total_return: 0.12,
    max_drawdown: -0.05,
    sharpe_ratio: 1.8,
    actual_start_date: '2026-01-05',
    actual_end_date: '2026-06-08',
    turnover: 1.4
  };
  summary.combo_scheme = `${strategyId}_combo_v1`;
  summary.evidence_source = 'validated replay fixture';
  return {
    strategy_id: strategyId,
    strategy_name: strategyName,
    read_only: false,
    execution_mode: 'validated',
    result_source: 'validated_combo_artifact_rerun',
    elapsed_ms: 1234,
    config: { adjust_type: 'hfq' },
    summary,
    equity_curve: [
      { date: '2026-06-05', equity: 1.1, drawdown: -0.01 },
      { date: '2026-06-08', equity: 1.12, drawdown: -0.02 }
    ],
    positions: [{ date: '2026-06-08', asset_id: 'CN:SZ:300951', weight: 0.05 }],
    trades: [{ date: '2026-06-08', asset_id: 'CN:SZ:300951', side: 'buy', weight: 0.05 }]
  };
}

function deferredRunResult() {
  let resolve!: (result: BacktestRunResult) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<BacktestRunResult>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

function deferredStrategies() {
  let resolve!: (strategies: StrategyCatalogItem[]) => void;
  const promise = new Promise<StrategyCatalogItem[]>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

describe('BacktestLabWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchBacktestStrategies.mockResolvedValue(makeStrategies());
    apiMocks.fetchPlatformReadiness.mockResolvedValue({
      mode: 'eod_local',
      status: 'ready',
      as_of: '2026-06-15T08:30:00+08:00',
      latest_market_date: '2026-06-08',
      checks: [],
      warnings: []
    });
    apiMocks.fetchPlatformSummary.mockResolvedValue(makeSummary());
    apiMocks.fetchStrategyCatalog.mockResolvedValue(makeStrategies());
    apiMocks.runBacktest.mockResolvedValue(makeRunResult());
    apiMocks.runFreshBacktest.mockResolvedValue({ ...makeRunResult(), read_only: false, execution_mode: 'validated' });
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

  it('loads the Backtest Lab catalog with validated combo strategies only', async () => {
    render(<BacktestLabWorkspace />);

    expect((await screen.findAllByText('LHB Shortline Combo')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mid Trend Combo').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Tech Bottleneck Combo').length).toBeGreaterThan(0);
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
    expect(screen.queryByText('Position Control Overlay')).not.toBeInTheDocument();
    expect(screen.getByText('Phase15 cash account plus Phase16C delayed exit.')).toBeInTheDocument();
    expect(screen.queryByText('runnable')).not.toBeInTheDocument();
    expect(screen.queryByText('Run backtest')).not.toBeInTheDocument();
    expect(screen.queryByText('lhb_shortline_v1 DB recompute benchmark final_equity=2.7640')).not.toBeInTheDocument();
    expect(screen.queryByText('replay_only')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('rebalance frequency')).not.toBeInTheDocument();
  });

  it('selects an explicit initial official strategy without starting a backtest', async () => {
    apiMocks.fetchBacktestStrategies.mockResolvedValueOnce(
      makeStrategies().map((strategy) =>
        strategy.strategy_id === 'mid_trend'
          ? {
              ...strategy,
              latest_metrics: {
                as_of_date: '2026-07-18',
                performance_as_of_date: '2026-07-18',
                total_return_pct: 49.12,
                signal_status: 'current_holdings',
                signal_count: 5,
                contract_id: 'mid_trend:balanced:top5_weekly_max2_selective_trend_holding_protection_v1',
                publish_id: 'mid-trend-20260718',
                artifact_version: 'mid_trend_publication_v2',
                contract_status: 'success'
              }
            }
          : strategy
      )
    );
    render(<BacktestLabWorkspace initialStrategyId="mid_trend" />);

    await waitFor(() => expect(screen.getByLabelText('strategy')).toHaveValue('mid_trend'));
    const publication = screen.getByRole('region', { name: 'Mid Trend Combo 策略数据状态' });
    expect(publication).toHaveAttribute('data-strategy-id', 'mid_trend');
    expect(within(publication).queryByText('正式合同')).not.toBeInTheDocument();
    expect(within(publication).queryByText('发布编号')).not.toBeInTheDocument();
    expect(within(publication).queryByText('产物版本')).not.toBeInTheDocument();
    expect(within(publication).getByText('数据正常')).toBeVisible();
    expect(within(publication).getByTestId('strategy-performance-date')).toHaveTextContent('2026-07-18');
    expect(within(publication).getByTestId('strategy-total-return')).toHaveTextContent('+49.12%');
    expect(apiMocks.runBacktest).not.toHaveBeenCalled();
    expect(apiMocks.runFreshBacktest).not.toHaveBeenCalled();
  });

  it('fails closed for an unknown deep-linked strategy instead of selecting the first official strategy', async () => {
    render(<BacktestLabWorkspace initialStrategyId="unknown_strategy" />);

    expect(await screen.findByRole('alert')).toHaveTextContent('未知策略 unknown_strategy');
    expect(screen.getByLabelText('strategy')).toHaveValue('');
    expect(screen.queryByRole('region', { name: /策略数据状态/ })).not.toBeInTheDocument();
    expect(apiMocks.runBacktest).not.toHaveBeenCalled();
    expect(apiMocks.runFreshBacktest).not.toHaveBeenCalled();
  });

  it('ignores an older catalog response after the deep-linked strategy changes', async () => {
    const firstCatalog = deferredStrategies();
    const secondCatalog = deferredStrategies();
    apiMocks.fetchBacktestStrategies
      .mockReturnValueOnce(firstCatalog.promise)
      .mockReturnValueOnce(secondCatalog.promise);
    const view = render(<BacktestLabWorkspace initialStrategyId="lhb_shortline" />);

    view.rerender(<BacktestLabWorkspace initialStrategyId="mid_trend" />);
    await act(async () => secondCatalog.resolve(makeStrategies()));
    await waitFor(() => expect(screen.getByLabelText('strategy')).toHaveValue('mid_trend'));

    await act(async () => firstCatalog.resolve(makeStrategies()));
    expect(screen.getByLabelText('strategy')).toHaveValue('mid_trend');
  });

  it('runs the default LHB combo backtest with default dates and parameters', async () => {
    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    await waitFor(() =>
      expect(apiMocks.runBacktest).toHaveBeenCalledWith({
        strategy_id: 'lhb_shortline',
        start_date: '2026-01-01',
        end_date: '2026-06-18',
        score_version: 'manual_v1',
        top_n: 5,
        transaction_cost_bps: 10,
        max_positions: null,
        max_position_weight: 0.2,
        risk_profile: 'balanced',
        adjust_type: 'hfq'
      })
    );
  });

  it('lets LHB users choose a risk profile for the run request', async () => {
    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    expect(screen.getByLabelText('risk profile')).toHaveValue('balanced');
    fireEvent.change(screen.getByLabelText('risk profile'), { target: { value: 'drawdown_control' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    await waitFor(() =>
      expect(apiMocks.runBacktest).toHaveBeenCalledWith(
        expect.objectContaining({
          strategy_id: 'lhb_shortline',
          risk_profile: 'drawdown_control'
        })
      )
    );
  });

  it('renders backtest results after a run resolves', async () => {
    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    expect(await screen.findByRole('heading', { name: 'Validated backtest' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Result Summary' })).toBeInTheDocument();
    expect(screen.getByText('Validated combo')).toBeInTheDocument();
    expect(screen.getByText('Final Equity')).toBeInTheDocument();
    expect(screen.getByText('1.12x')).toBeInTheDocument();
    expect(screen.getByText('Total Return')).toBeInTheDocument();
    expect(screen.getByText('+12.00%')).toBeInTheDocument();
    expect(screen.getAllByText('Strategy').length).toBeGreaterThan(0);
    expect(screen.getAllByText('lhb_shortline').length).toBeGreaterThan(0);
    expect(screen.getAllByRole('cell', { name: 'CN:SZ:300951' }).length).toBeGreaterThan(0);
    expect(screen.getByText('最近一次回测结果已保留在本页，修改参数后会清空并重新运行。')).toBeInTheDocument();
  });

  it('shows background job guidance while a backtest is pending', async () => {
    const pendingRun = deferredRunResult();
    apiMocks.runBacktest.mockReturnValueOnce(pendingRun.promise);

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    expect(screen.getByText('回测会提交为后台任务，页面自动等待结果；耗时较长时可先查看本页保留的最近一次结果。')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    expect(screen.getByRole('button', { name: 'Running...' })).toBeDisabled();
    expect(screen.getByText('后台回测任务已提交，正在等待结果返回。请不要重复点击或直接调用同步 run-fresh 接口。')).toBeInTheDocument();

    await act(async () => {
      pendingRun.resolve(makeRunResult());
    });

    expect(await screen.findByRole('heading', { name: 'Validated backtest' })).toBeInTheDocument();
  });

  it('rejects accidental vectorized results for selected LHB Shortline runs', async () => {
    apiMocks.runBacktest.mockResolvedValue({
      ...makeRunResult('mid_trend', 'Mid Trend Combo'),
      result_source: 'live_vectorized_backtest'
    });

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    expect(await screen.findByText(/LHB Shortline must run lhb_shortline_v1/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Fresh backtest' })).not.toBeInTheDocument();
  });

  it('uses the latest equity curve value when final equity is absent from summary', () => {
    const result = makeRunResult();
    const { final_equity: _finalEquity, ...summary } = result.summary;

    render(<BacktestResultDetail result={{ ...result, summary }} />);

    expect(screen.getByText('Final Equity')).toBeInTheDocument();
    expect(screen.getByText('1.12x')).toBeInTheDocument();
  });

  it('warns when LHB lifecycle replay is not daily marked to market', () => {
    const result = makeRunResult('lhb_shortline', 'LHB Shortline Combo');
    render(
      <BacktestResultDetail
        result={{
          ...result,
          summary: {
            ...result.summary,
            detail_source: 'phase16c_rebuilt_cash_account',
            mark_to_market: false
          }
        }}
      />
    );

    expect(screen.getByText('Risk metric caveat')).toBeInTheDocument();
    expect(screen.getByText(/not daily marked to market/i)).toBeInTheDocument();
  });

  it('hides empty Sharpe and replaces raw result tables with a trade ledger', () => {
    const result = makeRunResult('lhb_shortline', 'LHB Shortline Combo');
    render(
      <BacktestResultDetail
        result={{
          ...result,
          summary: {
            ...result.summary,
            sharpe_ratio: null
          },
          trades: [
            {
              date: '2026-06-08',
              asset_id: 'CN:SZ:300951',
              side: 'buy',
              weight: 0.2,
              price: 12.34
            }
          ],
          positions: [{ date: '2026-06-08', asset_id: 'CN:SZ:300951', weight: 0.2 }]
        }}
      />
    );

    expect(screen.queryByText('Sharpe')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Equity / Drawdown Chart' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Completed Trades' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Positions' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Trades' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Equity / Drawdown Rows' })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Position' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '20.00%' })).toBeInTheDocument();
  });

  it('renders LHB shortline completed trade lifecycle fields from backend trade column names', () => {
    render(
      <BacktestResultDetail
        result={{
          ...makeRunResult(),
          trades: [
            {
              trade_date: '2026-01-05',
              ts_code: '000001.SZ',
              entry_trade_date: '2026-01-06',
              entry_time: '10:30:00',
              entry_price: 14.38,
              exit_trade_date: '2026-01-08',
              exit_time: '14:55:00',
              exit_price: 16.1,
              position_notional: 0.2,
              realized_return: 0.1191
            }
          ],
          positions: [
            {
              trade_date: '2026-01-05',
              ts_code: '000001.SZ',
              position_weight: 0.2
            }
          ]
        }}
      />
    );

    const ledger = screen.getByRole('heading', { name: 'Completed Trades' }).closest('section')!;
    expect(within(ledger).getByRole('cell', { name: '000001.SZ' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '2026-01-06' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '10:30:00' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '14.38' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '2026-01-08' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '14:55:00' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '20.00%' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '16.1' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '+11.91%' })).toBeInTheDocument();
    expect(within(ledger).queryByRole('columnheader', { name: 'Side' })).not.toBeInTheDocument();
    expect(within(ledger).queryByRole('columnheader', { name: 'Current Holding' })).not.toBeInTheDocument();
  });

  it('renders user-readable Chinese exit reasons in the completed trade ledger', () => {
    render(
      <BacktestResultDetail
        result={{
          ...makeRunResult(),
          trades: [
            {
              trade_date: '2026-01-05',
              ts_code: '000001.SZ',
              entry_trade_date: '2026-01-06',
              entry_price: 14.38,
              exit_trade_date: '2026-01-08',
              exit_price: 16.1,
              position_notional: 0.2,
              realized_return: 0.1191,
              exit_reason: 'intraday_high_near_limit_but_failed_close_below_vwap'
            },
            {
              trade_date: '2026-01-06',
              ts_code: '000002.SZ',
              entry_trade_date: '2026-01-07',
              entry_price: 10,
              exit_trade_date: '2026-01-09',
              exit_price: 9.8,
              position_notional: 0.2,
              realized_return: -0.02,
              exit_reason: 'new_internal_reason'
            }
          ],
          positions: []
        }}
      />
    );

    const ledger = screen.getByRole('heading', { name: 'Completed Trades' }).closest('section')!;
    expect(within(ledger).getByRole('cell', { name: '冲高接近涨停后回落，收盘跌破均价' })).toBeInTheDocument();
    expect(within(ledger).queryByText('intraday_high_near_limit_but_failed_close_below_vwap')).not.toBeInTheDocument();
    const unknownReason = within(ledger).getByRole('cell', { name: '其他卖出原因' });
    expect(unknownReason).toHaveAttribute('title', 'new_internal_reason');
    expect(within(ledger).queryByText('new_internal_reason')).not.toBeInTheDocument();
  });

  it('renders portfolio rebalance trades for Mid Trend and Tech Bottleneck results', () => {
    render(
      <BacktestResultDetail
        result={{
          ...makeRunResult('mid_trend', 'Mid Trend Combo'),
          summary: {
            final_equity: 1.35,
            total_return: 0.35,
            max_drawdown: -0.13,
            trade_rows: 185,
            position_rows: 113
          },
          trades: [
            {
              trade_date: '2026-06-10',
              asset_id: 'CN:SZ:300408',
              side: 'buy',
              previous_weight: 0,
              target_weight: 0.2,
              turnover_contribution: 0.2,
              transaction_cost: 0.0004,
              reason: 'rebalance'
            },
            {
              trade_date: '2026-06-11',
              asset_id: 'CN:SH:601963',
              side: 'sell',
              previous_weight: 0.2,
              target_weight: 0,
              delta_weight: -0.2,
              turnover_contribution: 0.2,
              transaction_cost: 0.0004,
              reason: 'risk_exit'
            }
          ],
          positions: []
        }}
      />
    );

    const ledger = screen.getByRole('heading', { name: 'Rebalance Trades' }).closest('section')!;
    expect(within(ledger).getByRole('columnheader', { name: 'Trade Date' })).toBeInTheDocument();
    expect(within(ledger).getByRole('columnheader', { name: 'Side' })).toBeInTheDocument();
    expect(within(ledger).getByRole('columnheader', { name: 'Previous Weight' })).toBeInTheDocument();
    expect(within(ledger).getByRole('columnheader', { name: 'Target Weight' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '2026-06-11' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: 'CN:SH:601963' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: 'CN:SZ:300408' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '买入' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '卖出' })).toBeInTheDocument();
    expect(within(ledger).getAllByRole('cell', { name: '20.00%' }).length).toBeGreaterThanOrEqual(2);
    expect(within(ledger).getAllByRole('cell', { name: '0.00%' })).toHaveLength(2);
    expect(within(ledger).getByRole('cell', { name: '+20.00%' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '-20.00%' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '定期调仓' })).toBeInTheDocument();
    expect(within(ledger).getByRole('cell', { name: '风险退出' })).toBeInTheDocument();
  });

  it('renders concise LHB shortline v1 strategy setup and keeps engine details folded', () => {
    const result = makeRunResult('lhb_shortline', 'LHB Shortline Combo');
    render(
      <BacktestResultDetail
        result={{
          ...result,
          result_source: 'lhb_shortline_v1',
          elapsed_ms: 72900,
          config: {
            top_n: 5,
            max_position_weight: 0.2,
            transaction_cost_bps: 10
          },
          summary: {
            ...result.summary,
            engine_version: 'lhb_shortline_v1',
            strategy: 'auction_enhanced_rerank',
            risk_profile_label: '最佳平衡',
            phase18c_max_positions: 5,
            data_coverage: {
              source: 'db_base_tables',
              lhb_feature_rows: 7358,
              daily_bar_rows: 531871
            },
            legacy_benchmark: {
              benchmark_name: 'legacy_best_lhb_research',
              legacy_final_equity: 2.764,
              final_equity_delta: -1.644
            }
          }
        }}
      />
    );

    expect(screen.getByRole('heading', { name: 'Performance' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Strategy Setup' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Benchmark Comparison' })).not.toBeInTheDocument();
    expect(screen.getByText('Strategy')).toBeInTheDocument();
    expect(screen.getByText('Top N')).toBeInTheDocument();
    expect(screen.getByText('Max Weight Per Stock')).toBeInTheDocument();
    expect(screen.getByText('Max Holdings')).toBeInTheDocument();
    expect(screen.getByText('Cost')).toBeInTheDocument();
    expect(screen.getByText('Runtime')).toBeInTheDocument();
    expect(screen.getByText('Risk Profile')).toBeInTheDocument();
    expect(screen.getAllByText('最佳平衡').length).toBeGreaterThan(0);
    expect(screen.getAllByText('lhb_shortline').length).toBeGreaterThan(0);
    expect(screen.getAllByText('5').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('20.00%')).toBeInTheDocument();
    expect(screen.getByText('10 bps')).toBeInTheDocument();
    expect(screen.getByText('72.9s')).toBeInTheDocument();
    expect(screen.queryByText('Selector')).not.toBeInTheDocument();
    expect(screen.queryByText('Source')).not.toBeInTheDocument();
    expect(screen.queryByText('Engine')).not.toBeInTheDocument();
    expect(screen.queryByText('DB Coverage')).not.toBeInTheDocument();
    expect(screen.queryByText('7358 LHB / 531871 daily bars')).not.toBeInTheDocument();
    expect(screen.getByText(/legacy_best_lhb_research/)).toBeInTheDocument();
    expect(screen.getByText('Technical Details')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Raw Summary' })).not.toBeInTheDocument();
  });

  it('formats chart tooltip with equity plus drawdown or daily return', () => {
    const points = buildBacktestChartPoints({
      ...makeRunResult(),
      equity_curve: [
        { date: '2026-01-05', equity: 1, drawdown: 0 },
        { date: '2026-01-06', equity: 1.03, drawdown: 0, net_return: 0.03 },
        { date: '2026-01-07', equity: 1.01, drawdown: -0.019417 }
      ]
    });

    expect(formatBacktestChartTooltip(points[1])).toEqual([
      '2026-01-06',
      'Equity 1.0300x',
      'Daily Return +3.00%'
    ]);
    expect(formatBacktestChartTooltip(points[2])).toEqual([
      '2026-01-07',
      'Equity 1.0100x',
      'Drawdown -1.94%'
    ]);
  });

  it('does not expose cached replay actions', async () => {
    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');

    expect(screen.queryByRole('button', { name: 'Load Cached Replay' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Load Cached Replay Comparison' })).not.toBeInTheDocument();
  });

  it('runs LHB Shortline with the selected date range and risk parameters', async () => {
    render(<BacktestLabWorkspace />);

    const strategySelect = await screen.findByLabelText('strategy');
    fireEvent.change(strategySelect, { target: { value: 'lhb_shortline' } });
    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    await waitFor(() =>
      expect(apiMocks.runBacktest).toHaveBeenCalledWith({
        strategy_id: 'lhb_shortline',
        start_date: '2026-01-01',
        end_date: '2026-06-18',
        score_version: 'manual_v1',
        top_n: 5,
        transaction_cost_bps: 10,
        max_positions: null,
        max_position_weight: 0.2,
        risk_profile: 'balanced',
        adjust_type: 'hfq'
      })
    );
  });

  it('runs comparison across validated combo strategies with identical parameters', async () => {
    apiMocks.runBacktest.mockImplementation((request: { strategy_id: string }) => {
      const strategy = makeStrategies().find((row) => row.strategy_id === request.strategy_id);
      return Promise.resolve(makeRunResult(request.strategy_id, strategy?.strategy_name ?? request.strategy_id));
    });

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Comparison' }));

    await waitFor(() => expect(apiMocks.runBacktest).toHaveBeenCalledTimes(3));

    const expectedStrategyIds = [
      'lhb_shortline',
      'mid_trend',
      'tech_bottleneck'
    ];
    expectedStrategyIds.forEach((strategyId, index) => {
      const lhbPayload = strategyId === 'lhb_shortline' ? { risk_profile: 'balanced' } : {};
      expect(apiMocks.runBacktest).toHaveBeenNthCalledWith(index + 1, {
        strategy_id: strategyId,
        start_date: '2026-01-01',
        end_date: '2026-06-18',
        score_version: 'manual_v1',
        top_n: 5,
        transaction_cost_bps: 10,
        max_positions: null,
        max_position_weight: 0.2,
        ...lhbPayload,
        adjust_type: 'hfq'
      });
    });
    expect(screen.getByRole('heading', { name: 'Strategy Comparison' })).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'LHB Shortline Combo' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('cell', { name: 'Mid Trend Combo' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('cell', { name: 'validated' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('cell', { name: 'validated_combo_artifact_rerun' }).length).toBeGreaterThan(0);
  });

  it('renders comparison progress immediately and updates each strategy as it settles', async () => {
    const lhbRun = deferredRunResult();
    const midRun = deferredRunResult();
    const techRun = deferredRunResult();
    apiMocks.runBacktest
      .mockReturnValueOnce(lhbRun.promise)
      .mockReturnValueOnce(midRun.promise)
      .mockReturnValueOnce(techRun.promise);

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Comparison' }));

    expect(screen.getByRole('heading', { name: 'Strategy Comparison' })).toBeInTheDocument();
    expect(screen.getByText('0 / 3 completed')).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'running' })).toHaveLength(3);
    expect(screen.getByRole('button', { name: 'Comparing...' })).toBeDisabled();

    await act(async () => {
      lhbRun.resolve(makeRunResult('lhb_shortline', 'LHB Shortline Combo'));
    });

    expect(screen.getByText('1 / 3 completed')).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'passed' })).toHaveLength(1);
    expect(screen.getAllByRole('cell', { name: 'running' })).toHaveLength(2);

    await act(async () => {
      midRun.reject(new Error('no mid-trend signals'));
    });

    expect(screen.getByText('2 / 3 completed')).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'failed' })).toHaveLength(1);
    expect(screen.getByRole('cell', { name: 'no mid-trend signals' })).toBeInTheDocument();

    await act(async () => {
      techRun.resolve(makeRunResult('tech_bottleneck', 'Tech Bottleneck Combo'));
    });

    await waitFor(() => expect(screen.getByRole('button', { name: 'Run Comparison' })).not.toBeDisabled());
    expect(screen.getByText('3 / 3 completed')).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'passed' })).toHaveLength(2);
    expect(screen.queryByRole('cell', { name: 'running' })).not.toBeInTheDocument();
  });

  it('defaults comparison detail to the first strategy after out-of-order results settle', async () => {
    const lhbRun = deferredRunResult();
    const midRun = deferredRunResult();
    const techRun = deferredRunResult();
    apiMocks.runBacktest
      .mockReturnValueOnce(lhbRun.promise)
      .mockReturnValueOnce(midRun.promise)
      .mockReturnValueOnce(techRun.promise);

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Comparison' }));

    await act(async () => {
      techRun.resolve(makeRunResult('tech_bottleneck', 'Tech Bottleneck Combo'));
      midRun.resolve(makeRunResult('mid_trend', 'Mid Trend Combo'));
      lhbRun.resolve(makeRunResult('lhb_shortline', 'LHB Shortline Combo'));
    });

    await waitFor(() => expect(screen.getByText('3 / 3 completed')).toBeInTheDocument());
    expect(screen.getByRole('heading', { name: 'Validated backtest' })).toBeInTheDocument();
    expect(screen.getByText(/LHB Shortline Combo returned/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Viewing' })).toBeInTheDocument();
  });

  it('disables Run Backtest for backend-invalid inputs', async () => {
    render(<BacktestLabWorkspace />);
    await screen.findAllByText('LHB Shortline Combo');

    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '0' } });
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('max position percent'), { target: { value: '-1' } });
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('max position percent'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('transaction cost bps'), { target: { value: '-1' } });
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeDisabled();
  });

  it('ignores pending run responses after inputs change', async () => {
    const pendingRun = deferredRunResult();
    apiMocks.runBacktest.mockReturnValueOnce(pendingRun.promise);

    render(<BacktestLabWorkspace />);
    await screen.findAllByText('LHB Shortline Combo');

    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));
    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '10' } });

    await act(async () => {
      pendingRun.resolve(makeRunResult());
    });

    expect(screen.queryByRole('heading', { name: 'Validated backtest' })).not.toBeInTheDocument();
  });

  it('opens Backtest Lab through Strategy Lab from AppShell side navigation', async () => {
    render(<AppShell />);

    const navigation = within(screen.getByRole('navigation', { name: 'Workspace navigation' }));
    fireEvent.click(navigation.getByRole('button', { name: 'Open Strategy Lab workspace' }));

    expect(await screen.findByRole('heading', { name: 'Strategy Lab' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Run Backtest', selected: true })).toBeInTheDocument();
    expect((await screen.findAllByText('LHB Shortline Combo')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
  });
});
