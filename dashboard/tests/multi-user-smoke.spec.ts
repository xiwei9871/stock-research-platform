import { expect, test } from '@playwright/test';

test('multi-user dashboard login smoke flow works for watchlist and reviews', async ({ page }) => {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Unauthorized' })
    });
  });

  await page.route('/api/auth/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'set-cookie':
          'stock_research_session=session-1; Path=/; SameSite=Lax, stock_research_csrf=csrf-1; Path=/; SameSite=Lax'
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

  await page.goto('/');

  await page.getByLabel('用户名或邮箱').fill('admin');
  await page.getByLabel('密码').fill('secret123');
  await page.getByRole('button', { name: '登录' }).click();

  await page.getByRole('button', { name: '我的观察池' }).click();
  await expect(page.getByRole('heading', { name: '我的观察池' })).toBeVisible();
  await expect(page.getByText('暂无观察资产。')).toBeVisible();

  await page.getByRole('button', { name: '我的复盘' }).click();
  await expect(page.getByRole('heading', { name: '我的复盘' })).toBeVisible();
  await expect(page.getByText('暂无复盘记录。')).toBeVisible();
});
