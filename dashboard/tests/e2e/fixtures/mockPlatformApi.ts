import type { Page } from '@playwright/test';

import type { RuntimeEvidence } from './test';

export type MockPlatformApiResponse = {
  status?: number;
  json: unknown;
  headers?: Record<string, string>;
};

export type MockPlatformApiRoutes = Record<string, MockPlatformApiResponse>;

function normalizeRouteKey(key: string): string {
  const separator = key.indexOf(' ');
  if (separator < 1) return key.toUpperCase();
  return `${key.slice(0, separator).toUpperCase()} ${key.slice(separator + 1)}`;
}

export async function installMockPlatformApi(
  page: Page,
  routes: MockPlatformApiRoutes,
  evidence?: RuntimeEvidence
): Promise<void> {
  const normalizedRoutes = new Map(
    Object.entries(routes).map(([key, response]) => [normalizeRouteKey(key), response])
  );

  await page.route('/api/**', async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const pathname = new URL(request.url()).pathname;
    const key = `${method} ${pathname}`;
    const response = normalizedRoutes.get(key);

    if (!response) {
      evidence?.unhandledApiRoutes.push(key);
      await route.fulfill({
        status: 599,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'unhandled_mock_api_route', method, pathname })
      });
      return;
    }

    await route.fulfill({
      status: response.status ?? 200,
      contentType: 'application/json',
      headers: response.headers,
      body: JSON.stringify(response.json)
    });
  });
}
