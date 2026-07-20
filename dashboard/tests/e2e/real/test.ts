import type {
  APIRequestContext,
  APIResponse,
  Browser,
  BrowserContext,
  Page,
  Request,
  Response,
  Route
} from '@playwright/test';

import { sanitizeRuntimeEvidenceText } from '../assertions/runtime';
import {
  expect,
  test as sharedTest,
  type RuntimeEvidenceAllowlist
} from '../fixtures/test';

export const REAL_PROFILE_WRITE_FORBIDDEN = 'real_profile_write_forbidden';
export const REAL_PROFILE_API_ROUTE_OVERRIDE_FORBIDDEN =
  'real_profile_api_route_override_forbidden';
export const REAL_PROFILE_UNSCOPED_REQUEST_CONTEXT_FORBIDDEN =
  'real_profile_unscoped_request_context_forbidden';
export const REAL_PROFILE_UNSCOPED_BROWSER_CONTEXT_FORBIDDEN =
  'real_profile_unscoped_browser_context_forbidden';
const ALLOWED_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
const REDACTED = '[REDACTED]';

type Headers = Record<string, string>;

export type RealHttpExchange = {
  method: string;
  url: string;
  requestHeaders: Headers;
  responseStatus: number;
  responseHeaders: Headers;
};

export type RealHttpEvidence = {
  exchanges: RealHttpExchange[];
};

export type RealApiGetResponse = {
  status?: number;
  json: unknown;
  headers?: Headers;
};

export type RealApiControl = {
  stubGet(pathname: string, response: RealApiGetResponse): void;
  responseFor(pathname: string): RealApiGetResponse | undefined;
};

type RealFixtures = {
  realApi: RealApiControl;
  realBrowserContextGuard: void;
  realHttpEvidence: RealHttpEvidence;
  realReadOnlyGuard: void;
};

type RequestContextFactory = (
  options?: Record<string, unknown>
) => Promise<APIRequestContext>;

type RealWorkerFixtures = {
  realRequestContextGuard: void;
};

const scopedRequestContextFactories = new WeakMap<object, RequestContextFactory>();

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function safeUrl(rawUrl: string, baseURL?: string): URL | null {
  try {
    return new URL(rawUrl, baseURL);
  } catch {
    return null;
  }
}

