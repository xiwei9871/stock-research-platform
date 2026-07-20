import type { Page } from '@playwright/test';

import {
  expectNoFatalRuntimeErrors,
  expectNoHorizontalOverflow,
  expectNoUnhandledApiRoutes,
  serializeRuntimeEvidence
} from '../assertions/runtime';
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

function captureErrorMessage(assertion: () => void): string {
  try {
    assertion();
  } catch (error) {
    if (error instanceof Error) return error.message;
    throw error;
  }
  throw new Error('Expected runtime assertion to fail');
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

  expect(runtimeEvidence.consoleErrors).toEqual(['runtime-contract-console-error']);
  expect(captureErrorMessage(() => expectNoFatalRuntimeErrors(runtimeEvidence))).toBe(
    'Unexpected fatal runtime evidence:\n' +
      'consoleErrors:\n' +
      '- runtime-contract-console-error'
  );
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

  expect(runtimeEvidence.pageErrors).toEqual(['runtime-contract-page-error']);
  expect(captureErrorMessage(() => expectNoFatalRuntimeErrors(runtimeEvidence))).toBe(
    'Unexpected fatal runtime evidence:\n' +
      'pageErrors:\n' +
      '- runtime-contract-page-error'
  );
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
    .toEqual([
      {
        method: 'GET',
        url: new URL('/api/runtime-contract-abort', page.url()).toString(),
        failure: 'net::ERR_FAILED'
      }
    ]);
  await expect
    .poll(() => runtimeEvidence.consoleErrors)
    .toEqual(['Failed to load resource: net::ERR_FAILED']);
  const failedRequestUrl = new URL('/api/runtime-contract-abort', page.url()).toString();
  expect(captureErrorMessage(() => expectNoFatalRuntimeErrors(runtimeEvidence))).toBe(
    'Unexpected fatal runtime evidence:\n' +
      'consoleErrors:\n' +
      '- Failed to load resource: net::ERR_FAILED\n' +
      'failedRequests:\n' +
      `- GET ${failedRequestUrl} — net::ERR_FAILED`
  );
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
    }
  );
  await setContractContent(page, baseURL, '<main>server error contract</main>');
  await page.evaluate(() => fetch('/api/runtime-contract-server-error'));

  await expect
    .poll(() => runtimeEvidence.failedRequests)
    .toEqual([
      {
        method: 'GET',
        url: new URL('/api/runtime-contract-server-error', page.url()).toString(),
        failure: 'HTTP 503'
      }
    ]);
  const serverErrorConsole =
    'Failed to load resource: the server responded with a status of 503 (Service Unavailable)';
  await expect.poll(() => runtimeEvidence.consoleErrors).toEqual([serverErrorConsole]);
  const serverErrorUrl = new URL('/api/runtime-contract-server-error', page.url()).toString();
  expect(captureErrorMessage(() => expectNoFatalRuntimeErrors(runtimeEvidence))).toBe(
    'Unexpected fatal runtime evidence:\n' +
      'consoleErrors:\n' +
      `- ${serverErrorConsole}\n` +
      'failedRequests:\n' +
      `- GET ${serverErrorUrl} — HTTP 503`
  );
  test.fail();
});

test('unhandled mock API route fails closed with exact evidence @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence
}) => {
  await installMockPlatformApi(page, {});
  await setContractContent(page, baseURL, '<main>unhandled API contract</main>');
  const response = await page.evaluate(async () => {
    const result = await fetch('/api/access_token/path-secret?refresh_token=query-secret');
    return { status: result.status, body: await result.json() };
  });

  expect(response).toEqual({
    status: 599,
    body: {
      detail: 'unhandled_mock_api_route',
      method: 'GET',
      pathname: '/api/access_token/[REDACTED]'
    }
  });
  expect(runtimeEvidence.unhandledApiRoutes).toEqual([
    'GET /api/access_token/[REDACTED]'
  ]);
  expect(captureErrorMessage(() => expectNoUnhandledApiRoutes(runtimeEvidence))).toBe(
    'Unexpected unhandled API routes:\n- GET /api/access_token/[REDACTED]'
  );
  const unhandledConsole =
    'Failed to load resource: the server responded with a status of 599 (Unknown)';
  const unhandledUrl = new URL('/api/access_token/[REDACTED]', page.url()).toString();
  await expect.poll(() => runtimeEvidence.consoleErrors).toEqual([unhandledConsole]);
  await expect.poll(() => runtimeEvidence.failedRequests).toEqual([
    { method: 'GET', url: unhandledUrl, failure: 'HTTP 599' }
  ]);
  expect(captureErrorMessage(() => expectNoFatalRuntimeErrors(runtimeEvidence))).toBe(
    'Unexpected fatal runtime evidence:\n' +
      'consoleErrors:\n' +
      `- ${unhandledConsole}\n` +
      'failedRequests:\n' +
      `- GET ${unhandledUrl} — HTTP 599`
  );
  test.fail();
});

