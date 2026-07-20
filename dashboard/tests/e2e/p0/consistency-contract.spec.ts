import type { Page } from '@playwright/test';

import {
  expectApiUiConsistency,
  expectPublicationConsistency,
  expectRouteContext,
  expectStateRestored
} from '../assertions/consistency';
import { officialStrategies } from '../fixtures/officialStrategies';
import { expect, test } from '../fixtures/test';

async function setContractContent(
  page: Page,
  baseURL: string | undefined,
  path: string,
  content: string
) {
  if (!baseURL) throw new Error('Playwright baseURL is required for consistency contracts');
  const documentUrl = new URL(path, baseURL).toString();
  await page.route(documentUrl, (route) =>
    route.fulfill({ contentType: 'text/html; charset=utf-8', body: content })
  );
  await page.goto(documentUrl);
  await page.unroute(documentUrl);
}

async function captureErrorMessage(assertion: () => Promise<void>): Promise<string> {
  try {
    await assertion();
  } catch (error) {
    if (error instanceof Error) return error.message;
    throw error;
  }
  throw new Error('Expected consistency assertion to fail');
}

test('route context accepts decoded assets and exact source query @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/stock/300760.SZ?source=theme_research%2Fscientific_instruments',
    '<main>route context</main>'
  );

  await expectRouteContext(page, {
    path: /^\/stock\/300760\.SZ$/,
    assetId: '300760.SZ',
    source: 'theme_research/scientific_instruments'
  });
});

test('route context extracts the asset from a supported legacy stock route @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/tech-bottleneck/stock/300760.SZ?source=theme_research',
    '<main>legacy stock route context</main>'
  );

  await expectRouteContext(page, {
    path: /^\/tech-bottleneck\/stock\/300760\.SZ$/,
    assetId: '300760.SZ',
    source: 'theme_research'
  });
});

test('route context failure reports every expected and actual field @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/stock/600519.SH?source=global_search',
    '<main>route mismatch</main>'
  );

  expect(
    await captureErrorMessage(() =>
      expectRouteContext(page, {
        path: /^\/stock\/300760\.SZ$/,
        assetId: '300760.SZ',
        source: 'theme_research'
      })
    )
  ).toBe(
    'Route context mismatch:\n' +
      '- path: expected /^\\/stock\\/300760\\.SZ$/, rendered /stock/600519.SH\n' +
      '- assetId: expected "300760.SZ", rendered "600519.SH"\n' +
      '- source: expected "theme_research", rendered "global_search"'
  );
});

test('restored state reads the controlled search and accessible selected text @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/__consistency-state__',
    '<main><input aria-label="Global search" role="combobox" value="海能技术">' +
      '<nav><a role="option" aria-selected="true">科学仪器</a></nav>' +
      '<button role="tab" aria-selected="true"><span>研究事实表</span></button></main>'
  );

  await expectStateRestored(page, {
    searchQuery: '海能技术',
    selectedText: '研究事实表'
  });
});

test('restored state failure reports expected and rendered state @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/__consistency-state-mismatch__',
    '<main><input aria-label="Global search" role="combobox" value="鼎阳科技">' +
      '<button role="tab" aria-selected="true">公司映射</button></main>'
  );

  expect(
    await captureErrorMessage(() =>
      expectStateRestored(page, {
        searchQuery: '海能技术',
        selectedText: '研究事实表'
      })
    )
  ).toBe(
    'Restored state mismatch:\n' +
      '- searchQuery: expected "海能技术", rendered "鼎阳科技"\n' +
      '- selectedText: expected "研究事实表", rendered "公司映射"'
  );
});

test('API/UI rules format number, ratio, and percent without double scaling @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/__consistency-values__',
    '<main><strong id="number">-1,234.50</strong><strong id="ratio">+52.40%</strong>' +
      '<strong id="percent">52.40%</strong></main>'
  );

  await expectApiUiConsistency('-1234.5', page.locator('#number'), 'number');
  await expectApiUiConsistency(0.524, page.locator('#ratio'), 'ratio-as-percent');
  await expectApiUiConsistency('52.4', page.locator('#percent'), 'percent');
});

test('API/UI failure reports raw value, rendered text, and formatting rule @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/__consistency-value-mismatch__',
    '<main><strong id="return">175.29%</strong></main>'
  );

  expect(
    await captureErrorMessage(() =>
      expectApiUiConsistency(0.524, page.locator('#return'), 'ratio-as-percent')
    )
  ).toBe(
    'API/UI consistency mismatch: raw value 0.524; rendered text "175.29%"; ' +
      'rule ratio-as-percent; expected "52.40%".'
  );
});

