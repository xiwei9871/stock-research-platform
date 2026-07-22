import type { Page } from '@playwright/test';

import {
  expectApiUiConsistency,
  expectPublicationConsistency,
  expectRouteContext,
  expectStrategyPresentationConsistency,
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

test('restored state waits for delayed search and selected state @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/__consistency-delayed-state__',
    '<main><input id="search" aria-label="Global search" role="combobox" value="">' +
      '<button id="tab" role="tab" aria-selected="false">研究事实表</button>' +
      '<script>setTimeout(() => {' +
      'document.querySelector("#search").value = "海能技术";' +
      'document.querySelector("#tab").setAttribute("aria-selected", "true");' +
      '}, 150);</script></main>'
  );

  await expectStateRestored(page, {
    searchQuery: '海能技术',
    selectedText: '研究事实表'
  });
});

test('API/UI rules format number, ratio, and percent without double scaling @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  await setContractContent(
    page,
    baseURL,
    '/__consistency-values__',
    '<main><strong id="number">-1,234.50</strong><strong id="number-plain">1234.50</strong>' +
      '<strong id="ratio">+52.40%</strong><strong id="percent">52.40%</strong></main>'
  );

  await expectApiUiConsistency('-1234.5', page.locator('#number'), 'number');
  await expectApiUiConsistency('1234.5', page.locator('#number-plain'), 'number');
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

for (const [rawValue, renderedText] of [
  ['0x34', '52.00'],
  ['0b110100', '52.00'],
  ['NaN', 'NaN'],
  ['$52.4', '52.40']
] as const) {
  test(`API string rejects non-decimal syntax ${rawValue} @p0 @consistency-contract`, async ({
    page,
    baseURL
  }) => {
    await setContractContent(
      page,
      baseURL,
      `/__consistency-api-string-${encodeURIComponent(rawValue)}__`,
      `<main><strong id="value">${renderedText}</strong></main>`
    );

    expect(
      await captureErrorMessage(() =>
        expectApiUiConsistency(rawValue, page.locator('#value'), 'number')
      )
    ).toBe(
      `API/UI consistency mismatch: raw value "${rawValue}"; rendered text ` +
        `"${renderedText}"; rule number; expected a finite numeric value.`
    );
  });
}

for (const [caseName, renderedText, rule] of [
  ['invalid number grouping', '-12,34.50', 'number'],
  ['comma in percent', '5,2.40%', 'percent'],
  ['repeated percent symbol', '52.40%%', 'percent'],
  ['currency in percent', '$52.40%', 'percent']
] as const) {
  test(`rendered value rejects ${caseName} @p0 @consistency-contract`, async ({
    page,
    baseURL
  }) => {
    await setContractContent(
      page,
      baseURL,
      `/__consistency-rendered-${encodeURIComponent(caseName)}__`,
      `<main><strong id="value">${renderedText}</strong></main>`
    );

    const actual = rule === 'number' ? -1234.5 : 52.4;
    const expectedText = rule === 'number' ? '-1,234.50' : '52.40%';
    expect(
      await captureErrorMessage(() =>
        expectApiUiConsistency(actual, page.locator('#value'), rule)
      )
    ).toBe(
      `API/UI consistency mismatch: raw value ${actual}; rendered text ` +
        `"${renderedText}"; rule ${rule}; expected "${expectedText}".`
    );
  });
}

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
      `<span data-testid="strategy-contract-id">${strategy.contractId}</span> ` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}</span> ` +
      `<time data-testid="strategy-performance-date">${strategy.performanceDate}</time> ` +
      '<strong data-testid="strategy-total-return">+52.40%</strong></article></main>'
  );

  await expectPublicationConsistency(page.locator('article'), {
    contractId: strategy.contractId,
    publishId: strategy.publishId,
    tradeDate: strategy.performanceDate,
    totalReturnPct: strategy.totalReturn
  });
});

test('human strategy presentation matches without technical publication fields @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  const strategy = officialStrategies.lhb_shortline;
  await setContractContent(
    page,
    baseURL,
    '/__consistency-human-strategy__',
    `<main><article data-strategy-id="${strategy.strategyId}">` +
      `<time data-testid="strategy-performance-date">${strategy.performanceDate}</time> ` +
      '<strong data-testid="strategy-total-return">+52.40%</strong>' +
      '<span>数据正常</span></article></main>'
  );

  await expectStrategyPresentationConsistency(page.locator('article'), {
    strategyId: strategy.strategyId,
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
      `<span data-testid="strategy-contract-id">${strategy.contractId}</span> ` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}-stale</span> ` +
      '<time data-testid="strategy-performance-date">2026-07-18</time> ' +
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
      `- publishId: expected "${strategy.publishId}", rendered "${strategy.publishId}-stale"\n` +
      `- tradeDate: expected "${strategy.performanceDate}", rendered "2026-07-18"\n` +
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
        `<span data-testid="strategy-contract-id">${strategy.contractId}</span> ` +
        `<span data-testid="strategy-publish-id">${strategy.publishId}</span> ` +
        `<time data-testid="strategy-performance-date">${strategy.performanceDate}</time> ` +
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

