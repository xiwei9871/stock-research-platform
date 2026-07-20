import type { Page } from '@playwright/test';

import { expectRouteContext, expectStateRestored } from '../assertions/consistency';
import { installMockPlatformApi, type MockPlatformApiRoutes } from '../fixtures/mockPlatformApi';
import { expect, test } from '../fixtures/test';

const TRADE_DATE = '2026-07-17';

const USER = {
  user_id: 'handoff-user',
  username: 'handoff_user',
  display_name: 'Handoff User',
  role: 'user',
  is_active: true
};

function assetProfile(requestedAssetId: string, canonicalAssetId = requestedAssetId) {
  const isHaineng = canonicalAssetId === '430476.BJ' || canonicalAssetId === '920476.BJ';
  const symbol = canonicalAssetId.split('.')[0];
  return {
    asset_id: requestedAssetId,
    canonical_asset_id: canonicalAssetId,
    asset: {
      asset_id: canonicalAssetId,
      symbol,
      name: isHaineng ? '海能技术' : '聚光科技',
      exchange: canonicalAssetId.split('.')[1],
      board: isHaineng ? 'bse' : 'chinext',
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

function stockReadRoutes(requestedAssetId: string, canonicalAssetId = requestedAssetId): MockPlatformApiRoutes {
  return {
    [`GET /api/assets/${requestedAssetId}/profile`]: { json: assetProfile(requestedAssetId, canonicalAssetId) },
    [`GET /api/assets/${canonicalAssetId}/bars`]: { json: { items: [] } },
    [`GET /api/assets/${canonicalAssetId}/news`]: {
      json: {
        asset_id: canonicalAssetId,
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
    [`GET /api/assets/${canonicalAssetId}/research-reports`]: {
      json: {
        asset_id: canonicalAssetId,
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
    [`GET /api/stocks/${canonicalAssetId}/market-context/heatmap`]: {
      json: {
        asset_id: canonicalAssetId,
        trade_date: TRADE_DATE,
        data_status: 'missing',
        selected: null,
        peers: [],
        warnings: []
      }
    }
  };
}

function emptyHomeRoutes(): MockPlatformApiRoutes {
  return {
    'GET /api/backtests/strategies': { json: { items: [] } },
    'GET /api/market-monitor/eod': {
      json: {
        trade_date: TRADE_DATE,
        freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
        coverage: { market_assets: 0, score_assets: 0, factor_count: 0 },
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
        cases: [],
        warnings: []
      }
    },
    'GET /api/research/publication/snapshots': { json: { items: [] } }
  };
}

async function installSearchStockApi(page: Page) {
  await installMockPlatformApi(page, {
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
        market_asset_count: 0,
        score_asset_count: 0,
        factor_count: 0,
        score_versions: [],
        topn_preview: []
      }
    },
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
    ...emptyHomeRoutes(),
    ...stockReadRoutes('300203.SZ'),
    ...stockReadRoutes('920476.BJ'),
    ...stockReadRoutes('430476.BJ')
  });
}

async function expectStockIdentity(page: Page, heading: string, sourceLabel: string) {
  await expect(page.getByRole('heading', { name: heading })).toBeVisible();
  await expect(page.getByText(new RegExp(`来源工作台：\\s*${sourceLabel}`))).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await installSearchStockApi(page);
});

test('global search restores its query across stock Back and Forward @p0 @mock @handoff', async ({ page }) => {
  await page.goto('/');

  const search = page.getByRole('combobox', { name: 'Global search' });
  await search.fill('聚光科技');
  await page.getByRole('option', { name: /聚光科技/ }).click();

  await expectRouteContext(page, {
    path: /^\/stock\/300203\.SZ$/,
    assetId: '300203.SZ',
    source: 'search'
  });
  await expectStockIdentity(page, '聚光科技 300203.SZ', 'Search');

  await page.reload();
  await expectRouteContext(page, {
    path: /^\/stock\/300203\.SZ$/,
    assetId: '300203.SZ',
    source: 'search'
  });
  await expectStockIdentity(page, '聚光科技 300203.SZ', 'Search');

  await page.goBack();
  await expectRouteContext(page, { path: /^\/$/ });
  await expectStateRestored(page, { searchQuery: '聚光科技' });

  await page.goForward();
  await expectRouteContext(page, {
    path: /^\/stock\/300203\.SZ$/,
    assetId: '300203.SZ',
    source: 'search'
  });
  await expectStateRestored(page, { searchQuery: '' });
  await expectStockIdentity(page, '聚光科技 300203.SZ', 'Search');
});

test('current and legacy Haineng security-code deep links resolve the same company @p0 @mock @handoff', async ({ page }) => {
  const deepLinks = [
    {
      path: '/stock/920476.BJ?source=theme_research',
      route: /^\/stock\/920476\.BJ$/,
      assetId: '920476.BJ',
      heading: '海能技术 920476.BJ',
      legacyTechSourceToken: false
    },
    {
      path: '/stock/430476.BJ?source=theme_research',
      route: /^\/stock\/430476\.BJ$/,
      assetId: '430476.BJ',
      heading: '海能技术 430476.BJ',
      legacyTechSourceToken: false
    },
    {
      path: '/tech-bottleneck/stock/430476.BJ?source=theme_research',
      route: /^\/tech-bottleneck\/stock\/430476\.BJ$/,
      assetId: '430476.BJ',
      heading: '海能技术 430476.BJ',
      legacyTechSourceToken: true
    }
  ];

  for (const deepLink of deepLinks) {
    await page.goto(deepLink.path);
    await expectRouteContext(page, {
      path: deepLink.route,
      assetId: deepLink.assetId,
      source: 'theme_research'
    });
    await expect(page.getByRole('heading', { name: deepLink.heading })).toBeVisible();
    if (deepLink.legacyTechSourceToken) {
      await expect(page.getByText(/科技卡脖子来源\s+theme_research/)).toBeVisible();
    } else {
      await expect(page.getByText(/来源工作台：\s*Theme Research/)).toBeVisible();
    }
    await expect(page.getByText('No bars available.')).toBeVisible();

    await page.reload();
    await expectRouteContext(page, {
      path: deepLink.route,
      assetId: deepLink.assetId,
      source: 'theme_research'
    });
    await expect(page.getByRole('heading', { name: deepLink.heading })).toBeVisible();
    if (deepLink.legacyTechSourceToken) {
      await expect(page.getByText(/科技卡脖子来源\s+theme_research/)).toBeVisible();
    } else {
      await expect(page.getByText(/来源工作台：\s*Theme Research/)).toBeVisible();
    }
    await expect(page.getByText('No bars available.')).toBeVisible();
  }
});
