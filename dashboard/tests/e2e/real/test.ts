import type {
  APIRequestContext,
  APIResponse,
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

type RealFixtures = {
  realHttpEvidence: RealHttpEvidence;
  realReadOnlyGuard: void;
};

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

function isApiUrl(rawUrl: string, baseURL?: string): boolean {
  return safeUrl(rawUrl, baseURL)?.pathname.startsWith('/api/') ?? false;
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

async function rejectWriteRoute(route: Route): Promise<void> {
  const request = route.request();
  const method = request.method().toUpperCase();
  const url = new URL(request.url());
  if (!url.pathname.startsWith('/api/') || ALLOWED_METHODS.has(method)) {
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
  runtimePolicy: RuntimeEvidenceAllowlist
): Promise<() => Promise<void>> {
  allowGuardConsoleErrors(runtimePolicy);
  const restoreRequestContext = guardApiRequestContext(context.request, baseURL);
  await context.route('**/api/**', rejectWriteRoute);
  return async () => {
    await context.unroute('**/api/**', rejectWriteRoute);
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
    if (!url.pathname.startsWith('/api/')) return;
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

export const test = sharedTest.extend<RealFixtures>({
  request: async ({ playwright }, use, testInfo) => {
    const baseURL = baseURLFromProject(testInfo);
    const rawRequest = await playwright.request.newContext({ baseURL });
    const restore = guardApiRequestContext(rawRequest, baseURL);
    try {
      await use(rawRequest);
    } finally {
      restore();
      await rawRequest.dispose();
    }
  },
  realReadOnlyGuard: [
    async ({ context, runtimePolicy }, use, testInfo) => {
      const uninstall = await installContextGuard(
        context,
        baseURLFromProject(testInfo),
        runtimePolicy
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
    async ({ context, page }, use, testInfo) => {
      const evidence: RealHttpEvidence = { exchanges: [] };
      const captureErrors: string[] = [];
      const pending = new Set<Promise<void>>();
      const boundPages = new Set<Page>();
      const onResponse = (response: Response) => {
        const capture = addResponseEvidence(response, evidence, captureErrors);
        pending.add(capture);
        void capture.finally(() => pending.delete(capture));
      };
      const bindPage = (target: Page) => {
        if (boundPages.has(target)) return;
        boundPages.add(target);
        target.on('response', onResponse);
      };
      for (const target of context.pages()) bindPage(target);
      bindPage(page);
      context.on('page', bindPage);
      try {
        await use(evidence);
      } finally {
        context.off('page', bindPage);
        for (const target of boundPages) target.off('response', onResponse);
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
