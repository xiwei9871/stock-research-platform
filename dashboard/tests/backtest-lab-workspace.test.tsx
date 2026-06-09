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
      status: 'replay_only',
      description: 'Replay-only shortline validation strategy.',
      factor_groups: [],
      signal_inputs: ['lhb_events', 'operator_review'],
      default_parameters: {},
      latest_evidence: 'strategy_validation',
      primary_action: 'Inspect evidence'
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

function makeRunResult(): BacktestRunResult {
  return {
    strategy_id: 'manual_v1_topn_rotation',
    strategy_name: 'Manual V1 TopN Rotation',
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

  it('loads the strategy catalog with runnable and replay-only strategies', async () => {
    render(<BacktestLabWorkspace />);

    expect((await screen.findAllByText('Manual V1 TopN Rotation')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('LHB Shortline').length).toBeGreaterThan(0);
    expect(screen.getByText('Replay-only shortline validation strategy.')).toBeInTheDocument();
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

  it('disables Run Backtest when a replay-only strategy is selected', async () => {
    render(<BacktestLabWorkspace />);

    const strategySelect = await screen.findByLabelText('strategy');
    fireEvent.change(strategySelect, { target: { value: 'lhb_shortline' } });

    expect(screen.getByRole('button', { name: 'Run Backtest' })).toBeDisabled();
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
