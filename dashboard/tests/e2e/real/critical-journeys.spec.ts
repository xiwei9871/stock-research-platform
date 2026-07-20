import type { APIRequestContext, Page } from '@playwright/test';

import {
  expectPublicationConsistency,
  expectRouteContext,
  expectStateRestored
} from '../assertions/consistency';
import { loadAuthoritativeSnapshot } from './authoritativeSnapshot';
import { expect, test } from './test';

type JsonObject = Record<string, unknown>;

type SearchChoice = {
  assetId: string;
  query: string;
  title: string;
};

type ThemeCompanyChoice = {
  assetId: string;
  companyCode: string;
  companyName: string;
  stockPath: string;
  themeId: string;
};

type TechReviewChoice = {
  stockCode: string;
  stockName: string;
};

type ReviewQueueChoice = {
  groupCount: number;
  groupLabel: string;
  itemLabel: string;
  tradeDate: string;
};

function objectValue(value: unknown, code: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(code);
  }
  return value as JsonObject;
}

function arrayValue(value: unknown, code: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(code);
  return value;
}

function nonEmptyString(value: unknown, code: string): string {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(code);
  return value.trim();
}

async function apiJson(
  request: APIRequestContext,
  path: string,
  requestId: string
): Promise<unknown> {
  const response = await request.get(path, { headers: { 'x-request-id': requestId } });
  if (!response.ok()) {
    throw new Error(`real_critical_api_error:${path}:${response.status()}`);
  }
  return response.json() as Promise<unknown>;
}

async function loadTechReviewChoice(request: APIRequestContext): Promise<TechReviewChoice> {
  const payload = objectValue(
    await apiJson(
      request,
      '/api/research/tech-bottleneck/review-universe/stocks?limit=500',
      'playwright-real-critical-tech-stock'
    ),
    'real_critical_invalid_tech_stocks_payload'
  );
  const first = objectValue(
    arrayValue(payload.items, 'real_critical_invalid_tech_stocks_items')[0],
    'real_critical_tech_stock_missing'
  );
  return {
    stockCode: nonEmptyString(first.stock_code, 'real_critical_tech_stock_code_missing'),
    stockName: nonEmptyString(first.stock_name, 'real_critical_tech_stock_name_missing')
  };
}

async function loadThemeCompanyChoice(request: APIRequestContext): Promise<ThemeCompanyChoice> {
  const themesPayload = objectValue(
    await apiJson(
      request,
      '/api/research/theme-decomposition/themes',
      'playwright-real-critical-theme-list'
    ),
    'real_critical_invalid_theme_list_payload'
  );
  const themes = arrayValue(themesPayload.items, 'real_critical_invalid_theme_list_items');

  for (const rawTheme of themes) {
    const theme = objectValue(rawTheme, 'real_critical_invalid_theme');
    const themeId = nonEmptyString(theme.theme_id, 'real_critical_theme_id_missing');
    const companiesPayload = objectValue(
      await apiJson(
        request,
        `/api/research/theme-decomposition/themes/${encodeURIComponent(themeId)}/companies`,
        `playwright-real-critical-theme-companies-${themeId}`
      ),
      `real_critical_invalid_theme_companies_payload:${themeId}`
    );
    const companies = arrayValue(
      companiesPayload.items,
      `real_critical_invalid_theme_companies_items:${themeId}`
    );
    for (const rawCompany of companies) {
      const company = objectValue(rawCompany, `real_critical_invalid_theme_company:${themeId}`);
      if (
        typeof company.company_code !== 'string' ||
        typeof company.company_name !== 'string' ||
        typeof company.tech_bottleneck_stock_path !== 'string'
      ) {
        continue;
      }
      const stockUrl = new URL(company.tech_bottleneck_stock_path, 'http://playwright.local');
      const assetId = stockUrl.pathname.match(/\/stock\/([^/]+)$/)?.[1];
      if (!assetId) continue;
      return {
        assetId: decodeURIComponent(assetId),
        companyCode: company.company_code,
        companyName: company.company_name,
        stockPath: `${stockUrl.pathname}${stockUrl.search}`,
        themeId
      };
    }
  }

  throw new Error('real_critical_theme_company_missing');
}

