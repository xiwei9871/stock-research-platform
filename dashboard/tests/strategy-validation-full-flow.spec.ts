import { expect, test, type Page } from '@playwright/test';

type StrategyRun = {
  run_id: string;
  strategy_id: string;
  strategy_name: string;
  strategy_version: string;
  run_type: string;
  start_date: string;
  end_date: string;
  created_at: string;
  benchmark: string;
  universe: string;
  data_window: Record<string, unknown>;
  cost_config: Record<string, unknown>;
  slippage_config: Record<string, unknown>;
  risk_config: Record<string, unknown>;
  position_config: Record<string, unknown>;
  source_artifact_paths: string[];
  summary_metrics: Record<string, unknown>;
  warnings: string[];
};

type StrategyScenario = {
  run: StrategyRun;
  signal: {
    signal_type: string;
    signal_bucket: string;
    risk_bucket: string;
    rule_id: string;
    reason: string;
    signal_strength: number;
    tags: string[];
  };
  trade: {
    entry_reason: string;
    exit_reason: string;
    return_pct: number;
    max_drawdown_pct: number;
  };
  position: {
    position_weight: number;
    target_weight: number;
    cash_weight: number;
    exposure: number;
    position_cap: number;
    risk_budget: number;
    suppression_reason: string;
  };
  metric: {
    group_key: string;
    sample_count: number;
    complete_count: number;
    win_rate: number;
    forward_return_mean: number;
    max_drawdown_worst: number;
    turnover: number;
    exposure_mean: number;
  };
  artifact: {
    title: string;
    path: string;
    format: string;
  };
};

