import { expect, test, type Page } from '@playwright/test';

const topNScore = {
  trade_date: '2026-06-08',
  asset_id: 'CN:SZ:300951',
  rank: 1,
  score_total: 89.9,
  score_version: 'manual_v1',
  score_components: { ret_20: 0.82 }
};

const manualV1Strategy = {
  strategy_id: 'manual_v1_topn_rotation',
  strategy_name: 'Manual V1 TopN Rotation',
  status: 'runnable',
  description: 'Manual score TopN weekly rotation.',
  factor_groups: ['momentum', 'quality'],
  signal_inputs: ['factor.stock_score_daily'],
  default_parameters: { top_n: 20 },
  latest_evidence: 'vectorized_topn_backtest',
  primary_action: 'Run backtest'
};

const lhbStrategy = {
  strategy_id: 'lhb_shortline',
  strategy_name: 'LHB Shortline',
  status: 'replay_only',
  description: 'Replay-only shortline validation strategy.',
  factor_groups: [],
  signal_inputs: ['lhb_events', 'operator_review'],
  default_parameters: {},
  latest_evidence: 'strategy_validation',
  primary_action: 'Inspect evidence'
};

const validationRun = {
  run_id: 'lhb_shortline:fixture:platform-full-flow',
  strategy_id: 'lhb_shortline',
  strategy_name: 'LHB Shortline',
  strategy_version: 'phase16',
  run_type: 'replay',
  start_date: '2026-06-01',
  end_date: '2026-06-08',
  created_at: '2026-06-08T20:30:00+08:00',
  benchmark: '000300.SH',
  universe: 'a_share',
  data_window: { bar: 'daily', lhb_window_days: 5 },
  cost_config: { commission: 0.0003 },
  slippage_config: { type: 'fixed_bps', bps: 5 },
  risk_config: { max_position_weight: 0.2 },
  position_config: { initial_cash: 1000000 },
  source_artifact_paths: ['outputs/research/lhb_phase16_replay.json'],
  summary_metrics: { sample_count: 8, win_rate: 0.62 },
  warnings: ['fixture-backed LHB replay']
};

