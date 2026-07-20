import type { APIRequestContext, Page, Response, TestInfo } from '@playwright/test';

import platformValidationInventory from '../../../../config/platform_validation_routes.json' with {
  type: 'json'
};
import {
  sanitizeRuntimeEvidenceText,
  serializeRuntimeEvidence
} from '../assertions/runtime';
import type { RuntimeEvidence } from '../fixtures/test';
import { expect, test } from './test';

type JsonObject = Record<string, unknown>;

type InventoryApi = {
  access: string;
  census_scope: string;
  method: string;
  path: string;
};

type InventoryLandmark = {
  name: string;
  role: Parameters<Page['getByRole']>[0];
};

type InventoryItem = {
  id: string;
  label: string;
  landmark: InventoryLandmark;
  primary_apis: InventoryApi[];
  profiles: string[];
  reachable: boolean;
  route: string;
  route_params: Record<string, string>;
};

type ApiObservation = {
  method: string;
  path: string;
  requestId: string | null;
  status: number;
};

type CensusRecord = {
  actualUrl: string;
  apiResponses: ApiObservation[];
  consoleErrors: string[];
  failedRequests: RuntimeEvidence['failedRequests'];
  failure: string | null;
  failureAttachments: string[];
  inventoryId: string;
  pageErrors: string[];
  route: string;
  status: 'passed' | 'failed';
  unhandledApiRoutes: string[];
};

function objectValue(value: unknown, code: string): JsonObject {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(code);
  }
  return value as JsonObject;
}

function stringValue(value: unknown, code: string): string {
  if (typeof value !== 'string' || value.trim() === '') throw new Error(code);
  return value;
}

function stringArray(value: unknown, code: string): string[] {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== 'string')) {
    throw new Error(code);
  }
  return value as string[];
}

function readInventoryItems(): InventoryItem[] {
  const inventory = objectValue(
    platformValidationInventory as unknown,
    'real_route_census_invalid_inventory'
  );
  if (!Array.isArray(inventory.items)) throw new Error('real_route_census_invalid_inventory_items');
  return inventory.items.flatMap((rawItem, index) => {
    const item = objectValue(rawItem, `real_route_census_invalid_item:${index}`);
    const id = stringValue(item.id, `real_route_census_missing_id:${index}`);
    const profiles = stringArray(item.profiles, `real_route_census_invalid_profiles:${id}`);
    if (item.reachable !== true || !profiles.includes('real')) return [];
    const landmark = objectValue(item.landmark, `real_route_census_missing_landmark:${id}`);
    const routeParams = objectValue(item.route_params, `real_route_census_invalid_route_params:${id}`);
    if (!Array.isArray(item.primary_apis)) {
      throw new Error(`real_route_census_invalid_primary_apis:${id}`);
    }
    return [{
      id,
      label: stringValue(item.label, `real_route_census_missing_label:${id}`),
      landmark: {
        name: stringValue(landmark.name, `real_route_census_missing_landmark_name:${id}`),
        role: stringValue(
          landmark.role,
          `real_route_census_missing_landmark_role:${id}`
        ) as InventoryLandmark['role']
      },
      primary_apis: item.primary_apis.map((rawApi, apiIndex) => {
        const api = objectValue(rawApi, `real_route_census_invalid_api:${id}:${apiIndex}`);
        return {
          access: stringValue(api.access, `real_route_census_missing_api_access:${id}:${apiIndex}`),
          census_scope: stringValue(
            api.census_scope,
            `real_route_census_missing_api_scope:${id}:${apiIndex}`
          ),
          method: stringValue(
            api.method,
            `real_route_census_missing_api_method:${id}:${apiIndex}`
          ).toUpperCase(),
          path: stringValue(api.path, `real_route_census_missing_api_path:${id}:${apiIndex}`)
        };
      }),
      profiles,
      reachable: true,
      route: stringValue(item.route, `real_route_census_missing_route:${id}`),
      route_params: Object.fromEntries(
        Object.entries(routeParams).map(([key, value]) => [
          key,
          stringValue(value, `real_route_census_invalid_route_param:${id}:${key}`)
        ])
      )
    }];
  });
}

const REAL_ROUTE_ITEMS = readInventoryItems();

async function apiJson(
  request: APIRequestContext,
  path: string,
  requestId: string
): Promise<JsonObject> {
  const response = await request.get(path, { headers: { 'x-request-id': requestId } });
  if (!response.ok()) {
    throw new Error(`real_route_census_resolver_http_error:${path}:${response.status()}`);
  }
  return objectValue(await response.json(), `real_route_census_resolver_invalid_json:${path}`);
}

function firstNonEmptyString(container: JsonObject, fields: string[]): string | null {
  for (const field of fields) {
    const value = container[field];
    if (typeof value === 'string' && value.trim() !== '') return value.trim();
  }
  return null;
}