const scenarios: StrategyScenario[] = [
  {
    run: makeRun({
      run_id: 'lhb_shortline:fixture:phase16',
      strategy_id: 'lhb_shortline',
      strategy_name: 'LHB Shortline',
      strategy_version: 'phase16',
      data_window: { bar: 'daily', lhb_window_days: 5 },
      warnings: ['fixture-backed LHB replay']
    }),
    signal: {
      signal_type: 'support',
      signal_bucket: 'support',
      risk_bucket: 'normal',
      rule_id: 'lhb_phase16_follow',
      reason: 'support confirmed',
      signal_strength: 0.86,
      tags: ['lhb', 'support']
    },
    trade: {
      entry_reason: 'phase16_follow_candidate',
      exit_reason: 'phase16_exit_confirmed',
      return_pct: 0.0476,
      max_drawdown_pct: -0.02
    },
    position: {
      position_weight: 0.08,
      target_weight: 0.1,
      cash_weight: 0.9,
      exposure: 0.1,
      position_cap: 0.2,
      risk_budget: 0.6,
      suppression_reason: ''
    },
    metric: {
      group_key: 'support',
      sample_count: 8,
      complete_count: 8,
      win_rate: 0.62,
      forward_return_mean: 0.0476,
      max_drawdown_worst: -0.04,
      turnover: 0.1,
      exposure_mean: 0.08
    },
    artifact: {
      title: 'LHB Phase16 Replay Report',
      path: 'outputs/research/lhb_phase16_replay.md',
      format: 'md'
    }
  },
  {
    run: makeRun({
      run_id: 'mid_trend:fixture:stability',
      strategy_id: 'mid_trend',
      strategy_name: 'Mid Trend',
      strategy_version: 'stability',
      data_window: { bar: 'daily', trend_window_days: 20 },
      warnings: ['trend protection replay uses fixture metrics']
    }),
    signal: {
      signal_type: 'trend_protection',
      signal_bucket: 'trend_protection',
      risk_bucket: 'normal',
      rule_id: 'mid_trend_trend_protection_v1',
      reason: 'trend protection holds above stop band',
      signal_strength: 0.78,
      tags: ['trend', 'protection']
    },
    trade: {
      entry_reason: 'trend_pullback_entry',
      exit_reason: 'trend_decay_exit',
      return_pct: 0.031,
      max_drawdown_pct: -0.035
    },
    position: {
      position_weight: 0.12,
      target_weight: 0.14,
      cash_weight: 0.72,
      exposure: 0.28,
      position_cap: 0.15,
      risk_budget: 0.5,
      suppression_reason: 'trend_budget'
    },
    metric: {
      group_key: 'trend_protection',
      sample_count: 18,
      complete_count: 16,
      win_rate: 0.56,
      forward_return_mean: 0.031,
      max_drawdown_worst: -0.08,
      turnover: 0.18,
      exposure_mean: 0.22
    },
    artifact: {
      title: 'Mid Trend Stability CSV',
      path: 'outputs/research/mid_trend_stability.csv',
      format: 'csv'
    }
  },
  {
    run: makeRun({
      run_id: 'tech_bottleneck:fixture:c2',
      strategy_id: 'tech_bottleneck',
      strategy_name: 'Tech Bottleneck',
      strategy_version: 'c2',
      data_window: { bar: 'daily', rank_window_days: 30 },
      warnings: ['bottleneck ranking is research-only']
    }),
    signal: {
      signal_type: 'bottleneck_hit',
      signal_bucket: 'bottleneck_rank_top10',
      risk_bucket: 'elevated',
      rule_id: 'tech_bottleneck_rank_c2',
      reason: 'bottleneck rank entered top decile',
      signal_strength: 0.91,
      tags: ['bottleneck', 'rank']
    },
    trade: {
      entry_reason: 'bottleneck_rank_top10',
      exit_reason: 'rank_decay',
      return_pct: 0.082,
      max_drawdown_pct: -0.045
    },
    position: {
      position_weight: 0.1,
      target_weight: 0.1,
      cash_weight: 0.6,
      exposure: 0.4,
      position_cap: 0.1,
      risk_budget: 0.45,
      suppression_reason: 'bottleneck_concentration_cap'
    },
    metric: {
      group_key: 'bottleneck_rank_top10',
      sample_count: 24,
      complete_count: 20,
      win_rate: 0.58,
      forward_return_mean: 0.082,
      max_drawdown_worst: -0.12,
      turnover: 0.34,
      exposure_mean: 0.36
    },
    artifact: {
      title: 'Tech Bottleneck Rank JSON',
      path: 'outputs/research/tech_bottleneck_rank.json',
      format: 'json'
    }
  },
  {
    run: makeRun({
      run_id: 'position_control:fixture:budget',
      strategy_id: 'position_control',
      strategy_name: 'Position Control',
      strategy_version: 'budget',
      data_window: { bar: 'daily', exposure_window_days: 10 },
      warnings: ['position-control run has no production writes']
    }),
    signal: {
      signal_type: 'exposure_cap',
      signal_bucket: 'regime_budget',
      risk_bucket: 'reduced',
      rule_id: 'position_control_regime_budget',
      reason: 'drawdown pressure reduced target exposure',
      signal_strength: 0.67,
      tags: ['position', 'budget']
    },
    trade: {
      entry_reason: 'budget_allocation_allowed',
      exit_reason: 'drawdown_pressure_trim',
      return_pct: 0.012,
      max_drawdown_pct: -0.018
    },
    position: {
      position_weight: 0.06,
      target_weight: 0.08,
      cash_weight: 0.82,
      exposure: 0.18,
      position_cap: 0.08,
      risk_budget: 0.35,
      suppression_reason: 'drawdown_pressure'
    },
    metric: {
      group_key: 'regime_budget',
      sample_count: 12,
      complete_count: 12,
      win_rate: 0.5,
      forward_return_mean: 0.012,
      max_drawdown_worst: -0.05,
      turnover: 0.08,
      exposure_mean: 0.18
    },
    artifact: {
      title: 'Position Budget Audit',
      path: 'outputs/research/position_budget_audit.md',
      format: 'md'
    }
  }
];

