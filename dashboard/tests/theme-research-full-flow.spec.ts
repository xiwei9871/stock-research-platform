import { expect, test, type Page } from '@playwright/test';

declare const process: { env: Record<string, string | undefined> };

const themeApiBase = `http://127.0.0.1:${process.env.PLAYWRIGHT_API_PORT ?? '8766'}`;
const fixtureToken = process.env.PLAYWRIGHT_THEME_REPORT_FIXTURE_TOKEN ?? '';
const fixtureAdmin = { username: 'theme_report_e2e_admin', password: 'theme-report-admin-password' };
const fixtureUser = { username: 'theme_report_e2e_user', password: 'theme-report-user-password' };

async function login(page: Page, credentials: { username: string; password: string }) {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  await page.getByLabel('用户名').fill(credentials.username);
  await page.getByLabel('密码').fill(credentials.password);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText(credentials.username, { exact: true })).toBeVisible({ timeout: 10_000 });
}

async function logout(page: Page) {
  await page.getByRole('button', { name: '退出登录' }).click();
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
}

async function fixtureRequest(page: Page, path: string, method: 'GET' | 'POST' = 'GET') {
  return page.request.fetch(`${themeApiBase}${path}`, {
    method,
    headers: { 'X-Theme-Report-E2E-Token': fixtureToken }
  });
}

async function fixtureStatus(page: Page) {
  const response = await fixtureRequest(page, '/__test__/theme-report-fixture/status');
  expect(response.status()).toBe(200);
  return response.json() as Promise<{ theme_id: string; v1_report_version_id: string }>;
}

async function resetFixture(page: Page) {
  const response = await fixtureRequest(page, '/__test__/theme-report-fixture/reset', 'POST');
  expect(response.status()).toBe(200);
  expect(await response.json()).toMatchObject({
    v1_status: 'pending_review',
    v2_exists: false
  });
}

function captureUnexpectedServerErrors(page: Page) {
  const errors: string[] = [];
  page.on('response', (response) => {
    if (response.status() >= 500 && new URL(response.url()).pathname.startsWith('/api/')) {
      errors.push(`${response.status()} ${new URL(response.url()).pathname}`);
    }
  });
  return () => expect(errors).toEqual([]);
}

