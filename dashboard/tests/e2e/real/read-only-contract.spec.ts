import type { Page, Response, Route } from '@playwright/test';

import { loadAuthoritativeSnapshot } from './authoritativeSnapshot';
import {
  expect,
  serializeRealHttpEvidence,
  test,
  type RealApiControl
} from './test';

const WRITE_FORBIDDEN = 'real_profile_write_forbidden';
const ROUTE_OVERRIDE_FORBIDDEN = 'real_profile_api_route_override_forbidden';
const UNSCOPED_REQUEST_FORBIDDEN = 'real_profile_unscoped_request_context_forbidden';
const PROBE_DOCUMENT = '/__playwright_real_contract__';

type GuardedResult = {
  status: number;
  detail: string;
  guard: string | null;
};

async function openProbeDocument(page: Page): Promise<void> {
  await page.route(PROBE_DOCUMENT, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/html',
      body: '<!doctype html><html><body>real read-only contract</body></html>'
    });
  });
  await page.goto(PROBE_DOCUMENT);
}

async function resultFromResponse(response: Response): Promise<GuardedResult> {
  const payload = (await response.json()) as { detail?: unknown };
  return {
    status: response.status(),
    detail: typeof payload.detail === 'string' ? payload.detail : '',
    guard: response.headers()['x-playwright-real-guard'] ?? null
  };
}

async function mutateWithFetch(page: Page, method: 'PUT' | 'DELETE'): Promise<GuardedResult> {
  return page.evaluate(
    async ({ marker, requestMethod }) => {
      const response = await fetch(`/api/__playwright_real_contract__/${requestMethod}/fetch`, {
        method: requestMethod,
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ marker })
      });
      const payload = (await response.json()) as { detail?: unknown };
      return {
        status: response.status,
        detail: typeof payload.detail === 'string' ? payload.detail : '',
        guard: response.headers.get('x-playwright-real-guard')
      };
    },
    { marker: WRITE_FORBIDDEN, requestMethod: method }
  );
}

async function postWithFetch(page: Page, path: string): Promise<GuardedResult> {
  return page.evaluate(async (apiPath) => {
    const response = await fetch(apiPath, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ marker: 'real_profile_write_forbidden' })
    });
    const payload = (await response.json()) as { detail?: unknown };
    return {
      status: response.status,
      detail: typeof payload.detail === 'string' ? payload.detail : '',
      guard: response.headers.get('x-playwright-real-guard')
    };
  }, path);
}

async function mutateWithXhr(page: Page, method: 'PATCH'): Promise<GuardedResult> {
  return page.evaluate(
    ({ marker, requestMethod }) =>
      new Promise<GuardedResult>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open(requestMethod, `/api/__playwright_real_contract__/${requestMethod}/xhr`);
        xhr.setRequestHeader('content-type', 'application/json');
        xhr.addEventListener('load', () => {
          let payload: { detail?: unknown } = {};
          try {
            payload = JSON.parse(xhr.responseText) as { detail?: unknown };
          } catch {
            // The assertions below deliberately fail closed on an invalid response.
          }
          resolve({
            status: xhr.status,
            detail: typeof payload.detail === 'string' ? payload.detail : '',
            guard: xhr.getResponseHeader('x-playwright-real-guard')
          });
        });
        xhr.addEventListener('error', () => reject(new Error('xhr_request_failed_without_guard')));
        xhr.send(JSON.stringify({ marker }));
      }),
    { marker: WRITE_FORBIDDEN, requestMethod: method }
  );
}

async function mutateWithForm(page: Page): Promise<GuardedResult> {
  const responsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/__playwright_real_contract__/POST/form';
  });
  await page.evaluate(() => {
    const frame = document.createElement('iframe');
    frame.name = 'real-write-probe-frame';
    document.body.append(frame);

    const form = document.createElement('form');
    form.action = '/api/__playwright_real_contract__/POST/form';
    form.method = 'post';
    form.target = frame.name;
    const field = document.createElement('input');
    field.name = 'marker';
    field.value = 'real_profile_write_forbidden';
    form.append(field);
    document.body.append(form);
    form.submit();
  });
  return resultFromResponse(await responsePromise);
}

