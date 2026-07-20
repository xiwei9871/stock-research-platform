import type { Page } from '@playwright/test';

import type {
  RuntimeEvidence,
  RuntimeEvidenceAllowlist,
  RuntimeEvidencePattern
} from '../fixtures/test';

function matchesAllowlist(value: string, patterns: readonly RuntimeEvidencePattern[] = []): boolean {
  return patterns.some((pattern) => {
    if (typeof pattern === 'string') return value === pattern;
    pattern.lastIndex = 0;
    return pattern.test(value);
  });
}

function failedRequestLabel(entry: RuntimeEvidence['failedRequests'][number]): string {
  return `${entry.method} ${entry.url} — ${entry.failure}`;
}

function listUnexpected(label: string, values: readonly string[]): string[] {
  return values.length === 0 ? [] : [`${label}:`, ...values.map((value) => `- ${value}`)];
}

export function expectNoFatalRuntimeErrors(
  evidence: RuntimeEvidence,
  allowlist: Partial<RuntimeEvidenceAllowlist> = {}
): void {
  const unexpectedConsoleErrors = evidence.consoleErrors.filter(
    (value) => !matchesAllowlist(value, allowlist.consoleErrors)
  );
  const unexpectedPageErrors = evidence.pageErrors.filter(
    (value) => !matchesAllowlist(value, allowlist.pageErrors)
  );
  const unexpectedFailedRequests = evidence.failedRequests
    .map(failedRequestLabel)
    .filter((value) => !matchesAllowlist(value, allowlist.failedRequests));
  const details = [
    ...listUnexpected('consoleErrors', unexpectedConsoleErrors),
    ...listUnexpected('pageErrors', unexpectedPageErrors),
    ...listUnexpected('failedRequests', unexpectedFailedRequests)
  ];

  if (details.length > 0) {
    throw new Error(`Unexpected fatal runtime evidence:\n${details.join('\n')}`);
  }
}

export function expectNoUnhandledApiRoutes(
  evidence: RuntimeEvidence,
  allowlist: Partial<RuntimeEvidenceAllowlist> = {}
): void {
  const unexpected = evidence.unhandledApiRoutes.filter(
    (value) => !matchesAllowlist(value, allowlist.unhandledApiRoutes)
  );

  if (unexpected.length > 0) {
    throw new Error(
      `Unexpected unhandled API routes:\n${unexpected.map((value) => `- ${value}`).join('\n')}`
    );
  }
}

export async function expectNoHorizontalOverflow(page: Page): Promise<void> {
  const widths = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth
  }));
  const allowedMaximum = widths.clientWidth + 1;

  if (widths.scrollWidth > allowedMaximum) {
    throw new Error(
      'Horizontal overflow detected: ' +
        `document.documentElement.scrollWidth=${widths.scrollWidth}, ` +
        `clientWidth=${widths.clientWidth}, allowedMaximum=${allowedMaximum}`
    );
  }
}
