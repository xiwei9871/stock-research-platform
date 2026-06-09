import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StrategyValidationWorkspace } from '../src/components/StrategyValidationWorkspace';
import type { StrategyReplayPayload, StrategyValidationRun } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchStrategyValidationRuns: vi.fn(),
  fetchStrategyValidationReplay: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars, markers }: { bars: unknown[]; markers?: unknown[] }) => (
    <div data-testid="strategy-asset-chart">
      {bars.length} bars / {markers?.length ?? 0} markers
    </div>
  )
}));

function makeRun(overrides: Partial<StrategyValidationRun> = {}): StrategyValidationRun {
  return {
    run_id: 'lhb_shortline:fixture:phase16',
    strategy_id: 'lhb_shortline',
    strategy_name: 'LHB Shortline',
    strategy_version: 'phase16',
    run_type: 'replay',
    start_date: '2026-06-01',
    end_date: '2026-06-08',
    created_at: '2026-06-08T20:30:00+08:00',
    benchmark: '000300.SH',
    universe: 'a_share',
    data_window: { bar: 'daily' },
    cost_config: { commission: 0.0003 },
    slippage_config: { bps: 5 },
    risk_config: { max_position_weight: 0.2 },
    position_config: { initial_cash: 1000000 },
    source_artifact_paths: ['outputs/research/lhb.md'],
    summary_metrics: { sample_count: 1, win_rate: 1 },
    warnings: ['fixture-backed run'],
    ...overrides
  };
}

function makeReplay(): StrategyReplayPayload {
  return {
    run: makeRun(),
    asset_id: '000001.SZ',
    bars: [
      { time: '2026-06-03', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }
    ],
    signals: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        asset_id: '000001.SZ',
        stock_code: '000001',
        stock_name: '平安银行',
        signal_time: '2026-06-03',
        trade_date: '2026-06-03',
        signal_type: 'support',
        signal_strength: 0.86,
        signal_bucket: 'support',
        risk_bucket: 'normal',
        rule_id: 'lhb_phase16_follow',
        reason: 'LHB support behavior with next-day confirmation',
        tags: ['lhb'],
        source_artifact_path: 'outputs/research/lhb.csv'
      }
    ],
    trades: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        asset_id: '000001.SZ',
        entry_time: '2026-06-04',
        entry_price: 10.5,
        entry_reason: 'phase16_follow_candidate',
        exit_time: '2026-06-06',
        exit_price: 11,
        exit_reason: 'phase16_exit_confirmed',
        holding_days: 2,
        return_pct: 0.0476,
        max_high_return_pct: 0.08,
        max_drawdown_pct: -0.02,
        outcome_status: 'complete',
        source_artifact_path: 'outputs/research/lhb_trades.csv'
      }
    ],
    positions: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        trade_date: '2026-06-04',
        asset_id: '000001.SZ',
        position_weight: 0.08,
        target_weight: 0.08,
        cash_weight: 0.92,
        exposure: 0.08,
        position_cap: 0.1,
        risk_budget: 0.2,
        suppression_reason: '',
        source_artifact_path: 'outputs/research/lhb_positions.csv'
      }
    ],
    metrics: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        strategy_id: 'lhb_shortline',
        metric_level: 'signal_bucket',
        group_key: 'support',
        sample_count: 1,
        complete_count: 1,
        win_rate: 1,
        forward_return_mean: 0.0476,
        forward_return_median: 0.0476,
        max_high_return_mean: 0.08,
        max_drawdown_mean: -0.02,
        max_drawdown_worst: -0.02,
        turnover: 0.1,
        exposure_mean: 0.08,
        source_artifact_path: 'outputs/research/lhb_metrics.csv'
      }
    ],
    artifacts: [
      {
        run_id: 'lhb_shortline:fixture:phase16',
        artifact_type: 'markdown',
        title: 'LHB Fixture Report',
        path: 'outputs/research/lhb.md',
        format: 'md',
        trade_date: '2026-06-08',
        description: 'Fixture report'
      }
    ]
  };
}

describe('StrategyValidationWorkspace', () => {
  beforeEach(() => {
    apiMocks.fetchStrategyValidationRuns.mockResolvedValue([makeRun()]);
    apiMocks.fetchStrategyValidationReplay.mockResolvedValue(makeReplay());
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('loads runs and renders replay view', async () => {
    render(<StrategyValidationWorkspace />);

    expect(screen.getByText('Loading strategy validation...')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('LHB Shortline')).toBeInTheDocument());

    expect(screen.getByTestId('strategy-asset-chart')).toHaveTextContent('1 bars / 3 markers');
    expect(screen.getByText('support')).toBeInTheDocument();
    expect(screen.getByText('LHB support behavior with next-day confirmation')).toBeInTheDocument();
  });

  it('shows empty state when there are no runs', async () => {
    apiMocks.fetchStrategyValidationRuns.mockResolvedValue([]);

    render(<StrategyValidationWorkspace />);

    await waitFor(() => expect(screen.getByText('No strategy validation runs found.')).toBeInTheDocument());
  });

  it('switches to cohort, portfolio risk, and evidence tabs', async () => {
    render(<StrategyValidationWorkspace />);

    await waitFor(() => expect(screen.getByText('LHB Shortline')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Cohort' }));
    expect(screen.getByText('support')).toBeInTheDocument();
    expect(screen.getByText('1.00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Portfolio Risk' }));
    expect(screen.getByText('Exposure 0.08')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Evidence' }));
    expect(screen.getByText('fixture-backed run')).toBeInTheDocument();
    expect(screen.getByText('LHB Fixture Report')).toBeInTheDocument();
  });
});
