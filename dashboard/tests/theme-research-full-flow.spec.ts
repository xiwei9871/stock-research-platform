import { expect, test, type Page, type Route } from '@playwright/test';

const themeApiBase = 'http://127.0.0.1:8766';

async function proxyThemeApi(page: Page, route: Route) {
  const requestUrl = new URL(route.request().url());
  const response = await page.request.get(`${themeApiBase}${requestUrl.pathname}${requestUrl.search}`);
  await route.fulfill({
    status: response.status(),
    contentType: response.headers()['content-type'] ?? 'application/json',
    body: await response.text()
  });
}

async function prepareDashboard(page: Page) {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      json: {
        user: {
          user_id: 'theme-research-e2e',
          username: 'theme_research_e2e',
          display_name: 'Theme Research E2E',
          role: 'user',
          is_active: true
        }
      }
    });
  });
  await page.route('/api/platform/readiness**', async (route) => {
    await route.fulfill({ json: { display_trade_date: '2026-07-10', latest_market_date: '2026-07-10' } });
  });
  await page.route('/api/platform/summary**', async (route) => {
    await route.fulfill({ json: { latest_market_date: '2026-07-10' } });
  });
  await page.route('/api/research/theme-decomposition/**', (route) => proxyThemeApi(page, route));
}

test('theme research desktop flow preserves routes and deep-research views', async ({ page }) => {
  await prepareDashboard(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/theme-research');

  await expect(page.getByRole('heading', { name: '主题研究' })).toBeVisible();
  await expect(page.getByText(/^\d+ 个主题$/)).toBeVisible();
  await expect(page.getByRole('button', { name: /打开AI供电产业链/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /打开人形机器人：从头到脚的价值链与受益环节/ })).toBeVisible();

  await page.getByRole('button', { name: /打开AI供电产业链/ }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1$/);
  await expect(page.getByRole('heading', { name: 'AI供电产业链：谁在拿走价值量' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '研究结论', exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '受益公司', exact: true })).toBeVisible();

  await page.getByRole('tab', { name: '产业链节点' }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1\/nodes$/);
  await expect(page.locator('.theme-research-status', { hasText: '证据补齐优先' }).first()).toBeVisible();

  await page.getByRole('tab', { name: '来源证据' }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1\/sources$/);
  await expect(page.getByRole('heading', { name: '来源清单' })).toBeVisible();
  await expect(page.getByText('已采纳').first()).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '访问' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '支持来源' })).toBeVisible();

  await page.getByRole('tab', { name: '公司映射' }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1\/companies$/);
  await expect(page.getByText('覆盖缺口').first()).toBeVisible();
  await page.screenshot({ path: 'test-results/theme-research-desktop.png', fullPage: true });

});

test('theme research mobile layout contains wide tables without page overflow', async ({ page }) => {
  await prepareDashboard(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/theme-research/ai_power_value_capture_v1/nodes');

  await expect(page.getByRole('heading', { name: 'AI供电产业链：谁在拿走价值量' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '产业链节点' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('变压器').first()).toBeVisible();
  const pageHasNoHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
  );
  expect(pageHasNoHorizontalOverflow).toBe(true);
  await page.screenshot({ path: 'test-results/theme-research-mobile.png', fullPage: true });
});