function safeEvidenceUrl(rawUrl: string): string {
  const url = safeUrl(rawUrl);
  return url
    ? sanitizeRuntimeEvidenceText(`${url.origin}${url.pathname}`)
    : sanitizeRuntimeEvidenceText(rawUrl.split(/[?#]/, 1)[0]);
}

function isApiPath(pathname: string): boolean {
  return pathname === '/api' || pathname.startsWith('/api/');
}

function decodePathLayer(pathname: string): string {
  try {
    return decodeURIComponent(pathname);
  } catch {
    return pathname.replace(/%([0-9a-f]{2})/gi, (_match, encoded: string) => {
      const value = Number.parseInt(encoded, 16);
      return value <= 0x7f ? String.fromCharCode(value) : `%${encoded.toUpperCase()}`;
    });
  }
}

function hasMalformedPercent(value: string): boolean {
  return /%(?![0-9a-f]{2})/i.test(value);
}

function isApiUrl(rawUrl: string, baseURL?: string): boolean {
  const url = safeUrl(rawUrl, baseURL);
  if (!url) return false;
  let pathname = url.pathname;
  for (let layer = 0; layer < 8; layer += 1) {
    if (isApiPath(pathname)) return true;
    if (pathname.startsWith('/api%') && hasMalformedPercent(pathname.slice(4))) return true;
    const decoded = decodePathLayer(pathname);
    if (decoded === pathname) return false;
    pathname = decoded;
  }
  return isApiPath(pathname) ||
    (pathname.startsWith('/api%') && hasMalformedPercent(pathname.slice(4)));
}

function createRealApiControl(): RealApiControl {
  const responses = new Map<string, RealApiGetResponse>();
  return {
    stubGet(pathname, response) {
      if (!pathname.startsWith('/api/') || /[*{}]/.test(pathname) || pathname.includes('?')) {
        throw new Error('real_profile_get_stub_requires_exact_api_pathname');
      }
      responses.set(pathname, response);
    },
    responseFor(pathname) {
      return responses.get(pathname);
    }
  };
}

function isSensitiveHeader(name: string): boolean {
  return /(?:^|-)(?:authorization|cookie|set-cookie|password|passwd|token|secret|api-key|csrf-token)(?:-|$)/i.test(
    name
  );
}

function sanitizeHeaders(headers: Headers): Headers {
  return Object.fromEntries(
    Object.entries(headers)
      .map(([rawName, rawValue]) => {
        const name = rawName.toLowerCase();
        const value = isSensitiveHeader(name)
          ? REDACTED
          : sanitizeRuntimeEvidenceText(String(rawValue));
        return [name, value] as const;
      })
      .sort(([left], [right]) => compareStrings(left, right))
  );
}

export function serializeRealHttpEvidence(evidence: RealHttpEvidence): string {
  const exchanges = evidence.exchanges
    .map((exchange) => ({
      ...exchange,
      requestHeaders: sanitizeHeaders(exchange.requestHeaders),
      responseHeaders: sanitizeHeaders(exchange.responseHeaders)
    }))
    .sort((left, right) =>
      compareStrings(
        `${left.method}\u0000${left.url}\u0000${left.responseStatus}\u0000${JSON.stringify(left.requestHeaders)}\u0000${JSON.stringify(left.responseHeaders)}`,
        `${right.method}\u0000${right.url}\u0000${right.responseStatus}\u0000${JSON.stringify(right.requestHeaders)}\u0000${JSON.stringify(right.responseHeaders)}`
      )
    );
  return `${JSON.stringify({ exchanges }, null, 2)}\n`;
}

function forbiddenError(method: string, rawUrl: string): Error {
  const pathname = safeUrl(rawUrl)?.pathname ?? rawUrl.split(/[?#]/, 1)[0];
  return new Error(
    `${REAL_PROFILE_WRITE_FORBIDDEN}: ${method.toUpperCase()} ${sanitizeRuntimeEvidenceText(pathname)}`
  );
}

function assertReadOnlyApiRequest(method: string, rawUrl: string, baseURL?: string): void {
  const normalizedMethod = method.toUpperCase();
  if (isApiUrl(rawUrl, baseURL) && !ALLOWED_METHODS.has(normalizedMethod)) {
    throw forbiddenError(normalizedMethod, rawUrl);
  }
}

function guardApiRequestContext(request: APIRequestContext, baseURL?: string): () => void {
  const mutable = request as unknown as Record<string, unknown>;
  const restorers: Array<() => void> = [];
  const replace = (name: 'fetch' | 'delete' | 'patch' | 'post' | 'put', replacement: unknown) => {
    const hadOwnProperty = Object.prototype.hasOwnProperty.call(mutable, name);
    const previous = mutable[name];
    mutable[name] = replacement;
    restorers.push(() => {
      if (hadOwnProperty) mutable[name] = previous;
      else delete mutable[name];
    });
  };

  const originalFetch = request.fetch.bind(request);
  replace('fetch', (urlOrRequest: string | Request, options: { method?: string } = {}) => {
    const url = typeof urlOrRequest === 'string' ? urlOrRequest : urlOrRequest.url();
    const method = options.method ?? (typeof urlOrRequest === 'string' ? 'GET' : urlOrRequest.method());
    assertReadOnlyApiRequest(method, url, baseURL);
    return originalFetch(urlOrRequest, options);
  });

  for (const method of ['delete', 'patch', 'post', 'put'] as const) {
    const original = request[method].bind(request) as (
      url: string,
      options?: Record<string, unknown>
    ) => Promise<APIResponse>;
    replace(method, (url: string, options?: Record<string, unknown>) => {
      assertReadOnlyApiRequest(method, url, baseURL);
      return original(url, options);
    });
  }

  return () => {
    for (const restore of restorers.reverse()) restore();
  };
}

function guardResponseHeaders(method: string, pathname: string): Headers {
  const requestId = `playwright-real-guard-${method.toLowerCase()}-${pathname
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-|-$/g, '')}`;
  return {
    'cache-control': 'no-store',
    'x-playwright-real-guard': REAL_PROFILE_WRITE_FORBIDDEN,
    'x-request-id': requestId
  };
}

async function rejectWriteRoute(route: Route, realApi: RealApiControl): Promise<void> {
  const request = route.request();
  const method = request.method().toUpperCase();
  const url = new URL(request.url());
  if (!isApiUrl(request.url())) {
    await route.fallback();
    return;
  }

  if (method === 'GET') {
    const response = realApi.responseFor(url.pathname);
    if (response) {
      await route.fulfill({
        status: response.status ?? 200,
        headers: { 'content-type': 'application/json', ...response.headers },
        body: JSON.stringify(response.json)
      });
      return;
    }
  }

  if (ALLOWED_METHODS.has(method)) {
    await route.fallback();
    return;
  }

  await route.fulfill({
    status: 460,
    contentType: 'application/json',
    headers: guardResponseHeaders(method, url.pathname),
    body: JSON.stringify({
      detail: REAL_PROFILE_WRITE_FORBIDDEN,
      method,
      pathname: sanitizeRuntimeEvidenceText(url.pathname)
    })
  });
}

type RouteOwner = Page | BrowserContext;
type RoutePattern = Parameters<Page['route']>[0];

function routePatternMayMatchApi(pattern: RoutePattern, baseURL?: string): boolean {
  if (typeof pattern !== 'string') return true;
  if (/[*{}]/.test(pattern)) return true;
  const url = safeUrl(pattern, baseURL);
  if (!url) return true;
  return url.pathname === '/api' || url.pathname.startsWith('/api/');
}

function assertRoutePatternAllowed(pattern: RoutePattern, baseURL?: string): void {
  if (routePatternMayMatchApi(pattern, baseURL)) {
    throw new Error(REAL_PROFILE_API_ROUTE_OVERRIDE_FORBIDDEN);
  }
}

function guardRouteOverrides(owner: RouteOwner, baseURL?: string): () => void {
  const mutable = owner as unknown as Record<string, unknown>;
  const hadOwnRoute = Object.prototype.hasOwnProperty.call(mutable, 'route');
  const hadOwnUnroute = Object.prototype.hasOwnProperty.call(mutable, 'unroute');
  const hadOwnUnrouteAll = Object.prototype.hasOwnProperty.call(mutable, 'unrouteAll');
  const previousRoute = mutable.route;
  const previousUnroute = mutable.unroute;
  const previousUnrouteAll = mutable.unrouteAll;
  const originalRoute = owner.route.bind(owner);
  const originalUnroute = owner.unroute.bind(owner);
  const originalUnrouteAll = owner.unrouteAll.bind(owner);

  mutable.route = (pattern: RoutePattern, ...rest: unknown[]) => {
    assertRoutePatternAllowed(pattern, baseURL);
    return (originalRoute as unknown as (...args: unknown[]) => Promise<unknown>)(pattern, ...rest);
  };
  mutable.unroute = (pattern: RoutePattern, ...rest: unknown[]) => {
    assertRoutePatternAllowed(pattern, baseURL);
    return (originalUnroute as (...args: unknown[]) => Promise<void>)(pattern, ...rest);
  };
  mutable.unrouteAll = () => {
    throw new Error(REAL_PROFILE_API_ROUTE_OVERRIDE_FORBIDDEN);
  };

  return () => {
    if (hadOwnRoute) mutable.route = previousRoute;
    else delete mutable.route;
    if (hadOwnUnroute) mutable.unroute = previousUnroute;
    else delete mutable.unroute;
    if (hadOwnUnrouteAll) mutable.unrouteAll = previousUnrouteAll;
    else delete mutable.unrouteAll;
  };
}

function guardBrowserContextCreation(browser: Browser): () => void {
  const mutable = browser as unknown as Record<string, unknown>;
  const hadOwnNewContext = Object.prototype.hasOwnProperty.call(mutable, 'newContext');
  const hadOwnNewPage = Object.prototype.hasOwnProperty.call(mutable, 'newPage');
  const previousNewContext = mutable.newContext;
  const previousNewPage = mutable.newPage;
  mutable.newContext = async () => {
    throw new Error(REAL_PROFILE_UNSCOPED_BROWSER_CONTEXT_FORBIDDEN);
  };
  mutable.newPage = async () => {
    throw new Error(REAL_PROFILE_UNSCOPED_BROWSER_CONTEXT_FORBIDDEN);
  };

  return () => {
    if (hadOwnNewContext) mutable.newContext = previousNewContext;
    else delete mutable.newContext;
    if (hadOwnNewPage) mutable.newPage = previousNewPage;
    else delete mutable.newPage;
  };
}

function baseURLFromProject(testInfo: { project: { use: Record<string, unknown> } }): string | undefined {
  const value = testInfo.project.use.baseURL;
  return typeof value === 'string' ? value : undefined;
}

function allowGuardConsoleErrors(runtimePolicy: RuntimeEvidenceAllowlist): void {
  runtimePolicy.consoleErrors.push(
    'Failed to load resource: the server responded with a status of 460 ()',
    'Failed to load resource: the server responded with a status of 460 (Unknown)',
    'Failed to load resource: the server responded with a status of 460 (Unknown Status)'
  );
}

async function installContextGuard(
  context: BrowserContext,
  baseURL: string | undefined,
  runtimePolicy: RuntimeEvidenceAllowlist,
  realApi: RealApiControl
): Promise<() => Promise<void>> {
  allowGuardConsoleErrors(runtimePolicy);
  const restoreRequestContext = guardApiRequestContext(context.request, baseURL);
  const originalContextRoute = context.route.bind(context);
  const originalContextUnroute = context.unroute.bind(context);
  const routeHandler = (route: Route) => rejectWriteRoute(route, realApi);
  const apiRoutePattern = (url: URL) => isApiUrl(url.href);
  await originalContextRoute(apiRoutePattern, routeHandler);
  const restoreContextRoutes = guardRouteOverrides(context, baseURL);
  const pageRouteRestorers = new Map<Page, () => void>();
  const guardPage = (page: Page) => {
    if (!pageRouteRestorers.has(page)) {
      pageRouteRestorers.set(page, guardRouteOverrides(page, baseURL));
    }
  };
  for (const page of context.pages()) guardPage(page);
  context.on('page', guardPage);
  return async () => {
    context.off('page', guardPage);
    for (const restore of pageRouteRestorers.values()) restore();
    restoreContextRoutes();
    await originalContextUnroute(apiRoutePattern, routeHandler);
    restoreRequestContext();
  };
}

function addResponseEvidence(
  response: Response,
  evidence: RealHttpEvidence,
  captureErrors: string[]
): Promise<void> {
  return (async () => {
    const request: Request = response.request();
    const url = new URL(response.url());
    if (!isApiUrl(response.url())) return;
    try {
      const [requestHeaders, responseHeaders] = await Promise.all([
        request.allHeaders(),
        response.allHeaders()
      ]);
      evidence.exchanges.push({
        method: request.method().toUpperCase(),
        url: safeEvidenceUrl(response.url()),
        requestHeaders: sanitizeHeaders(requestHeaders),
        responseStatus: response.status(),
        responseHeaders: sanitizeHeaders(responseHeaders)
      });
    } catch (error) {
      captureErrors.push(
        sanitizeRuntimeEvidenceText(error instanceof Error ? error.message : String(error))
      );
    }
  })();
}

export const test = sharedTest.extend<RealFixtures, RealWorkerFixtures>({
  realRequestContextGuard: [
    async ({ playwright }, use) => {
      const request = playwright.request as unknown as Record<string, unknown>;
      const hadOwnNewContext = Object.prototype.hasOwnProperty.call(request, 'newContext');
      const previousNewContext = request.newContext;
      const originalNewContext = playwright.request.newContext.bind(
        playwright.request
      ) as unknown as RequestContextFactory;
      request.newContext = async () => {
        throw new Error(REAL_PROFILE_UNSCOPED_REQUEST_CONTEXT_FORBIDDEN);
      };
      scopedRequestContextFactories.set(playwright.request, originalNewContext);
      try {
        await use();
      } finally {
        scopedRequestContextFactories.delete(playwright.request);
        if (hadOwnNewContext) request.newContext = previousNewContext;
        else delete request.newContext;
      }
    },
    { scope: 'worker', auto: true }
  ],
  request: async ({ playwright, realRequestContextGuard: _guard }, use, testInfo) => {
    const baseURL = baseURLFromProject(testInfo);
    const factory = scopedRequestContextFactories.get(playwright.request);
    if (!factory) throw new Error('real_profile_request_context_guard_not_initialized');
    const rawRequest = await factory({ baseURL });
    const restore = guardApiRequestContext(rawRequest, baseURL);
    try {
      await use(rawRequest);
    } finally {
      restore();
      await rawRequest.dispose();
    }
  },
  realApi: async ({}, use) => {
    await use(createRealApiControl());
  },
  realBrowserContextGuard: [
    async ({ browser, context }, use) => {
      void context;
      const restore = guardBrowserContextCreation(browser);
      try {
        await use();
      } finally {
        restore();
      }
    },
    { auto: true }
  ],
  realReadOnlyGuard: [
    async ({ context, realApi, runtimePolicy }, use, testInfo) => {
      const uninstall = await installContextGuard(
        context,
        baseURLFromProject(testInfo),
        runtimePolicy,
        realApi
      );
      try {
        await use();
      } finally {
        await uninstall();
      }
    },
    { auto: true }
  ],
  realHttpEvidence: [
    async ({ context }, use, testInfo) => {
      const evidence: RealHttpEvidence = { exchanges: [] };
      const captureErrors: string[] = [];
      const pending = new Set<Promise<void>>();
      const onResponse = (response: Response) => {
        const capture = addResponseEvidence(response, evidence, captureErrors);
        pending.add(capture);
        void capture.finally(() => pending.delete(capture));
      };
      context.on('response', onResponse);
      try {
        await use(evidence);
      } finally {
        context.off('response', onResponse);
        await Promise.all([...pending]);
        await testInfo.attach('real-http-evidence.json', {
          body: serializeRealHttpEvidence(evidence),
          contentType: 'application/json'
        });
        if (captureErrors.length > 0) {
          throw new Error(
            `real_http_evidence_capture_failed:\n${captureErrors.sort(compareStrings).join('\n')}`
          );
        }
      }
    },
    { auto: true }
  ]
});

export { expect };