function expectLocallyRejected(result: GuardedResult): void {
  expect(result).toEqual({
    status: 460,
    detail: WRITE_FORBIDDEN,
    guard: WRITE_FORBIDDEN
  });
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

const COMPLETE_PUBLICATIONS = [
  {
    strategyId: 'lhb_shortline',
    tradeDate: '2026-07-19',
    totalReturnPct: 52.4,
    contractId: 'lhb-contract',
    publishId: 'lhb-publish',
    artifactVersion: 'lhb-v1'
  },
  {
    strategyId: 'mid_trend',
    tradeDate: '2026-07-18',
    totalReturnPct: 49.12,
    contractId: 'mid-contract',
    publishId: 'mid-publish',
    artifactVersion: 'mid-v2'
  },
  {
    strategyId: 'tech_bottleneck',
    tradeDate: '2026-07-17',
    totalReturnPct: 70.5,
    contractId: 'tech-contract',
    publishId: 'tech-publish',
    artifactVersion: 'tech-v3'
  }
] as const;

async function installSnapshotResponses(
  realApi: RealApiControl,
  conflictStrategyId?: string
): Promise<void> {
  realApi.stubGet('/api/platform/display-date', {
    json: {
      display_trade_date: '2026-07-20',
      candidate_trade_date: '2026-07-21'
    }
  });
  realApi.stubGet('/api/strategies/catalog', {
    json: {
      items: COMPLETE_PUBLICATIONS.map((publication) => ({
        strategy_id: publication.strategyId,
        latest_metrics: {
          performance_as_of_date: publication.tradeDate,
          total_return_pct: publication.totalReturnPct,
          contract_id: publication.contractId,
          publish_id: publication.publishId,
          artifact_version: publication.artifactVersion
        }
      }))
    }
  });
  realApi.stubGet('/api/review-queue', {
    json: {
      groups: COMPLETE_PUBLICATIONS.map((publication) => ({
        bucket: `strategy:${publication.strategyId}`,
        items: [
          {
            strategy_id: publication.strategyId,
            performance_as_of_date: publication.tradeDate,
            total_return_pct: publication.totalReturnPct,
            contract_id: publication.contractId,
            publish_id:
              publication.strategyId === conflictStrategyId
                ? `${publication.publishId}-conflict`
                : publication.publishId,
            artifact_version: publication.artifactVersion
          }
        ]
      }))
    }
  });
}

test('@read-only-contract GET control reaches the real API', async ({ page }) => {
  await openProbeDocument(page);

  const result = await page.evaluate(async () => {
    const response = await fetch('/api/platform/display-date', {
      headers: { 'x-request-id': 'playwright-real-read-control' }
    });
    return {
      ok: response.ok,
      status: response.status,
      requestId: response.headers.get('x-request-id'),
      payload: (await response.json()) as unknown
    };
  });

  expect(result.ok).toBe(true);
  expect(result.status).toBe(200);
  expect(result.requestId).toBe('playwright-real-read-control');
  expect(result.payload).toEqual(expect.objectContaining({ display_trade_date: expect.any(String) }));
});

test('@read-only-contract exact API root GET reaches the server and is recorded', async ({
  page,
  realHttpEvidence,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(
    'Failed to load resource: the server responded with a status of 404 (Not Found)'
  );
  await openProbeDocument(page);

  const result = await page.evaluate(async () => {
    const response = await fetch('/api', {
      headers: { 'x-request-id': 'playwright-real-api-root-get' }
    });
    return {
      status: response.status,
      guard: response.headers.get('x-playwright-real-guard'),
      requestId: response.headers.get('x-request-id')
    };
  });

  expect([200, 404]).toContain(result.status);
  expect(result.guard).toBeNull();
  expect(result.requestId).toBe('playwright-real-api-root-get');
  await expect
    .poll(() =>
      realHttpEvidence.exchanges.filter(
        (exchange) => exchange.method === 'GET' && new URL(exchange.url).pathname === '/api'
      )
    )
    .toEqual([
      expect.objectContaining({
        responseStatus: result.status,
        responseHeaders: expect.objectContaining({
          'x-request-id': 'playwright-real-api-root-get'
        })
      })
    ]);
});

test('@read-only-contract exact API root writes are locally rejected with or without query', async ({
  page,
  realHttpEvidence,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(
    'Failed to load resource: the server responded with a status of 404 (Not Found)'
  );
  await openProbeDocument(page);

  expectLocallyRejected(await postWithFetch(page, '/api'));
  expectLocallyRejected(await postWithFetch(page, '/api?probe=1'));
  await expect
    .poll(() =>
      realHttpEvidence.exchanges.filter(
        (exchange) => exchange.method === 'POST' && new URL(exchange.url).pathname === '/api'
      )
    )
    .toEqual([
      expect.objectContaining({
        responseStatus: 460,
        responseHeaders: expect.objectContaining({
          'x-playwright-real-guard': WRITE_FORBIDDEN
        })
      }),
      expect.objectContaining({
        responseStatus: 460,
        responseHeaders: expect.objectContaining({
          'x-playwright-real-guard': WRITE_FORBIDDEN
        })
      })
    ]);
});

test('@read-only-contract API sibling paths are neither guarded nor recorded as API traffic', async ({
  page,
  realHttpEvidence,
  runtimePolicy
}) => {
  runtimePolicy.consoleErrors.push(
    'Failed to load resource: the server responded with a status of 404 (Not Found)'
  );
  await openProbeDocument(page);

  const result = await page.evaluate(async () => {
    const response = await fetch('/apix', { method: 'POST' });
    return {
      status: response.status,
      guard: response.headers.get('x-playwright-real-guard')
    };
  });

  expect(result.status).toBe(404);
  expect(result.guard).toBeNull();
  expect(realHttpEvidence.exchanges).toEqual([]);
});

test('@read-only-contract shared header evidence is deterministic and secret-free', async ({
  page,
  realApi,
  realHttpEvidence
}) => {
  await openProbeDocument(page);
  await page.context().addCookies([
    { name: 'real_secret_cookie', value: 'cookie-secret-value', url: new URL(page.url()).origin }
  ]);
  realApi.stubGet('/api/__playwright_real_header_probe__', {
    status: 200,
    headers: {
      authorization: 'Bearer response-secret-value',
      'set-cookie': 'server_secret_cookie=set-cookie-secret-value; Path=/',
      'x-request-id': 'playwright-real-header-probe'
    },
    json: { ok: true }
  });

  await page.evaluate(async () => {
    await fetch('/api/__playwright_real_header_probe__', {
      headers: {
        authorization: 'Bearer request-secret-value',
        'x-api-key': 'api-key-secret-value'
      }
    });
  });
  await expect.poll(() => realHttpEvidence.exchanges.length).toBe(1);

  const serialized = serializeRealHttpEvidence(realHttpEvidence);
  expect(serialized).not.toContain('request-secret-value');
  expect(serialized).not.toContain('response-secret-value');
  expect(serialized).not.toContain('api-key-secret-value');
  expect(serialized).not.toContain('cookie-secret-value');
  expect(serialized).not.toContain('set-cookie-secret-value');
  expect(serialized).toContain('playwright-real-header-probe');
  expect(serialized).toContain('[REDACTED]');
});

test('@read-only-contract APIRequestContext cannot bypass the write guard', async ({
  page,
  request
}) => {
  await expect(async () => request.post('/api/__playwright_real_contract__/request')).rejects.toThrow(
    WRITE_FORBIDDEN
  );
  await expect(async () =>
    page.request.delete('/api/__playwright_real_contract__/page-request')
  ).rejects.toThrow(WRITE_FORBIDDEN);

  const control = await request.get('/api/platform/display-date', {
    headers: { 'x-request-id': 'playwright-real-request-context-control' }
  });
  expect(control.ok()).toBe(true);
  expect(control.headers()['x-request-id']).toBe('playwright-real-request-context-control');
});

test('@read-only-contract API route overrides cannot take precedence over the guard', async ({
  context,
  page
}) => {
  const handler = async (route: Route) => {
    await route.fulfill({ json: { bypassed: true } });
  };
  const attempt = async (
    install: () => Promise<unknown>,
    cleanup: () => Promise<unknown>
  ): Promise<string> => {
    try {
      await install();
    } catch (error) {
      return errorText(error);
    }
    await cleanup();
    return '';
  };

  const pageError = await attempt(
    () => page.route('/api', handler),
    () => page.unroute('/api', handler)
  );
  const contextError = await attempt(
    () => context.route('/api?probe=1', handler),
    () => context.unroute('/api?probe=1', handler)
  );
  const nextPage = await context.newPage();
  const nextPageError = await attempt(
    () => nextPage.route('/api/__playwright_real_new_page_bypass__', handler),
    () => nextPage.unroute('/api/__playwright_real_new_page_bypass__', handler)
  );
  await nextPage.close();

  expect([pageError, contextError, nextPageError]).toEqual([
    ROUTE_OVERRIDE_FORBIDDEN,
    ROUTE_OVERRIDE_FORBIDDEN,
    ROUTE_OVERRIDE_FORBIDDEN
  ]);

  await openProbeDocument(page);
  expectLocallyRejected(await mutateWithFetch(page, 'PUT'));
});

test('@read-only-contract unscoped request.newContext is forbidden in the real worker', async ({
  playwright
}) => {
  let created: Awaited<ReturnType<typeof playwright.request.newContext>> | undefined;
  let message = '';
  try {
    created = await playwright.request.newContext();
  } catch (error) {
    message = errorText(error);
  } finally {
    await created?.dispose();
  }

  expect(message).toBe(UNSCOPED_REQUEST_FORBIDDEN);
});

test('@read-only-contract service workers stay blocked and cannot send an API write', async ({
  context,
  page,
  realHttpEvidence
}) => {
  await openProbeDocument(page);
  let serviceWorkerScriptRequests = 0;
  await page.route('/__playwright_real_write_probe_sw.js', (route) => {
    serviceWorkerScriptRequests += 1;
    return route.fulfill({
      contentType: 'application/javascript',
      body:
        "self.addEventListener('install', event => event.waitUntil(" +
        "fetch('/api/__playwright_real_contract__/POST/service-worker', { method: 'POST' })" +
        '));'
    });
  });

  await page.evaluate(async () => {
    try {
      await navigator.serviceWorker.register('/__playwright_real_write_probe_sw.js');
    } catch {
      // Browsers may reject or return an inert registration when Playwright blocks workers.
    }
  });

  expect(serviceWorkerScriptRequests).toBe(0);
  expect(context.serviceWorkers()).toHaveLength(0);
  expectLocallyRejected(await mutateWithForm(page));
  await expect
    .poll(() =>
      realHttpEvidence.exchanges.filter((exchange) =>
        exchange.url.includes('/api/__playwright_real_contract__/POST/')
      )
    )
    .toEqual([
      expect.objectContaining({
        method: 'POST',
        responseStatus: 460,
        responseHeaders: expect.objectContaining({
          'x-playwright-real-guard': WRITE_FORBIDDEN
        })
      })
    ]);
});

test('@read-only-contract snapshot parser accepts matching explicit identities', async ({
  page,
  realApi
}) => {
  await openProbeDocument(page);
  await installSnapshotResponses(realApi);

  await expect(loadAuthoritativeSnapshot(page)).resolves.toEqual({
    displayTradeDate: '2026-07-20',
    candidateTradeDate: '2026-07-21',
    strategies: COMPLETE_PUBLICATIONS
  });
});

test('@read-only-contract snapshot parser fails closed on publication identity conflict', async ({
  page,
  realApi
}) => {
  await openProbeDocument(page);
  await installSnapshotResponses(realApi, 'lhb_shortline');

  await expect(loadAuthoritativeSnapshot(page)).rejects.toThrow(
    'authoritative_snapshot_publication_identity_conflict:lhb_shortline'
  );
});

test('@read-only-contract POST form is rejected before the server', async ({ page }) => {
  await openProbeDocument(page);
  expectLocallyRejected(await mutateWithForm(page));
});

test('@read-only-contract PATCH XHR is rejected before the server', async ({ page }) => {
  await openProbeDocument(page);
  expectLocallyRejected(await mutateWithXhr(page, 'PATCH'));
});

test('@read-only-contract PUT fetch is rejected before the server', async ({ page }) => {
  await openProbeDocument(page);
  expectLocallyRejected(await mutateWithFetch(page, 'PUT'));
});

test('@read-only-contract DELETE fetch is rejected before the server', async ({ page }) => {
  await openProbeDocument(page);
  expectLocallyRejected(await mutateWithFetch(page, 'DELETE'));
});
