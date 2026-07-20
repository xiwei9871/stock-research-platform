import type { Locator, Page } from '@playwright/test';

import { installMockPlatformApi, type MockPlatformApiRoutes } from '../fixtures/mockPlatformApi';
import { officialStrategies } from '../fixtures/officialStrategies';
import { expect, test } from '../fixtures/test';

const TRADE_DATE = '2026-07-19';
const THEME_ID = 'scientific_instruments_value_chain_v1';

const USER = {
  user_id: 'visual-audit-user',
  username: 'visual_audit_user',
  display_name: 'Visual Audit User',
  role: 'user',
  is_active: true
};

const strategyNames = {
  lhb_shortline: 'LHB Shortline Combo',
  mid_trend: 'Mid Trend Combo',
  tech_bottleneck: 'Tech Bottleneck Combo'
} as const;

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

function catalogItem(strategy: (typeof officialStrategies)[keyof typeof officialStrategies]) {
  return {
    strategy_id: strategy.strategyId,
    strategy_name: strategyNames[strategy.strategyId],
    status: 'runnable',
    description: '正式版本策略产物。',
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

function reviewItem() {
  const strategy = officialStrategies.lhb_shortline;
  return {
    queue_id: `${strategy.performanceDate}:strategy_topn:${strategy.strategyId}`,
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    trade_date: strategy.performanceDate,
    latest_trade_date: strategy.performanceDate,
    run_id: `${strategy.strategyId}:eod`,
    score_version: 'strategy_topn',
    display_name: 'LHB Shortline Combo 标的',
    rank: 1,
    score: 88,
    source_type: 'strategy_manifest',
    source_name: strategyNames.lhb_shortline,
    source_rank: 1,
    topn_rank: 1,
    strategy_id: strategy.strategyId,
    strategy_name: strategyNames.lhb_shortline,
    strategy_run_id: `${strategy.strategyId}:run`,
    contract_id: strategy.contractId,
    publish_id: strategy.publishId,
    artifact_version: strategy.artifactVersion,
    performance_as_of_date: strategy.performanceDate,
    total_return_pct: strategy.totalReturn,
    contract_status: 'success',
    review_tier: 'top5_focus',
    digest_key: `${strategy.strategyId}:digest`,
    digest_title: 'LHB 正式复盘',
    bucket: 'strong',
    source_kinds: ['strategy'],
    risk_count: 0,
    warning_count: 0,
    next_action_count: 0,
    digest: {
      asset_id: '000001.SZ',
      canonical_asset_id: '000001.SZ',
      trade_date: strategy.performanceDate,
      title: 'LHB 正式复盘',
      score: 88,
      bucket: 'strong',
      facts: [{ kind: '策略', label: 'Top5 先选后校验，不补位', value: '正式合同已通过' }],
      risk_flags: [],
      source_refs: { strategy_asset_id: '000001.SZ' },
      warnings: [],
      next_actions: []
    }
  };
}

const THEME = {
  theme_id: THEME_ID,
  theme_name: '科学仪器价值链',
  theme_type: 'scientific_instruments',
  summary: '科学分析仪器、关键部件与服务。',
  status: 'reviewed',
  created_from: 'official_reports',
  last_updated: TRADE_DATE,
  node_count: 1,
  source_count: 1,
  claim_count: 1,
  company_count: 1,
  evidence_gap_count: 0,
  deep_research_node_count: 1,
  review_queue_count: 0,
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
};

const TECH_STOCK = {
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

function assetProfile() {
  return {
    asset_id: '300203.SZ',
    canonical_asset_id: '300203.SZ',
    asset: {
      asset_id: '300203.SZ',
      symbol: '300203',
      name: '聚光科技',
      exchange: 'SZ',
      board: 'chinext',
      is_active: true
    },
    bars: [
      {
        time: TRADE_DATE,
        open: 10,
        high: 10.8,
        low: 9.8,
        close: 10.5,
        volume: 1000,
        amount: 10500
      }
    ],
    score: null,
    signals: [],
    decisions: [],
    outcomes: [],
    factor_values: [],
    coverage: {}
  };
}

function authenticatedRoutes(): MockPlatformApiRoutes {
  const strategies = Object.values(officialStrategies);
  const selectedReviewItem = reviewItem();
  return {
    'GET /api/auth/me': { json: { user: USER } },
    'GET /api/platform/readiness': { json: readiness() },
    'GET /api/platform/summary': { json: platformSummary() },
    'GET /api/backtests/strategies': { json: { items: strategies.map(catalogItem) } },
    'GET /api/review-queue': {
      json: {
        trade_date: TRADE_DATE,
        score_version: 'strategy_topn',
        review_mode: 'strategy_topn',
        generated_at: '2026-07-19T16:00:00Z',
        warnings: [],
        groups: [
          {
            bucket: 'strong',
            label: strategyNames.lhb_shortline,
            count: 1,
            items: [selectedReviewItem]
          }
        ]
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
    'GET /api/research/publication/snapshots': { json: { items: [] } },
    'GET /api/assets/300203.SZ/profile': { json: assetProfile() },
    'GET /api/assets/300203.SZ/bars': { json: { items: [] } },
    'GET /api/assets/300203.SZ/news': {
      json: {
        asset_id: '300203.SZ',
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
    'GET /api/assets/300203.SZ/research-reports': {
      json: {
        asset_id: '300203.SZ',
        summary: {
          report_count_30d: 0,
          report_count_90d: 0,
          broker_coverage_count_90d: 0,
          latest_report_date: null,
          latest_rating: '',
          latest_target_price: null
        },
        items: [],
        warnings: []
      }
    },
    'GET /api/assets/search': { json: { items: [] } },
    'GET /api/evidence-digest': { json: { warnings: [] } },
    'GET /api/stocks/300203.SZ/market-context/heatmap': {
      json: {
        asset_id: '300203.SZ',
        trade_date: TRADE_DATE,
        data_status: 'missing',
        selected: null,
        peers: [],
        warnings: []
      }
    },
    'GET /api/research/theme-decomposition/themes': { json: { total: 1, items: [THEME] } },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}`]: {
      json: {
        theme: THEME,
        node_summary: { total: 1, by_priority_class: { deep_research_priority: 1 }, by_review_status: { reviewed: 1 } },
        source_summary: { total: 1, by_review_status: { accepted: 1 } },
        claim_summary: { total: 1, by_platform_use_status: { research_lead: 1 } },
        company_summary: { total: 1, by_priority_band: { high: 1 }, by_integration_status: { linked_existing_universe: 1 } },
        evidence_gap_summary: { total: 0, by_priority_band: {} },
        source_reliability_distribution: { S0: 1 },
        claim_evidence_status_distribution: { verified: 1 },
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
      }
    },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/nodes`]: { json: { total: 0, items: [] } },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/sources`]: { json: { total: 0, items: [] } },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/claims`]: { json: { total: 0, items: [] } },
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
      json: { total: 1, limit: 500, offset: 0, items: [TECH_STOCK] }
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
    }
  };
}

async function freezeVisualState(page: Page) {
  await page.evaluate(async () => {
    await document.fonts.ready;
  });
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation-delay: 0s !important;
        animation-duration: 0s !important;
        caret-color: transparent !important;
        scroll-behavior: auto !important;
        transition-delay: 0s !important;
        transition-duration: 0s !important;
      }
    `
  });
}

function commonMasks(page: Page) {
  return [
    page.locator('canvas'),
    page.locator('time'),
    page.locator('[data-testid*="date"]'),
    page.locator('[data-generated-at], [data-testid*="generated"]'),
    page.locator('.cursor-overlay, .crosshair, [class*="cursor-line"], [class*="crosshair"]')
  ];
}

async function expectRegionScreenshot(
  page: Page,
  region: Locator,
  name: string,
  masks: Locator[] = []
) {
  await freezeVisualState(page);
  await expect(region).toBeVisible();
  await region.scrollIntoViewIfNeeded();
  await expect(region).toHaveScreenshot(name, {
    animations: 'disabled',
    caret: 'hide',
    mask: [...commonMasks(page), ...masks],
    maskColor: '#d1d5db',
    scale: 'css'
  });
}

async function expectCombinedRegionScreenshot(
  page: Page,
  regions: Locator[],
  name: string,
  masks: Locator[] = []
) {
  await freezeVisualState(page);
  for (const region of regions) {
    await expect(region).toBeVisible();
  }
  await regions[0].scrollIntoViewIfNeeded();
  const boxes = await Promise.all(regions.map((region) => region.boundingBox()));
  expect(boxes.every(Boolean)).toBe(true);
  const visibleBoxes = boxes.filter((box): box is NonNullable<typeof box> => Boolean(box));
  const left = Math.min(...visibleBoxes.map((box) => box.x));
  const top = Math.min(...visibleBoxes.map((box) => box.y));
  const right = Math.max(...visibleBoxes.map((box) => box.x + box.width));
  const bottom = Math.max(...visibleBoxes.map((box) => box.y + box.height));
  const screenshot = await page.screenshot({
    animations: 'disabled',
    caret: 'hide',
    clip: { x: left, y: top, width: right - left, height: bottom - top },
    mask: [...commonMasks(page), ...masks],
    maskColor: '#d1d5db',
    scale: 'css'
  });
  expect(screenshot).toMatchSnapshot(name);
}

test.beforeEach(async ({}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'chromium-desktop',
    'Reviewed visual baselines are intentionally generated only for Chromium desktop.'
  );
});

test('login panel stable region @audit @visual', async ({ page, runtimePolicy }) => {
  runtimePolicy.consoleErrors.push(
    /^Failed to load resource: the server responded with a status of 401 \(Unauthorized\)$/
  );
  await installMockPlatformApi(page, {
    'GET /api/auth/me': { status: 401, json: { detail: 'not_authenticated' } }
  });
  await page.goto('/');

  await expectRegionScreenshot(page, page.locator('.login-panel'), 'login-panel.png');
});

test('home strategy performance stable region @audit @visual', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto('/');

  const overflowingContractValues = await page
    .locator('.strategy-command-card .strategy-metric-grid[aria-label] > div')
    .evaluateAll((cells) =>
      cells.flatMap((cell) => {
        const value = cell.querySelector('strong');
        if (!value) return [];
        const cellRect = cell.getBoundingClientRect();
        const valueRect = value.getBoundingClientRect();
        return valueRect.right > cellRect.right + 1 || valueRect.left < cellRect.left - 1
          ? [value.textContent?.trim() ?? 'unknown']
          : [];
      })
    );
  expect(overflowingContractValues).toEqual([]);

  await expectRegionScreenshot(
    page,
    page.getByRole('region', { name: '启用策略表现' }),
    'home-strategy-performance.png',
    [page.locator('.strategy-command-card > .strategy-metric-grid:not([aria-label]) strong')]
  );
});

test('selected review queue formal contract stable region @audit @visual', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto('/review-queue');

  const selectedEvidence = page.getByRole('region', { name: '选中标的证据' });
  const formalContract = selectedEvidence.getByLabel('正式发布合同');
  await expectRegionScreenshot(page, formalContract, 'review-queue-formal-contract.png', [
    formalContract.getByTestId('strategy-total-return')
  ]);
});

test('stock source context stable region @audit @visual', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto('/stock/300203.SZ?source=search&match_reason=股票名称匹配');

  const stockWorkspace = page.getByRole('region', { name: '个股复盘工作台' });
  await expectRegionScreenshot(
    page,
    stockWorkspace.locator('header.workspace-header'),
    'stock-source-context.png'
  );
});

test('theme research header and tabs stable region @audit @visual', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto(`/theme-research/${THEME_ID}`);

  const workspace = page.getByRole('region', { name: '主题研究详情' });
  await expectCombinedRegionScreenshot(
    page,
    [workspace.locator('.theme-research-header'), workspace.getByRole('tablist', { name: '主题研究视图' })],
    'theme-header-tabs.png'
  );
});

test('technology bottleneck summary stable region @audit @visual', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto('/research/tech-bottleneck/review-universe');

  const workspace = page.getByRole('region', { name: '科技卡脖子复盘工作台' });
  await expectCombinedRegionScreenshot(
    page,
    [workspace.locator('header.workspace-header'), page.getByRole('region', { name: '科技卡脖子复盘指标' })],
    'tech-bottleneck-summary.png'
  );
});
