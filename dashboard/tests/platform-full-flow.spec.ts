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
  strategy_name: 'LHB Shortline Combo',
  status: 'runnable',
  description: 'Phase15 cash account plus Phase16C delayed exit.',
  factor_groups: ['lhb', 'auction', 'position_control'],
  signal_inputs: ['Phase14C lifecycle entry/exit', 'Phase15 cash account', 'Phase16C limit-break-failed delayed exit'],
  default_parameters: { top_n: 20 },
  latest_evidence: 'Phase16C account_final_equity=3.1279',
  primary_action: 'Run backtest'
};

const midTrendStrategy = {
  strategy_id: 'mid_trend',
  strategy_name: 'Mid Trend Combo',
  status: 'runnable',
  description: 'report_mild_bonus plus Top5 weekly max2 selective trend holding protection.',
  factor_groups: ['trend', 'research_overlay'],
  signal_inputs: ['mid_trend funnel', 'report_mild_bonus', 'C2 stock protection'],
  default_parameters: { top_n: 5 },
  latest_evidence: 'report_mild_bonus final_equity=4.2056',
  primary_action: 'Run backtest'
};

const techBottleneckStrategy = {
  strategy_id: 'tech_bottleneck',
  strategy_name: 'Tech Bottleneck Combo',
  status: 'runnable',
  description: 'tech_hard_filter plus top5_adaptive_daily_check_max2_v1.',
  factor_groups: ['tech_bottleneck', 'trend'],
  signal_inputs: ['tech_hard_filter', 'top5_adaptive_daily_check_max2_v1'],
  default_parameters: { top_n: 5 },
  latest_evidence: 'tech_hard_filter final_equity=3.4973',
  primary_action: 'Run backtest'
};

const positionControlStrategy = {
  strategy_id: 'position_control',
  strategy_name: 'Position Control Overlay',
  status: 'runnable',
  description: 'Risk-adjusted position control strategy.',
  factor_groups: ['risk', 'trend'],
  signal_inputs: ['factor_values', 'manual_scores'],
  default_parameters: { top_n: 20 },
  latest_evidence: 'strategy_validation',
  primary_action: 'Run backtest'
};

const backtestStrategies = [
  lhbStrategy,
  midTrendStrategy,
  techBottleneckStrategy
];

const strategyCatalog = [
  manualV1Strategy,
  ...backtestStrategies,
  positionControlStrategy
];

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

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

function makeReviewQueueFixture() {
  return {
    trade_date: '2026-06-08',
    score_version: 'strategy_topn',
    review_mode: 'strategy_topn',
    generated_at: '2026-06-08T00:00:00+00:00',
    groups: [
      {
        bucket: 'strategy:mid_trend',
        label: 'Mid Trend Combo',
        count: 1,
        items: [{
          queue_id: '2026-06-08:strategy_topn:CN:SZ:300951',
          asset_id: 'CN:SZ:300951',
          canonical_asset_id: 'CN:SZ:300951',
          trade_date: '2026-06-08',
          score_version: 'strategy_topn',
          display_name: 'Fixture Stock',
          rank: 1,
          score: 89.9,
          source_type: 'strategy_topn',
          source_name: 'Mid Trend Combo',
          source_rank: 1,
          strategy_id: 'mid_trend',
          strategy_name: 'Mid Trend Combo',
          strategy_run_id: 'mid_trend:run',
          review_tier: 'top5_focus',
          digest_title: 'Strong evidence',
          bucket: 'strong',
          source_kinds: ['strategy', 'news'],
          risk_count: 0,
          warning_count: 0,
          next_action_count: 1,
          digest: {
            asset_id: 'CN:SZ:300951',
            canonical_asset_id: 'CN:SZ:300951',
            trade_date: '2026-06-08',
            title: 'Strong evidence',
            score: 81,
            bucket: 'strong',
            facts: [{ kind: 'news', label: 'Fixture news evidence' }],
            risk_flags: [],
            source_refs: {},
            next_actions: [{ key: 'review_stock', label: 'Review Stock', workspace: 'stock', asset_id: 'CN:SZ:300951', query: 'Fixture Stock' }],
            warnings: []
          }
        }]
      },
      { bucket: 'strategy:tech_bottleneck', label: 'Tech Bottleneck Combo', count: 0, items: [] }
    ],
    warnings: []
  };
}

