import { expect, test, type Page, type Route } from '@playwright/test';

const themeApiBase = 'http://127.0.0.1:8766';
const reportThemeId = 'ai_power_value_capture_v1';
const csrfToken = 'theme-report-e2e-csrf';

type FixtureRole = 'user' | 'admin';
type FixtureReportStatus = 'pending_review' | 'published' | 'archived';
type FixtureReport = {
  report_version_id: string;
  theme_id: string;
  version: string;
  title: string;
  summary: string;
  status: FixtureReportStatus;
  generated_at: string;
  indexed_at: string;
  published_at: string | null;
  published_by_user_id: string | null;
  rejected_at: string | null;
  rejected_by_user_id: string | null;
  rejection_reason: string | null;
  row_version: number;
  metadata: Record<string, never>;
  created_at: string;
  updated_at: string;
  html: string;
  has_pdf: boolean;
};

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

function makeFixtureReport(version: 'v1' | 'v2'): FixtureReport {
  const isV2 = version === 'v2';
  const generatedAt = isV2 ? '2026-08-01T11:00:00+08:00' : '2026-07-31T11:00:00+08:00';
  return {
    report_version_id: `theme-report-${version}`,
    theme_id: reportThemeId,
    version: isV2 ? '2026-08-01.1' : '2026-07-31.1',
    title: isV2 ? 'AI供电产业链分析报告（第二版）' : 'AI供电产业链分析报告（第一版）',
    summary: isV2 ? '第二版补充液冷与电网侧证据。' : '第一版覆盖电源、液冷与价值量。',
    status: 'pending_review',
    generated_at: generatedAt,
    indexed_at: generatedAt,
    published_at: null,
    published_by_user_id: null,
    rejected_at: null,
    rejected_by_user_id: null,
    rejection_reason: null,
    row_version: 1,
    metadata: {},
    created_at: generatedAt,
    updated_at: generatedAt,
    html: isV2
      ? '<h2>第二版核心结论</h2><p>液冷与电网侧证据已经补强。</p>'
      : '<h2>第一版核心结论</h2><p>服务器电源价值量持续提升。</p>',
    has_pdf: true
  };
}

function publicReport(report: FixtureReport) {
  const { html: _html, has_pdf: _hasPdf, rejected_at: _rejectedAt, rejected_by_user_id: _rejectedBy, rejection_reason: _reason, ...safe } = report;
  return safe;
}

function adminReport(report: FixtureReport) {
  const { html: _html, has_pdf: _hasPdf, ...record } = report;
  return record;
}

