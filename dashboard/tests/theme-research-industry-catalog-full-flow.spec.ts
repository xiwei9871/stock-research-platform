import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';

type CatalogPreflightIndex = {
  summary: {
    sector_count: number;
    chain_count: number;
    detailed_chain_count: number;
    skeleton_chain_count: number;
    structural_completeness_percent: number;
  };
  chains: Array<{
    chain_id: string;
    chain_name: string;
    aliases: string[];
    status: string;
  }>;
};

type CatalogPreflightDetail = {
  chain: { chain_id: string; chain_name: string };
  nodes: Array<{ node_id: string; node_name: string; level: string; status: string }>;
  theme_links: Array<{ theme_id: string; node_links: unknown[]; unmapped_theme_node_ids: string[] }>;
};

async function prepareDashboard(page: Page) {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      json: {
        user: {
          user_id: 'industry-catalog-acceptance',
          username: 'industry_catalog_acceptance',
          display_name: 'Industry Catalog Acceptance',
          role: 'user',
          is_active: true
        }
      }
    });
  });
}

async function expectLiveCatalogPreflight(page: Page) {
  const [indexResponse, detailResponse] = await Promise.all([
    page.request.get('/api/research/technology-industry-catalog'),
    page.request.get('/api/research/technology-industry-catalog/chains/ai_data_center_power')
  ]);
  expect(indexResponse.ok()).toBe(true);
  expect(detailResponse.ok()).toBe(true);

  const index = (await indexResponse.json()) as CatalogPreflightIndex;
  expect(index.summary).toMatchObject({
    sector_count: 10,
    chain_count: 82,
    detailed_chain_count: 14,
    skeleton_chain_count: 68,
    structural_completeness_percent: 17.07
  });
  const aiPowerChain = index.chains.find((chain) => chain.chain_id === 'ai_data_center_power');
  expect(aiPowerChain).toMatchObject({
    chain_id: 'ai_data_center_power',
    chain_name: 'AI Data Center Power',
    status: 'draft'
  });
  expect(aiPowerChain?.aliases).toContain('AI数据中心供电');

  const detail = (await detailResponse.json()) as CatalogPreflightDetail;
  expect(detail.chain).toMatchObject({
    chain_id: 'ai_data_center_power',
    chain_name: 'AI Data Center Power'
  });
  expect(detail.nodes).toEqual(expect.arrayContaining([
    expect.objectContaining({ node_id: 'ai_power_backup_power', level: 'L3', status: 'draft' }),
    expect.objectContaining({
      node_id: 'ai_power_automatic_transfer_switch_role',
      level: 'L4',
      status: 'draft'
    })
  ]));
  expect(detail.theme_links).toEqual(expect.arrayContaining([
    expect.objectContaining({
      theme_id: 'ai_power_value_capture_v1',
      node_links: expect.any(Array),
      unmapped_theme_node_ids: expect.any(Array)
    })
  ]));
}

async function expectNoPageOverflow(page: Page) {
  const horizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  );
  expect(horizontalOverflow).toBeLessThanOrEqual(1);
}

async function expectNoOverlap(first: Locator, second: Locator) {
  const [firstBox, secondBox] = await Promise.all([first.boundingBox(), second.boundingBox()]);
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();

  const horizontalOverlap = Math.min(firstBox!.x + firstBox!.width, secondBox!.x + secondBox!.width)
    - Math.max(firstBox!.x, secondBox!.x);
  const verticalOverlap = Math.min(firstBox!.y + firstBox!.height, secondBox!.y + secondBox!.height)
    - Math.max(firstBox!.y, secondBox!.y);

  expect(horizontalOverlap <= 1 || verticalOverlap <= 1).toBe(true);
}

async function expectInsideViewport(page: Page, locator: Locator) {
  const box = await locator.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(-1);
  expect(box!.y).toBeGreaterThanOrEqual(-1);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width + 1);
  expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height + 1);
}

async function expectTableOverflowContained(page: Page, wrapper: Locator, requireLocalScroll = false) {
  await expect(wrapper).toBeVisible();
  const layout = await wrapper.evaluate((element) => {
    const table = element.querySelector('table');
    const rect = element.getBoundingClientRect();
    return {
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      overflowX: window.getComputedStyle(element).overflowX,
      tableWidth: table?.scrollWidth ?? 0,
      left: rect.left,
      right: rect.right,
      documentWidth: document.documentElement.clientWidth
    };
  });

  expect(layout.overflowX).toMatch(/auto|scroll/);
  expect(layout.left).toBeGreaterThanOrEqual(-1);
  expect(layout.right).toBeLessThanOrEqual(layout.documentWidth + 1);
  expect(layout.tableWidth).toBeGreaterThan(0);
  expect(layout.tableWidth).toBeLessThanOrEqual(layout.scrollWidth + 1);
  if (requireLocalScroll) {
    expect(layout.scrollWidth - layout.clientWidth).toBeGreaterThan(1);
  }
  await expectNoPageOverflow(page);
}