function makeRun(overrides: Partial<StrategyRun>): StrategyRun {
  return {
    run_id: '',
    strategy_id: '',
    strategy_name: '',
    strategy_version: '',
    run_type: 'replay',
    start_date: '2026-06-01',
    end_date: '2026-06-08',
    created_at: '2026-06-08T20:30:00+08:00',
    benchmark: '000300.SH',
    universe: 'a_share',
    data_window: { bar: 'daily' },
    cost_config: { commission: 0.0003 },
    slippage_config: { type: 'fixed_bps', bps: 5 },
    risk_config: { max_position_weight: 0.2 },
    position_config: { initial_cash: 1000000 },
    source_artifact_paths: ['outputs/research/strategy_validation_fixture.json'],
    summary_metrics: { sample_count: 1, win_rate: 1 },
    warnings: [],
    ...overrides
  };
}

async function mockFullFlowApi(page: Page) {
  await page.route('/api/**', async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === '/api/strategy-validation/runs') {
      await route.fulfill({ json: { items: scenarios.map((scenario) => scenario.run) } });
      return;
    }

    const replayMatch = url.pathname.match(/\/api\/strategy-validation\/runs\/(.+)\/assets\/(.+)\/replay$/);
    if (replayMatch) {
      const runId = decodeURIComponent(replayMatch[1]);
      const assetId = decodeURIComponent(replayMatch[2]);
      const scenario = scenarios.find((item) => item.run.run_id === runId) ?? scenarios[0];
      await route.fulfill({ json: makeReplayPayload(scenario, assetId) });
      return;
    }

    if (url.pathname === '/api/dashboard/overview') {
      await route.fulfill({
        json: {
          trade_date: '2026-05-29',
          score_version: 'manual_v1',
          watchlist_id: 'default',
          top_scores: [
            {
              trade_date: '2026-05-29',
              asset_id: '000001.SZ',
              rank: 1,
              score_total: 91.2,
              score_version: 'manual_v1',
              score_components: {}
            }
          ],
          watchlist_signals: [],
          reports: []
        }
      });
      return;
    }

    if (url.pathname.endsWith('/bars')) {
      await route.fulfill({
        json: {
          asset_id: '000001.SZ',
          resolution: '1D',
          items: [{ time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }]
        }
      });
      return;
    }

    if (url.pathname.endsWith('/scores')) {
      await route.fulfill({
        json: {
          item: {
            trade_date: '2026-05-29',
            asset_id: '000001.SZ',
            rank: 1,
            score_total: 91.2,
            score_version: 'manual_v1',
            score_components: {}
          }
        }
      });
      return;
    }

    await route.fulfill({ json: { items: [] } });
  });
}

