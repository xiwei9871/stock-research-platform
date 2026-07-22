import type { Page } from '@playwright/test';

import {
  expectApiUiConsistency,
  expectRouteContext,
  expectStrategyPresentationConsistency
} from '../assertions/consistency';
import { installMockPlatformApi, type MockPlatformApiRoutes } from '../fixtures/mockPlatformApi';
import {
  officialStrategies,
  type OfficialStrategyFixture,
  type OfficialStrategyId
} from '../fixtures/officialStrategies';
import { expect, test } from '../fixtures/test';

const strategyNames: Record<OfficialStrategyId, string> = {
  lhb_shortline: 'LHB Shortline Combo',
  mid_trend: 'Mid Trend Combo',
  tech_bottleneck: 'Tech Bottleneck Combo'
};

const rawTotalReturnRatios: Record<OfficialStrategyId, number> = {
  lhb_shortline: 0.524,
  mid_trend: 0.4912,
  tech_bottleneck: 0.705
};

function catalogItem(strategy: OfficialStrategyFixture) {
  return {
    strategy_id: strategy.strategyId,
    strategy_name: strategyNames[strategy.strategyId],
    status: 'runnable',
    description: 'Official versioned strategy publication.',
    factor_groups: ['official'],
    signal_inputs: ['versioned publication'],
    default_parameters: { top_n: 5 },
    latest_evidence: '正式策略产物。',
    latest_metrics: {
      as_of_date: strategy.performanceDate,
      performance_as_of_date: strategy.performanceDate,
      total_return_pct: strategy.totalReturn,
      max_drawdown_pct: -5,
      signal_status: 'current_holdings',
      signal_count: 5,
      contract_id: strategy.contractId,
      publish_id: strategy.publishId,
      artifact_version: strategy.artifactVersion,
      contract_status: 'success'
    },
    primary_action: 'Run backtest'
  };
}

function reviewItem(strategy: OfficialStrategyFixture, index: number) {
  const name = strategyNames[strategy.strategyId];
  const assetId = `00000${index + 1}.SZ`;
  return {
    queue_id: `${strategy.performanceDate}:strategy_topn:${strategy.strategyId}`,
    asset_id: assetId,
    canonical_asset_id: assetId,
    trade_date: strategy.performanceDate,
    latest_trade_date: strategy.performanceDate,
    run_id: `${strategy.strategyId}:eod`,
    score_version: 'strategy_topn',
    display_name: `${name} 标的`,
    rank: 1,
    score: 88,
    source_type: 'strategy_manifest',
    source_name: name,
    source_rank: 1,
    topn_rank: 1,
    strategy_id: strategy.strategyId,
    strategy_name: name,
    strategy_run_id: `${strategy.strategyId}:run`,
    contract_id: strategy.contractId,
    publish_id: strategy.publishId,
    artifact_version: strategy.artifactVersion,
    performance_as_of_date: strategy.performanceDate,
    total_return_pct: strategy.totalReturn,
    contract_status: 'success',
    review_tier: 'top5_focus',
    digest_key: `${strategy.strategyId}:digest`,
    digest_title: `${name} 正式复盘`,
    bucket: 'strong',
    source_kinds: ['strategy'],
    risk_count: 0,
    warning_count: 0,
    next_action_count: 0,
    digest: {
      asset_id: assetId,
      canonical_asset_id: assetId,
      trade_date: strategy.performanceDate,
      title: `${name} 正式复盘`,
      score: 88,
      bucket: 'strong',
      facts: [],
      risk_flags: [],
      source_refs: { strategy_asset_id: assetId },
      warnings: [],
      next_actions: []
    }
  };
}

