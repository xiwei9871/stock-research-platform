import type { Page } from '@playwright/test';

import type {
  RuntimeEvidence,
  RuntimeEvidenceAllowlist,
  RuntimeEvidencePattern
} from '../fixtures/test';

function patternMatches(pattern: RegExp, value: string): boolean {
  pattern.lastIndex = 0;
  const match = pattern.exec(value);
  pattern.lastIndex = 0;
  return match !== null && match.index === 0 && match[0].length === value.length;
}

function hasUnescapedEndAnchor(source: string): boolean {
  if (!source.endsWith('$')) return false;
  let backslashCount = 0;
  for (let index = source.length - 2; index >= 0 && source[index] === '\\'; index -= 1) {
    backslashCount += 1;
  }
  return backslashCount % 2 === 0;
}

function hasTopLevelAlternation(source: string): boolean {
  let groupDepth = 0;
  let inCharacterClass = false;
  let escaped = false;

  for (const character of source) {
    if (escaped) {
      escaped = false;
      continue;
    }
    if (character === '\\') {
      escaped = true;
      continue;
    }
    if (character === '[') {
      inCharacterClass = true;
      continue;
    }
    if (character === ']' && inCharacterClass) {
      inCharacterClass = false;
      continue;
    }
    if (inCharacterClass) continue;
    if (character === '(') {
      groupDepth += 1;
      continue;
    }
    if (character === ')') {
      groupDepth = Math.max(0, groupDepth - 1);
      continue;
    }
    if (character === '|' && groupDepth === 0) return true;
  }

  return false;
}

function validateAllowlist(patterns: readonly RuntimeEvidencePattern[] = []): void {
  for (const pattern of patterns) {
    if (typeof pattern === 'string') continue;
    const matchesEverySample = [
      'runtime-console-error',
      'GET /api/unexpected',
      'POST https://example.test/api/data — net::ERR_FAILED',
      '{"pageErrors":["completely-different-value"]}'
    ].every((sample) => patternMatches(pattern, sample));
    if (matchesEverySample) {
      throw new Error(`Runtime evidence allowlist rejects match-all pattern: ${pattern.toString()}`);
    }
    if (
      !pattern.source.startsWith('^') ||
      !hasUnescapedEndAnchor(pattern.source) ||
      hasTopLevelAlternation(pattern.source) ||
      pattern.multiline
    ) {
      throw new Error(`Runtime evidence allowlist rejects unanchored pattern: ${pattern.toString()}`);
    }
  }
}

function matchesAllowlist(value: string, patterns: readonly RuntimeEvidencePattern[] = []): boolean {
  return patterns.some((pattern) => {
    if (typeof pattern === 'string') return value === pattern;
    return patternMatches(pattern, value);
  });
}

export function sanitizeRuntimeEvidenceText(value: string): string {
  const sensitiveKey =
    'authorization|password|passwd|token|access[_-]?token|refresh[_-]?token|' +
    'csrf[_-]?token|api[_-]?key|secret|cookie|set-cookie';
  return value
    .replace(/https?:\/\/[^\s"')]+/g, (rawUrl) => {
      try {
        const url = new URL(rawUrl);
        return `${url.origin}${url.pathname}`;
      } catch {
        return rawUrl.split(/[?#]/, 1)[0];
      }
    })
    .replace(/\b(set-cookie|cookie)(\s*:\s*)[^\r\n]*/gi, '$1$2[REDACTED]')
    .replace(
      new RegExp(`(["'])(${sensitiveKey})\\1(\\s*[:=]\\s*)(["'])(.*?)\\4`, 'gi'),
      (_match, quote: string, key: string, separator: string, valueQuote: string) =>
        `${quote}${key}${quote}${separator}${valueQuote}[REDACTED]${valueQuote}`
    )
    .replace(
      /\b(authorization)\b(\s*[:=]\s*)(?:bearer\s+)?([^\s,;}]+)/gi,
      '$1$2[REDACTED]'
    )
    .replace(
      new RegExp(`\\b(${sensitiveKey})\\b(\\s*[:=]\\s*)([^\\s,;}]+)`, 'gi'),
      '$1$2[REDACTED]'
    )
    .replace(
      new RegExp(`/(password|passwd|token|access[_-]?token|refresh[_-]?token|` +
        `csrf[_-]?token|api[_-]?key|secret)/([^/?#\\s]+)`, 'gi'),
      '/$1/[REDACTED]'
    );
}

function compareStrings(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

export function sanitizeRuntimeEvidence(evidence: RuntimeEvidence): RuntimeEvidence {
  const sanitize = (value: string) => sanitizeRuntimeEvidenceText(value);
  return {
    consoleErrors: evidence.consoleErrors.map(sanitize).sort(compareStrings),
    pageErrors: evidence.pageErrors.map(sanitize).sort(compareStrings),
    failedRequests: evidence.failedRequests
      .map((entry) => ({
        method: sanitize(entry.method),
        url: sanitize(entry.url),
        failure: sanitize(entry.failure)
      }))
      .sort((left, right) =>
        compareStrings(
          `${left.method}\u0000${left.url}\u0000${left.failure}`,
          `${right.method}\u0000${right.url}\u0000${right.failure}`
        )
      ),
    unhandledApiRoutes: evidence.unhandledApiRoutes.map(sanitize).sort(compareStrings)
  };
}

export function serializeRuntimeEvidence(evidence: RuntimeEvidence): string {
  return `${JSON.stringify(sanitizeRuntimeEvidence(evidence), null, 2)}\n`;
}

function failedRequestLabel(entry: RuntimeEvidence['failedRequests'][number]): string {
  return `${entry.method} ${entry.url} — ${entry.failure}`;
}

export function isExpectedNavigationCancellation(
  method: string,
  rawUrl: string,
  failure: string
): boolean {
  if (method.toUpperCase() !== 'GET' || failure !== 'net::ERR_ABORTED') return false;
  try {
    const pathname = new URL(rawUrl, 'http://playwright.local').pathname;
    return /^\/api\/assets\/[^/]+\/profile$/.test(pathname);
  } catch {
    return false;
  }
}

function listUnexpected(label: string, values: readonly string[]): string[] {
  return values.length === 0 ? [] : [`${label}:`, ...values.map((value) => `- ${value}`)];
}

export function expectNoFatalRuntimeErrors(
  evidence: RuntimeEvidence,
  allowlist: Partial<RuntimeEvidenceAllowlist> = {}
): void {
  validateAllowlist(allowlist.consoleErrors);
  validateAllowlist(allowlist.pageErrors);
  validateAllowlist(allowlist.failedRequests);
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
  validateAllowlist(allowlist.unhandledApiRoutes);
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