function makeReplayPayload(scenario: StrategyScenario, assetId: string) {
  return {
    run: scenario.run,
    asset_id: assetId,
    bars: [
      { time: '2026-06-01', open: 10, high: 10.8, low: 9.8, close: 10.5, volume: 100000, amount: 1000000 },
      { time: '2026-06-02', open: 10.5, high: 11.1, low: 10.3, close: 10.9, volume: 120000, amount: 1250000 },
      { time: '2026-06-03', open: 10.9, high: 11.5, low: 10.7, close: 11.2, volume: 140000, amount: 1500000 },
      { time: '2026-06-04', open: 11.2, high: 11.4, low: 10.8, close: 11.0, volume: 110000, amount: 1210000 },
      { time: '2026-06-05', open: 11.0, high: 11.7, low: 10.9, close: 11.5, volume: 160000, amount: 1800000 }
    ],
    signals: [
      {
        run_id: scenario.run.run_id,
        strategy_id: scenario.run.strategy_id,
        asset_id: assetId,
        stock_code: '000001',
        stock_name: 'Ping An Bank',
        signal_time: '2026-06-03',
        trade_date: '2026-06-03',
        signal_type: scenario.signal.signal_type,
        signal_strength: scenario.signal.signal_strength,
        signal_bucket: scenario.signal.signal_bucket,
        risk_bucket: scenario.signal.risk_bucket,
        rule_id: scenario.signal.rule_id,
        reason: scenario.signal.reason,
        tags: scenario.signal.tags,
        source_artifact_path: scenario.artifact.path
      }
    ],
    trades: [
      {
        run_id: scenario.run.run_id,
        strategy_id: scenario.run.strategy_id,
        asset_id: assetId,
        entry_time: '2026-06-03',
        entry_price: 10.9,
        entry_reason: scenario.trade.entry_reason,
        exit_time: '2026-06-05',
        exit_price: 11.5,
        exit_reason: scenario.trade.exit_reason,
        holding_days: 2,
        return_pct: scenario.trade.return_pct,
        max_high_return_pct: scenario.trade.return_pct + 0.02,
        max_drawdown_pct: scenario.trade.max_drawdown_pct,
        outcome_status: 'complete',
        source_artifact_path: scenario.artifact.path
      }
    ],
    positions: [
      {
        run_id: scenario.run.run_id,
        strategy_id: scenario.run.strategy_id,
        trade_date: '2026-06-05',
        asset_id: assetId,
        position_weight: scenario.position.position_weight,
        target_weight: scenario.position.target_weight,
        cash_weight: scenario.position.cash_weight,
        exposure: scenario.position.exposure,
        position_cap: scenario.position.position_cap,
        risk_budget: scenario.position.risk_budget,
        suppression_reason: scenario.position.suppression_reason,
        source_artifact_path: scenario.artifact.path
      }
    ],
    metrics: [
      {
        run_id: scenario.run.run_id,
        strategy_id: scenario.run.strategy_id,
        metric_level: 'signal_bucket',
        group_key: scenario.metric.group_key,
        sample_count: scenario.metric.sample_count,
        complete_count: scenario.metric.complete_count,
        win_rate: scenario.metric.win_rate,
        forward_return_mean: scenario.metric.forward_return_mean,
        forward_return_median: scenario.metric.forward_return_mean,
        max_high_return_mean: scenario.metric.forward_return_mean + 0.03,
        max_drawdown_mean: scenario.metric.max_drawdown_worst / 2,
        max_drawdown_worst: scenario.metric.max_drawdown_worst,
        turnover: scenario.metric.turnover,
        exposure_mean: scenario.metric.exposure_mean,
        source_artifact_path: scenario.artifact.path
      }
    ],
    artifacts: [
      {
        run_id: scenario.run.run_id,
        artifact_type: scenario.artifact.format,
        title: scenario.artifact.title,
        path: scenario.artifact.path,
        format: scenario.artifact.format,
        trade_date: '2026-06-08',
        description: `${scenario.run.strategy_name} validation artifact`
      }
    ]
  };
}

async function openStrategyValidation(page: Page) {
  await page.goto('/');
  await expect(page.getByText('Stock Research')).toBeVisible();
  await page.getByRole('button', { name: 'Open Strategy Lab workspace' }).click();
  await page.getByRole('tab', { name: 'Validation Replay' }).click();
  await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toHaveValue(scenarios[0].run.run_id);
}

async function assertReplayTab(page: Page, scenario: StrategyScenario) {
  await page.getByRole('button', { name: 'Replay' }).click();
  await expect(page.getByText(scenario.signal.reason)).toBeVisible();
  await expect(page.getByText(`${scenario.signal.rule_id} / ${scenario.signal.risk_bucket}`)).toBeVisible();
  await expect(page.getByText(scenario.trade.entry_reason)).toBeVisible();
  await expect(page.getByText(scenario.trade.exit_reason)).toBeVisible();
  await expect(page.getByText('Bars are unavailable for selected range.')).toHaveCount(0);
  await expect(page.locator('canvas').first()).toBeVisible();
}

