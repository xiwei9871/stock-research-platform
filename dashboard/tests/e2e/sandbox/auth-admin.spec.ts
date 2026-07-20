import type { Page } from '@playwright/test';

import { expect, test } from '../fixtures/test';

test.use({ trace: 'off', video: 'off' });


function requiredEnv(name: string): string {
  const value = (
    globalThis as typeof globalThis & {
      process?: { env?: Record<string, string | undefined> };
    }
  ).process?.env?.[name]?.trim();
  if (!value) throw new Error(`sandbox_fixture_env_missing:${name}`);
  return value;
}


async function login(page: Page, username: string, password: string) {
  await page.getByLabel('用户名').fill(username);
  await page.getByLabel('密码').fill(password);
  await page.getByRole('button', { name: '登录' }).click();
}


test('@sandbox admin can manage a unique user and the reset password authenticates', async ({ page }) => {
  const adminUsername = requiredEnv('PLAYWRIGHT_SANDBOX_ADMIN_USERNAME');
  const adminPassword = requiredEnv('PLAYWRIGHT_SANDBOX_ADMIN_PASSWORD');
  const createdUsername = requiredEnv('PLAYWRIGHT_SANDBOX_CREATED_USERNAME');
  const initialPassword = requiredEnv('PLAYWRIGHT_SANDBOX_CREATED_INITIAL_PASSWORD');
  const resetPassword = requiredEnv('PLAYWRIGHT_SANDBOX_CREATED_RESET_PASSWORD');

  await page.goto('/admin/users');
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  await login(page, adminUsername, adminPassword);
  await expect(page.getByRole('heading', { name: '用户管理' })).toBeVisible();

  await page.getByLabel('新用户名').fill(createdUsername);
  await page.getByLabel('显示名').fill(`Sandbox ${createdUsername}`);
  await page.getByLabel('初始密码').fill(initialPassword);
  await page.getByLabel('角色').selectOption('user');
  await page.getByRole('button', { name: '创建用户' }).click();

  const createdRow = page.getByRole('row').filter({ hasText: createdUsername });
  await expect(createdRow).toContainText('active');
  await createdRow.getByRole('button', { name: `停用 ${createdUsername}` }).click();
  await expect(createdRow).toContainText('disabled');
  await createdRow.getByRole('button', { name: `启用 ${createdUsername}` }).click();
  await expect(createdRow).toContainText('active');

  await createdRow.getByLabel(`重置 ${createdUsername} 密码`).fill(resetPassword);
  const [resetResponse] = await Promise.all([
    page.waitForResponse((response) =>
      response.url().includes('/reset-password') && response.request().method() === 'POST'
    ),
    createdRow.getByRole('button', { name: `重置 ${createdUsername} 密码` }).click()
  ]);
  expect(resetResponse.ok()).toBe(true);
  await expect(createdRow).toContainText('active');

  await page.getByRole('button', { name: '退出登录' }).click();
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  await login(page, createdUsername, resetPassword);
  await expect(page.getByText(`Sandbox ${createdUsername}`, { exact: true })).toBeVisible();
});