async function authoritativeStockAssetId(request: APIRequestContext): Promise<string> {
  const themesPayload = await apiJson(
    request,
    '/api/research/theme-decomposition/themes',
    'playwright-real-census-stock-themes'
  );
  const themes = Array.isArray(themesPayload.items) ? themesPayload.items : [];
  for (const rawTheme of themes) {
    if (typeof rawTheme !== 'object' || rawTheme === null || Array.isArray(rawTheme)) continue;
    const themeId = firstNonEmptyString(rawTheme as JsonObject, ['theme_id']);
    if (!themeId) continue;
    const companiesPayload = await apiJson(
      request,
      `/api/research/theme-decomposition/themes/${encodeURIComponent(themeId)}/companies`,
      `playwright-real-census-stock-theme-${themeId}`
    );
    const companies = Array.isArray(companiesPayload.items) ? companiesPayload.items : [];
    for (const rawCompany of companies) {
      if (typeof rawCompany !== 'object' || rawCompany === null || Array.isArray(rawCompany)) continue;
      const assetId = firstNonEmptyString(rawCompany as JsonObject, [
        'company_code',
        'asset_id',
        'canonical_asset_id'
      ]);
      if (assetId) return assetId;
    }
  }

  const reviewPayload = await apiJson(
    request,
    '/api/review-queue?limit=10&lookback_days=90',
    'playwright-real-census-stock-review-queue'
  );
  const groups = Array.isArray(reviewPayload.groups) ? reviewPayload.groups : [];
  for (const rawGroup of groups) {
    if (typeof rawGroup !== 'object' || rawGroup === null || Array.isArray(rawGroup)) continue;
    const items = Array.isArray((rawGroup as JsonObject).items)
      ? ((rawGroup as JsonObject).items as unknown[])
      : [];
    for (const rawItem of items) {
      if (typeof rawItem !== 'object' || rawItem === null || Array.isArray(rawItem)) continue;
      const assetId = firstNonEmptyString(rawItem as JsonObject, [
        'canonical_asset_id',
        'asset_id'
      ]);
      if (assetId) return assetId;
    }
  }

  const techPayload = await apiJson(
    request,
    '/api/research/tech-bottleneck/review-universe/stocks?limit=1',
    'playwright-real-census-stock-tech-review'
  );
  const techItems = Array.isArray(techPayload.items) ? techPayload.items : [];
  for (const rawItem of techItems) {
    if (typeof rawItem !== 'object' || rawItem === null || Array.isArray(rawItem)) continue;
    const assetId = firstNonEmptyString(rawItem as JsonObject, ['asset_id', 'stock_code']);
    if (assetId) return assetId;
  }

  throw new Error('real_route_census_authoritative_stock_asset_id_missing');
}

async function resolveRoute(
  item: InventoryItem,
  request: APIRequestContext
): Promise<{ params: Record<string, string>; route: string }> {
  const params: Record<string, string> = {};
  for (const [routeParam, resolver] of Object.entries(item.route_params)) {
    if (resolver !== 'authoritative_stock_asset_id') {
      throw new Error(`real_route_census_unknown_route_param_resolver:${item.id}:${resolver}`);
    }
    params[routeParam] = await authoritativeStockAssetId(request);
  }

  let route = item.route;
  for (const [routeParam, value] of Object.entries(params)) {
    route = route.replaceAll(`{${routeParam}}`, encodeURIComponent(value));
  }
  if (/\{[^}]+\}/.test(route)) {
    throw new Error(`real_route_census_unresolved_route_param:${item.id}:${route}`);
  }
  return { params, route };
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function apiPathPattern(template: string, params: Record<string, string>): RegExp {
  let pattern = escapeRegExp(template);
  for (const [name, value] of Object.entries(params)) {
    pattern = pattern.replaceAll(`\\{${escapeRegExp(name)}\\}`, escapeRegExp(encodeURIComponent(value)));
  }
  pattern = pattern.replace(/\\\{[^}]+\\\}/g, '[^/]+');
  return new RegExp(`^${pattern}$`);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function runtimeFailures(evidence: RuntimeEvidence): string[] {
  const failures: string[] = [];
  if (evidence.consoleErrors.length > 0) failures.push('consoleErrors');
  if (evidence.pageErrors.length > 0) failures.push('pageErrors');
  if (evidence.failedRequests.length > 0) failures.push('failedRequests');
  if (evidence.unhandledApiRoutes.length > 0) failures.push('unhandledApiRoutes');
  return failures;
}