async function assertCohortTab(page: Page, scenario: StrategyScenario) {
  await page.getByRole('button', { name: 'Cohort' }).click();
  const row = page.getByRole('row').filter({ has: page.getByRole('cell', { name: scenario.metric.group_key }) });
  await expect(row).toBeVisible();
  await expect(row.getByRole('cell', { name: String(scenario.metric.sample_count) }).first()).toBeVisible();
  await expect(row.getByRole('cell', { name: String(scenario.metric.complete_count) }).first()).toBeVisible();
  await expect(row.getByRole('cell', { name: scenario.metric.win_rate.toFixed(2) })).toBeVisible();
  await expect(row.getByRole('cell', { name: scenario.metric.forward_return_mean.toFixed(2) })).toBeVisible();
  await expect(row.getByRole('cell', { name: scenario.metric.max_drawdown_worst.toFixed(2) })).toBeVisible();
}

async function assertPortfolioRiskTab(page: Page, scenario: StrategyScenario) {
  await page.getByRole('button', { name: 'Portfolio Risk' }).click();
  await expect(page.getByText(`Exposure ${scenario.position.exposure.toFixed(2)}`)).toBeVisible();
  await expect(page.getByText(`Position ${scenario.position.position_weight.toFixed(2)}`)).toBeVisible();
  await expect(page.getByText(`Cash ${scenario.position.cash_weight.toFixed(2)}`)).toBeVisible();
  await expect(page.getByText(scenario.position.suppression_reason || 'No suppression')).toBeVisible();
}

async function assertEvidenceTab(page: Page, scenario: StrategyScenario) {
  await page.getByRole('button', { name: 'Evidence' }).click();
  await expect(page.getByText(scenario.run.run_id)).toBeVisible();
  await expect(page.getByText(`${scenario.run.strategy_version} / ${scenario.run.run_type}`)).toBeVisible();
  await expect(page.getByText(scenario.run.warnings[0])).toBeVisible();
  await expect(page.getByText('Data Window')).toBeVisible();
  await expect(page.getByText('Cost Config')).toBeVisible();
  await expect(page.getByText('Slippage Config')).toBeVisible();
  await expect(page.getByText('Risk Config')).toBeVisible();
  await expect(page.getByText('Position Config')).toBeVisible();
  await expect(page.getByText(scenario.artifact.title)).toBeVisible();
  await expect(page.getByText(scenario.artifact.format, { exact: true })).toBeVisible();
  await expect(page.getByText(scenario.artifact.path)).toBeVisible();
}

async function assertNoUnsafeExecutionControls(page: Page) {
  await expect(page.getByRole('button', { name: /place order/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /auto trade/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /promote/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /production write/i })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /place order|auto trade|promote|production write/i })).toHaveCount(0);
}

async function assertNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(hasOverflow).toBe(false);
}

test('strategy validation full flow covers all strategy tabs and run types', async ({ page }) => {
  await mockFullFlowApi(page);
  await openStrategyValidation(page);

  for (const scenario of scenarios) {
    await page.getByRole('combobox', { name: 'strategy validation run' }).selectOption(scenario.run.run_id);
    await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toHaveValue(scenario.run.run_id);
    await assertReplayTab(page, scenario);
    await assertCohortTab(page, scenario);
    await assertPortfolioRiskTab(page, scenario);
    await assertEvidenceTab(page, scenario);
    await assertNoUnsafeExecutionControls(page);
    await assertNoHorizontalOverflow(page);
  }
});

test('strategy validation full flow remains usable on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockFullFlowApi(page);
  await openStrategyValidation(page);

  const scenario = scenarios[2];
  await page.getByRole('combobox', { name: 'strategy validation run' }).selectOption(scenario.run.run_id);
  await assertReplayTab(page, scenario);
  await assertEvidenceTab(page, scenario);
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);
});
