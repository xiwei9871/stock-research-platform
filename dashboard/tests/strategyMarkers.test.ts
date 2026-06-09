import { describe, expect, it } from 'vitest';
import { toStrategyChartMarkers } from '../src/charts/strategyMarkers';
import type { StrategySignal, StrategyTrade } from '../src/api/types';

function signal(overrides: Partial<StrategySignal> = {}): StrategySignal {
  return {
    run_id: 'run-1',
    strategy_id: 'lhb_shortline',
    asset_id: '000001.SZ',
    stock_code: '000001',
    stock_name: '平安银行',
    signal_time: '2026-06-03',
    trade_date: '2026-06-03',
    signal_type: 'support',
    signal_strength: 0.8,
    signal_bucket: 'support',
    risk_bucket: 'normal',
    rule_id: 'rule-1',
    reason: 'support confirmed',
    tags: ['lhb'],
    source_artifact_path: 'outputs/research/lhb.csv',
    ...overrides
  };
}

function trade(overrides: Partial<StrategyTrade> = {}): StrategyTrade {
  return {
    run_id: 'run-1',
    strategy_id: 'lhb_shortline',
    asset_id: '000001.SZ',
    entry_time: '2026-06-04',
    entry_price: 10,
    entry_reason: 'follow',
    exit_time: '2026-06-06',
    exit_price: 11,
    exit_reason: 'exit_confirmed',
    holding_days: 2,
    return_pct: 0.1,
    max_high_return_pct: 0.12,
    max_drawdown_pct: -0.02,
    outcome_status: 'complete',
    source_artifact_path: 'outputs/research/trades.csv',
    ...overrides
  };
}

describe('strategy chart markers', () => {
  it('converts signals and trades into stable marker view models', () => {
    const markers = toStrategyChartMarkers([signal()], [trade()]);

    expect(markers).toEqual([
      {
        time: '2026-06-03',
        position: 'aboveBar',
        color: '#2563eb',
        shape: 'circle',
        text: 'support'
      },
      {
        time: '2026-06-04',
        position: 'belowBar',
        color: '#1f9d55',
        shape: 'arrowUp',
        text: 'entry'
      },
      {
        time: '2026-06-06',
        position: 'aboveBar',
        color: '#d64545',
        shape: 'arrowDown',
        text: 'exit'
      }
    ]);
  });

  it('skips missing trade times', () => {
    const markers = toStrategyChartMarkers([], [trade({ entry_time: null, exit_time: null })]);

    expect(markers).toEqual([]);
  });
});