async function mockPlatformApi(page: Page) {
  const unhandledRoutes: string[] = [];
  await page.route('/api/**', async (route) => {
    const url = new URL(route.request().url());

    if (url.pathname === '/api/platform/summary') {
      await route.fulfill({
        json: {
          latest_market_date: '2026-06-08',
          latest_score_date: '2026-06-08',
          latest_factor_date: '2026-06-08',
          market_asset_count: 5207,
          score_asset_count: 5207,
          factor_count: 43,
          score_versions: ['manual_v1'],
          topn_preview: [topNScore]
        }
      });
      return;
    }

    if (url.pathname === '/api/strategies/catalog') {
      await route.fulfill({ json: { items: [manualV1Strategy, lhbStrategy] } });
      return;
    }

    if (url.pathname === '/api/assets/000001.SZ/profile') {
      await route.fulfill({ json: makeAssetProfile() });
      return;
    }

    if (url.pathname === '/api/factors/library') {
      await route.fulfill({
        json: {
          items: [
            {
              factor_name: 'ret_20',
              factor_group: 'momentum',
              direction: 'higher',
              description: '20 day return',
              source: 'daily_bars',
              calc_version: 'v1',
              status: 'active',
              availability_start_date: '2020-01-01',
              availability_reason: null,
              latest_available_date: '2026-06-08',
              coverage_count: 5120,
              used_in_manual_v1: true,
              manual_v1_weight: 1
            },
            {
              factor_name: 'volatility_20',
              factor_group: 'risk',
              direction: 'lower',
              description: '20 day realized volatility',
              source: 'daily_bars',
              calc_version: 'v1',
              status: 'active',
              availability_start_date: '2020-01-01',
              availability_reason: null,
              latest_available_date: '2026-06-08',
              coverage_count: 5110,
              used_in_manual_v1: false,
              manual_v1_weight: null
            }
          ]
        }
      });
      return;
    }

    if (url.pathname === '/api/factors/score-preview') {
      await route.fulfill({
        json: {
          trade_date: '2026-06-08',
          selected_factors: [{ factor_name: 'ret_20', direction: 'higher', weight: 1 }],
          items: [
            {
              trade_date: '2026-06-08',
              asset_id: 'CN:SZ:300951',
              rank: 1,
              score_total: 98.25,
              score_components: { ret_20: 0.82 }
            }
          ]
        }
      });
      return;
    }

    if (url.pathname === '/api/backtests/strategies') {
      await route.fulfill({ json: { items: [manualV1Strategy, lhbStrategy] } });
      return;
    }

    if (url.pathname === '/api/backtests/run') {
      await route.fulfill({ json: makeBacktestResult() });
      return;
    }

    if (url.pathname === '/api/dashboard/overview') {
      await route.fulfill({
        json: {
          trade_date: '2026-06-08',
          score_version: 'manual_v1',
          watchlist_id: 'default',
          top_scores: [topNScore],
          watchlist_signals: [],
          reports: [
            {
              report_type: 'daily',
              title: 'Daily TopN',
              path: '/reports/daily-topn.html',
              format: 'html',
              trade_date: '2026-06-08'
            }
          ]
        }
      });
      return;
    }

    if (url.pathname === '/api/strategy-validation/runs') {
      await route.fulfill({ json: { items: [validationRun] } });
      return;
    }

    const replayMatch = url.pathname.match(/\/api\/strategy-validation\/runs\/(.+)\/assets\/(.+)\/replay$/);
    if (replayMatch) {
      await route.fulfill({ json: makeReplayPayload(decodeURIComponent(replayMatch[2])) });
      return;
    }

    unhandledRoutes.push(url.pathname);
    await route.abort('failed');
  });
  return unhandledRoutes;
}

function makeAssetProfile() {
  return {
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
    bars: [
      { time: '2026-06-06', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 },
      { time: '2026-06-08', open: 10.5, high: 11.2, low: 10.2, close: 11, volume: 120, amount: 1320 }
    ],
    score: {
      trade_date: '2026-06-08',
      asset_id: '000001.SZ',
      rank: 12,
      score_total: 88.5,
      score_version: 'manual_v1',
      score_components: { ret_20: 0.42 }
    },
    signals: [],
    decisions: [],
    outcomes: [],
    factor_values: [
      {
        trade_date: '2026-06-08',
        asset_id: '000001.SZ',
        factor_group: 'momentum',
        factor_name: 'ret_20',
        factor_value: 0.1234,
        calc_version: 'v1',
        source: 'unit',
        source_data_version: '20260608'
      }
    ],
    coverage: {
      daily_bars: {
        min_date: '1991-04-03',
        max_date: '2026-06-08',
        row_count: 8240
      },
      factors: {
        latest_factor_date: '2026-06-08',
        factor_count: 43
      }
    }
  };
}

