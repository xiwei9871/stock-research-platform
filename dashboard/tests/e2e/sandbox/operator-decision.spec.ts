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


const FORBIDDEN_TRADING_CAPABILITY = /(?:自动(?:交易|下单|执行)|实盘(?:交易|下单|执行)|auto(?:matic)?[\s_-]*(?:trade|order|execution)|live[\s_-]*(?:trade|order|execution))/i;
const FORBIDDEN_CAPABILITY_FIELD = /(?:auto[_-]?(?:trade|order|execute|execution)|automatic[_-]?(?:trade|order|execute|execution)|live[_-]?(?:trade|order|execute|execution)|trading[_-]?(?:enabled|capability))/i;

type CapabilityField = {
  path: string;
  value: unknown;
};

function capabilityFields(value: unknown, path = ''): CapabilityField[] {
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => capabilityFields(item, `${path}[${index}]`));
  }
  if (typeof value !== 'object' || value === null) return [];
  return Object.entries(value as Record<string, unknown>).flatMap(([key, fieldValue]) => {
    const fieldPath = path ? `${path}.${key}` : key;
    return [
      ...(FORBIDDEN_CAPABILITY_FIELD.test(key) ? [{ path: fieldPath, value: fieldValue }] : []),
      ...capabilityFields(fieldValue, fieldPath)
    ];
  });
}

function expectCapabilitiesDisabled(value: unknown) {
  for (const field of capabilityFields(value)) {
    expect(field.value, `${field.path} must remain false when present`).toBe(false);
  }
}

async function expectNoTradingControlsOrMarkers(page: Page) {
  const interactiveRoles = [
    'button',
    'link',
    'menuitem',
    'menuitemcheckbox',
    'menuitemradio',
    'checkbox',
    'switch',
    'tab',
    'radio',
    'textbox',
    'combobox',
    'listbox',
    'option',
    'slider',
    'spinbutton'
  ] as const;
  for (const role of interactiveRoles) {
    await expect(page.getByRole(role, { name: FORBIDDEN_TRADING_CAPABILITY })).toHaveCount(0);
  }

  const markerValues = await page
    .locator('[id], [name], [data-capability], [data-feature], [data-action], [data-field]')
    .evaluateAll((elements) =>
      elements.flatMap((element) =>
        ['id', 'name', 'data-capability', 'data-feature', 'data-action', 'data-field']
          .map((attribute) => element.getAttribute(attribute))
          .filter((value): value is string => Boolean(value))
      )
    );
  expect(
    markerValues.filter(
      (value) => FORBIDDEN_CAPABILITY_FIELD.test(value) || FORBIDDEN_TRADING_CAPABILITY.test(value)
    )
  ).toEqual([]);
}


test('@sandbox operator notes and follow-up edits persist without auto-trade controls', async ({ page }) => {
  const adminUsername = requiredEnv('PLAYWRIGHT_SANDBOX_ADMIN_USERNAME');
  const adminPassword = requiredEnv('PLAYWRIGHT_SANDBOX_ADMIN_PASSWORD');
  const writeToken = requiredEnv('PLAYWRIGHT_SANDBOX_WRITE_TOKEN');
  const assetId = requiredEnv('PLAYWRIGHT_SANDBOX_ASSET_ID');
  const tradeDate = requiredEnv('PLAYWRIGHT_SANDBOX_TRADE_DATE');
  const runId = requiredEnv('PLAYWRIGHT_SANDBOX_RUN_ID');
  const operatorEventId = requiredEnv('PLAYWRIGHT_SANDBOX_OPERATOR_EVENT_ID');
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
  const patchRequestPromise = page.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === 'PATCH' &&
      decodeURIComponent(url.pathname.replace('/api/operator-decisions/', '')) === operatorEventId;
  });
  const patchResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === 'PATCH' &&
      decodeURIComponent(url.pathname.replace('/api/operator-decisions/', '')) === operatorEventId;
  });
  await seededDecision.getByRole('button', { name: '保存复盘日志' }).click();
  const [patchRequest, patchResponse] = await Promise.all([patchRequestPromise, patchResponsePromise]);
  expect(patchResponse.ok()).toBe(true);
  const patchPayload = patchRequest.postDataJSON() as Record<string, unknown>;
  expect(Object.keys(patchPayload).sort()).toEqual(['follow_up_note', 'notes', 'requires_follow_up']);
  expect(capabilityFields(patchPayload)).toEqual([]);
  const patchBody = (await patchResponse.json()) as { item?: Record<string, unknown> };
  expectCapabilitiesDisabled(patchBody.item);
  await expect(seededDecision).toContainText(updatedNote);
  await expect(seededDecision).toContainText(followUpNote);
  await expect(seededDecision).toContainText('需要跟进');

  const reloadedProfilePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return response.request().method() === 'GET' && /^\/api\/assets\/[^/]+\/profile$/.test(url.pathname);
  });
  await page.reload();
  const reloadedProfileResponse = await reloadedProfilePromise;
  expect(reloadedProfileResponse.ok()).toBe(true);
  const reloadedProfile = (await reloadedProfileResponse.json()) as {
    decisions?: Array<Record<string, unknown>>;
  };
  const reloadedDecision = reloadedProfile.decisions?.find(
    (item) => item.event_id === operatorEventId
  );
  expect(reloadedDecision).toMatchObject({
    event_id: operatorEventId,
    notes: updatedNote,
    follow_up_note: followUpNote,
    requires_follow_up: true
  });
  expectCapabilitiesDisabled(reloadedDecision);
  const persistedDecision = page.locator('.decision-row').filter({ hasText: updatedNote });
  await expect(persistedDecision).toContainText(followUpNote);
  await expect(persistedDecision).toContainText('需要跟进');

  await expectNoTradingControlsOrMarkers(page);
});