async function attachFailureScreenshot(
  page: Page,
  testInfo: TestInfo,
  record: CensusRecord
): Promise<void> {
  const attachmentName = 'route-census-failure.png';
  const path = testInfo.outputPath(attachmentName);
  try {
    await page.screenshot({ path, fullPage: true });
    await testInfo.attach(attachmentName, { path, contentType: 'image/png' });
    record.failureAttachments.push(attachmentName);
  } catch (error) {
    record.failureAttachments.push(`screenshot-capture-error:${errorMessage(error)}`);
  }
}

const ANSI_CSI_PATTERN = /(?:\u001B\[|\u009B)[0-?]*[ -/]*[@-~]/g;

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function canonicalEvidenceText(value: string): string {
  return sanitizeRuntimeEvidenceText(value.replace(ANSI_CSI_PATTERN, ''));
}

function canonicalRuntimeEvidence(record: CensusRecord): RuntimeEvidence {
  const withoutAnsi: RuntimeEvidence = {
    consoleErrors: record.consoleErrors.map((value) => value.replace(ANSI_CSI_PATTERN, '')),
    pageErrors: record.pageErrors.map((value) => value.replace(ANSI_CSI_PATTERN, '')),
    failedRequests: record.failedRequests.map((entry) => ({
      method: entry.method.replace(ANSI_CSI_PATTERN, ''),
      url: entry.url.replace(ANSI_CSI_PATTERN, ''),
      failure: entry.failure.replace(ANSI_CSI_PATTERN, '')
    })),
    unhandledApiRoutes: record.unhandledApiRoutes.map((value) =>
      value.replace(ANSI_CSI_PATTERN, '')
    )
  };
  return JSON.parse(serializeRuntimeEvidence(withoutAnsi)) as RuntimeEvidence;
}

function serializeCensusRecordForAttachment(record: CensusRecord): string {
  const runtime = canonicalRuntimeEvidence(record);
  const canonical: CensusRecord = {
    actualUrl: canonicalEvidenceText(record.actualUrl),
    apiResponses: record.apiResponses
      .map((observation) => ({
        method: canonicalEvidenceText(observation.method),
        path: canonicalEvidenceText(observation.path),
        requestId:
          observation.requestId === null
            ? null
            : canonicalEvidenceText(observation.requestId),
        status: observation.status
      }))
      .sort((left, right) =>
        compareStrings(
          `${left.method}\u0000${left.path}\u0000${left.status}\u0000${left.requestId ?? ''}`,
          `${right.method}\u0000${right.path}\u0000${right.status}\u0000${right.requestId ?? ''}`
        )
      ),
    consoleErrors: runtime.consoleErrors,
    failedRequests: runtime.failedRequests,
    failure: record.failure === null ? null : canonicalEvidenceText(record.failure),
    failureAttachments: record.failureAttachments.map(canonicalEvidenceText).sort(compareStrings),
    inventoryId: canonicalEvidenceText(record.inventoryId),
    pageErrors: runtime.pageErrors,
    route: canonicalEvidenceText(record.route),
    status: record.status,
    unhandledApiRoutes: runtime.unhandledApiRoutes
  };
  return `${JSON.stringify(canonical, null, 2)}\n`;
}

test('route census evidence serialization is deterministic, ANSI-free, and secret-free @route-census-contract', () => {
  const first: CensusRecord = {
    actualUrl: 'http://127.0.0.1:5174/stock/000001.SZ?token=raw-url-secret',
    apiResponses: [
      {
        method: 'GET',
        path: '/api/token/raw-path-secret',
        requestId: '\u001b[35mrequest-secret=raw-request-secret\u001b[0m',
        status: 200
      },
      {
        method: 'GET',
        path: '/api/platform/summary',
        requestId: 'request-b',
        status: 200
      }
    ],
    consoleErrors: [
      '\u001b[31;1mconsole-b\u001b[0m token=raw-console-secret',
      '\u009b2Kconsole-a'
    ],
    failedRequests: [
      {
        method: 'GET',
        url: 'https://example.test/api/data?api_key=raw-query-secret',
        failure: '\u001b[1msecret=raw-failure-secret\u001b[0m'
      },
      {
        method: 'GET',
        url: 'https://example.test/api/alpha',
        failure: '\u009b2Kfailure-a'
      }
    ],
    failure: '\u001b[31mauthorization: Bearer raw-authorization-secret\u001b[0m',
    failureAttachments: [
      '\u001b[32mscreenshot-capture-error:token=raw-attachment-secret\u001b[0m',
      'route-census-failure.png'
    ],
    inventoryId: 'secret=raw-inventory-secret',
    pageErrors: ['page-b password=raw-password-secret', '\u001b[2Jpage-a'],
    route: '/stock/{asset_id}?csrf_token=raw-route-secret',
    status: 'failed',
    unhandledApiRoutes: [
      'GET /api/z?access_token=raw-access-secret',
      '\u001b[33mGET /api/a\u001b[0m'
    ]
  };
  const second: CensusRecord = {
    ...first,
    apiResponses: [...first.apiResponses].reverse(),
    consoleErrors: [...first.consoleErrors].reverse(),
    failedRequests: [...first.failedRequests].reverse(),
    failureAttachments: [...first.failureAttachments].reverse(),
    pageErrors: [...first.pageErrors].reverse(),
    unhandledApiRoutes: [...first.unhandledApiRoutes].reverse()
  };

  const firstSerialized = serializeCensusRecordForAttachment(first);
  const secondSerialized = serializeCensusRecordForAttachment(second);

  expect(firstSerialized).toBe(secondSerialized);
  expect(firstSerialized).not.toMatch(/[\u001b\u009b]/);
  for (const secret of [
    'raw-url-secret',
    'raw-path-secret',
    'raw-request-secret',
    'raw-console-secret',
    'raw-query-secret',
    'raw-failure-secret',
    'raw-authorization-secret',
    'raw-attachment-secret',
    'raw-inventory-secret',
    'raw-password-secret',
    'raw-route-secret',
    'raw-access-secret'
  ]) {
    expect(firstSerialized).not.toContain(secret);
  }
  expect(firstSerialized).toContain('[REDACTED]');
});

for (const item of REAL_ROUTE_ITEMS) {
  test(`route census ${item.id}: ${item.label} @real @route-census`, async ({
    page,
    request,
    runtimeEvidence
  }, testInfo) => {
    const observations: ApiObservation[] = [];
    const routeLoadApis = item.primary_apis.filter((api) => api.census_scope === 'route_load');
    for (const api of routeLoadApis) {
      if (api.access !== 'read' || !['GET', 'HEAD', 'OPTIONS'].includes(api.method)) {
        throw new Error(`real_route_census_mutating_route_load_api:${item.id}:${api.method}:${api.path}`);
      }
    }

    const record: CensusRecord = {
      actualUrl: '',
      apiResponses: observations,
      consoleErrors: runtimeEvidence.consoleErrors,
      failedRequests: runtimeEvidence.failedRequests,
      failure: null,
      failureAttachments: [],
      inventoryId: item.id,
      pageErrors: runtimeEvidence.pageErrors,
      route: item.route,
      status: 'passed',
      unhandledApiRoutes: runtimeEvidence.unhandledApiRoutes
    };
    let failure: unknown = null;

    try {
      const resolved = await resolveRoute(item, request);
      record.route = resolved.route;
      const expectedApis = routeLoadApis.map((api) => ({
        ...api,
        pattern: apiPathPattern(api.path, resolved.params)
      }));
      const onResponse = (response: Response) => {
        const requestForResponse = response.request();
        const method = requestForResponse.method().toUpperCase();
        const path = new URL(response.url()).pathname;
        if (!expectedApis.some((api) => api.method === method && api.pattern.test(path))) return;
        observations.push({
          method,
          path,
          requestId: response.headers()['x-request-id'] ?? null,
          status: response.status()
        });
      };
      page.on('response', onResponse);
      try {
        await page.goto(resolved.route);
        await expect(
          page.getByRole(item.landmark.role, { name: item.landmark.name })
        ).toBeVisible();
        await expect
          .poll(
            () =>
              expectedApis.every((api) =>
                observations.some(
                  (observation) =>
                    observation.method === api.method && api.pattern.test(observation.path)
                )
              ),
            { timeout: 15_000 }
          )
          .toBe(true);

        const missingOrFailed = expectedApis.filter((api) => {
          const matches = observations.filter(
            (observation) => observation.method === api.method && api.pattern.test(observation.path)
          );
          return matches.length === 0 || matches.every((observation) => observation.status >= 400);
        });
        if (missingOrFailed.length > 0) {
          throw new Error(
            `real_route_census_primary_api_failed:${item.id}:${missingOrFailed
              .map((api) => `${api.method} ${api.path}`)
              .join(',')}`
          );
        }
      } finally {
        page.off('response', onResponse);
      }

      const evidenceFailures = runtimeFailures(runtimeEvidence);
      if (evidenceFailures.length > 0) {
        throw new Error(`real_route_census_runtime_errors:${item.id}:${evidenceFailures.join(',')}`);
      }
    } catch (error) {
      failure = error;
      record.status = 'failed';
      record.failure = errorMessage(error);
      await attachFailureScreenshot(page, testInfo, record);
    } finally {
      record.actualUrl = page.url();
      await testInfo.attach('route-census.json', {
        body: serializeCensusRecordForAttachment(record),
        contentType: 'application/json'
      });
    }

    if (failure) throw failure;
  });
}
