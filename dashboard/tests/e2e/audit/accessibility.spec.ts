import type { Locator, Page } from '@playwright/test';

import { installMockPlatformApi, type MockPlatformApiRoutes } from '../fixtures/mockPlatformApi';
import { officialStrategies } from '../fixtures/officialStrategies';
import { expect, test } from '../fixtures/test';

const TRADE_DATE = '2026-07-19';
const THEME_ID = 'scientific_instruments_value_chain_v1';

const USER = {
  user_id: 'accessibility-audit-user',
  username: 'accessibility_audit_user',
  display_name: 'Accessibility Audit User',
  role: 'user',
  is_active: true
};

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

function strategyCatalogItem(strategy: (typeof officialStrategies)[keyof typeof officialStrategies]) {
  const names = {
    lhb_shortline: 'LHB Shortline Combo',
    mid_trend: 'Mid Trend Combo',
    tech_bottleneck: 'Tech Bottleneck Combo'
  } as const;
  return {
    strategy_id: strategy.strategyId,
    strategy_name: names[strategy.strategyId],
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

function authenticatedRoutes(): MockPlatformApiRoutes {
  return {
    'GET /api/auth/me': { json: { user: USER } },
    'GET /api/platform/readiness': {
      json: {
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
      }
    },
    'GET /api/platform/summary': {
      json: {
        latest_market_date: TRADE_DATE,
        latest_score_date: TRADE_DATE,
        latest_factor_date: TRADE_DATE,
        market_asset_count: 3,
        score_asset_count: 3,
        factor_count: 3,
        score_versions: ['strategy_topn'],
        topn_preview: []
      }
    },
    'GET /api/backtests/strategies': {
      json: { items: Object.values(officialStrategies).map(strategyCatalogItem) }
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
    'GET /api/search': {
      json: {
        query: '聚光科技',
        groups: [
          {
            key: 'assets',
            label: '股票',
            items: [
              {
                type: 'asset',
                id: '300203.SZ',
                title: '聚光科技',
                subtitle: '300203.SZ',
                metadata: {},
                target: { workspace: 'stock', asset_id: '300203.SZ' },
                match_reason: '股票名称匹配'
              }
            ]
          }
        ],
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
    },
    'GET /api/research-reports/summary': {
      json: {
        total_reports: 1,
        readable_report_count: 1,
        pdf_report_count: 0,
        web_index_report_count: 1,
        covered_stocks: 1,
        latest_publish_date: TRADE_DATE,
        latest_feature_date: TRADE_DATE,
        source_count: 1,
        source_counts: [],
        rating_counts: [],
        broker_counts: []
      }
    },
    'GET /api/research-reports': {
      json: {
        total: 1,
        limit: 50,
        offset: 0,
        warnings: [],
        items: [
          {
            event_key: 'report-event-1',
            report_id: 'report-1',
            asset_id: '300203.SZ',
            ts_code: '300203.SZ',
            stock_name: '聚光科技',
            industry_name: '仪器仪表',
            report_title: '科学仪器国产化跟踪',
            publish_date: TRADE_DATE,
            report_date: TRADE_DATE,
            broker: '审计券商',
            analyst: '审计员',
            rating: '增持',
            rating_change: '维持',
            target_price: 30,
            target_upside: 0.1,
            source_type: 'broker_report',
            source_name: 'deterministic_mock',
            source_confidence: 1,
            public_access: true,
            copyright_note: '测试数据',
            source_url: 'https://example.invalid/report-1',
            raw_summary: '国产科学仪器进入验证期。',
            company_view: '订单结构改善。',
            industry_view: '国产替代继续。',
            risk_summary: '验证节奏不确定。',
            metadata: {}
          }
        ]
      }
    },
    'GET /api/research-reports/report-1/document': {
      json: {
        report_id: 'report-1',
        report_title: '科学仪器国产化跟踪',
        has_pdf: false,
        pdf_url: '',
        source_url: 'https://example.invalid/report-1',
        file_name: '',
        public_access: true,
        copyright_note: '测试数据',
        warnings: []
      }
    }
  };
}

async function expectPageHeadingStructure(page: Page, title: string) {
  await expect(page.getByRole('main')).toHaveCount(1);
  await expect(page.getByRole('heading', { level: 1, name: title })).toHaveCount(1);

  const hierarchy = await page.getByRole('main').evaluate((main) => {
    const headings = Array.from(main.querySelectorAll('h1, h2, h3, h4, h5, h6')).filter((node) => {
      const element = node as HTMLElement;
      const style = window.getComputedStyle(element);
      return style.display !== 'none' && style.visibility !== 'hidden' && element.getClientRects().length > 0;
    });
    return headings.map((heading) => Number(heading.tagName.slice(1)));
  });

  expect(hierarchy[0]).toBe(1);
  for (let index = 1; index < hierarchy.length; index += 1) {
    expect(
      hierarchy[index],
      `heading level jumped from h${hierarchy[index - 1]} to h${hierarchy[index]}`
    ).toBeLessThanOrEqual(hierarchy[index - 1] + 1);
  }
}

async function expectAccessibleName(locator: Locator) {
  await expect(locator).toBeVisible();
  await expect(locator).toHaveAccessibleName(/\S+/);
}

async function expectVisibleKeyboardFocus(locator: Locator) {
  await locator.focus();
  await expect(locator).toBeFocused();
  const focusIndicator = await locator.evaluate((element) => {
    const style = window.getComputedStyle(element);
    const outlineVisible = style.outlineStyle !== 'none' && style.outlineWidth !== '0px';
    const shadowVisible = style.boxShadow !== 'none';
    return { outlineVisible, shadowVisible };
  });
  expect(focusIndicator.outlineVisible || focusIndicator.shadowVisible).toBe(true);
}

test('login has one main, one page title, named controls, and visible keyboard focus @audit @webkit-critical', async ({
  page,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(
    /^Failed to load resource: the server responded with a status of 401 \(Unauthorized\)$/
  );
  await installMockPlatformApi(page, {
    'GET /api/auth/me': { status: 401, json: { detail: 'not_authenticated' } }
  });
  await page.goto('/');

  await expectPageHeadingStructure(page, '登录');
  await expectAccessibleName(page.getByRole('textbox', { name: '用户名' }));
  await expectAccessibleName(page.getByLabel('密码'));
  await expectAccessibleName(page.getByRole('button', { name: '登录' }));

  await page.keyboard.press('Tab');
  await expect(page.getByRole('textbox', { name: '用户名' })).toBeFocused();
  await expectVisibleKeyboardFocus(page.getByRole('textbox', { name: '用户名' }));
});

test('representative workspaces keep one main and a non-skipping page heading hierarchy @audit', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  const pages = [
    { path: '/', title: '策略指挥中心' },
    { path: `/theme-research/${THEME_ID}`, title: '科学仪器价值链' },
    { path: '/research/tech-bottleneck/review-universe', title: '科技卡脖子复盘' }
  ];

  for (const representative of pages) {
    await page.goto(representative.path);
    await expectPageHeadingStructure(page, representative.title);
  }
});

test('workspace navigation and primary controls expose accessible names and keyboard focus @audit', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto('/');

  const navigation = page.getByRole('navigation', { name: 'Workspace navigation' });
  await expect(navigation).toBeVisible();
  const navigationButtons = navigation.getByRole('button');
  expect(await navigationButtons.count()).toBeGreaterThan(5);
  for (let index = 0; index < (await navigationButtons.count()); index += 1) {
    await expectAccessibleName(navigationButtons.nth(index));
  }

  await expectAccessibleName(page.getByRole('combobox', { name: 'Global search' }));
  await expectAccessibleName(page.getByRole('button', { name: '退出登录' }));
  await expectAccessibleName(page.getByRole('button', { name: '打开策略实验室' }));
  await expectVisibleKeyboardFocus(navigationButtons.first());
  await expectVisibleKeyboardFocus(page.getByRole('combobox', { name: 'Global search' }));
});

test('global search results support Escape, Tab, and Shift+Tab without trapping focus @audit', async ({ page }) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto('/');

  const search = page.getByRole('combobox', { name: 'Global search' });
  await search.fill('聚光科技');
  await expect(page.getByRole('option', { name: /聚光科技/ })).toBeVisible();
  await search.press('Escape');
  await expect(search).toHaveAttribute('aria-expanded', 'false');
  await expect(search).toBeFocused();

  await search.fill('');
  await search.fill('聚光科技');
  await expect(page.getByRole('option', { name: /聚光科技/ })).toBeVisible();
  await search.press('Tab');
  await expect(page.getByRole('button', { name: '退出登录' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(search).toBeFocused();
});

test('full-screen report reader does not trap forward, backward, or Escape keyboard movement @audit', async ({
  page
}) => {
  await installMockPlatformApi(page, authenticatedRoutes());
  await page.goto('/research-reports');
  await page.getByRole('button', { name: 'Open report 科学仪器国产化跟踪' }).click();

  const reader = page.getByRole('region', { name: 'Research report full-screen reader' });
  await expect(reader).toBeVisible();
  const back = reader.getByRole('button', { name: '返回研报列表' });
  await back.focus();
  await page.keyboard.press('Shift+Tab');
  await expect
    .poll(() => page.evaluate(() => document.activeElement?.closest('[aria-label="Research report full-screen reader"]') === null))
    .toBe(true);

  const source = reader.getByRole('link', { name: '来源链接' });
  await source.focus();
  const forwardTabResult = page.evaluate(
    () =>
      new Promise<{ defaultPrevented: boolean }>((resolve) => {
        document.addEventListener(
          'keydown',
          (event) => {
            window.setTimeout(() => resolve({ defaultPrevented: event.defaultPrevented }), 0);
          },
          { once: true }
        );
      })
  );
  await page.keyboard.press('Tab');
  expect(await forwardTabResult).toEqual({ defaultPrevented: false });

  await back.focus();
  await page.keyboard.press('Escape');
  await page.keyboard.press('Tab');
  await expect(back).not.toBeFocused();
});