test('runtime evidence redacts credential-shaped console and page errors @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence,
  runtimePolicy
}) => {
  const rawEvidence =
    'Authorization: Bearer auth-secret ' +
    'Cookie: session=cookie-secret; theme=theme-secret; csrf_token=csrf-cookie-secret\n' +
    'Set-Cookie: access_token=set-cookie-secret; Path=/; refresh_token=refresh-cookie-secret\n' +
    '{"token":"token-secret","access_token":"access-secret",' +
    '"refreshToken":"refresh-secret","csrf_token":"csrf-secret",' +
    '"password":"password-secret","api_key":"api-key-secret","secret":"json-secret"}';
  const redactedEvidence =
    'Authorization: [REDACTED] ' +
    'Cookie: [REDACTED]\n' +
    'Set-Cookie: [REDACTED]\n' +
    '{"token":"[REDACTED]","access_token":"[REDACTED]",' +
    '"refreshToken":"[REDACTED]","csrf_token":"[REDACTED]",' +
    '"password":"[REDACTED]","api_key":"[REDACTED]","secret":"[REDACTED]"}';
  runtimePolicy.consoleErrors.push(redactedEvidence);
  runtimePolicy.pageErrors.push(redactedEvidence);

  await setContractContent(page, baseURL, '<main>redaction contract</main>');
  await page.evaluate((message) => console.error(message), rawEvidence);
  const pageError = page.waitForEvent('pageerror');
  await page.evaluate((message) => {
    window.setTimeout(() => {
      throw new Error(message);
    }, 0);
  }, rawEvidence);
  await pageError;

  expect(runtimeEvidence.consoleErrors).toEqual([redactedEvidence]);
  expect(runtimeEvidence.pageErrors).toEqual([redactedEvidence]);
});

test('runtime evidence attachment sanitizes every field and sorts arrays @p0 @runtime-contract', async () => {
  const rawEvidence = {
    consoleErrors: [
      'z-error accessToken=console-access-secret',
      'Cookie: session=first-secret; theme=second-secret; csrf_token=third-secret'
    ],
    pageErrors: [
      '{"refresh_token":"page-refresh-secret","csrfToken":"page-csrf-secret"}'
    ],
    failedRequests: [
      {
        method: 'POST',
        url: 'https://example.test/api/refresh_token/path-refresh-secret?access_token=query-secret',
        failure: 'password=failure-secret'
      },
      {
        method: 'GET',
        url: 'https://example.test/api/clean',
        failure: 'secret=failure-secret'
      }
    ],
    unhandledApiRoutes: [
      'POST /api/secret/path-secret?csrf_token=query-secret',
      'GET /api/access_token/route-secret?refreshToken=query-secret'
    ]
  };
  const reverseEvidence = {
    consoleErrors: [...rawEvidence.consoleErrors].reverse(),
    pageErrors: [...rawEvidence.pageErrors].reverse(),
    failedRequests: [...rawEvidence.failedRequests].reverse(),
    unhandledApiRoutes: [...rawEvidence.unhandledApiRoutes].reverse()
  };

  const serialized = serializeRuntimeEvidence(rawEvidence);

  expect(serialized).toBe(serializeRuntimeEvidence(reverseEvidence));
  expect(JSON.parse(serialized)).toEqual({
    consoleErrors: [
      'Cookie: [REDACTED]',
      'z-error accessToken=[REDACTED]'
    ],
    pageErrors: [
      '{"refresh_token":"[REDACTED]","csrfToken":"[REDACTED]"}'
    ],
    failedRequests: [
      {
        method: 'GET',
        url: 'https://example.test/api/clean',
        failure: 'secret=[REDACTED]'
      },
      {
        method: 'POST',
        url: 'https://example.test/api/refresh_token/[REDACTED]',
        failure: 'password=[REDACTED]'
      }
    ],
    unhandledApiRoutes: [
      'GET /api/access_token/[REDACTED]?refreshToken=[REDACTED]',
      'POST /api/secret/[REDACTED]?csrf_token=[REDACTED]'
    ]
  });
  expect(rawEvidence.consoleErrors[0]).toBe('z-error accessToken=console-access-secret');
});