async function captureViewport(page: Page, testInfo: TestInfo, name: string) {
  const path = testInfo.outputPath(`${name}.png`);
  await page.screenshot({ path });
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

test('desktop enters the catalog through AppShell and combined workspace navigation', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await prepareDashboard(page);
  await expectLiveCatalogPreflight(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');

  await expect(page.getByRole('heading', { name: '策略指挥中心' })).toBeVisible();
  const canonicalNavButton = page.getByRole('button', {
    name: 'Open Theme Research and Industry Catalog workspace'
  });
  await expect(canonicalNavButton).toHaveCount(1);
  await expect(canonicalNavButton).toHaveText('主题研究与产业目录');
  await expectInsideViewport(page, canonicalNavButton);

  await canonicalNavButton.click();
  await expect(page).toHaveURL(/\/theme-research$/);
  await expect(page.getByRole('heading', { name: '主题研究' })).toBeVisible();
  await expect(page.getByText('5 个主题')).toBeVisible();

  const combinedNavigation = page.getByRole('navigation', { name: '主题研究与产业目录视图' });
  const themeResearchButton = combinedNavigation.getByRole('button', { name: '主题研究' });
  const catalogButton = combinedNavigation.getByRole('button', { name: '产业目录' });
  await expect(themeResearchButton).toHaveAttribute('aria-current', 'page');
  await expect(catalogButton).not.toHaveAttribute('aria-current', 'page');

  const catalogResponsePromise = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return url.pathname === '/api/research/technology-industry-catalog' && response.request().method() === 'GET';
  });
  await catalogButton.click();
  const catalogResponse = await catalogResponsePromise;
  expect(catalogResponse.status()).toBe(200);
  await expect(page).toHaveURL(/\/theme-research\/catalog$/);
  await expect(catalogButton).toHaveAttribute('aria-current', 'page');
  await expect(themeResearchButton).not.toHaveAttribute('aria-current', 'page');

  const indexHeader = page.locator('.industry-catalog-index > .theme-research-header');
  const metrics = page.getByLabel('产业目录概况');
  const toolbar = page.locator('.industry-catalog-index > .theme-research-toolbar');
  const catalogSearch = page.getByRole('textbox', { name: '搜索产业目录' });
  const sectorSelect = page.getByRole('combobox', { name: '产业板块筛选' });
  await expect(page.getByRole('heading', { name: '科技产业目录' })).toBeVisible();
  for (const value of ['10', '82', '14', '68', '17.07%']) {
    await expect(metrics.getByText(value, { exact: true })).toBeVisible();
  }
  await expect(page.locator('.industry-catalog-sector')).toHaveCount(10);
  for (const locator of [combinedNavigation, indexHeader, metrics, toolbar, catalogSearch, sectorSelect]) {
    await expectInsideViewport(page, locator);
  }
  await expectNoOverlap(combinedNavigation, indexHeader);
  await expectNoOverlap(indexHeader, metrics);
  await expectNoOverlap(metrics, toolbar);
  await expectNoOverlap(catalogSearch, sectorSelect);
  await expectNoPageOverflow(page);
  await captureViewport(page, testInfo, 'desktop-catalog-index');

  await catalogSearch.fill('AI数据中心供电');
  const aiPowerChainButton = page.getByRole('button', { name: '打开AI Data Center Power产业链' });
  await expect(aiPowerChainButton).toBeVisible();
  await expect(page.locator('.industry-catalog-sector')).toHaveCount(1);
  const aiPowerRow = page.getByRole('row').filter({ has: aiPowerChainButton });
  await expect(aiPowerRow.getByText('应用主题链', { exact: true })).toBeVisible();
  await expect(aiPowerRow.getByText('基础设施流', { exact: true })).toBeVisible();
  await expect(aiPowerRow.getByText('草稿', { exact: true })).toBeVisible();
  await expect(aiPowerRow.getByText('已展开', { exact: true })).toBeVisible();
  const filteredSector = page.locator('.industry-catalog-sector');
  await expectTableOverflowContained(page, filteredSector.locator('.industry-catalog-table-wrap'));

  await aiPowerChainButton.click();
  await expect(page).toHaveURL(/\/theme-research\/catalog\/ai_data_center_power$/);
  const heading = page.getByRole('heading', { name: 'AI Data Center Power', exact: true });
  const backButton = page.getByRole('button', { name: '返回产业目录' });
  const detailStatus = page.locator('.theme-research-title-line .theme-research-status');
  const detailHeader = page.locator('.industry-catalog-detail-grid > .theme-research-header');
  await expect(heading).toBeVisible();
  await expect(detailStatus).toHaveText('草稿');

  const definition = page.getByLabel('产业链定义');
  const definitionHeading = definition.getByRole('heading', { name: '链条定义' });
  await expect(definitionHeading).toBeVisible();
  await expect(definition.getByRole('row', { name: /范围 Covers capacity planning/ })).toBeVisible();
  await expect(definition.getByRole('row', { name: /别名 .*AI数据中心供电/ })).toBeVisible();
  await expect(definition.getByRole('row', { name: '链条类型 应用主题链' })).toBeVisible();
  await expect(definition.getByRole('row', { name: '拆解方法 基础设施流' })).toBeVisible();
  await expect(definition.getByRole('row', { name: '状态 草稿' })).toBeVisible();

  const nodeHierarchy = page.getByLabel('L3和L4节点');
  const nodeHierarchyHeading = nodeHierarchy.getByRole('heading', { name: 'L3/L4 节点' });
  const backupGroup = nodeHierarchy.getByRole('region', { name: 'Backup Power节点组' });
  await expect(nodeHierarchyHeading).toBeVisible();
  await expect(backupGroup.getByRole('heading', { name: 'Backup Power', exact: true })).toBeVisible();
  await expect(backupGroup.locator('.theme-research-view-header').getByText('草稿', { exact: true })).toBeVisible();
  const automaticTransferRow = backupGroup.getByRole('row').filter({ hasText: 'Automatic Transfer Switching' });
  await expect(automaticTransferRow.getByText('Automatic Transfer Switching', { exact: true })).toBeVisible();
  await expect(automaticTransferRow.getByText('power_switching_role', { exact: true })).toBeVisible();
  await expect(automaticTransferRow.getByText('草稿', { exact: true })).toBeVisible();

  const linkedTheme = page.getByLabel('关联主题');
  const linkedThemeRow = linkedTheme.getByRole('row').filter({ hasText: 'ai_power_value_capture_v1' });
  await expect(linkedThemeRow.getByText('ai_power_value_capture_v1', { exact: true })).toBeVisible();
  await expect(linkedThemeRow.getByText('已映射 11', { exact: true })).toBeVisible();
  await expect(linkedThemeRow.getByText('未映射 2', { exact: true })).toBeVisible();
  const openLinkedTheme = linkedThemeRow.getByRole('button', {
    name: '打开关联主题 ai_power_value_capture_v1'
  });
  await expect(openLinkedTheme).toBeVisible();

  for (const locator of [combinedNavigation, detailHeader, backButton, heading, detailStatus, definitionHeading, nodeHierarchyHeading]) {
    await locator.scrollIntoViewIfNeeded();
    await expectInsideViewport(page, locator);
  }
  await expectNoOverlap(combinedNavigation, detailHeader);
  await expectNoOverlap(backButton, heading);
  await expectNoOverlap(heading, detailStatus);
  await expectNoOverlap(definition, nodeHierarchy);
  await expectTableOverflowContained(page, definition.locator('.industry-catalog-table-wrap'));
  await expectTableOverflowContained(page, backupGroup.locator('.industry-catalog-table-wrap'));
  await captureViewport(page, testInfo, 'desktop-catalog-detail');

  await automaticTransferRow.scrollIntoViewIfNeeded();
  await captureViewport(page, testInfo, 'desktop-catalog-l3-l4');
  await openLinkedTheme.click();
  await expect(page).toHaveURL(/\/theme-research\/ai_power_value_capture_v1$/);
  await expect(page.getByRole('heading', { name: 'AI供电产业链：谁在拿走价值量' })).toBeVisible();

  await page.goBack();
  await expect(page).toHaveURL(/\/theme-research\/catalog\/ai_data_center_power$/);
  await page.getByRole('button', { name: '返回产业目录' }).click();
  await expect(page).toHaveURL(/\/theme-research\/catalog$/);
  await expect(page.getByRole('heading', { name: '科技产业目录' })).toBeVisible();

  await themeResearchButton.click();
  await expect(page).toHaveURL(/\/theme-research$/);
  await expect(page.getByRole('heading', { name: '主题研究' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '科技产业目录' })).toHaveCount(0);
  await expect(page.locator('.industry-catalog-workspace')).toHaveCount(0);
});

