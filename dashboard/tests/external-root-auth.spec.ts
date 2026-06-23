import { expect, test, type Page } from '@playwright/test';

async function mockLoggedOutEntry(page: Page) {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unauthorized' })
    });
  });
}

async function mockAdminSession(page: Page) {
  await mockLoggedOutEntry(page);
  await page.route('/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'set-cookie':
          'stock_research_session=session-admin; Path=/; SameSite=Lax, stock_research_csrf=csrf-admin; Path=/; SameSite=Lax'
      },
      body: JSON.stringify({
        id: 1,
        username: 'admin',
        display_name: 'Admin User',
        role: 'admin',
        is_active: true
      })
    });
  });
  await page.route('/api/admin/users', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: 1,
            username: 'admin',
            email: 'admin@example.com',
            display_name: 'Admin User',
            role: 'admin',
            is_active: true,
            disabled_at: null
          }
        ]
      })
    });
  });
  await page.route('/api/auth/logout', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'set-cookie':
          'stock_research_session=; Path=/; Max-Age=0; SameSite=Lax, stock_research_csrf=; Path=/; Max-Age=0; SameSite=Lax'
      },
      body: JSON.stringify({ ok: true })
    });
  });
}

async function mockStandardUserSession(page: Page) {
  await mockLoggedOutEntry(page);
  await page.route('/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'set-cookie':
          'stock_research_session=session-user; Path=/; SameSite=Lax, stock_research_csrf=csrf-user; Path=/; SameSite=Lax'
      },
      body: JSON.stringify({
        id: 9,
        username: 'analyst',
        display_name: 'Analyst User',
        role: 'user',
        is_active: true
      })
    });
  });
  await page.route('/api/my/watchlist', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] })
    });
  });
  await page.route('/api/my/reviews', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] })
    });
  });
}

test('unauthenticated root path shows LoginView and admin can login then logout back to LoginView', async ({ page }) => {
  await mockAdminSession(page);

  await page.goto('/');

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();

  await page.getByLabel('用户名或邮箱').fill('admin');
  await page.getByLabel('密码').fill('secret123');
  await page.getByRole('button', { name: '登录' }).click();

  await page.getByRole('button', { name: '用户管理' }).click();
  await expect(page.getByRole('heading', { name: '用户管理' })).toBeVisible();
  await expect(page.getByRole('button', { name: '用户管理' })).toBeVisible();

  await page.getByRole('button', { name: '退出登录' }).click();

  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  await expect(page.getByRole('button', { name: '用户管理' })).toHaveCount(0);
});

test('standard user login hides 用户管理 and can open 我的观察池 and 我的复盘 from the external root', async ({ page }) => {
  await mockStandardUserSession(page);

  await page.goto('/');

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();

  await page.getByLabel('用户名或邮箱').fill('analyst');
  await page.getByLabel('密码').fill('secret123');
  await page.getByRole('button', { name: '登录' }).click();

  await page.getByRole('button', { name: '我的观察池' }).click();
  await expect(page.getByRole('heading', { name: '我的观察池' })).toBeVisible();
  await expect(page.getByText('暂无观察资产。')).toBeVisible();
  await expect(page.getByRole('button', { name: '用户管理' })).toHaveCount(0);

  await page.getByRole('button', { name: '我的复盘' }).click();

  await expect(page.getByRole('heading', { name: '我的复盘' })).toBeVisible();
  await expect(page.getByText('暂无复盘记录。')).toBeVisible();
  await expect(page.getByRole('button', { name: '用户管理' })).toHaveCount(0);
});
