import type { Page } from '@playwright/test';

import { expectNoFatalRuntimeErrors, expectNoHorizontalOverflow } from '../assertions/runtime';
import { installMockPlatformApi } from '../fixtures/mockPlatformApi';
import { expect, test } from '../fixtures/test';

async function setContractContent(page: Page, baseURL: string | undefined, content: string) {
  if (!baseURL) throw new Error('Playwright baseURL is required for runtime contract tests');
  const documentUrl = new URL('/__runtime-contract__', baseURL).toString();
  await page.route(documentUrl, (route) =>
    route.fulfill({ contentType: 'text/html', body: content })
  );
  await page.goto(documentUrl);
  await page.unroute(documentUrl);
}

test('clean control passes @p0 @runtime-contract', async ({ page, baseURL, runtimeEvidence }) => {
  await setContractContent(page, baseURL, '<main>runtime contract control</main>');

  expect(runtimeEvidence).toEqual({
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    unhandledApiRoutes: []
  });
});

test('unexpected console.error fails with exact evidence @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence
}) => {
  await setContractContent(page, baseURL, '<main>console error contract</main>');
  await page.evaluate(() => console.error('runtime-contract-console-error'));

  expect(runtimeEvidence.consoleErrors).toContain('runtime-contract-console-error');
  test.fail();
});

test('uncaught page error fails with exact evidence @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence
}) => {
  const pageError = page.waitForEvent('pageerror');
  await setContractContent(page, baseURL, '<main>page error contract</main>');
  await page.evaluate(() => {
    window.setTimeout(() => {
      throw new Error('runtime-contract-page-error');
    }, 0);
  });
  await pageError;

  expect(runtimeEvidence.pageErrors).toContain('runtime-contract-page-error');
  test.fail();
});

test('failed critical API request fails with exact evidence @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence
}) => {
  await page.route('/api/runtime-contract-abort', (route) => route.abort('failed'));
  await setContractContent(page, baseURL, '<main>failed request contract</main>');
  await page.evaluate(() => fetch('/api/runtime-contract-abort').catch(() => undefined));

  await expect
    .poll(() => runtimeEvidence.failedRequests)
    .toContainEqual({
      method: 'GET',
      url: new URL('/api/runtime-contract-abort', page.url()).toString(),
      failure: 'net::ERR_FAILED'
    });
  test.fail();
});

test('fulfilled critical API 5xx fails with exact evidence @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence
}) => {
  await installMockPlatformApi(
    page,
    {
      'GET /api/runtime-contract-server-error': {
        status: 503,
        json: { detail: 'intentional server error' }
      }
    },
    runtimeEvidence
  );
  await setContractContent(page, baseURL, '<main>server error contract</main>');
  await page.evaluate(() => fetch('/api/runtime-contract-server-error'));

  await expect
    .poll(() => runtimeEvidence.failedRequests)
    .toContainEqual({
      method: 'GET',
      url: new URL('/api/runtime-contract-server-error', page.url()).toString(),
      failure: 'HTTP 503'
    });
  test.fail();
});

test('unhandled mock API route fails closed with exact evidence @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence
}) => {
  await installMockPlatformApi(page, {}, runtimeEvidence);
  await setContractContent(page, baseURL, '<main>unhandled API contract</main>');
  const response = await page.evaluate(async () => {
    const result = await fetch('/api/unexpected?ignored=query');
    return { status: result.status, body: await result.json() };
  });

  expect(response).toEqual({
    status: 599,
    body: {
      detail: 'unhandled_mock_api_route',
      method: 'GET',
      pathname: '/api/unexpected'
    }
  });
  expect(runtimeEvidence.unhandledApiRoutes).toEqual(['GET /api/unexpected']);
  test.fail();
});

test('explicit allowlist is narrow and permits only the intended error @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(/^intentional-runtime-console-error$/);

  await setContractContent(page, baseURL, '<main>allowlist contract</main>');
  await page.evaluate(() => console.error('intentional-runtime-console-error'));

  expect(runtimeEvidence.consoleErrors).toEqual(['intentional-runtime-console-error']);
  expect(() =>
    expectNoFatalRuntimeErrors(
      {
        consoleErrors: ['intentional-runtime-console-error-extra'],
        pageErrors: [],
        failedRequests: [],
        unhandledApiRoutes: []
      },
      runtimePolicy
    )
  ).toThrow(/intentional-runtime-console-error-extra/);
});

test('horizontal overflow helper passes for contained content @p0 @runtime-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '<main style="max-width: 100%">contained content</main>'
  );

  await expectNoHorizontalOverflow(page);
});

test('horizontal overflow helper reports measured widths @p0 @runtime-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '<main style="width: 2000px">overflowing content</main>'
  );

  let overflowError: Error | undefined;
  try {
    await expectNoHorizontalOverflow(page);
  } catch (error) {
    if (error instanceof Error) overflowError = error;
  }

  if (!overflowError) throw new Error('Expected horizontal overflow assertion to fail');
  const widths = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }));
  expect(overflowError.message).toContain(
    `scrollWidth=${widths.scrollWidth}, clientWidth=${widths.clientWidth}, ` +
      `allowedMaximum=${widths.clientWidth + 1}`
  );
  test.fail();
  throw overflowError;
});