test('explicit allowlist is narrow and permits only the intended error @p0 @runtime-contract', async ({
  page,
  baseURL,
  runtimeEvidence,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(/^intentional-runtime-console-error$/g);

  await setContractContent(page, baseURL, '<main>allowlist contract</main>');
  await page.evaluate(() => console.error('intentional-runtime-console-error'));

  expect(runtimeEvidence.consoleErrors).toEqual(['intentional-runtime-console-error']);
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(
        {
          consoleErrors: ['intentional-runtime-console-error-extra'],
          pageErrors: [],
          failedRequests: [],
          unhandledApiRoutes: []
        },
        runtimePolicy
      )
    )
  ).toBe(
    'Unexpected fatal runtime evidence:\n' +
      'consoleErrors:\n' +
      '- intentional-runtime-console-error-extra'
  );
});

test('match-all runtime allowlists are rejected exactly @p0 @runtime-contract', async () => {
  const evidence = {
    consoleErrors: ['runtime-contract-console-error'],
    pageErrors: [],
    failedRequests: [],
    unhandledApiRoutes: []
  };

  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(
        {
          consoleErrors: [],
          pageErrors: [],
          failedRequests: [],
          unhandledApiRoutes: []
        },
        {
          consoleErrors: [/.*/]
        }
      )
    )
  ).toBe('Runtime evidence allowlist rejects match-all pattern: /.*/');
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(evidence, {
        consoleErrors: [/.+/]
      })
    )
  ).toBe('Runtime evidence allowlist rejects match-all pattern: /.+/');
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(evidence, {
        consoleErrors: [/^.+$/s]
      })
    )
  ).toBe('Runtime evidence allowlist rejects match-all pattern: /^.+$/s');
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(evidence, {
        consoleErrors: [/.*/]
      })
    )
  ).toBe('Runtime evidence allowlist rejects match-all pattern: /.*/');
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(evidence, {
        consoleErrors: [/^.*$/]
      })
    )
  ).toBe('Runtime evidence allowlist rejects match-all pattern: /^.*$/');
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(evidence, {
        consoleErrors: [/runtime-contract-console-error/]
      })
    )
  ).toBe(
    'Runtime evidence allowlist rejects unanchored pattern: /runtime-contract-console-error/'
  );
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(
        {
          consoleErrors: ['prefix-unexpected-error'],
          pageErrors: [],
          failedRequests: [],
          unhandledApiRoutes: []
        },
        {
          consoleErrors: [/^intentional$|unexpected-error$/]
        }
      )
    )
  ).toBe(
    'Runtime evidence allowlist rejects unanchored pattern: /^intentional$|unexpected-error$/'
  );
  expect(
    captureErrorMessage(() =>
      expectNoFatalRuntimeErrors(
        {
          consoleErrors: ['intentional-runtime-console-error\nunexpected-tail'],
          pageErrors: [],
          failedRequests: [],
          unhandledApiRoutes: []
        },
        {
          consoleErrors: [/^intentional-runtime-console-error$/g]
        }
      )
    )
  ).toBe(
    'Unexpected fatal runtime evidence:\n' +
      'consoleErrors:\n' +
      '- intentional-runtime-console-error\n' +
      'unexpected-tail'
  );
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
  expect(overflowError.message).toBe(
    'Horizontal overflow detected: ' +
      'document.documentElement.' +
      `scrollWidth=${widths.scrollWidth}, clientWidth=${widths.clientWidth}, ` +
      `allowedMaximum=${widths.clientWidth + 1}`
  );
  test.fail();
  throw overflowError;
});
