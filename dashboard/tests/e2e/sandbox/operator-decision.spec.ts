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


test('@sandbox operator notes and follow-up edits persist without auto-trade controls', async ({ page }) => {
  const adminUsername = requiredEnv('PLAYWRIGHT_SANDBOX_ADMIN_USERNAME');
  const adminPassword = requiredEnv('PLAYWRIGHT_SANDBOX_ADMIN_PASSWORD');
  const writeToken = requiredEnv('PLAYWRIGHT_SANDBOX_WRITE_TOKEN');
  const assetId = requiredEnv('PLAYWRIGHT_SANDBOX_ASSET_ID');
  const tradeDate = requiredEnv('PLAYWRIGHT_SANDBOX_TRADE_DATE');
  const runId = requiredEnv('PLAYWRIGHT_SANDBOX_RUN_ID');
  const updatedNote = `sandbox persisted note ${runId}`;
  const followUpNote = `sandbox follow-up ${runId}`;

  await page.route('**/api/operator-decisions/**', async (route) => {
    await route.continue({
      headers: {
        ...route.request().headers(),
        'x-dashboard-write-token': writeToken
      }
    });
  });

  await page.goto(`/stock/${encodeURIComponent(assetId)}?trade_date=${encodeURIComponent(tradeDate)}`);
  await expect(page.getByRole('heading', { name: '登录' })).toBeVisible();
  await login(page, adminUsername, adminPassword);
  await expect(page.getByRole('heading', { name: new RegExp(assetId.replace('.', '\\.')) })).toBeVisible();

  const seededDecision = page.locator('.decision-row').filter({ hasText: 'sandbox seed note' });
  await expect(seededDecision).toBeVisible();
  await seededDecision.getByRole('button', { name: '编辑复盘日志' }).click();
  await seededDecision.getByLabel('复盘日志备注').fill(updatedNote);
  await seededDecision.getByLabel('需要跟进').check();
  await seededDecision.getByLabel('跟进说明').fill(followUpNote);
  await seededDecision.getByRole('button', { name: '保存复盘日志' }).click();
  await expect(seededDecision).toContainText(updatedNote);
  await expect(seededDecision).toContainText(followUpNote);
  await expect(seededDecision).toContainText('需要跟进');

  await page.reload();
  const persistedDecision = page.locator('.decision-row').filter({ hasText: updatedNote });
  await expect(persistedDecision).toContainText(followUpNote);
  await expect(persistedDecision).toContainText('需要跟进');

  await expect(page.getByRole('button', { name: /auto.?trade|自动交易/i })).toHaveCount(0);
  await expect(page.getByRole('switch', { name: /auto.?trade|自动交易/i })).toHaveCount(0);
  await expect(page.getByRole('checkbox', { name: /auto.?trade|自动交易/i })).toHaveCount(0);
});