async function createReportPublicationFixture(page: Page) {
  // Playwright currently starts the shared local API without an isolated report root/DB hook.
  // Keep publication state inside this per-page boundary; real PostgreSQL behavior is covered
  // by the dedicated integration suite and no production artifact or credential is used here.
  let role: FixtureRole = 'user';
  const reports = new Map<string, FixtureReport>([['theme-report-v1', makeFixtureReport('v1')]]);
  await page.context().addCookies([
    { name: 'stock_research_csrf', value: csrfToken, domain: '127.0.0.1', path: '/' }
  ]);

  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      json: {
        user: {
          user_id: `${role}-theme-report-e2e`,
          username: role === 'admin' ? 'admin' : 'theme_report_reader',
          display_name: role === 'admin' ? 'Theme Report Admin' : 'Theme Report Reader',
          role,
          is_active: true
        }
      }
    });
  });
  await page.route('/api/platform/readiness**', async (route) => {
    await route.fulfill({ json: { display_trade_date: '2026-08-01', latest_market_date: '2026-08-01' } });
  });
  await page.route('/api/platform/summary**', async (route) => {
    await route.fulfill({ json: { latest_market_date: '2026-08-01' } });
  });

  await page.route('/api/research/theme-decomposition/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const reportsBase = `/api/research/theme-decomposition/themes/${reportThemeId}/reports`;

    if (path === reportsBase) {
      const items = [...reports.values()]
        .filter((report) => report.status === 'published' || report.status === 'archived')
        .sort((left, right) => right.published_at!.localeCompare(left.published_at!))
        .map(publicReport);
      await route.fulfill({ json: { total: items.length, items } });
      return;
    }

    const reportMatch = path.match(new RegExp(`^${reportsBase}/([^/]+)(/pdf)?$`));
    if (reportMatch) {
      const report = reports.get(decodeURIComponent(reportMatch[1]));
      if (!report || (report.status !== 'published' && report.status !== 'archived')) {
        await route.fulfill({ status: 404, json: { detail: 'report_not_found' } });
        return;
      }
      if (reportMatch[2] === '/pdf') {
        await route.fulfill({
          status: 200,
          contentType: 'application/pdf',
          headers: { 'Content-Disposition': `attachment; filename="${report.report_version_id}.pdf"` },
          body: `%PDF-1.4\nfixture-${report.report_version_id}`
        });
        return;
      }
      await route.fulfill({
        json: {
          ...publicReport(report),
          has_pdf: report.has_pdf,
          html: report.html
        }
      });
      return;
    }

    const upstream = await page.request.get(`${themeApiBase}${path}${url.search}`);
    if (!upstream.ok()) {
      await route.fulfill({
        status: upstream.status(),
        contentType: upstream.headers()['content-type'] ?? 'application/json',
        body: await upstream.body()
      });
      return;
    }
    const payload = await upstream.json();
    const current = [...reports.values()].find((report) => report.status === 'published');
    const summary = current
      ? {
          status: 'published',
          report_version_id: current.report_version_id,
          version: current.version,
          published_at: current.published_at,
          has_pdf: current.has_pdf
        }
      : { status: 'researching' };
    if (path === '/api/research/theme-decomposition/themes') {
      payload.items = payload.items.map((item: { theme_id: string }) =>
        item.theme_id === reportThemeId ? { ...item, analysis_report: summary } : item
      );
    } else if (path === `/api/research/theme-decomposition/themes/${reportThemeId}`) {
      payload.theme = { ...payload.theme, analysis_report: summary };
    }
    await route.fulfill({ json: payload });
  });

  await page.route('/api/admin/theme-research/reports**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (role !== 'admin') {
      await route.fulfill({ status: 403, json: { detail: 'admin_required' } });
      return;
    }
    if (path === '/api/admin/theme-research/reports' && request.method() === 'GET') {
      const requestedStatus = url.searchParams.get('status');
      const items = [...reports.values()]
        .filter((report) => !requestedStatus || report.status === requestedStatus)
        .sort((left, right) => right.generated_at.localeCompare(left.generated_at))
        .map(adminReport);
      await route.fulfill({ json: { total: items.length, items } });
      return;
    }
    const match = path.match(/^\/api\/admin\/theme-research\/reports\/([^/]+)(?:\/(publish|pdf))?$/);
    const report = match ? reports.get(decodeURIComponent(match[1])) : undefined;
    if (!match || !report) {
      await route.fulfill({ status: 404, json: { detail: 'report_not_found' } });
      return;
    }
    if (match[2] === 'pdf') {
      await route.fulfill({ status: 200, contentType: 'application/pdf', body: '%PDF-1.4\nadmin-preview' });
      return;
    }
    if (match[2] === 'publish' && request.method() === 'POST') {
      const body = request.postDataJSON() as { expected_row_version?: number; idempotency_key?: string };
      if (request.headers()['x-csrf-token'] !== csrfToken) {
        await route.fulfill({ status: 403, json: { detail: 'csrf_invalid' } });
        return;
      }
      if (body.expected_row_version !== report.row_version || !body.idempotency_key) {
        await route.fulfill({ status: 409, json: { detail: 'report_version_conflict' } });
        return;
      }
      const publishedAt = report.report_version_id === 'theme-report-v2'
        ? '2026-08-01T12:00:00+08:00'
        : '2026-07-31T12:00:00+08:00';
      for (const candidate of reports.values()) {
        if (candidate.status === 'published') {
          candidate.status = 'archived';
          candidate.row_version += 1;
          candidate.updated_at = publishedAt;
        }
      }
      report.status = 'published';
      report.published_at = publishedAt;
      report.published_by_user_id = 'admin-theme-report-e2e';
      report.row_version += 1;
      report.updated_at = publishedAt;
      await route.fulfill({ json: { report: adminReport(report) } });
      return;
    }
    await route.fulfill({
      json: {
        ...adminReport(report),
        has_pdf: report.has_pdf,
        html: report.html,
        generator_name: 'theme-research-report-pipeline',
        generator_version: '1.0.0'
      }
    });
  });

  return {
    async loginAs(nextRole: FixtureRole) {
      role = nextRole;
      await page.goto('/');
      await expect(
        page.getByText(nextRole === 'admin' ? 'admin' : 'theme_report_reader', { exact: true })
      ).toBeVisible();
    },
    indexSecondVersion() {
      reports.set('theme-report-v2', makeFixtureReport('v2'));
    },
    snapshot() {
      return [...reports.values()].map((report) => ({
        id: report.report_version_id,
        status: report.status,
        rowVersion: report.row_version
      }));
    },
    cleanup() {
      reports.clear();
    }
  };
}