function sharedRoutes(): MockPlatformApiRoutes {
  const strategies = Object.values(officialStrategies);
  return {
    'GET /api/auth/me': {
      json: {
        user: {
          user_id: 'publication-user',
          username: 'publication_user',
          display_name: 'Publication User',
          role: 'user',
          is_active: true
        }
      }
    },
    'GET /api/platform/readiness': {
      json: {
        mode: 'eod_local',
        status: 'READY',
        display_trade_date: officialStrategies.lhb_shortline.performanceDate,
        latest_trade_date: officialStrategies.lhb_shortline.performanceDate,
        latest_market_date: officialStrategies.lhb_shortline.performanceDate,
        checks: [],
        health_groups: [],
        warnings: [],
        policy: {
          ready_for_dashboard: true,
          ready_for_publication: true,
          blocking_reasons: [],
          warnings: []
        }
      }
    },
    'GET /api/platform/summary': {
      json: {
        latest_market_date: officialStrategies.lhb_shortline.performanceDate,
        latest_score_date: officialStrategies.lhb_shortline.performanceDate,
        latest_factor_date: officialStrategies.lhb_shortline.performanceDate,
        market_asset_count: 3,
        score_asset_count: 3,
        factor_count: 3,
        score_versions: ['strategy_topn'],
        topn_preview: []
      }
    },
    'GET /api/backtests/strategies': { json: { items: strategies.map(catalogItem) } },
    'GET /api/review-queue': {
      json: {
        trade_date: officialStrategies.lhb_shortline.performanceDate,
        score_version: 'strategy_topn',
        review_mode: 'strategy_topn',
        generated_at: '2026-07-19T16:00:00Z',
        warnings: [],
        groups: strategies.map((strategy, index) => ({
          bucket: `strategy:${strategy.strategyId}`,
          label: strategyNames[strategy.strategyId],
          count: 1,
          items: [reviewItem(strategy, index)]
        }))
      }
    },
    'GET /api/market-monitor/eod': {
      json: {
        trade_date: officialStrategies.lhb_shortline.performanceDate,
        freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
        coverage: { market_assets: 3, score_assets: 3, factor_count: 3 },
        market_breadth: {},
        market_regime: {},
        strategy_signals: [],
        warnings: []
      }
    },
    'GET /api/public-news': { json: { items: [], total: 0, limit: 5, offset: 0 } },
    'GET /api/strategy-score-audit': {
      json: {
        trade_date: officialStrategies.lhb_shortline.performanceDate,
        overall_status: 'ok',
        anomaly_row_count: 0,
        anomaly_counts_by_type: {},
        strategies: []
      }
    },
    'GET /api/research/cases': { json: { items: [] } },
    'GET /api/research/evidence': { json: { items: [] } },
    'GET /api/research/queue/health': {
      json: {
        status: 'ready',
        can_review: true,
        can_publish_research_queue: false,
        summary: {
          case_count: 0,
          open_case_count: 0,
          claim_count: 0,
          evidence_artifact_count: 0,
          evidence_link_count: 0,
          evidence_gap_count: 0,
          unmatched_digest_count: 0
        },
        top_gap_cases: []
      }
    },
    'GET /api/research/queue/publish-gate': {
      json: {
        status: 'empty',
        research_ready_for_publication: false,
        internal_snapshot_enabled: false,
        summary: { pending_gap_count: 0, request_more_evidence_count: 0, error_count: 0 },
        blockers: [],
        top_blocked_cases: [],
        warnings: []
      }
    },
    'GET /api/research/publication/snapshots': { json: { items: [] } }
  };
}

async function expectFullPublication(card: ReturnType<Page['locator']>, strategy: OfficialStrategyFixture) {
  await expect(card).toBeVisible();
  await expectStrategyPresentationConsistency(card, {
    strategyId: strategy.strategyId,
    tradeDate: strategy.performanceDate,
    totalReturnPct: strategy.totalReturn
  });
  await expect(card.getByText('数据正常', { exact: true })).toBeVisible();
  await expect(card.getByText(strategy.contractId, { exact: true })).toHaveCount(0);
  await expect(card.getByText(strategy.publishId, { exact: true })).toHaveCount(0);
  await expect(card.getByText(strategy.artifactVersion, { exact: true })).toHaveCount(0);
}