async function loadSearchChoice(request: APIRequestContext): Promise<SearchChoice> {
  const candidates: Array<{ query: string }> = [];
  try {
    const tech = await loadTechReviewChoice(request);
    candidates.push({ query: tech.stockName }, { query: tech.stockCode });
  } catch {
    // Theme data remains a second authoritative source when the review universe is unavailable.
  }
  try {
    const theme = await loadThemeCompanyChoice(request);
    candidates.push({ query: theme.companyName }, { query: theme.companyCode });
  } catch {
    // The final error below reports that no real search-backed stock could be selected.
  }

  for (const [candidateIndex, candidate] of candidates.entries()) {
    if (candidate.query.trim().length < 2) continue;
    const payload = objectValue(
      await apiJson(
        request,
        `/api/search?q=${encodeURIComponent(candidate.query)}&limit=5`,
        `playwright-real-critical-search-${candidateIndex}`
      ),
      'real_critical_invalid_search_payload'
    );
    const groups = arrayValue(payload.groups, 'real_critical_invalid_search_groups');
    for (const rawGroup of groups) {
      const group = objectValue(rawGroup, 'real_critical_invalid_search_group');
      const items = arrayValue(group.items, 'real_critical_invalid_search_items');
      for (const rawItem of items) {
        const item = objectValue(rawItem, 'real_critical_invalid_search_item');
        const target = objectValue(item.target, 'real_critical_search_target_missing');
        if (target.workspace !== 'stock' || typeof target.asset_id !== 'string') continue;
        return {
          assetId: nonEmptyString(target.asset_id, 'real_critical_search_asset_id_missing'),
          query: candidate.query,
          title: nonEmptyString(item.title, 'real_critical_search_title_missing')
        };
      }
    }
  }

  throw new Error('real_critical_search_stock_missing');
}

async function loadReviewQueueChoice(request: APIRequestContext): Promise<ReviewQueueChoice> {
  const payload = objectValue(
    await apiJson(
      request,
      '/api/review-queue?limit=10&lookback_days=90',
      'playwright-real-critical-review-queue'
    ),
    'real_critical_invalid_review_queue_payload'
  );
  const tradeDate = nonEmptyString(payload.trade_date, 'real_critical_review_trade_date_missing');
  const groups = arrayValue(payload.groups, 'real_critical_invalid_review_groups');
  for (const rawGroup of groups) {
    const group = objectValue(rawGroup, 'real_critical_invalid_review_group');
    const items = arrayValue(group.items, 'real_critical_invalid_review_items');
    if (items.length === 0) continue;
    const firstItem = objectValue(items[0], 'real_critical_invalid_review_item');
    const groupCount = group.count;
    if (typeof groupCount !== 'number' || !Number.isFinite(groupCount)) {
      throw new Error('real_critical_review_group_count_missing');
    }
    return {
      groupCount,
      groupLabel: nonEmptyString(group.label, 'real_critical_review_group_label_missing'),
      itemLabel: nonEmptyString(firstItem.display_name, 'real_critical_review_item_label_missing'),
      tradeDate
    };
  }
  throw new Error('real_critical_review_queue_empty');
}

async function expectStockWorkspace(page: Page, assetId: string, source: string): Promise<void> {
  await expectRouteContext(page, {
    path: new RegExp(`/stock/${assetId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}$`),
    assetId,
    source
  });
  await expect(page.getByRole('region', { name: '个股复盘工作台' })).toBeVisible();
}

async function openReadOnlyApiHarness(page: Page): Promise<void> {
  const path = '/__playwright_real_critical_api_harness__';
  await page.route(path, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body>real critical API harness</body></html>'
    });
  });
  await page.goto(path);
}

test('authoritative publication snapshot is complete before any product journey @real @critical', async ({
  page
}) => {
  await openReadOnlyApiHarness(page);
  const snapshot = await loadAuthoritativeSnapshot(page);

  expect(snapshot.strategies.map((strategy) => strategy.strategyId)).toEqual([
    'lhb_shortline',
    'mid_trend',
    'tech_bottleneck'
  ]);
});

test('auth-disabled Real profile can enter the authenticated application shell @real @critical', async ({
  request
}, testInfo) => {
  const [authResponse, summaryResponse] = await Promise.all([
    request.get('/api/auth/me', {
      headers: { 'x-request-id': 'playwright-real-critical-auth-prerequisite' }
    }),
    request.get('/api/platform/summary', {
      headers: { 'x-request-id': 'playwright-real-critical-summary-prerequisite' }
    })
  ]);
  const evidence = {
    authMeStatus: authResponse.status(),
    authRequiredEnvironment: false,
    platformSummaryStatus: summaryResponse.status()
  };
  await testInfo.attach('real-auth-prerequisite.json', {
    body: `${JSON.stringify(evidence, null, 2)}\n`,
    contentType: 'application/json'
  });

  expect(summaryResponse.ok()).toBe(true);
  expect(
    authResponse.status(),
    'AUTH_REQUIRED=false permits platform reads but /api/auth/me still blocks DashboardAuthRoot'
  ).toBe(200);
});

