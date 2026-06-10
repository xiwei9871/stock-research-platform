import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';
import { BacktestLabWorkspace } from '../src/components/BacktestLabWorkspace';
import { BacktestResultDetail } from '../src/components/BacktestResultDetail';
import type { BacktestRunResult, PlatformSummary, StrategyCatalogItem } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchBacktestStrategies: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
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
      default_parameters: { top_n: 20 },
      latest_evidence: 'Phase16C account_final_equity=3.1279',
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

describe('BacktestLabWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchBacktestStrategies.mockResolvedValue(makeStrategies());
    apiMocks.fetchPlatformSummary.mockResolvedValue(makeSummary());
    apiMocks.fetchStrategyCatalog.mockResolvedValue(makeStrategies());
    apiMocks.runBacktest.mockResolvedValue(makeRunResult());
    apiMocks.runFreshBacktest.mockResolvedValue({ ...makeRunResult(), read_only: false, execution_mode: 'validated' });
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
    expect(screen.queryByText('Phase16C account_final_equity=3.1279')).not.toBeInTheDocument();
    expect(screen.queryByText('replay_only')).not.toBeInTheDocument();
  });

  it('runs the default LHB combo backtest with default dates and parameters', async () => {
    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Fresh Backtest' }));

    await waitFor(() =>
      expect(apiMocks.runFreshBacktest).toHaveBeenCalledWith({
        strategy_id: 'lhb_shortline',
        start_date: '2026-01-01',
        end_date: '2026-06-08',
        score_version: 'manual_v1',
        top_n: 20,
        rebalance_frequency: 'weekly',
        transaction_cost_bps: 10,
        max_positions: 20,
        adjust_type: 'hfq'
      })
    );
  });

  it('renders backtest results after a run resolves', async () => {
    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Fresh Backtest' }));

    expect(await screen.findByRole('heading', { name: 'Validated backtest' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Result Summary' })).toBeInTheDocument();
    expect(screen.getByText('Validated combo')).toBeInTheDocument();
    expect(screen.getByText('Final Equity')).toBeInTheDocument();
    expect(screen.getByText('1.12x')).toBeInTheDocument();
    expect(screen.getByText('Total Return')).toBeInTheDocument();
    expect(screen.getByText('+12.00%')).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'CN:SZ:300951' }).length).toBeGreaterThan(0);
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
    fireEvent.click(screen.getByRole('button', { name: 'Run Fresh Backtest' }));

    await waitFor(() =>
      expect(apiMocks.runFreshBacktest).toHaveBeenCalledWith({
        strategy_id: 'lhb_shortline',
        start_date: '2026-01-01',
        end_date: '2026-06-08',
        score_version: 'manual_v1',
        top_n: 20,
        rebalance_frequency: 'weekly',
        transaction_cost_bps: 10,
        max_positions: 20,
        adjust_type: 'hfq'
      })
    );
  });

  it('runs comparison across validated combo strategies with identical parameters', async () => {
    apiMocks.runFreshBacktest.mockImplementation((request: { strategy_id: string }) => {
      const strategy = makeStrategies().find((row) => row.strategy_id === request.strategy_id);
      return Promise.resolve(makeRunResult(request.strategy_id, strategy?.strategy_name ?? request.strategy_id));
    });

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Fresh Comparison' }));

    await waitFor(() => expect(apiMocks.runFreshBacktest).toHaveBeenCalledTimes(3));

    const expectedStrategyIds = [
      'lhb_shortline',
      'mid_trend',
      'tech_bottleneck'
    ];
    expectedStrategyIds.forEach((strategyId, index) => {
      expect(apiMocks.runFreshBacktest).toHaveBeenNthCalledWith(index + 1, {
        strategy_id: strategyId,
        start_date: '2026-01-01',
        end_date: '2026-06-08',
        score_version: 'manual_v1',
        top_n: 20,
        rebalance_frequency: 'weekly',
        transaction_cost_bps: 10,
        max_positions: 20,
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
    apiMocks.runFreshBacktest
      .mockReturnValueOnce(lhbRun.promise)
      .mockReturnValueOnce(midRun.promise)
      .mockReturnValueOnce(techRun.promise);

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Fresh Comparison' }));

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

    await waitFor(() => expect(screen.getByRole('button', { name: 'Run Fresh Comparison' })).not.toBeDisabled());
    expect(screen.getByText('3 / 3 completed')).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'passed' })).toHaveLength(2);
    expect(screen.queryByRole('cell', { name: 'running' })).not.toBeInTheDocument();
  });

  it('defaults comparison detail to the first strategy after out-of-order results settle', async () => {
    const lhbRun = deferredRunResult();
    const midRun = deferredRunResult();
    const techRun = deferredRunResult();
    apiMocks.runFreshBacktest
      .mockReturnValueOnce(lhbRun.promise)
      .mockReturnValueOnce(midRun.promise)
      .mockReturnValueOnce(techRun.promise);

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('LHB Shortline Combo');
    fireEvent.click(screen.getByRole('button', { name: 'Run Fresh Comparison' }));

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

  it('disables Run Fresh Backtest for backend-invalid inputs', async () => {
    render(<BacktestLabWorkspace />);
    await screen.findAllByText('LHB Shortline Combo');

    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '0' } });
    expect(screen.getByRole('button', { name: 'Run Fresh Backtest' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('max positions'), { target: { value: '-1' } });
    expect(screen.getByRole('button', { name: 'Run Fresh Backtest' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('max positions'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('transaction cost bps'), { target: { value: '-1' } });
    expect(screen.getByRole('button', { name: 'Run Fresh Backtest' })).toBeDisabled();
  });

  it('ignores pending run responses after inputs change', async () => {
    const pendingRun = deferredRunResult();
    apiMocks.runFreshBacktest.mockReturnValueOnce(pendingRun.promise);

    render(<BacktestLabWorkspace />);
    await screen.findAllByText('LHB Shortline Combo');

    fireEvent.click(screen.getByRole('button', { name: 'Run Fresh Backtest' }));
    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '10' } });

    await act(async () => {
      pendingRun.resolve(makeRunResult());
    });

    expect(screen.queryByRole('heading', { name: 'Validated backtest' })).not.toBeInTheDocument();
  });

  it('opens Backtest Lab from AppShell side navigation', async () => {
    render(<AppShell />);

    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));
    fireEvent.click(navigation.getByRole('button', { name: 'Open Backtest Lab workspace' }));

    expect(await screen.findByRole('heading', { name: 'Backtest Lab' })).toBeInTheDocument();
    expect((await screen.findAllByText('LHB Shortline Combo')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
  });
});