function makeBacktestResult() {
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

function makeReplayPayload(assetId: string) {
  return {
    run: validationRun,
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
        run_id: validationRun.run_id,
        strategy_id: validationRun.strategy_id,
        asset_id: assetId,
        stock_code: '000001',
        stock_name: '平安银行',
        signal_time: '2026-06-03',
        trade_date: '2026-06-03',
        signal_type: 'support',
        signal_strength: 0.86,
        signal_bucket: 'support',
        risk_bucket: 'normal',
        rule_id: 'lhb_phase16_follow',
        reason: 'support confirmed',
        tags: ['lhb', 'support'],
        source_artifact_path: 'outputs/research/lhb_phase16_replay.json'
      }
    ],
    trades: [
      {
        run_id: validationRun.run_id,
        strategy_id: validationRun.strategy_id,
        asset_id: assetId,
        entry_time: '2026-06-03',
        entry_price: 10.9,
        entry_reason: 'phase16_follow_candidate',
        exit_time: '2026-06-05',
        exit_price: 11.5,
        exit_reason: 'phase16_exit_confirmed',
        holding_days: 2,
        return_pct: 0.0476,
        max_high_return_pct: 0.0676,
        max_drawdown_pct: -0.02,
        outcome_status: 'complete',
        source_artifact_path: 'outputs/research/lhb_phase16_replay.json'
      }
    ],
    positions: [
      {
        run_id: validationRun.run_id,
        strategy_id: validationRun.strategy_id,
        trade_date: '2026-06-05',
        asset_id: assetId,
        position_weight: 0.08,
        target_weight: 0.1,
        cash_weight: 0.9,
        exposure: 0.1,
        position_cap: 0.2,
        risk_budget: 0.6,
        suppression_reason: '',
        source_artifact_path: 'outputs/research/lhb_phase16_replay.json'
      }
    ],
    metrics: [
      {
        run_id: validationRun.run_id,
        strategy_id: validationRun.strategy_id,
        metric_level: 'signal_bucket',
        group_key: 'support',
        sample_count: 8,
        complete_count: 8,
        win_rate: 0.62,
        forward_return_mean: 0.0476,
        forward_return_median: 0.0476,
        max_high_return_mean: 0.0776,
        max_drawdown_mean: -0.02,
        max_drawdown_worst: -0.04,
        turnover: 0.1,
        exposure_mean: 0.08,
        source_artifact_path: 'outputs/research/lhb_phase16_replay.json'
      }
    ],
    artifacts: [
      {
        run_id: validationRun.run_id,
        artifact_type: 'md',
        title: 'LHB Phase16 Replay Report',
        path: 'outputs/research/lhb_phase16_replay.md',
        format: 'md',
        trade_date: '2026-06-08',
        description: 'LHB validation artifact'
      }
    ]
  };
}

async function assertNoUnsafeExecutionControls(page: Page) {
  await expect(page.getByRole('button', { name: /place order/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /auto trade/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /production write/i })).toHaveCount(0);
  await expect(page.getByRole('link', { name: /place order|auto trade|production write/i })).toHaveCount(0);
}

async function assertNoHorizontalOverflow(page: Page) {
  const hasOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(hasOverflow).toBe(false);
}

test('platform full flow covers all research workspaces with mocked API responses', async ({ page }) => {
  const unhandledRoutes = await mockPlatformApi(page);

  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
  await expect(page.getByText('Manual V1 TopN Rotation')).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Data Explorer workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Data Explorer' })).toBeVisible();
  await expect(page.getByText('平安银行')).toBeVisible();
  await expect(page.getByText('CN:SZ:000001')).toBeVisible();
  await expect(page.getByText('Score 88.5')).toBeVisible();
  await expect(page.getByRole('cell', { name: 'ret_20' })).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Factor Lab workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Factor Lab' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'ret_20', exact: true })).toBeVisible();
  await page.getByLabel('select ret_20').check();
  await page.getByRole('button', { name: 'Preview Scores' }).click();
  await expect(page.getByRole('cell', { name: 'CN:SZ:300951' })).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Backtest Lab workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Backtest Lab' })).toBeVisible();
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'LHB Shortline' })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'strategy' })).toContainText('Manual V1 TopN Rotation');
  await page.getByRole('button', { name: 'Run Backtest' }).click();
  await expect(page.getByRole('heading', { name: 'Read-only backtest' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'total_return' })).toBeVisible();
  const positionsSection = page.locator('.backtest-result-section').filter({ has: page.getByRole('heading', { name: 'Positions' }) });
  await expect(positionsSection.getByRole('cell', { name: 'CN:SZ:300951' })).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Strategy Validation workspace' }).click();
  await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toContainText('LHB Shortline');
  await expect(page.getByText('support confirmed')).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Reports workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Reports', level: 1 })).toBeVisible();
  await expect(page.getByText('Daily TopN')).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);
  expect(unhandledRoutes).toEqual([]);
});
