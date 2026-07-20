import type { Page, Response } from '@playwright/test';

import { loadAuthoritativeSnapshot } from './authoritativeSnapshot';
import { expect, serializeRealHttpEvidence, test } from './test';

const WRITE_FORBIDDEN = 'real_profile_write_forbidden';
const PROBE_DOCUMENT = '/__playwright_real_contract__';

type GuardedResult = {
  status: number;
  detail: string;
  guard: string | null;
};

async function openProbeDocument(page: Page): Promise<void> {
  await page.route(`**${PROBE_DOCUMENT}`, async (route) => {
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

async function installSnapshotResponses(page: Page, conflictStrategyId?: string): Promise<void> {
  await page.route('**/api/platform/display-date', (route) =>
    route.fulfill({
      json: {
        display_trade_date: '2026-07-20',
        candidate_trade_date: '2026-07-21'
      }
    })
  );
  await page.route('**/api/strategies/catalog', (route) =>
    route.fulfill({
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
    })
  );
  await page.route('**/api/review-queue?*', (route) =>
    route.fulfill({
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
    })
  );
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

test('@read-only-contract shared header evidence is deterministic and secret-free', async ({
  page,
  realHttpEvidence
}) => {
  await openProbeDocument(page);
  await page.context().addCookies([
    { name: 'real_secret_cookie', value: 'cookie-secret-value', url: new URL(page.url()).origin }
  ]);
  await page.route('**/api/__playwright_real_header_probe__', (route) =>
    route.fulfill({
      status: 200,
      headers: {
        authorization: 'Bearer response-secret-value',
        'set-cookie': 'server_secret_cookie=set-cookie-secret-value; Path=/',
        'x-request-id': 'playwright-real-header-probe'
      },
      json: { ok: true }
    })
  );

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

test('@read-only-contract snapshot parser accepts matching explicit identities', async ({ page }) => {
  await openProbeDocument(page);
  await installSnapshotResponses(page);

  await expect(loadAuthoritativeSnapshot(page)).resolves.toEqual({
    displayTradeDate: '2026-07-20',
    candidateTradeDate: '2026-07-21',
    strategies: COMPLETE_PUBLICATIONS
  });
});

test('@read-only-contract snapshot parser fails closed on publication identity conflict', async ({
  page
}) => {
  await openProbeDocument(page);
  await installSnapshotResponses(page, 'lhb_shortline');

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