test('mobile detail contains wide tables and keeps navigation controls usable', async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await prepareDashboard(page);
  await expectLiveCatalogPreflight(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/theme-research/catalog/ai_data_center_power');

  await expect(page).toHaveURL(/\/theme-research\/catalog\/ai_data_center_power$/);
  const combinedNavigation = page.getByRole('navigation', { name: '主题研究与产业目录视图' });
  const themeResearchButton = combinedNavigation.getByRole('button', { name: '主题研究' });
  const catalogButton = combinedNavigation.getByRole('button', { name: '产业目录' });
  const detailHeader = page.locator('.industry-catalog-detail-grid > .theme-research-header');
  const heading = page.getByRole('heading', { name: 'AI Data Center Power', exact: true });
  const backButton = page.getByRole('button', { name: '返回产业目录' });
  const detailStatus = page.locator('.theme-research-title-line .theme-research-status');
  await expect(themeResearchButton).toBeVisible();
  await expect(catalogButton).toHaveAttribute('aria-current', 'page');
  await expect(heading).toBeVisible();
  await expect(detailStatus).toHaveText('草稿');
  await expect(page.getByText(/Application-chain view of the electrical, thermal, software/)).toBeVisible();

  const definition = page.getByLabel('产业链定义');
  const definitionHeading = definition.getByRole('heading', { name: '链条定义' });
  await expect(definitionHeading).toBeVisible();
  await expect(definition.getByRole('row', { name: /范围 Covers capacity planning/ })).toBeVisible();
  await expect(definition.getByRole('row', { name: /别名 .*AI数据中心供电/ })).toBeVisible();
  await expect(definition.getByRole('row', { name: '链条类型 应用主题链' })).toBeVisible();
  await expect(definition.getByRole('row', { name: '拆解方法 基础设施流' })).toBeVisible();
  await expect(definition.getByRole('row', { name: '状态 草稿' })).toBeVisible();

  const nodeHierarchy = page.getByLabel('L3和L4节点');
  const backupGroup = nodeHierarchy.getByRole('region', { name: 'Backup Power节点组' });
  await expect(nodeHierarchy.getByRole('heading', { name: 'L3/L4 节点' })).toBeVisible();
  await expect(backupGroup.getByRole('heading', { name: 'Backup Power', exact: true })).toBeVisible();
  await expect(backupGroup.locator('.theme-research-view-header').getByText('草稿', { exact: true })).toBeVisible();
  const automaticTransferRow = backupGroup.getByRole('row').filter({ hasText: 'Automatic Transfer Switching' });
  await expect(automaticTransferRow.getByText('Automatic Transfer Switching', { exact: true })).toBeVisible();
  await expect(automaticTransferRow.getByText('power_switching_role', { exact: true })).toBeVisible();
  await expect(automaticTransferRow.getByText('草稿', { exact: true })).toBeVisible();

  for (const locator of [combinedNavigation, detailHeader, backButton, heading, detailStatus, definitionHeading]) {
    await expectInsideViewport(page, locator);
  }
  await expectNoOverlap(themeResearchButton, catalogButton);
  await expectNoOverlap(combinedNavigation, detailHeader);
  await expectNoOverlap(backButton, heading);
  await expectNoOverlap(heading, detailStatus);
  await expectNoOverlap(detailHeader, definitionHeading);
  await expectTableOverflowContained(page, definition.locator('.industry-catalog-table-wrap'), true);
  const l4TableWrapper = backupGroup.locator('.industry-catalog-table-wrap');
  await expectTableOverflowContained(page, l4TableWrapper, true);
  await expectNoPageOverflow(page);
  await captureViewport(page, testInfo, 'mobile-catalog-detail');

  await automaticTransferRow.getByText('Automatic Transfer Switching', { exact: true }).scrollIntoViewIfNeeded();
  await captureViewport(page, testInfo, 'mobile-catalog-l3-l4-left');
  await l4TableWrapper.evaluate((element) => {
    element.scrollLeft = element.scrollWidth - element.clientWidth;
  });
  expect(await l4TableWrapper.evaluate((element) => element.scrollLeft)).toBeGreaterThan(1);
  await expect(automaticTransferRow.getByText('草稿', { exact: true })).toBeInViewport();
  await expectNoPageOverflow(page);
  await captureViewport(page, testInfo, 'mobile-catalog-l3-l4-status');

  await backButton.click();
  await expect(page).toHaveURL(/\/theme-research\/catalog$/);
  const indexHeader = page.locator('.industry-catalog-index > .theme-research-header');
  const metrics = page.getByLabel('产业目录概况');
  const toolbar = page.locator('.industry-catalog-index > .theme-research-toolbar');
  const catalogSearch = page.getByRole('textbox', { name: '搜索产业目录' });
  const sectorSelect = page.getByRole('combobox', { name: '产业板块筛选' });
  await expect(page.getByRole('heading', { name: '科技产业目录' })).toBeVisible();
  for (const locator of [combinedNavigation, indexHeader, metrics, toolbar, catalogSearch, sectorSelect]) {
    await expectInsideViewport(page, locator);
  }
  await expectNoOverlap(combinedNavigation, indexHeader);
  await expectNoOverlap(indexHeader, metrics);
  await expectNoOverlap(metrics, toolbar);
  await expectNoOverlap(catalogSearch, sectorSelect);
  await expectNoPageOverflow(page);
  await captureViewport(page, testInfo, 'mobile-catalog-index');
});
