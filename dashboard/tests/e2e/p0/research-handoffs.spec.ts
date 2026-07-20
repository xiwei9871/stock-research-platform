import type { Page } from '@playwright/test';

import { expectRouteContext, expectStateRestored } from '../assertions/consistency';
import { installMockPlatformApi, type MockPlatformApiRoutes } from '../fixtures/mockPlatformApi';
import { expect, test } from '../fixtures/test';

const TRADE_DATE = '2026-07-17';
const THEME_ID = 'scientific_instruments_value_chain_v1';

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

const HAINENG_COMPANY = {
  theme_id: THEME_ID,
  mapping_id: 'g5_430476_chromatography_separation_instruments',
  company_code: '430476.BJ',
  company_name: '海能技术',
  market: 'CN',
  mapped_node_id: 'chromatography_separation_instruments',
  mapping_type: 'direct_product',
  business_stage: 'primary_business',
  confidence: 0.95,
  evidence_ids: ['g5_430476_product'],
  revenue_relevance: 'meaningful',
  bottleneck_relevance: 'core',
  business_materiality: 'meaningful_segment',
  product_or_service: '色谱仪',
  relationship_summary: '平台保留 430476.BJ 兼容路由，官方报告证券代码为 920476。',
  review_status: 'reviewed',
  notes: 'current_security_code=920476; platform_compatibility_code=430476.BJ',
  mapped_node: {
    node_id: 'chromatography_separation_instruments',
    node_name: '色谱分离仪器',
    evidence_strength: 5
  },
  company_research_priority_score: 88,
  company_relevance_score: 4.8,
  business_materiality_score: 4,
  priority_band: 'high',
  recommended_action: 'deep_company_research',
  rationale_codes: ['official_report_supported'],
  integration_status: 'linked_existing_universe',
  integration_ref: '430476.BJ',
  existing_review_context: { status: 'reviewed', reviewer_decision: 'keep' },
  tech_bottleneck_stock_path: '/tech-bottleneck/stock/430476.BJ?source=theme_research',
  beneficiary_tier: 'core_beneficiary',
  mapping_evidence: [],
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
};

const REVIEW_STOCK = {
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
    bars: [
      {
        time: TRADE_DATE,
        open: 10,
        high: 11,
        low: 9.5,
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

function stockReadRoutes(assetId: string, name: string): MockPlatformApiRoutes {
  return {
    [`GET /api/assets/${assetId}/profile`]: { json: assetProfile(assetId, name) },
    [`GET /api/assets/${assetId}/bars`]: { json: { items: [] } },
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
      json: {
        asset_id: assetId,
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
    [`GET /api/stocks/${assetId}/market-context/heatmap`]: {
      json: {
        asset_id: assetId,
        trade_date: TRADE_DATE,
        data_status: 'missing',
        selected: null,
        peers: [],
        warnings: []
      }
    }
  };
}

const themeDetail = {
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
  top_company_priorities: [HAINENG_COMPANY],
  catalog_context: null,
  research_profile: null,
  beneficiary_summary: { total: 1, by_tier: { core_beneficiary: 1 }, reviewed_beneficiary_count: 1 },
  research_only: true,
  used_for_signal: false,
  used_for_admission: false
};

async function installResearchApi(page: Page) {
  await installMockPlatformApi(page, {
    'GET /api/auth/me': {
      json: {
        user: {
          user_id: 'research-handoff-user',
          username: 'research_handoff_user',
          display_name: 'Research Handoff User',
          role: 'user',
          is_active: true
        }
      }
    },
    'GET /api/platform/readiness': {
      json: {
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
      }
    },
    'GET /api/platform/summary': {
      json: {
        latest_market_date: TRADE_DATE,
        latest_score_date: TRADE_DATE,
        latest_factor_date: TRADE_DATE,
        market_asset_count: 0,
        score_asset_count: 0,
        factor_count: 0,
        score_versions: [],
        topn_preview: []
      }
    },
    'GET /api/research/theme-decomposition/themes': { json: { total: 1, items: [THEME] } },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}`]: { json: themeDetail },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/nodes`]: { json: { total: 0, items: [] } },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/sources`]: { json: { total: 0, items: [] } },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/claims`]: { json: { total: 0, items: [] } },
    [`GET /api/research/theme-decomposition/themes/${THEME_ID}/companies`]: {
      json: { total: 1, items: [HAINENG_COMPANY] }
    },
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
      json: { total: 1, limit: 500, offset: 0, items: [REVIEW_STOCK] }
    },
    'GET /api/research/tech-bottleneck/review-universe/stocks/300760': { json: REVIEW_STOCK },
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
    ...stockReadRoutes('430476.BJ', '海能技术'),
    ...stockReadRoutes('300760.SZ', '迈瑞医疗')
  });
}

test.beforeEach(async ({ page }) => {
  await installResearchApi(page);
});