test('theme research desktop flow preserves routes and stock handoff', async ({ page }) => {
  await prepareDashboard(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/theme-research');

  await expect(page.getByRole('heading', { name: '主题研究' })).toBeVisible();
  await expect(page.getByText('2 个主题')).toBeVisible();
  await expect(page.getByRole('button', { name: /打开AI供电产业链/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /打开人形机器人从头到脚拆解/ })).toBeVisible();

  await page.getByRole('button', { name: /打开AI供电产业链/ }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1$/);
  await expect(page.getByRole('heading', { name: 'AI供电产业链：谁在拿走价值量' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '待补证据缺口' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '重点公司' })).toBeVisible();

  await page.getByRole('tab', { name: '产业链节点' }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1\/nodes$/);
  await expect(page.locator('.theme-research-status', { hasText: '证据补齐优先' }).first()).toBeVisible();

  await page.getByRole('tab', { name: '来源证据' }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1\/sources$/);
  await expect(page.getByRole('heading', { name: '来源清单' })).toBeVisible();
  await expect(page.getByText('仅作线索').first()).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '访问' })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: '支持来源' })).toBeVisible();

  await page.getByRole('tab', { name: '公司映射' }).click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1\/companies$/);
  await expect(page.getByText('覆盖缺口').first()).toBeVisible();
  await page.screenshot({ path: 'test-results/theme-research-desktop.png', fullPage: true });

  await page.getByRole('button', { name: '打开欧陆通个股工作台' }).click();
  await expect(page).toHaveURL(/\/tech-bottleneck\/stock\/300870\.SZ\?source=theme_research$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1\/companies$/);
  await expect(page.getByRole('heading', { name: '公司映射' })).toBeVisible();
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

test('theme report publication keeps pending versions private and approved history immutable', async ({ page }) => {
  test.setTimeout(60_000);
  const fixture = await createReportPublicationFixture(page);
  try {
    await fixture.loginAs('user');
    await page.goto('/admin/theme-research/report-review');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByText('报告审核')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: '主题报告审核' })).toHaveCount(0);
    await page.goto(`/theme-research/${reportThemeId}`);
    await expect(page.getByRole('heading', { name: '分析报告' })).toBeVisible();
    await expect(page.getByText('研究中', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '在线阅读' })).toHaveCount(0);
    const pendingRead = await page.evaluate(async (themeId) => {
      const list = await fetch(`/api/research/theme-decomposition/themes/${themeId}/reports`).then((response) => response.json());
      const direct = await fetch(`/api/research/theme-decomposition/themes/${themeId}/reports/theme-report-v1`);
      return { total: list.total, directStatus: direct.status };
    }, reportThemeId);
    expect(pendingRead).toEqual({ total: 0, directStatus: 404 });

    await fixture.loginAs('admin');
    await page.goto('/admin/theme-research/report-review');
    await expect(page).toHaveURL(/\/admin\/theme-research\/report-review$/);
    await expect(page.getByText('报告审核', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '主题报告审核' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '第一版核心结论' })).toBeVisible();
    await page.getByRole('button', { name: '批准发布' }).click();
    await expect(page.getByText('报告已批准发布')).toBeVisible();
    expect(fixture.snapshot()).toEqual([{ id: 'theme-report-v1', status: 'published', rowVersion: 2 }]);

    await fixture.loginAs('user');
    await page.goto(`/theme-research/${reportThemeId}`);
    await expect(page.getByText(/版本 2026-07-31\.1/)).toBeVisible();
    await page.getByRole('button', { name: '在线阅读' }).click();
    await expect(page.getByRole('heading', { name: 'AI供电产业链分析报告（第一版）' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '第一版核心结论' })).toBeVisible();
    const pdf = await page.evaluate(async (themeId) => {
      const response = await fetch(`/api/research/theme-decomposition/themes/${themeId}/reports/theme-report-v1/pdf`);
      return {
        status: response.status,
        contentType: response.headers.get('content-type'),
        prefix: (await response.text()).slice(0, 8)
      };
    }, reportThemeId);
    expect(pdf).toEqual({ status: 200, contentType: 'application/pdf', prefix: '%PDF-1.4' });

    fixture.indexSecondVersion();
    await page.goto(`/theme-research/${reportThemeId}`);
    await expect(page.getByText(/版本 2026-07-31\.1/)).toBeVisible();
    await page.getByRole('button', { name: '在线阅读' }).click();
    await expect(page.getByRole('heading', { name: 'AI供电产业链分析报告（第一版）' })).toBeVisible();

    await fixture.loginAs('admin');
    await page.goto('/admin/theme-research/report-review');
    await expect(page.getByText('报告审核', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'AI供电产业链分析报告（第二版）' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '第二版核心结论' })).toBeVisible();
    await page.getByRole('button', { name: '批准发布' }).click();
    await expect(page.getByText('报告已批准发布')).toBeVisible();
    expect(fixture.snapshot()).toEqual([
      { id: 'theme-report-v1', status: 'archived', rowVersion: 3 },
      { id: 'theme-report-v2', status: 'published', rowVersion: 2 }
    ]);

    await fixture.loginAs('user');
    await page.goto(`/theme-research/${reportThemeId}`);
    await expect(page.getByText(/版本 2026-08-01\.1/)).toBeVisible();
    await page.getByRole('button', { name: '在线阅读' }).click();
    await expect(page.getByRole('heading', { name: 'AI供电产业链分析报告（第二版）' })).toBeVisible();
    const history = page.getByRole('combobox', { name: '报告历史版本' });
    await expect(history.locator('option').nth(0)).toContainText('2026-08-01.1 · 当前发布');
    await expect(history.locator('option').nth(1)).toContainText('2026-07-31.1 · 历史归档');
  } finally {
    fixture.cleanup();
  }
});