test('publication waits for delayed stable fields @p0 @consistency-contract', async ({
  page,
  baseURL
}) => {
  const strategy = officialStrategies.lhb_shortline;
  await setContractContent(
    page,
    baseURL,
    '/__consistency-publication-delayed__',
    `<main><article id="card" data-strategy-id="${strategy.strategyId}"></article>` +
      '<script>setTimeout(() => {' +
      `document.querySelector("#card").innerHTML = ` +
      '`<span data-testid="strategy-contract-id">' +
      `${strategy.contractId}</span> ` +
      '<span data-testid="strategy-publish-id">' +
      `${strategy.publishId}</span> ` +
      '<time data-testid="strategy-performance-date">' +
      `${strategy.performanceDate}</time> ` +
      '<strong data-testid="strategy-total-return">52.40%</strong>`;' +
      '}, 150);</script></main>'
  );

  await expectPublicationConsistency(page.locator('article'), {
    contractId: strategy.contractId,
    publishId: strategy.publishId,
    tradeDate: strategy.performanceDate,
    totalReturnPct: strategy.totalReturn
  });
});

for (const [caseName, strategyIdAttribute, fieldsHtml, expectedLines] of [
  [
    'missing strategy identity',
    '',
    (strategy: typeof officialStrategies.lhb_shortline) =>
      `<span data-testid="strategy-contract-id">${strategy.contractId}</span>` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}</span>` +
      `<time data-testid="strategy-performance-date">${strategy.performanceDate}</time>` +
      '<strong data-testid="strategy-total-return">52.40%</strong>',
    (strategy: typeof officialStrategies.lhb_shortline) => [
      `- strategyId: expected "${strategy.strategyId}", rendered "<missing>"`
    ]
  ],
  [
    'wrong strategy identity',
    'mid_trend',
    (strategy: typeof officialStrategies.lhb_shortline) =>
      `<span data-testid="strategy-contract-id">${strategy.contractId}</span>` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}</span>` +
      `<time data-testid="strategy-performance-date">${strategy.performanceDate}</time>` +
      '<strong data-testid="strategy-total-return">52.40%</strong>',
    (strategy: typeof officialStrategies.lhb_shortline) => [
      `- strategyId: expected "${strategy.strategyId}", rendered "mid_trend"`
    ]
  ],
  [
    'wrong contract marker with unrelated text',
    'lhb_shortline',
    (strategy: typeof officialStrategies.lhb_shortline) =>
      `<span data-testid="strategy-contract-label">${strategy.contractId}</span>` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}</span>` +
      `<time data-testid="strategy-performance-date">${strategy.performanceDate}</time>` +
      '<strong data-testid="strategy-total-return">52.40%</strong>',
    (strategy: typeof officialStrategies.lhb_shortline) => [
      '- contractId: expected a unique visible field, rendered "<missing>"'
    ]
  ],
  [
    'duplicate publish field',
    'lhb_shortline',
    (strategy: typeof officialStrategies.lhb_shortline) =>
      `<span data-testid="strategy-contract-id">${strategy.contractId}</span>` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}</span>` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}</span>` +
      `<time data-testid="strategy-performance-date">${strategy.performanceDate}</time>` +
      '<strong data-testid="strategy-total-return">52.40%</strong>',
    () => ['- publishId: expected a unique visible field, rendered "<ambiguous:2>"']
  ],
  [
    'hidden performance date field',
    'lhb_shortline',
    (strategy: typeof officialStrategies.lhb_shortline) =>
      `<span data-testid="strategy-contract-id">${strategy.contractId}</span>` +
      `<span data-testid="strategy-publish-id">${strategy.publishId}</span>` +
      `<time hidden data-testid="strategy-performance-date">${strategy.performanceDate}</time>` +
      '<strong data-testid="strategy-total-return">52.40%</strong>',
    () => ['- tradeDate: expected a unique visible field, rendered "<hidden>"']
  ]
] as const) {
  test(`publication fails closed for ${caseName} @p0 @consistency-contract`, async ({
    page,
    baseURL
  }) => {
    const strategy = officialStrategies.lhb_shortline;
    const attribute = strategyIdAttribute
      ? ` data-strategy-id="${strategyIdAttribute}"`
      : '';
    await setContractContent(
      page,
      baseURL,
      `/__consistency-publication-identity-${encodeURIComponent(caseName)}__`,
      `<main><article${attribute}>${fieldsHtml(strategy)}</article></main>`
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
        `publish ID "${strategy.publishId}":\n${expectedLines(strategy).join('\n')}`
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