test('theme company handoff preserves its source token and restores the selected company tab @p0 @mock @handoff', async ({ page }) => {
  await page.goto('/theme-research');
  await page.getByRole('button', { name: '打开科学仪器价值链' }).click();
  await expectRouteContext(page, { path: new RegExp(`^/theme-research/${THEME_ID}$`) });

  await page.getByRole('tab', { name: '公司映射' }).click();
  await expectRouteContext(page, { path: new RegExp(`^/theme-research/${THEME_ID}/companies$`) });
  await page.getByRole('row', { name: /海能技术 430476\.BJ/ }).click();

  await expectRouteContext(page, {
    path: /^\/tech-bottleneck\/stock\/430476\.BJ$/,
    assetId: '430476.BJ',
    source: 'theme_research'
  });
  await expect(page.getByRole('heading', { name: '海能技术 430476.BJ' })).toBeVisible();
  await expect(page.getByText(/科技卡脖子来源\s+theme_research/)).toBeVisible();

  await page.reload();
  await expectRouteContext(page, {
    path: /^\/tech-bottleneck\/stock\/430476\.BJ$/,
    assetId: '430476.BJ',
    source: 'theme_research'
  });
  await expect(page.getByRole('heading', { name: '海能技术 430476.BJ' })).toBeVisible();
  await expect(page.getByText(/科技卡脖子来源\s+theme_research/)).toBeVisible();

  await page.goBack();
  await expectRouteContext(page, { path: new RegExp(`^/theme-research/${THEME_ID}/companies$`) });
  await expectStateRestored(page, { searchQuery: '', selectedText: '公司映射' });
  await expect(page.getByRole('heading', { name: '公司映射' })).toBeVisible();
});

test('technology-bottleneck review universe hands a row to stock and restores on return @p0 @mock @handoff', async ({ page }) => {
  await page.goto('/research/tech-bottleneck/review-universe');
  await expect(page.getByRole('heading', { name: '科技卡脖子复盘' })).toBeVisible();
  await page.getByRole('row', { name: /300760 迈瑞医疗/ }).click();

  await expectRouteContext(page, {
    path: /^\/tech-bottleneck\/stock\/300760$/,
    assetId: '300760',
    source: 'tech_bottleneck_review_universe_frontend_dataset_v1'
  });
  await expect(page.getByRole('heading', { name: '迈瑞医疗 300760.SZ' })).toBeVisible();
  await expect(page.getByText('techBottleneck', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '科技卡脖子复盘摘要' })).toBeVisible();

  await page.reload();
  await expectRouteContext(page, {
    path: /^\/tech-bottleneck\/stock\/300760$/,
    assetId: '300760',
    source: 'tech_bottleneck_review_universe_frontend_dataset_v1'
  });
  await expect(page.getByRole('heading', { name: '迈瑞医疗 300760.SZ' })).toBeVisible();
  await expect(page.getByText('techBottleneck', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '科技卡脖子复盘摘要' })).toBeVisible();

  await page.goBack();
  await expectRouteContext(page, { path: /^\/research\/tech-bottleneck\/review-universe$/ });
  await expectStateRestored(page, { searchQuery: '' });
  await expect(page.getByRole('row', { name: /300760 迈瑞医疗/ })).toBeVisible();
});

test('research P0 deep links survive direct refresh and legacy review redirects @p0 @mock @handoff', async ({ page }) => {
  await page.goto(`/theme-research/${THEME_ID}/companies`);
  await expectRouteContext(page, { path: new RegExp(`^/theme-research/${THEME_ID}/companies$`) });
  await expectStateRestored(page, { searchQuery: '', selectedText: '公司映射' });
  await expect(page.getByRole('row', { name: /海能技术 430476\.BJ/ })).toBeVisible();
  await page.reload();
  await expectRouteContext(page, { path: new RegExp(`^/theme-research/${THEME_ID}/companies$`) });
  await expectStateRestored(page, { searchQuery: '', selectedText: '公司映射' });

  await page.goto('/research/tech-bottleneck/review-universe');
  await expectRouteContext(page, { path: /^\/research\/tech-bottleneck\/review-universe$/ });
  await expect(page.getByRole('row', { name: /300760 迈瑞医疗/ })).toBeVisible();
  await page.reload();
  await expectRouteContext(page, { path: /^\/research\/tech-bottleneck\/review-universe$/ });
  await expect(page.getByRole('row', { name: /300760 迈瑞医疗/ })).toBeVisible();

  await page.goto('/tech-bottleneck/watchlist-review');
  await expect(page).toHaveURL('/research/tech-bottleneck/review-universe');
  await expectRouteContext(page, { path: /^\/research\/tech-bottleneck\/review-universe$/ });
  await expect(page.getByRole('row', { name: /300760 迈瑞医疗/ })).toBeVisible();
  await page.reload();
  await expectRouteContext(page, { path: /^\/research\/tech-bottleneck\/review-universe$/ });
  await expect(page.getByRole('row', { name: /300760 迈瑞医疗/ })).toBeVisible();
});
