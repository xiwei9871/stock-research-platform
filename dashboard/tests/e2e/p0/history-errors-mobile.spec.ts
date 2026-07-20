import type { Locator, Page } from '@playwright/test';

import { expectNoHorizontalOverflow } from '../assertions/runtime';
import { installMockPlatformApi, type MockPlatformApiRoutes } from '../fixtures/mockPlatformApi';
import { officialStrategies, type OfficialStrategyId } from '../fixtures/officialStrategies';
import { expect, test } from '../fixtures/test';

const TRADE_DATE = '2026-07-19';
const THEME_ID = 'scientific_instruments_value_chain_v1';

const strategyNames: Record<OfficialStrategyId, string> = {
  lhb_shortline: 'LHB Shortline Combo',
  mid_trend: 'Mid Trend Combo',
  tech_bottleneck: 'Tech Bottleneck Combo'
};

function strategyCatalogItem(strategyId: OfficialStrategyId) {
  const strategy = officialStrategies[strategyId];
  const failed = strategyId === 'tech_bottleneck';
  return {
    strategy_id: strategyId,
    strategy_name: strategyNames[strategyId],
    status: 'runnable',
    description: failed ? '正式策略产物失败。' : 'Official versioned strategy publication.',
    factor_groups: ['official'],
    signal_inputs: ['versioned publication'],
    default_parameters: { top_n: 5 },
    latest_evidence: failed
      ? 'Tech Bottleneck Combo 正式策略产物失败：candidate source freshness metadata missing'
      : '正式策略产物。',
    latest_metrics: failed
      ? {
          as_of_date: TRADE_DATE,
          signal_status: 'strategy_failed',
          signal_count: 0,
          error_message: 'candidate source freshness metadata missing'
        }
      : {
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

function readiness() {
  return {
    mode: 'eod_local',
    status: 'READY',
    display_trade_date: TRADE_DATE,
    latest_trade_date: TRADE_DATE,
    latest_market_date: TRADE_DATE,
    checks: [],
    health_groups: [],
    warnings: [],
    policy: {
      ready_for_dashboard: true,
      ready_for_publication: true,
      blocking_reasons: [],
      warnings: []
    }
  };
}

function platformSummary() {
  return {
    latest_market_date: TRADE_DATE,
    latest_score_date: TRADE_DATE,
    latest_factor_date: TRADE_DATE,
    market_asset_count: 3,
    score_asset_count: 3,
    factor_count: 3,
    score_versions: ['strategy_topn'],
    topn_preview: []
  };
}

function homeRoutes(): MockPlatformApiRoutes {
  return {
    'GET /api/backtests/strategies': {
      json: {
        items: (Object.keys(officialStrategies) as OfficialStrategyId[]).map(strategyCatalogItem)
      }
    },
    'GET /api/market-monitor/eod': {
      json: {
        trade_date: TRADE_DATE,
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
        trade_date: TRADE_DATE,
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

function themeDetail() {
  return {
    theme: {
      theme_id: THEME_ID,
      theme_name: '科学仪器价值链',
      theme_type: 'scientific_instruments',
      summary: '科学分析仪器、关键部件与服务。',
      status: 'reviewed',
      created_from: 'official_reports',
      last_updated: TRADE_DATE,
      node_count: 0,
      source_count: 0,
      claim_count: 0,
      company_count: 0,
      evidence_gap_count: 0,
      deep_research_node_count: 0,
      review_queue_count: 0,
      research_only: true,
      used_for_signal: false,
      used_for_admission: false
    },
    node_summary: { total: 0, by_priority_class: {}, by_review_status: {} },
    source_summary: { total: 0, by_review_status: {} },
    claim_summary: { total: 0, by_platform_use_status: {} },
    company_summary: { total: 0, by_priority_band: {}, by_integration_status: {} },
    evidence_gap_summary: { total: 0, by_priority_band: {} },
    source_reliability_distribution: {},
    claim_evidence_status_distribution: {},
    review_queue_action_distribution: {},
    top_node_priorities: [],
    evidence_gaps: [],
    top_company_priorities: [],
    catalog_context: null,
    research_profile: null,
    beneficiary_summary: { total: 0, by_tier: {}, reviewed_beneficiary_count: 0 },
    research_only: true,
    used_for_signal: false,
    used_for_admission: false
  };
}

function assetProfile(assetId: string, name: string) {
  return {
    asset_id: assetId,
    canonical_asset_id: assetId,
    asset: {
      asset_id: assetId,
      symbol: assetId.split('.')[0],
      name,
      exchange: assetId.split('.')[1],
      board: 'main',
      is_active: true
    },
    bars: [{ time: TRADE_DATE, open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }],
    score: null,
    signals: [],
    decisions: [],
    outcomes: [],
    factor_values: [],
    coverage: {}
  };
}

function stockRoutes(assetId: string, name: string): MockPlatformApiRoutes {
  return {
    [`GET /api/assets/${assetId}/profile`]: { json: assetProfile(assetId, name) },
    [`GET /api/assets/${assetId}/bars`]: { json: { asset_id: assetId, items: [] } },
    [`GET /api/assets/${assetId}/news`]: {
      json: {
        asset_id: assetId,
        items: [],
        summary: {
          news_count_1d: 0,
          news_count_3d: 0,
          news_count_7d: 0,
          latest_published_at: null,
          source_count: 0,
          category_counts: []
        },
        warnings: []
      }
    },
    [`GET /api/assets/${assetId}/research-reports`]: {
      json: { asset_id: assetId, summary: { report_count_90d: 0 }, items: [], warnings: [] }
    },
    [`GET /api/stocks/${assetId}/market-context/heatmap`]: {
      json: { asset_id: assetId, trade_date: TRADE_DATE, data_status: 'missing', selected: null, peers: [], warnings: [] }
    }
  };
}

function reviewQueue() {
  return {
    trade_date: TRADE_DATE,
    score_version: 'strategy_topn',
    review_mode: 'strategy_topn',
    generated_at: '2026-07-19T16:00:00Z',
    warnings: [],
    groups: []
  };
}

function reviewUniverseStock() {
  return {
    stock_code: '300760',
    stock_name: '迈瑞医疗',
    review_universe_source: 'tech_bottleneck_review_universe_frontend_dataset_v1',
    current_layer_status: 'manual_review',
    manual_approval_status: 'pending',
    frontend_review_status: 'pending_review',
    evidence_count: 8,
    page_citation_count: 8,
    source_pdf_count: 2,
    primary_source_supported: true,
    hard_tech_domain: 'supported',
    supply_chain_role_hint: 'supported',
    business_relevance_hint: 'supported',
    bottleneck_or_chokepoint_hint: 'core',
    concept_pollution_risk: 'low',
    route_around_or_substitution_risk: 'needs_manual_review',
    value_capture_risk: 'needs_manual_review',
    disconfirmation_trigger: false,
    next_primary_source_to_check: '2025 annual report',
    strongest_primary_source_claim: 'Official filing supports the instrument exposure.',
    weakest_or_riskiest_claim: 'Localization rate needs verification.',
    evidence_summary_for_review: '8 page-level citations',
    industry: '医疗器械',
    concept_tags: ['高端医疗设备'],
    evidence_strength: 'strong',
    bottleneck_relevance: 'core',
    bottleneck_confidence_score: 82,
    evidence_quality_score: 78,
    source_group: 'official_filings',
    previous_tier: 'quality_pool',
    review_status: 'pending_review',
    reviewer_decision: '',
    reviewer_note: '',
    used_for_signal: false,
    used_for_admission: false,
    auto_added_to_quality_pool: false
  };
}

function deepRouteRoutes(): MockPlatformApiRoutes {
  const reviewStock = reviewUniverseStock();
  return {
    'GET /api/auth/me': {
      json: {
        user: {
          user_id: 'failure-isolation-user',
          username: 'failure_isolation_user',
          display_name: 'Failure Isolation User',
          role: 'user',
          is_active: true
        }
      }
    },
    'GET /api/platform/readiness': { json: readiness() },
    'GET /api/platform/summary': { json: platformSummary() },
    ...homeRoutes(),
    'GET /api/review-queue': { json: reviewQueue() },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}`]: { json: themeDetail() },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/companies`]: { json: { total: 0, items: [] } },
    'GET /api/research/tech-bottleneck/review-universe/summary': {
      json: {
        frontend_dataset_count: 1,
        v5_hydrated_count: 1,
        v7_proposal_new_count: 0,
        v5_targeted_hydrated_count: 0,
        remaining_evidence_gap_count: 0,
        evidence_index_row_count: 8,
        source_index_row_count: 2,
        used_for_signal_count: 0,
        used_for_admission_count: 0,
        readonly_page: true,
        reviewer_decision_write_enabled: false,
        database_write_enabled: false,
        csv_writeback_enabled: false,
        acceptance_decision: 'review_universe_ready'
      }
    },
    'GET /api/research/tech-bottleneck/review-universe/stocks': {
      json: { total: 1, limit: 500, offset: 0, items: [reviewStock] }
    },
    'GET /api/research/tech-bottleneck/review-universe/filter-options': { json: {} },
    'GET /api/research/tech-bottleneck/review-universe/decision-summary': {
      json: {
        total_review_universe_count: 1,
        reviewed_count: 0,
        pending_count: 1,
        keep_count: 0,
        hold_count: 0,
        need_more_evidence_count: 0,
        downgrade_count: 0,
        reject_count: 0,
        last_reviewed_at: '',
        used_for_signal_count: 0,
        used_for_admission_count: 0,
        frozen_v7_generated: false
      }
    },
    'GET /api/assets/search': { json: { items: [] } },
    'GET /api/evidence-digest': { json: { warnings: [] } },
    ...stockRoutes('300203.SZ', '聚光科技'),
    ...stockRoutes('430476.BJ', '海能技术')
  };
}

async function installDeepRouteApi(page: Page, overrides: MockPlatformApiRoutes = {}) {
  await installMockPlatformApi(page, { ...deepRouteRoutes(), ...overrides });
}

async function expectStrategyCard(region: Locator, strategyId: OfficialStrategyId) {
  await expect(region.locator(`article[data-strategy-id="${strategyId}"]`)).toBeVisible();
}

test('one failed official strategy remains isolated from two usable publications @p0 @mock @failure-isolation', async ({
  page
}) => {
  await installDeepRouteApi(page);
  await page.goto('/');

  const performance = page.getByRole('region', { name: '启用策略表现' });
  await expectStrategyCard(performance, 'lhb_shortline');
  await expectStrategyCard(performance, 'mid_trend');
  await expectStrategyCard(performance, 'tech_bottleneck');
  const failedCard = performance.locator('article[data-strategy-id="tech_bottleneck"]');
  await expect(failedCard.getByText('未就绪', { exact: true })).toBeVisible();
  await expect(failedCard.getByText('正式产物失败', { exact: true })).toBeVisible();
  await expect(failedCard.getByText(/candidate source freshness metadata missing/)).toBeVisible();
  await expect(failedCard.getByTestId('strategy-total-return')).toHaveText('-');
  await expect(performance.locator('article[data-strategy-id="lhb_shortline"]')).toContainText('+52.40%');
  await expect(performance.locator('article[data-strategy-id="mid_trend"]')).toContainText('+49.12%');
});

test('a noncritical API 503 degrades its widget while the platform remains usable @p0 @mock @failure-isolation', async ({
  page,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(
    'Failed to load resource: the server responded with a status of 503 (Service Unavailable)'
  );
  runtimePolicy.failedRequests.push(
    /^GET http:\/\/127\.0\.0\.1:\d+\/api\/public-news — HTTP 503$/
  );
  await installDeepRouteApi(page, {
    'GET /api/public-news': { status: 503, json: { detail: 'news temporarily unavailable' } }
  });
  await page.goto('/');

  await expect(page.getByRole('heading', { name: '策略指挥中心' })).toBeVisible();
  await expect(page.getByText(/新闻流不可用：.*failed with 503/)).toBeVisible();
  const performance = page.getByRole('region', { name: '启用策略表现' });
  await expectStrategyCard(performance, 'lhb_shortline');
  await expectStrategyCard(performance, 'mid_trend');
});

test('a critical API 500 exposes a local error and succeeds through the real retry control @p0 @mock @failure-isolation', async ({
  page,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(
    'Failed to load resource: the server responded with a status of 500 (Internal Server Error)'
  );
  runtimePolicy.failedRequests.push(
    /^GET http:\/\/127\.0\.0\.1:\d+\/api\/research\/theme-decomposition\/themes\/scientific_instruments_value_chain_v1 — HTTP 500$/
  );
  await installDeepRouteApi(page);
  let detailAttempts = 0;
  let detailPhase: 'failure' | 'success' = 'failure';
  await page.route(`/api/research/theme-decomposition/themes/${THEME_ID}`, async (route) => {
    detailAttempts += 1;
    if (detailPhase === 'failure') {
      await route.fulfill({ status: 500, json: { detail: 'theme store unavailable' } });
      return;
    }
    await route.fallback();
  });

  await page.goto(`/theme-research/${THEME_ID}/companies`);
  const errorState = page.locator('.theme-research-state');
  await expect(errorState).toHaveAttribute('role', 'alert');
  await expect(errorState).toContainText('无法读取主题研究数据，请重试。');
  expect(detailAttempts).toBeGreaterThanOrEqual(1);
  const attemptsBeforeRetry = detailAttempts;
  detailPhase = 'success';
  await errorState.getByRole('button', { name: '重试' }).click();

  await expect(page.getByRole('heading', { name: '公司映射' })).toBeVisible();
  expect(detailAttempts).toBeGreaterThan(attemptsBeforeRetry);
});

test('every P0 deep route survives a direct refresh @p0 @mock @failure-isolation', async ({ page }) => {
  await installDeepRouteApi(page);
  const routes = [
    { path: '/review-queue', heading: '策略复盘队列' },
    { path: '/strategy-lab?strategy_id=lhb_shortline', heading: 'Strategy Lab' },
    { path: `/theme-research/${THEME_ID}/companies`, heading: '公司映射' },
    { path: '/research/tech-bottleneck/review-universe', heading: '科技卡脖子复盘' },
    { path: '/stock/300203.SZ?source=search', heading: '聚光科技 300203.SZ' },
    {
      path: '/tech-bottleneck/stock/430476.BJ?source=theme_research',
      heading: '海能技术 430476.BJ'
    }
  ];

  for (const route of routes) {
    await page.goto(route.path);
    await expect(page.getByRole('heading', { name: route.heading })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.reload();
    await expect(page.getByRole('heading', { name: route.heading })).toBeVisible();
    await page.waitForLoadState('networkidle');
  }
});

test('the mobile P0 subset has no page-level horizontal overflow @p0 @mock @failure-isolation @mobile', async ({
  page
}) => {
  await installDeepRouteApi(page);
  const routes = [
    { path: '/', heading: '策略指挥中心' },
    { path: '/review-queue', heading: '策略复盘队列' },
    { path: `/theme-research/${THEME_ID}/companies`, heading: '公司映射' },
    { path: '/stock/300203.SZ?source=search', heading: '聚光科技 300203.SZ' }
  ];

  for (const route of routes) {
    await page.goto(route.path);
    await expect(page.getByRole('heading', { name: route.heading })).toBeVisible();
    await page.waitForLoadState('networkidle');
    await expectNoHorizontalOverflow(page);
  }
});