test('API/UI assertions fail closed for null and invalid numeric values @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/__consistency-invalid-values__',
    '<main><strong id="empty">-</strong><strong id="invalid">NaN%</strong></main>'
  );

  expect(
    await captureErrorMessage(() =>
      expectApiUiConsistency(null, page.locator('#empty'), 'percent')
    )
  ).toBe(
    'API/UI consistency mismatch: raw value null; rendered text "-"; rule percent; ' +
      'expected a finite numeric value.'
  );
  expect(
    await captureErrorMessage(() =>
      expectApiUiConsistency('not-a-number', page.locator('#invalid'), 'percent')
    )
  ).toBe(
    'API/UI consistency mismatch: raw value "not-a-number"; rendered text "NaN%"; ' +
      'rule percent; expected a finite numeric value.'
  );
});

test('publication identity matches official fixture and visible card @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  const strategy = officialStrategies.lhb_shortline;
  await setContractContent(
    page,
    baseURL,
    '/__consistency-publication__',
    `<main><article data-strategy-id="${strategy.strategyId}">` +
      `<span>${strategy.contractId}</span> <span>${strategy.publishId}</span> ` +
      `<time>${strategy.performanceDate}</time> ` +
      '<strong data-testid="strategy-total-return">+52.40%</strong></article></main>'
  );

  await expectPublicationConsistency(page.locator('article'), {
    contractId: strategy.contractId,
    publishId: strategy.publishId,
    tradeDate: strategy.performanceDate,
    totalReturnPct: strategy.totalReturn
  });
});

test('publication failure reports strategy and publish identity plus values @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  const strategy = officialStrategies.lhb_shortline;
  await setContractContent(
    page,
    baseURL,
    '/__consistency-publication-mismatch__',
    `<main><article data-strategy-id="${strategy.strategyId}">` +
      `<span>${strategy.contractId}</span> <span>${strategy.publishId}-stale</span> ` +
      '<time>2026-07-18</time> ' +
      '<strong data-testid="strategy-total-return">175.29%</strong></article></main>'
  );

  expect(
    await captureErrorMessage(() =>
      expectPublicationConsistency(page.locator('article'), {
        contractId: strategy.contractId,
        publishId: strategy.publishId,
        tradeDate: strategy.performanceDate,
        totalReturnPct: strategy.totalReturn
      })
    )
  ).toBe(
    `Publication consistency mismatch for strategy ID "${strategy.strategyId}" and ` +
      `publish ID "${strategy.publishId}":\n` +
      `- publishId: expected "${strategy.publishId}", rendered text did not contain it\n` +
      `- tradeDate: expected "${strategy.performanceDate}", rendered text did not contain it\n` +
      '- totalReturnPct: raw value 52.4; rendered text "175.29%"; ' +
      'rule percent; expected "52.40%".'
  );
});

for (const [caseName, totalReturnText, otherMetricText] of [
  ['larger percentage token', '152.40%', '9.10%'],
  ['opposite sign', '-52.40%', '9.10%'],
  ['matching value in another field', '175.29%', '52.40%']
] as const) {
  test(`publication total return rejects ${caseName} @p0 @consistency-contract`, async ({
    page,
    baseURL
  }) => {
    const strategy = officialStrategies.lhb_shortline;
    await setContractContent(
      page,
      baseURL,
      `/__consistency-publication-return-${encodeURIComponent(caseName)}__`,
      `<main><article data-strategy-id="${strategy.strategyId}">` +
        `<span>${strategy.contractId}</span> <span>${strategy.publishId}</span> ` +
        `<time>${strategy.performanceDate}</time> ` +
        `<strong data-testid="strategy-total-return">${totalReturnText}</strong> ` +
        `<span data-testid="another-metric">${otherMetricText}</span></article></main>`
    );

    expect(
      await captureErrorMessage(() =>
        expectPublicationConsistency(page.locator('article'), {
          contractId: strategy.contractId,
          publishId: strategy.publishId,
          tradeDate: strategy.performanceDate,
          totalReturnPct: strategy.totalReturn
        })
      )
    ).toBe(
      `Publication consistency mismatch for strategy ID "${strategy.strategyId}" and ` +
        `publish ID "${strategy.publishId}":\n` +
        `- totalReturnPct: raw value 52.4; rendered text "${totalReturnText}"; ` +
        'rule percent; expected "52.40%".'
    );
  });
}

test('official strategy fixtures are distinct and exclude the regressed LHB value @p0 @consistency-contract', () => {
  const strategies = Object.values(officialStrategies);

  expect(strategies.map((strategy) => strategy.strategyId)).toEqual([
    'lhb_shortline',
    'mid_trend',
    'tech_bottleneck'
  ]);
  for (const field of [
    'contractId',
    'publishId',
    'artifactVersion',
    'performanceDate',
    'totalReturn'
  ] as const) {
    expect(new Set(strategies.map((strategy) => strategy[field])).size).toBe(3);
  }
  expect(officialStrategies.lhb_shortline.totalReturn).toBe(52.4);
  expect(JSON.stringify(officialStrategies)).not.toContain('175.29');
});
