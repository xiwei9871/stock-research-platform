import type { Locator, Page } from '@playwright/test';

type ValueRule = 'number' | 'ratio-as-percent' | 'percent';

function quoted(value: string): string {
  return JSON.stringify(value);
}

function decodedPathname(url: URL): string {
  try {
    return decodeURIComponent(url.pathname);
  } catch {
    return url.pathname;
  }
}

function patternMatches(pattern: RegExp, value: string): boolean {
  const stablePattern = new RegExp(pattern.source, pattern.flags.replace(/[gy]/g, ''));
  return stablePattern.test(value);
}

function compactText(value: string | null): string {
  return (value ?? '').replace(/\s+/g, ' ').trim();
}

function rawValueText(value: number | string | null): string {
  return typeof value === 'string' ? quoted(value) : String(value);
}

function finiteValue(value: number | string | null): number | null {
  if (value === null) return null;
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  const trimmed = value.trim();
  if (trimmed === '') return null;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatValue(value: number, rule: ValueRule): string {
  const scaled = rule === 'ratio-as-percent' ? value * 100 : value;
  const formatted = scaled.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: rule === 'number'
  });
  return rule === 'number' ? formatted : `${formatted}%`;
}

function normalizedRenderedValue(value: string): string {
  return compactText(value).replace(/,/g, '').replace(/^\+/, '');
}

function normalizedExpectedValue(value: string): string {
  return value.replace(/,/g, '').replace(/^\+/, '');
}

function valueMatches(rendered: string, expected: string): boolean {
  return normalizedRenderedValue(rendered) === normalizedExpectedValue(expected);
}

function valueAppearsInText(rendered: string, expected: string): boolean {
  const normalizedText = compactText(rendered).replace(/,/g, '');
  const normalizedExpected = expected.replace(/,/g, '');
  const candidates = [normalizedExpected, `+${normalizedExpected}`];
  return candidates.some((candidate) => normalizedText.includes(candidate));
}

export async function expectRouteContext(
  page: Page,
  expected: { path: RegExp; assetId?: string; source?: string }
): Promise<void> {
  const url = new URL(page.url());
  const pathname = decodedPathname(url);
  const assetMatch = pathname.match(/(?:^|\/)stock\/([^/]+)$/);
  const actualAssetId = assetMatch?.[1] ?? '';
  const actualSource = url.searchParams.get('source') ?? '';
  const mismatches: string[] = [];

  if (!patternMatches(expected.path, pathname)) {
    mismatches.push(`- path: expected ${String(expected.path)}, rendered ${pathname}`);
  }
  if (expected.assetId !== undefined && expected.assetId !== actualAssetId) {
    mismatches.push(
      `- assetId: expected ${quoted(expected.assetId)}, rendered ${quoted(actualAssetId)}`
    );
  }
  if (expected.source !== undefined && expected.source !== actualSource) {
    mismatches.push(
      `- source: expected ${quoted(expected.source)}, rendered ${quoted(actualSource)}`
    );
  }

  if (mismatches.length > 0) {
    throw new Error(`Route context mismatch:\n${mismatches.join('\n')}`);
  }
}

export async function expectStateRestored(
  page: Page,
  expected: { searchQuery?: string; selectedText?: string }
): Promise<void> {
  const mismatches: string[] = [];

  if (expected.searchQuery !== undefined) {
    const search = page.getByRole('combobox', { name: 'Global search' });
    const actualQuery = (await search.count()) === 1 ? await search.inputValue() : '';
    if (actualQuery !== expected.searchQuery) {
      mismatches.push(
        `- searchQuery: expected ${quoted(expected.searchQuery)}, rendered ${quoted(actualQuery)}`
      );
    }
  }

  if (expected.selectedText !== undefined) {
    const selectedTexts = await page
      .locator('[aria-selected="true"]:visible')
      .allInnerTexts()
      .then((values) => values.map((value) => compactText(value)).filter(Boolean));
    if (!selectedTexts.includes(expected.selectedText)) {
      mismatches.push(
        `- selectedText: expected ${quoted(expected.selectedText)}, rendered ${quoted(selectedTexts.join(' | '))}`
      );
    }
  }

  if (mismatches.length > 0) {
    throw new Error(`Restored state mismatch:\n${mismatches.join('\n')}`);
  }
}

export async function expectApiUiConsistency(
  actual: number | string | null,
  locator: Locator,
  rule: 'number' | 'ratio-as-percent' | 'percent'
): Promise<void> {
  const renderedText = compactText(await locator.innerText());
  const numericValue = finiteValue(actual);

  if (numericValue === null) {
    throw new Error(
      `API/UI consistency mismatch: raw value ${rawValueText(actual)}; rendered text ` +
        `${quoted(renderedText)}; rule ${rule}; expected a finite numeric value.`
    );
  }

  const expectedText = formatValue(numericValue, rule);
  if (!valueMatches(renderedText, expectedText)) {
    throw new Error(
      `API/UI consistency mismatch: raw value ${rawValueText(actual)}; rendered text ` +
        `${quoted(renderedText)}; rule ${rule}; expected ${quoted(expectedText)}.`
    );
  }
}

export async function expectPublicationConsistency(
  card: Locator,
  expected: {
    contractId: string;
    publishId: string;
    tradeDate: string;
    totalReturnPct: number;
  }
): Promise<void> {
  const renderedText = compactText(await card.innerText());
  const strategyId = (await card.getAttribute('data-strategy-id')) ?? '<missing>';
  const mismatches: string[] = [];
  const hasExactText = async (text: string) =>
    (await card.getByText(text, { exact: true }).count()) > 0;

  if (!(await hasExactText(expected.contractId))) {
    mismatches.push(
      `- contractId: expected ${quoted(expected.contractId)}, rendered text did not contain it`
    );
  }
  if (!(await hasExactText(expected.publishId))) {
    mismatches.push(
      `- publishId: expected ${quoted(expected.publishId)}, rendered text did not contain it`
    );
  }
  if (!(await hasExactText(expected.tradeDate))) {
    mismatches.push(
      `- tradeDate: expected ${quoted(expected.tradeDate)}, rendered text did not contain it`
    );
  }

  const numericValue = finiteValue(expected.totalReturnPct);
  const expectedReturn = numericValue === null ? null : formatValue(numericValue, 'percent');
  if (expectedReturn === null || !valueAppearsInText(renderedText, expectedReturn)) {
    const returnExpectation =
      expectedReturn === null
        ? 'expected a finite numeric value.'
        : `expected ${quoted(expectedReturn)}.`;
    mismatches.push(
      `- totalReturnPct: raw value ${rawValueText(expected.totalReturnPct)}; rendered text ` +
        `${quoted(renderedText)}; rule percent; ${returnExpectation}`
    );
  }

  if (mismatches.length > 0) {
    throw new Error(
      `Publication consistency mismatch for strategy ID ${quoted(strategyId)} and ` +
        `publish ID ${quoted(expected.publishId)}:\n${mismatches.join('\n')}`
    );
  }
}
