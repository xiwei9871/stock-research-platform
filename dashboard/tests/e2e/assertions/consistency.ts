import { expect, type Locator, type Page } from '@playwright/test';

type ValueRule = 'number' | 'ratio-as-percent' | 'percent';
type StableField = {
  count: number;
  visible: boolean;
  rendered: string;
};
type PublicationSnapshot = {
  cardCount: number;
  cardVisible: boolean;
  strategyId: string;
  contractId: StableField;
  publishId: StableField;
  tradeDate: StableField;
  totalReturn: StableField;
};

const CONSISTENCY_TIMEOUT_MS = 750;
const DECIMAL_API_VALUE = /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/;

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
  if (!DECIMAL_API_VALUE.test(value)) return null;
  const parsed = Number(value);
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

function signVariants(value: string, numericValue: number): string[] {
  return numericValue >= 0 ? [value, `+${value}`] : [value];
}

function renderedValueCandidates(value: number, rule: ValueRule): string[] {
  const scaled = rule === 'ratio-as-percent' ? value * 100 : value;
  const plain = scaled.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: false
  });
  if (rule !== 'number') {
    return signVariants(`${plain}%`, scaled);
  }

  const grouped = scaled.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    useGrouping: true
  });
  return [...new Set([...signVariants(plain, scaled), ...signVariants(grouped, scaled)])];
}

function valueMatches(rendered: string, value: number, rule: ValueRule): boolean {
  return renderedValueCandidates(value, rule).includes(compactText(rendered));
}

async function waitForConsistency(predicate: () => Promise<boolean>): Promise<void> {
  try {
    await expect
      .poll(predicate, {
        timeout: CONSISTENCY_TIMEOUT_MS,
        intervals: [25, 50, 100]
      })
      .toBe(true);
  } catch {
    // The caller takes a final snapshot and emits the stable contract error.
  }
}

async function readRestoredState(page: Page) {
  const search = page.getByRole('combobox', { name: 'Global search' });
  const searchQuery = (await search.count()) === 1 ? await search.inputValue() : '';
  const selectedTexts = await page
    .locator('[aria-selected="true"]:visible')
    .allInnerTexts()
    .then((values) => values.map((value) => compactText(value)).filter(Boolean));
  return { searchQuery, selectedTexts };
}

async function readStableField(card: Locator, testId: string): Promise<StableField> {
  const field = card.getByTestId(testId);
  const count = await field.count();
  if (count === 0) return { count, visible: false, rendered: '<missing>' };
  if (count > 1) return { count, visible: false, rendered: `<ambiguous:${count}>` };
  if (!(await field.isVisible())) return { count, visible: false, rendered: '<hidden>' };
  return { count, visible: true, rendered: compactText(await field.innerText()) };
}

async function readPublication(card: Locator): Promise<PublicationSnapshot> {
  const cardCount = await card.count();
  return {
    cardCount,
    cardVisible: cardCount === 1 && (await card.isVisible()),
    strategyId:
      cardCount === 1
        ? ((await card.getAttribute('data-strategy-id')) ?? '<missing>')
        : `<ambiguous:${cardCount}>`,
    contractId: await readStableField(card, 'strategy-contract-id'),
    publishId: await readStableField(card, 'strategy-publish-id'),
    tradeDate: await readStableField(card, 'strategy-performance-date'),
    totalReturn: await readStableField(card, 'strategy-total-return')
  };
}

function isUniqueVisible(field: StableField): boolean {
  return field.count === 1 && field.visible;
}

function strategyIdFromContract(contractId: string): string {
  const separator = contractId.indexOf(':');
  return separator > 0 ? contractId.slice(0, separator) : contractId;
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
  await waitForConsistency(async () => {
    const state = await readRestoredState(page);
    return (
      (expected.searchQuery === undefined || state.searchQuery === expected.searchQuery) &&
      (expected.selectedText === undefined || state.selectedTexts.includes(expected.selectedText))
    );
  });

  const state = await readRestoredState(page);
  const mismatches: string[] = [];
  if (expected.searchQuery !== undefined && state.searchQuery !== expected.searchQuery) {
    mismatches.push(
      `- searchQuery: expected ${quoted(expected.searchQuery)}, rendered ${quoted(state.searchQuery)}`
    );
  }
  if (
    expected.selectedText !== undefined &&
    !state.selectedTexts.includes(expected.selectedText)
  ) {
    mismatches.push(
      `- selectedText: expected ${quoted(expected.selectedText)}, rendered ${quoted(state.selectedTexts.join(' | '))}`
    );
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
  if (!valueMatches(renderedText, numericValue, rule)) {
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
  const expectedStrategyId = strategyIdFromContract(expected.contractId);
  const numericValue = finiteValue(expected.totalReturnPct);
  const expectedReturn = numericValue === null ? null : formatValue(numericValue, 'percent');

  await waitForConsistency(async () => {
    const publication = await readPublication(card);
    return (
      publication.cardCount === 1 &&
      publication.cardVisible &&
      publication.strategyId === expectedStrategyId &&
      isUniqueVisible(publication.contractId) &&
      publication.contractId.rendered === expected.contractId &&
      isUniqueVisible(publication.publishId) &&
      publication.publishId.rendered === expected.publishId &&
      isUniqueVisible(publication.tradeDate) &&
      publication.tradeDate.rendered === expected.tradeDate &&
      isUniqueVisible(publication.totalReturn) &&
      numericValue !== null &&
      valueMatches(publication.totalReturn.rendered, numericValue, 'percent')
    );
  });

  const publication = await readPublication(card);
  const mismatches: string[] = [];
  if (publication.strategyId !== expectedStrategyId) {
    mismatches.push(
      `- strategyId: expected ${quoted(expectedStrategyId)}, rendered ${quoted(publication.strategyId)}`
    );
  }

  const appendIdentityMismatch = (
    label: 'contractId' | 'publishId' | 'tradeDate',
    field: StableField,
    expectedValue: string
  ) => {
    if (!isUniqueVisible(field)) {
      mismatches.push(
        `- ${label}: expected a unique visible field, rendered ${quoted(field.rendered)}`
      );
    } else if (field.rendered !== expectedValue) {
      mismatches.push(
        `- ${label}: expected ${quoted(expectedValue)}, rendered ${quoted(field.rendered)}`
      );
    }
  };
  appendIdentityMismatch('contractId', publication.contractId, expected.contractId);
  appendIdentityMismatch('publishId', publication.publishId, expected.publishId);
  appendIdentityMismatch('tradeDate', publication.tradeDate, expected.tradeDate);

  if (
    !isUniqueVisible(publication.totalReturn) ||
    numericValue === null ||
    !valueMatches(publication.totalReturn.rendered, numericValue, 'percent')
  ) {
    const returnExpectation =
      expectedReturn === null
        ? 'expected a finite numeric value.'
        : `expected ${quoted(expectedReturn)}.`;
    mismatches.push(
      `- totalReturnPct: raw value ${rawValueText(expected.totalReturnPct)}; rendered text ` +
        `${quoted(publication.totalReturn.rendered)}; rule percent; ${returnExpectation}`
    );
  }

  if (mismatches.length > 0) {
    throw new Error(
      `Publication consistency mismatch for strategy ID ${quoted(expectedStrategyId)} and ` +
        `publish ID ${quoted(expected.publishId)}:\n${mismatches.join('\n')}`
    );
  }
}