test('home official strategy cards match the authoritative publication snapshot @real @critical', async ({
  page
}) => {
  await openReadOnlyApiHarness(page);
  const snapshot = await loadAuthoritativeSnapshot(page);

  await page.goto('/');
  await expect(page.getByRole('region', { name: '策略指挥中心' })).toBeVisible();
  for (const strategyId of ['lhb_shortline', 'mid_trend', 'tech_bottleneck']) {
    await expect(page.locator(`article[data-strategy-id="${strategyId}"]`)).toBeVisible();
  }

  for (const publication of snapshot.strategies) {
    await expectPublicationConsistency(
      page.locator(`article[data-strategy-id="${publication.strategyId}"]`),
      {
        contractId: publication.contractId,
        publishId: publication.publishId,
        tradeDate: publication.tradeDate,
        totalReturnPct: publication.totalReturnPct
      }
    );
  }
  await expect(page.getByText('+175.29%', { exact: true })).toHaveCount(0);
});

test('review queue renders a current real strategy group and item @real @critical', async ({
  page,
  request
}) => {
  const choice = await loadReviewQueueChoice(request);
  await page.goto('/review-queue');

  await expect(page.getByRole('region', { name: '策略复盘队列' })).toBeVisible();
  await expect(page.getByText(choice.tradeDate, { exact: true }).first()).toBeVisible();
  await expect(
    page.getByRole('button', { name: `${choice.groupLabel} ${choice.groupCount}` })
  ).toBeVisible();
  await expect(page.getByText(choice.itemLabel, { exact: true }).first()).toBeVisible();
});

test('global search opens a dynamically selected stock and restores Back and Forward state @real @critical', async ({
  page,
  request
}) => {
  const choice = await loadSearchChoice(request);
  await page.goto('/');

  const search = page.getByRole('combobox', { name: 'Global search' });
  await search.fill(choice.query);
  await page.getByRole('option').filter({ hasText: choice.title }).first().click();

  await expectStockWorkspace(page, choice.assetId, 'search');
  await page.goBack();
  await expectRouteContext(page, { path: /^\/$/ });
  await expectStateRestored(page, { searchQuery: choice.query });

  await page.goForward();
  await expectStockWorkspace(page, choice.assetId, 'search');
  await expectStateRestored(page, { searchQuery: '' });
});

test('theme-research company handoff returns to its dynamically selected company list @real @critical', async ({
  page,
  request
}) => {
  const choice = await loadThemeCompanyChoice(request);
  await page.goto(`/theme-research/${encodeURIComponent(choice.themeId)}/companies`);

  const companyRow = page
    .getByRole('row')
    .filter({ hasText: choice.companyName })
    .filter({ hasText: choice.companyCode })
    .first();
  await expect(companyRow).toBeVisible();
  await companyRow.click();
  await expect(page).toHaveURL(choice.stockPath);
  await expectStockWorkspace(page, choice.assetId, 'theme_research');

  await page.goBack();
  await expectRouteContext(page, {
    path: new RegExp(`^/theme-research/${choice.themeId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}/companies$`)
  });
  await expectStateRestored(page, { selectedText: '公司映射' });
  await expect(companyRow).toBeVisible();
});

test('technology-bottleneck review row returns to the real review universe @real @critical', async ({
  page,
  request
}) => {
  const choice = await loadTechReviewChoice(request);
  await page.goto('/research/tech-bottleneck/review-universe');

  const reviewRow = page
    .getByRole('row')
    .filter({ hasText: choice.stockCode })
    .filter({ hasText: choice.stockName })
    .first();
  await expect(reviewRow).toBeVisible();
  await reviewRow.click();
  await expectStockWorkspace(
    page,
    choice.stockCode,
    'tech_bottleneck_review_universe_frontend_dataset_v1'
  );

  await page.goBack();
  await expectRouteContext(page, { path: /^\/research\/tech-bottleneck\/review-universe$/ });
  await expect(page.getByRole('region', { name: '科技卡脖子复盘工作台' })).toBeVisible();
  await expect(reviewRow).toBeVisible();
});

test('a dynamically selected stock deep link survives direct refresh @real @critical', async ({
  page,
  request
}) => {
  const choice = await loadSearchChoice(request);
  await page.goto(`/stock/${encodeURIComponent(choice.assetId)}?source=search`);
  await expectStockWorkspace(page, choice.assetId, 'search');

  await page.reload();
  await expectStockWorkspace(page, choice.assetId, 'search');
});