test.beforeEach(async ({ page }) => {
  await installMockPlatformApi(page, sharedRoutes());
});

test('official publication identity is stable across home and strategy-specific review deep links @p0 @mock @publication', async ({
  page
}) => {
  const runRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (
      request.method() === 'POST' &&
      url.pathname.startsWith('/api/backtests/') &&
      /(run|execute|jobs)/.test(url.pathname)
    ) {
      runRequests.push(`${request.method()} ${url.pathname}`);
    }
  });

  await page.goto('/');

  for (const strategy of Object.values(officialStrategies)) {
    const homeCard = page.locator(`article[data-strategy-id="${strategy.strategyId}"]`);
    await expectFullPublication(homeCard, strategy);
    if (strategy.strategyId === 'lhb_shortline') {
      await expectApiUiConsistency(
        rawTotalReturnRatios.lhb_shortline,
        homeCard.getByTestId('strategy-total-return'),
        'ratio-as-percent'
      );
    }
    await expect(page.getByText('+175.29%', { exact: true })).toHaveCount(0);

    await homeCard.getByRole('button', { name: `查看 ${strategyNames[strategy.strategyId]} 复盘` }).click();
    await expectRouteContext(page, { path: /^\/review-queue$/ });
    await expect(page).toHaveURL(new RegExp(`strategy_id=${strategy.strategyId}$`));
    await expect(page.getByRole('button', { name: `${strategyNames[strategy.strategyId]} 1` })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    const reviewContract = page.locator(
      `[aria-label="选中标的证据"] [data-strategy-id="${strategy.strategyId}"]`
    );
    await expectFullPublication(reviewContract, strategy);
    await expect(page.getByText('+175.29%', { exact: true })).toHaveCount(0);
    await expect(runRequests).toEqual([]);

    await page.reload();
    await expectRouteContext(page, { path: /^\/review-queue$/ });
    await expect(page).toHaveURL(new RegExp(`strategy_id=${strategy.strategyId}$`));
    await expect(page.getByRole('button', { name: `${strategyNames[strategy.strategyId]} 1` })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expectFullPublication(
      page.locator(`[aria-label="选中标的证据"] [data-strategy-id="${strategy.strategyId}"]`),
      strategy
    );
    await expect(runRequests).toEqual([]);

    await page.getByRole('button', { name: 'Open Home workspace' }).click();
  }

  await page.getByRole('button', { name: 'Open Review Queue workspace' }).click();
  await expectRouteContext(page, { path: /^\/review-queue$/ });

  for (const strategy of Object.values(officialStrategies)) {
    await page.getByRole('button', { name: `${strategyNames[strategy.strategyId]} 1` }).click();
    const reviewContract = page.locator(
      `[aria-label="选中标的证据"] [data-strategy-id="${strategy.strategyId}"]`
    );
    await expectFullPublication(reviewContract, strategy);
  }

  await expect(page.getByText('+175.29%', { exact: true })).toHaveCount(0);
  await expect(runRequests).toEqual([]);
});

test('unknown strategy deep links fail closed without selecting or running an official strategy @p0 @mock @publication', async ({
  page
}) => {
  const runRequests: string[] = [];
  page.on('request', (request) => {
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname.startsWith('/api/backtests/')) {
      runRequests.push(`${request.method()} ${url.pathname}`);
    }
  });

  await page.goto('/strategy-lab?strategy_id=unknown_strategy');

  await expect(page).toHaveURL(/\/strategy-lab\?strategy_id=unknown_strategy$/);
  await expect(page.getByRole('alert')).toHaveText('未知策略 unknown_strategy');
  await expect(page.getByLabel('strategy', { exact: true })).toHaveValue('');
  await expect(page.getByRole('region', { name: /策略数据状态/ })).toHaveCount(0);
  await expect(runRequests).toEqual([]);
});