async function mockPlatformApi(page: Page) {
  const unhandledRoutes: string[] = [];
  const backtestRunStrategyIds: string[] = [];
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

    if (url.pathname === '/api/platform/readiness') {
      await route.fulfill({
        json: {
          mode: 'eod_local',
          status: 'partial',
          as_of: '2026-06-08T20:00:00+08:00',
          latest_market_date: '2026-06-08',
          checks: [
            {
              key: 'market_data',
              label: 'Market data',
              status: 'ready',
              detail: 'Latest EOD data loaded'
            },
            {
              key: 'strategy_validation',
              label: 'Strategy validation',
              status: 'partial',
              detail: 'Replay artifacts current for Task 4'
            }
          ],
          warnings: ['News collector lagging']
        }
      });
      return;
    }

    if (url.pathname === '/api/strategies/catalog') {
      await route.fulfill({ json: { items: strategyCatalog } });
      return;
    }

    if (url.pathname === '/api/market-monitor/eod') {
      await route.fulfill({
        json: {
          trade_date: '2026-06-08',
          freshness: {
            mode: 'eod',
            label: 'Last completed trading day',
            is_realtime: false,
            latest_market_date: '2026-06-08',
            latest_factor_date: '2026-06-08',
            latest_score_date: '2026-06-08'
          },
          coverage: {
            market_assets: 5207,
            score_assets: 5207,
            factor_count: 43
          },
          market_breadth: {
            advancers: 2800,
            decliners: 2200,
            limit_up: 36,
            limit_down: 9,
            advancing_ratio: 0.56,
            turnover_change_pct: 0.02,
            status: 'ok'
          },
          index_snapshot: [],
          sector_strength: { strongest: [], weakest: [], status: 'ok' },
          unusual_moves: [],
          watchlist_alerts: [],
          strategy_signal_summary: {
            topn_preview_count: 1,
            topn_preview: [topNScore],
            risk_filter_counts: {}
          },
          generated_reports: [],
          warnings: []
        }
      });
      return;
    }

    if (url.pathname === '/api/public-news') {
      await route.fulfill({
        json: {
          items: [
            {
              news_id: 'news-1',
              source: 'sina_finance',
              source_channel: 'market',
              category: 'market',
              title: '600000 浦发银行公告',
              summary: 'fixture news',
              url: 'https://example.com/news/1',
              published_at: '2026-06-08T09:30:00',
              collected_at: '2026-06-08T09:31:00',
              raw_id: 'news-1',
              raw_payload: {},
              status: 'active'
            }
          ],
          warnings: []
        }
      });
      return;
    }

    if (url.pathname === '/api/evidence-digest') {
      const assetId = url.searchParams.get('asset_id') ?? 'CN:SZ:300951';
      await route.fulfill({
        json: {
          asset_id: assetId,
          canonical_asset_id: assetId,
          trade_date: url.searchParams.get('trade_date') ?? '2026-06-08',
          title: 'Strong evidence',
          score: 81,
          bucket: 'strong',
          facts: [],
          risk_flags: [],
          source_refs: {},
          next_actions: [],
          warnings: []
        }
      });
      return;
    }

    if (url.pathname === '/api/review-queue') {
      await route.fulfill({ json: makeReviewQueueFixture() });
      return;
    }

    const assetProfileMatch = url.pathname.match(/^\/api\/assets\/(.+)\/profile$/);
    if (assetProfileMatch) {
      await route.fulfill({ json: makeAssetProfile(decodeURIComponent(assetProfileMatch[1])) });
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
      await route.fulfill({ json: { items: backtestStrategies } });
      return;
    }

    if (
      url.pathname === '/api/backtests/run-fresh' ||
      url.pathname === '/api/backtests/run-replay' ||
      url.pathname === '/api/backtests/run'
    ) {
      const request = route.request().postDataJSON() as { strategy_id?: string };
      const strategy = backtestStrategies.find((item) => item.strategy_id === request.strategy_id) ?? lhbStrategy;
      backtestRunStrategyIds.push(strategy.strategy_id);
      if (backtestRunStrategyIds.length > 1) {
        await delay(50);
      }
      const mode = url.pathname === '/api/backtests/run-fresh' ? 'validated' : 'replay';
      await route.fulfill({ json: makeBacktestResult(strategy.strategy_id, strategy.strategy_name, mode) });
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
  return { unhandledRoutes, backtestRunStrategyIds };
}

function makeAssetProfile(assetId = '000001.SZ') {
  const isReviewQueueAsset = assetId === 'CN:SZ:300951';
  const canonicalAssetId = isReviewQueueAsset ? 'CN:SZ:300951' : 'CN:SZ:000001';
  const symbol = isReviewQueueAsset ? '300951' : '000001';
  const name = isReviewQueueAsset ? 'Fixture Stock' : '平安银行';
  return {
    asset_id: assetId,
    canonical_asset_id: canonicalAssetId,
    asset: {
      asset_id: assetId,
      symbol,
      name,
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
      asset_id: assetId,
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
        asset_id: assetId,
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

function makeBacktestResult(
  strategyId = 'lhb_shortline',
  strategyName = 'LHB Shortline Combo',
  mode: 'validated' | 'replay' = 'validated'
) {
  const summary: Record<string, number | string> = {
    final_equity: 1.12,
    total_return: 0.12,
    max_drawdown: -0.05,
    sharpe_ratio: 1.8,
    turnover: 1.4
  };
  summary.combo_scheme = `${strategyId}_combo_v1`;
  summary.evidence_source = 'validated replay fixture';
  return {
    strategy_id: strategyId,
    strategy_name: strategyName,
    read_only: mode === 'replay',
    execution_mode: mode,
    result_source: mode === 'validated' ? 'validated_combo_artifact_rerun' : 'database_replay',
    elapsed_ms: mode === 'validated' ? 1234 : 30,
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
  const { unhandledRoutes, backtestRunStrategyIds } = await mockPlatformApi(page);

  await page.goto('/');

  await expect(page.getByRole('heading', { name: '策略指挥中心' })).toBeVisible();
  const activeStrategies = page.getByRole('region', { name: '启用策略表现' });
  await expect(activeStrategies.getByText('LHB Shortline Combo')).toBeVisible();
  await expect(activeStrategies.getByText('Mid Trend Combo')).toBeVisible();
  await expect(activeStrategies.getByText('Tech Bottleneck Combo')).toBeVisible();
  await expect(page.getByText('Manual V1 TopN Rotation')).toHaveCount(0);
  await expect(page.getByText('策略持仓状态')).toBeVisible();
  const readiness = page.getByRole('region', { name: '平台就绪状态' });
  await expect(readiness.getByText('就绪状态')).toBeVisible();
  await expect(readiness.getByText('本地日线')).toBeVisible();
  await expect(readiness.getByText('模式')).toBeVisible();
  await expect(readiness.getByText('部分可用')).toBeVisible();
  await expect(readiness.getByText('警告数')).toBeVisible();
  await expect(readiness.getByText('1')).toBeVisible();
  await expect(readiness.getByText('News collector lagging')).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Review Queue workspace' }).click();
  await expect(page.getByRole('heading', { name: '策略复盘队列' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Strong evidence' })).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await expect(page.getByRole('button', { name: 'Open Data Explorer workspace' })).toHaveCount(0);

  await page.getByRole('button', { name: 'Open Factor Lab workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Factor Lab' })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'ret_20', exact: true })).toBeVisible();
  await page.getByLabel('select ret_20').check();
  await page.getByRole('button', { name: 'Preview Scores' }).click();
  await expect(page.getByRole('cell', { name: 'CN:SZ:300951' })).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Strategy Lab workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Strategy Lab' })).toBeVisible();
  await expect(page.getByRole('tab', { name: 'Run Backtest' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'LHB Shortline Combo' })).toBeVisible();
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'Mid Trend Combo' })).toBeVisible();
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'Tech Bottleneck Combo' })).toBeVisible();
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'Position Control Overlay' })).toHaveCount(0);
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'runnable' })).toHaveCount(0);
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'Run backtest' })).toHaveCount(0);
  await expect(page.locator('.backtest-catalog-row').filter({ hasText: 'final_equity' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Load Cached Replay' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Load Cached Replay Comparison' })).toHaveCount(0);
  await expect(page.getByRole('combobox', { name: 'strategy' })).not.toContainText('Manual V1 TopN Rotation');
  await page.getByRole('combobox', { name: 'strategy' }).selectOption('lhb_shortline');
  await page.getByRole('button', { name: 'Run Backtest' }).click();
  await expect(page.getByRole('heading', { name: 'Validated backtest' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Result Summary' })).toBeVisible();
  await expect(page.getByText('LHB Shortline Combo').last()).toBeVisible();
  await expect(page.getByText('Total Return')).toBeVisible();
  await expect(page.getByText('+12.00%', { exact: true })).toBeVisible();
  const tradesSection = page.locator('.backtest-result-section').filter({ has: page.getByRole('heading', { name: 'Completed Trades' }) });
  await expect(tradesSection.getByRole('cell', { name: 'CN:SZ:300951' })).toBeVisible();
  await page.getByRole('button', { name: 'Run Comparison' }).click();
  await expect(page.getByRole('heading', { name: 'Strategy Comparison' })).toBeVisible();
  await expect(page.getByText('0 / 3 completed')).toBeVisible();
  const comparisonTable = page.locator('.backtest-comparison-table');
  await expect(comparisonTable.getByRole('cell', { name: 'running' })).toHaveCount(3);
  await expect(comparisonTable.getByRole('cell', { name: 'Manual V1 TopN Rotation' })).toHaveCount(0);
  await expect(comparisonTable.getByRole('cell', { name: 'LHB Shortline Combo' })).toBeVisible();
  await expect(comparisonTable.getByRole('cell', { name: 'Mid Trend Combo' })).toBeVisible();
  await expect(comparisonTable.getByRole('cell', { name: 'Tech Bottleneck Combo' })).toBeVisible();
  await expect(comparisonTable.getByRole('cell', { name: 'validated', exact: true })).toHaveCount(3);
  await expect(comparisonTable.getByRole('cell', { name: 'validated_combo_artifact_rerun', exact: true })).toHaveCount(3);
  await expect(comparisonTable.getByRole('cell', { name: 'Position Control Overlay' })).toHaveCount(0);
  await expect(page.getByText('3 / 3 completed')).toBeVisible();
  await expect(comparisonTable.getByRole('cell', { name: 'passed' })).toHaveCount(3);
  expect(backtestRunStrategyIds).toEqual([
    'lhb_shortline',
    'lhb_shortline',
    'mid_trend',
    'tech_bottleneck'
  ]);
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('tab', { name: 'Validation Replay' }).click();
  await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toContainText('LHB Shortline');
  await expect(page.getByText('support confirmed')).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);

  await page.getByRole('button', { name: 'Open Generated Reports workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Generated Reports', level: 1 })).toBeVisible();
  await expect(page.getByText('Daily TopN')).toBeVisible();
  await assertNoUnsafeExecutionControls(page);
  await assertNoHorizontalOverflow(page);
  expect(unhandledRoutes).toEqual([]);
});
