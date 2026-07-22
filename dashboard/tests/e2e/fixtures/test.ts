import { expect, test as base } from '@playwright/test';

import {
  expectNoFatalRuntimeErrors,
  expectNoUnhandledApiRoutes,
  isExpectedNavigationCancellation,
  sanitizeRuntimeEvidenceText,
  serializeRuntimeEvidence
} from '../assertions/runtime';
import { bindRuntimeEvidenceToPage } from './mockPlatformApi';

export type RuntimeEvidence = {
  consoleErrors: string[];
  pageErrors: string[];
  failedRequests: Array<{ method: string; url: string; failure: string }>;
  unhandledApiRoutes: string[];
};

export type RuntimeEvidencePattern = string | RegExp;

export type RuntimeEvidenceAllowlist = {
  consoleErrors: RuntimeEvidencePattern[];
  pageErrors: RuntimeEvidencePattern[];
  failedRequests: RuntimeEvidencePattern[];
  unhandledApiRoutes: RuntimeEvidencePattern[];
};

type RuntimeFixtures = {
  runtimeEvidence: RuntimeEvidence;
  runtimePolicy: RuntimeEvidenceAllowlist;
};

function freshEvidence(): RuntimeEvidence {
  return {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    unhandledApiRoutes: []
  };
}

function freshPolicy(): RuntimeEvidenceAllowlist {
  return {
    consoleErrors: [],
    pageErrors: [],
    failedRequests: [],
    unhandledApiRoutes: []
  };
}

function safeUrl(rawUrl: string): string {
  try {
    const url = new URL(rawUrl);
    return url.origin === 'null' ? `${url.protocol}${url.pathname}` : `${url.origin}${url.pathname}`;
  } catch {
    return rawUrl.split(/[?#]/, 1)[0];
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export const test = base.extend<RuntimeFixtures>({
  runtimePolicy: async ({}, use) => {
    await use(freshPolicy());
  },
  runtimeEvidence: [
    async ({ page, runtimePolicy }, use, testInfo) => {
      const evidence = freshEvidence();
      const unbindRuntimeEvidence = bindRuntimeEvidenceToPage(page, evidence);
      const onConsole = (message: { type(): string; text(): string }) => {
        if (message.type() === 'error') {
          evidence.consoleErrors.push(sanitizeRuntimeEvidenceText(message.text()));
        }
      };
      const onPageError = (error: Error) => {
        evidence.pageErrors.push(sanitizeRuntimeEvidenceText(error.message));
      };
      const onRequestFailed = (request: {
        method(): string;
        url(): string;
        failure(): { errorText: string } | null;
      }) => {
        const method = request.method().toUpperCase();
        const url = request.url();
        const failure = request.failure()?.errorText ?? 'request_failed';
        if (isExpectedNavigationCancellation(method, url, failure)) return;
        evidence.failedRequests.push({
          method,
          url: sanitizeRuntimeEvidenceText(safeUrl(url)),
          failure: sanitizeRuntimeEvidenceText(failure)
        });
      };
      const onResponse = (response: {
        status(): number;
        url(): string;
        request(): { method(): string };
      }) => {
        const status = response.status();
        const url = new URL(response.url());
        if (status >= 500 && url.pathname.startsWith('/api/')) {
          evidence.failedRequests.push({
            method: response.request().method().toUpperCase(),
            url: sanitizeRuntimeEvidenceText(safeUrl(response.url())),
            failure: `HTTP ${status}`
          });
        }
      };

      page.on('console', onConsole);
      page.on('pageerror', onPageError);
      page.on('requestfailed', onRequestFailed);
      page.on('response', onResponse);

      try {
        await use(evidence);
      } finally {
        page.off('console', onConsole);
        page.off('pageerror', onPageError);
        page.off('requestfailed', onRequestFailed);
        page.off('response', onResponse);
        unbindRuntimeEvidence();

        await testInfo.attach('runtime-evidence.json', {
          body: serializeRuntimeEvidence(evidence),
          contentType: 'application/json'
        });

        const assertionErrors: string[] = [];
        try {
          expectNoUnhandledApiRoutes(evidence, runtimePolicy);
        } catch (error) {
          assertionErrors.push(errorMessage(error));
        }
        try {
          expectNoFatalRuntimeErrors(evidence, runtimePolicy);
        } catch (error) {
          assertionErrors.push(errorMessage(error));
        }
        if (assertionErrors.length > 0) {
          throw new Error(assertionErrors.join('\n\n'));
        }
      }
    },
    { auto: true }
  ]
});

export { expect };
