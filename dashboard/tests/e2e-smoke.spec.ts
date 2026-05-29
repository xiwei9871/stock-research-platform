import { expect, test } from '@playwright/test';

test('playwright smoke runner is wired', async ({ browserName }) => {
  expect(browserName).toBeTruthy();
});
