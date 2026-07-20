import { expect, test, type Page } from '@playwright/test';

const NORMAL_USER = {
  user_id: 'user:analyst',
  username: 'analyst',
  display_name: 'Research Analyst',
  role: 'user',
  is_active: true
};

const ADMIN_USER = {
  user_id: 'user:admin',
  username: 'admin',
  display_name: 'Platform Admin',
  role: 'admin',
  is_active: true
};

type AuthApiOptions = {
  authenticated?: boolean;
  user?: typeof NORMAL_USER;
  expireAdminRequests?: boolean;
};

async function mockAuthJourneyApi(page: Page, options: AuthApiOptions = {}) {
  let authenticated = options.authenticated ?? false;
  let currentUser = options.user ?? NORMAL_USER;
  let logoutCalls = 0;
  const unexpectedRequests: string[] = [];

  await page.route('/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname === '/api/auth/me') {
      await route.fulfill(
        authenticated
          ? { json: { user: currentUser } }
          : { status: 401, json: { detail: 'not authenticated' } }
      );
      return;
    }

    if (url.pathname === '/api/auth/login') {
      const credentials = request.postDataJSON() as { username?: string; password?: string };
      if (credentials.username !== 'analyst' || credentials.password !== 'secret') {
        await route.fulfill({ status: 401, json: { detail: 'invalid credentials' } });
        return;
      }
      authenticated = true;
      currentUser = NORMAL_USER;
      await route.fulfill({ json: { user: currentUser } });
      return;
    }

    if (url.pathname === '/api/admin/users' && options.expireAdminRequests) {
      await route.fulfill({ status: 401, json: { detail: 'session expired' } });
      return;
    }

    if (url.pathname === '/api/auth/logout') {
      logoutCalls += 1;
      authenticated = false;
      await route.fulfill({ json: { status: 'ok' } });
      return;
    }

    if (url.pathname === '/api/platform/readiness') {
      await route.fulfill({
        json: {
          mode: 'eod_local',
          status: 'READY',
          display_trade_date: '2026-07-17',
          latest_trade_date: '2026-07-17',
          latest_market_date: '2026-07-17',
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
      });
      return;
    }

    if (url.pathname === '/api/platform/summary') {
      await route.fulfill({
        json: {
          latest_market_date: '2026-07-17',
          latest_score_date: '2026-07-17',
          latest_factor_date: '2026-07-17',
          market_asset_count: 0,
          score_asset_count: 0,
          factor_count: 0,
          score_versions: [],
          topn_preview: []
        }
      });
      return;
    }

    if (url.pathname === '/api/backtests/strategies') {
      await route.fulfill({ json: { items: [] } });
      return;
    }

    if (url.pathname === '/api/market-monitor/eod') {
      await route.fulfill({
        json: {
          trade_date: '2026-07-17',
          freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
          coverage: { market_assets: 0, score_assets: 0, factor_count: 0 },
          market_breadth: {},
          market_regime: {},
          strategy_signals: [],
          warnings: []
        }
      });
      return;
    }

    if (url.pathname === '/api/public-news') {
      await route.fulfill({ json: { items: [], total: 0, limit: 5, offset: 0 } });
      return;
    }

    if (url.pathname === '/api/strategy-score-audit') {
      await route.fulfill({
        json: {
          trade_date: '2026-07-17',
          overall_status: 'ok',
          anomaly_row_count: 0,
          anomaly_counts_by_type: {},
          strategies: []
        }
      });
      return;
    }

    if (url.pathname === '/api/research/cases' || url.pathname === '/api/research/evidence') {
      await route.fulfill({ json: { items: [] } });
      return;
    }

    if (url.pathname === '/api/research/queue/health') {
      await route.fulfill({
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
      });
      return;
    }

    if (url.pathname === '/api/research/queue/publish-gate') {
      await route.fulfill({
        json: {
          status: 'empty',
          research_ready_for_publication: false,
          internal_snapshot_enabled: false,
          summary: { pending_gap_count: 0, request_more_evidence_count: 0, error_count: 0 },
          blockers: [],
          top_blocked_cases: []
        }
      });
      return;
    }

    if (url.pathname === '/api/research/publication/snapshots') {
      await route.fulfill({ json: { items: [] } });
      return;
    }

    unexpectedRequests.push(`${request.method()} ${url.pathname}`);
    await route.fulfill({ status: 599, json: { detail: `unexpected API request: ${url.pathname}` } });
  });

  return {
    logoutCallCount: () => logoutCalls,
    unexpectedRequests
  };
}

test('unauthenticated initial session renders LoginView', async ({ page }) => {
  const authApi = await mockAuthJourneyApi(page);

  await page.goto('/');

  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  expect(authApi.unexpectedRequests).toEqual([]);
});

test('invalid login fails visibly, successful login opens the normal-user home shell, and logout returns to LoginView', async ({ page }) => {
  const authApi = await mockAuthJourneyApi(page);
  await page.goto('/');

  await page.getByLabel('用户名').fill('analyst');
  await page.getByLabel('密码').fill('wrong');
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByRole('alert')).toContainText('invalid credentials');

  await page.getByLabel('密码').fill('secret');
  await page.getByRole('button', { name: '登录' }).click();

  await expect(page.getByText('A股策略研究')).toBeVisible();
  await expect(page.getByRole('heading', { name: '策略指挥中心' })).toBeVisible();
  await expect(page.getByText('今日暂无待处理研究事项。')).toBeVisible();
  await expect(page.locator('.platform-topbar')).toContainText('Research Analyst');
  await expect(page.getByRole('button', { name: 'Open User Management workspace' })).toHaveCount(0);

  await page.getByRole('button', { name: '退出登录' }).click();

  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  expect(authApi.logoutCallCount()).toBe(1);
  expect(authApi.unexpectedRequests).toEqual([]);
});

test('a credentialed API 401 expires the active session and returns to LoginView', async ({ page }) => {
  const authApi = await mockAuthJourneyApi(page, { authenticated: true, user: ADMIN_USER, expireAdminRequests: true });
  await page.goto('/');

  await expect(page.locator('.platform-topbar')).toContainText('Platform Admin');
  await page.getByRole('button', { name: 'Open User Management workspace' }).click();

  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  expect(authApi.unexpectedRequests).toEqual([]);
});
