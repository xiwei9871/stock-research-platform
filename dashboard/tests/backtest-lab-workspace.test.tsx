import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppShell } from '../src/components/AppShell';
import { BacktestLabWorkspace } from '../src/components/BacktestLabWorkspace';
import type { BacktestRunResult, PlatformSummary, StrategyCatalogItem } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchBacktestStrategies: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  runBacktest: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeStrategies(): StrategyCatalogItem[] {
  return [
    {
      strategy_id: 'manual_v1_topn_rotation',
      strategy_name: 'Manual V1 TopN Rotation',
      status: 'runnable',
      description: 'Manual score TopN weekly rotation.',
      factor_groups: ['momentum', 'quality'],
      signal_inputs: ['factor.stock_score_daily'],
      default_parameters: { top_n: 20 },
      latest_evidence: 'vectorized_topn_backtest',
      primary_action: 'Run backtest'
    },
    {
      strategy_id: 'lhb_shortline',
      strategy_name: 'LHB Shortline',
      status: 'runnable',
      description: '龙虎榜超短线 validation strategy.',
      factor_groups: ['lhb', 'momentum'],
      signal_inputs: ['lhb_events', 'technical_factors'],
      default_parameters: { top_n: 20 },
      latest_evidence: 'strategy_validation',
      primary_action: 'Run backtest'
    },
    {
      strategy_id: 'mid_trend',
      strategy_name: 'Mid Trend Shortline',
      status: 'runnable',
      description: 'Shortline trend continuation strategy.',
      factor_groups: ['trend', 'liquidity'],
      signal_inputs: ['factor_values', 'manual_scores'],
      default_parameters: { top_n: 20 },
      latest_evidence: 'strategy_validation',
      primary_action: 'Run backtest'
    },
    {
      strategy_id: 'tech_bottleneck',
      strategy_name: 'Tech Bottleneck Discovery+',
      status: 'runnable',
      description: 'Technical bottleneck discovery strategy.',
      factor_groups: ['breakout', 'volume'],
      signal_inputs: ['factor_values', 'manual_scores'],
      default_parameters: { top_n: 20 },
      latest_evidence: 'strategy_validation',
      primary_action: 'Run backtest'
    },
    {
      strategy_id: 'position_control',
      strategy_name: 'Position Control Overlay',
      status: 'runnable',
      description: 'Risk-adjusted position control strategy.',
      factor_groups: ['risk', 'trend'],
      signal_inputs: ['factor_values', 'manual_scores'],
      default_parameters: { top_n: 20 },
      latest_evidence: 'strategy_validation',
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
  strategyId = 'manual_v1_topn_rotation',
  strategyName = 'Manual V1 TopN Rotation'
): BacktestRunResult {
  return {
    strategy_id: strategyId,
    strategy_name: strategyName,
    read_only: true,
    config: { adjust_type: 'hfq' },
    summary: {
      total_return: 0.12,
      max_drawdown: -0.05,
      turnover: 1.4
    },
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
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('loads the strategy catalog with every strategy runnable', async () => {
    render(<BacktestLabWorkspace />);

    expect((await screen.findAllByText('Manual V1 TopN Rotation')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('LHB Shortline').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mid Trend Shortline').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Tech Bottleneck Discovery+').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Position Control Overlay').length).toBeGreaterThan(0);
    expect(screen.getByText('龙虎榜超短线 validation strategy.')).toBeInTheDocument();
    expect(screen.queryByText('replay_only')).not.toBeInTheDocument();
  });

  it('runs a read-only TopN backtest with default dates and parameters', async () => {
    render(<BacktestLabWorkspace />);

    await screen.findAllByText('Manual V1 TopN Rotation');
    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    await waitFor(() =>
      expect(apiMocks.runBacktest).toHaveBeenCalledWith({
        strategy_id: 'manual_v1_topn_rotation',
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

    await screen.findAllByText('Manual V1 TopN Rotation');
    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));

    expect(await screen.findByRole('heading', { name: 'Read-only backtest' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'total_return' })).toBeInTheDocument();
    expect(screen.getAllByRole('cell', { name: 'CN:SZ:300951' }).length).toBeGreaterThan(0);
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

  it('runs comparison across every runnable strategy with identical parameters', async () => {
    apiMocks.runBacktest.mockImplementation((request: { strategy_id: string }) => {
      const strategy = makeStrategies().find((row) => row.strategy_id === request.strategy_id);
      return Promise.resolve(makeRunResult(request.strategy_id, strategy?.strategy_name ?? request.strategy_id));
    });

    render(<BacktestLabWorkspace />);

    await screen.findAllByText('Manual V1 TopN Rotation');
    fireEvent.click(screen.getByRole('button', { name: 'Run Comparison' }));

    await waitFor(() => expect(apiMocks.runBacktest).toHaveBeenCalledTimes(5));

    const expectedStrategyIds = [
      'manual_v1_topn_rotation',
      'lhb_shortline',
      'mid_trend',
      'tech_bottleneck',
      'position_control'
    ];
    expectedStrategyIds.forEach((strategyId, index) => {
      expect(apiMocks.runBacktest).toHaveBeenNthCalledWith(index + 1, {
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
    expect(screen.getAllByRole('cell', { name: 'LHB Shortline' }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole('cell', { name: 'Mid Trend Shortline' }).length).toBeGreaterThan(0);
  });

  it('disables Run Backtest for backend-invalid inputs', async () => {
    render(<BacktestLabWorkspace />);
    await screen.findAllByText('Manual V1 TopN Rotation');

    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '0' } });
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('max positions'), { target: { value: '-1' } });
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('max positions'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('transaction cost bps'), { target: { value: '-1' } });
    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeDisabled();
  });

  it('ignores pending run responses after inputs change', async () => {
    const pendingRun = deferredRunResult();
    apiMocks.runBacktest.mockReturnValueOnce(pendingRun.promise);

    render(<BacktestLabWorkspace />);
    await screen.findAllByText('Manual V1 TopN Rotation');

    fireEvent.click(screen.getByRole('button', { name: 'Run Backtest' }));
    fireEvent.change(screen.getByLabelText('top n'), { target: { value: '10' } });

    await act(async () => {
      pendingRun.resolve(makeRunResult());
    });

    expect(screen.queryByRole('heading', { name: 'Read-only backtest' })).not.toBeInTheDocument();
  });

  it('opens Backtest Lab from AppShell side navigation', async () => {
    render(<AppShell />);

    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));
    fireEvent.click(navigation.getByRole('button', { name: 'Open Backtest Lab workspace' }));

    expect(await screen.findByRole('heading', { name: 'Backtest Lab' })).toBeInTheDocument();
    expect((await screen.findAllByText('Manual V1 TopN Rotation')).length).toBeGreaterThan(0);
  });
});
