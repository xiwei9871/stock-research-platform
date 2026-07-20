import type { Page } from '@playwright/test';

import type { RuntimeEvidence } from './test';

const runtimeEvidenceKey: unique symbol = Symbol('playwrightRuntimeEvidence');
type RuntimeEvidencePage = Page & { [runtimeEvidenceKey]?: RuntimeEvidence };

export type MockPlatformApiResponse = {
  status?: number;
  json: unknown;
  headers?: Record<string, string>;
};

export type MockPlatformApiRoutes = Record<string, MockPlatformApiResponse>;

export function bindRuntimeEvidenceToPage(
  page: Page,
  evidence: RuntimeEvidence
): () => void {
  const evidencePage = page as RuntimeEvidencePage;
  evidencePage[runtimeEvidenceKey] = evidence;
  return () => {
    if (evidencePage[runtimeEvidenceKey] === evidence) delete evidencePage[runtimeEvidenceKey];
  };
}

function normalizeRouteKey(key: string): string {
  const separator = key.indexOf(' ');
  if (separator < 1) return key.toUpperCase();
  return `${key.slice(0, separator).toUpperCase()} ${key.slice(separator + 1)}`;
}

export async function installMockPlatformApi(
  page: Page,
  routes: MockPlatformApiRoutes
): Promise<void> {
  const evidence = (page as RuntimeEvidencePage)[runtimeEvidenceKey];
  if (!evidence) {
    throw new Error('installMockPlatformApi requires the shared runtime test fixture');
  }
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
      evidence.unhandledApiRoutes.push(key);
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