test('theme research desktop flow uses the isolated backend without route mocks', async ({ page }) => {
  const expectNoServerErrors = captureUnexpectedServerErrors(page);
  const fixture = await fixtureStatus(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await login(page, fixtureUser);
  await page.goto('/theme-research');

  await expect(page.getByRole('heading', { name: '主题研究' })).toBeVisible();
  await expect(page.getByText(/^\d+ 个主题$/)).toBeVisible();
  await expect(page.getByRole('button', { name: '打开AI供电测试产业链' })).toBeVisible();

  await page.getByRole('button', { name: '打开AI供电测试产业链' }).click();
  await expect(page).toHaveURL(new RegExp(`/theme-research/${fixture.theme_id}$`));
  await expect(page.getByRole('heading', { name: 'AI供电测试产业链' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '待补证据缺口' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '重点公司' })).toBeVisible();

  await page.getByRole('tab', { name: '产业链节点' }).click();
  await expect(page).toHaveURL(new RegExp(`/theme-research/${fixture.theme_id}/nodes$`));
  await expect(page.getByText('变压器').first()).toBeVisible();
  await expect(page.locator('.theme-research-status', { hasText: '证据补齐优先' }).first()).toBeVisible();

  await page.getByRole('tab', { name: '来源证据' }).click();
  await expect(page).toHaveURL(new RegExp(`/theme-research/${fixture.theme_id}/sources$`));
  await expect(page.getByRole('heading', { name: '来源清单' })).toBeVisible();
  await expect(page.getByText('当前主题还没有关联来源。')).toBeVisible();

  await page.getByRole('tab', { name: '公司映射' }).click();
  await expect(page).toHaveURL(new RegExp(`/theme-research/${fixture.theme_id}/companies$`));
  await expect(page.getByText('当前主题还没有公司映射。')).toBeVisible();
  await page.screenshot({ path: 'test-results/theme-research-desktop.png', fullPage: true });
  expectNoServerErrors();
});

test('theme research mobile layout contains wide tables without page overflow', async ({ page }) => {
  const expectNoServerErrors = captureUnexpectedServerErrors(page);
  const fixture = await fixtureStatus(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, fixtureUser);
  await page.goto(`/theme-research/${fixture.theme_id}/nodes`);

  await expect(page.getByRole('heading', { name: 'AI供电测试产业链' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '产业链节点' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByText('变压器').first()).toBeVisible();
  const pageHasNoHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth <= document.documentElement.clientWidth
  );
  expect(pageHasNoHorizontalOverflow).toBe(true);
  await page.screenshot({ path: 'test-results/theme-research-mobile.png', fullPage: true });
  expectNoServerErrors();
});

test('theme report publication keeps pending versions private and approved history immutable', async ({ page }) => {
  test.setTimeout(60_000);
  const expectNoServerErrors = captureUnexpectedServerErrors(page);
  const untrustedFixtureRequest = await page.request.get(`${themeApiBase}/__test__/theme-report-fixture/status`);
  expect(untrustedFixtureRequest.status()).toBe(404);
  await resetFixture(page);
  const fixture = await fixtureStatus(page);
  const fixtureThemeId = fixture.theme_id;

  await login(page, fixtureUser);
    await page.goto('/admin/theme-research/report-review');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText('报告审核')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '主题报告审核' })).toHaveCount(0);
    await page.goto(`/theme-research/${fixtureThemeId}`);
    await expect(page.getByRole('heading', { name: '分析报告' })).toBeVisible();
    await expect(page.getByText('研究中', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '在线阅读' })).toHaveCount(0);
    const pendingRead = await page.evaluate(async ({ themeId, reportVersionId }) => {
      const list = await fetch(`/api/research/theme-decomposition/themes/${themeId}/reports`).then((response) => response.json());
      const direct = await fetch(`/api/research/theme-decomposition/themes/${themeId}/reports/${reportVersionId}`);
      return { total: list.total, directStatus: direct.status };
    }, { themeId: fixtureThemeId, reportVersionId: fixture.v1_report_version_id });
    expect(pendingRead).toEqual({ total: 0, directStatus: 404 });

    await logout(page);
    await login(page, fixtureAdmin);
    await page.goto(`/theme-research/${fixtureThemeId}`);
    await expect(page.getByText('主题已审核', { exact: true })).toBeVisible();
    await expect(page.getByText('待审核', { exact: true })).toBeVisible();
    const enterReviewButton = page.getByRole('button', { name: '进入报告审核' });
    await expect(enterReviewButton).toBeVisible();
    await enterReviewButton.click();
    await expect(page).toHaveURL(/\/admin\/theme-research\/report-review$/);
    await expect(page.getByText('报告审核', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '主题报告审核' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '第一版核心结论' })).toBeVisible();
    await page.getByRole('button', { name: '批准发布' }).click();
    await expect(page.getByText('报告已批准发布')).toBeVisible();

    await logout(page);
    await login(page, fixtureUser);
    await page.goto(`/theme-research/${fixtureThemeId}`);
    await expect(page.getByText(/版本 2026-07-31\.1/)).toBeVisible();
    await page.getByRole('button', { name: '在线阅读' }).click();
    await expect(page.getByRole('article').getByRole('heading', { name: 'AI供电产业链分析报告（第一版）' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '第一版核心结论' })).toBeVisible();
    const pdf = await page.evaluate(async ({ themeId, reportVersionId }) => {
      const response = await fetch(`/api/research/theme-decomposition/themes/${themeId}/reports/${reportVersionId}/pdf`);
      return {
        status: response.status,
        contentType: response.headers.get('content-type'),
        contentDisposition: response.headers.get('content-disposition'),
        prefix: (await response.text()).slice(0, 8)
      };
    }, { themeId: fixtureThemeId, reportVersionId: fixture.v1_report_version_id });
    expect(pdf.status).toBe(200);
    expect(pdf.contentType).toBe('application/pdf');
    expect(pdf.contentDisposition).toMatch(/^attachment; filename="[A-Za-z0-9._-]+\.pdf"$/);
    expect(pdf.prefix).toBe('%PDF-1.4');

    const indexV2Response = await fixtureRequest(page, '/__test__/theme-report-fixture/index-v2', 'POST');
    expect(indexV2Response.status()).toBe(200);
    await page.goto(`/theme-research/${fixtureThemeId}`);
    await expect(page.getByText(/版本 2026-07-31\.1/)).toBeVisible();
    await page.getByRole('button', { name: '在线阅读' }).click();
    await expect(page.getByRole('article').getByRole('heading', { name: 'AI供电产业链分析报告（第一版）' })).toBeVisible();

    await logout(page);
    await login(page, fixtureAdmin);
    await page.goto('/admin/theme-research/report-review');
    await expect(page.getByText('报告审核', { exact: true })).toBeVisible();
    await expect(page.getByRole('article').getByRole('heading', { name: 'AI供电产业链分析报告（第二版）' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '第二版核心结论' })).toBeVisible();
    await page.getByRole('button', { name: '批准发布' }).click();
    await expect(page.getByText('报告已批准发布')).toBeVisible();

    await logout(page);
    await login(page, fixtureUser);
    await page.goto(`/theme-research/${fixtureThemeId}`);
    await expect(page.getByText(/版本 2026-08-01\.1/)).toBeVisible();
    await page.getByRole('button', { name: '在线阅读' }).click();
    await expect(page.getByRole('article').getByRole('heading', { name: 'AI供电产业链分析报告（第二版）' })).toBeVisible();
    const history = page.getByRole('combobox', { name: '报告历史版本' });
    await expect(history.locator('option').nth(0)).toContainText('2026-08-01.1 · 当前发布');
    await expect(history.locator('option').nth(1)).toContainText('2026-07-31.1 · 历史归档');
    expectNoServerErrors();
});
