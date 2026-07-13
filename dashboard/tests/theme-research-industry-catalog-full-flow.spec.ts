import { expect, test, type Locator, type Page } from '@playwright/test';

const desktopScreenshot = 'test-results/theme-research-industry-catalog-desktop.png';
const mobileScreenshot = 'test-results/theme-research-industry-catalog-mobile.png';

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

async function expectWithinDocumentWidth(page: Page, locator: Locator) {
  const box = await locator.boundingBox();
  const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(-1);
  expect(box!.x + box!.width).toBeLessThanOrEqual(clientWidth + 1);
}

test('desktop catalog flow uses canonical navigation and opens the linked AI power chain', async ({ page }) => {
  test.setTimeout(120_000);
  await prepareDashboard(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/theme-research/catalog');

  const canonicalNavButton = page.getByRole('button', {
    name: 'Open Theme Research and Industry Catalog workspace'
  });
  await expect(canonicalNavButton).toHaveCount(1);
  await expect(canonicalNavButton).toHaveText('主题研究与产业目录');

  const combinedNavigation = page.getByRole('navigation', { name: '主题研究与产业目录视图' });
  const themeResearchButton = combinedNavigation.getByRole('button', { name: '主题研究' });
  const catalogButton = combinedNavigation.getByRole('button', { name: '产业目录' });
  await expect(themeResearchButton).toBeVisible();
  await expect(catalogButton).toHaveAttribute('aria-current', 'page');
  await expect(themeResearchButton).not.toHaveAttribute('aria-current', 'page');

  await expect(page.getByRole('heading', { name: '科技产业目录' })).toBeVisible();
  const metrics = page.getByLabel('产业目录概况');
  for (const value of ['10', '82', '13', '69', '15.85%']) {
    await expect(metrics.getByText(value, { exact: true })).toBeVisible();
  }

  const sectorHierarchy = page.locator('.industry-catalog-sector');
  await expect(sectorHierarchy).toHaveCount(10);
  await expect(sectorHierarchy.first()).toBeVisible();

  const catalogSearch = page.getByRole('textbox', { name: '搜索产业目录' });
  await catalogSearch.fill('AI数据中心供电');
  const aiPowerChainButton = page.getByRole('button', { name: '打开AI Data Center Power产业链' });
  await expect(aiPowerChainButton).toBeVisible();
  await expect(page.locator('.industry-catalog-sector')).toHaveCount(1);

  await aiPowerChainButton.click();
  await expect(page).toHaveURL(/\/theme-research\/catalog\/ai_data_center_power$/);
  await expect(page.getByRole('heading', { name: 'AI Data Center Power', exact: true })).toBeVisible();

  const definition = page.getByLabel('产业链定义');
  await expect(definition.getByRole('heading', { name: '链条定义' })).toBeVisible();
  await expect(definition.getByRole('row', { name: /范围 Covers capacity planning/ })).toBeVisible();
  await expect(definition.getByRole('row', { name: /别名 .*AI数据中心供电/ })).toBeVisible();

  const nodeHierarchy = page.getByLabel('L3和L4节点');
  await expect(nodeHierarchy.getByRole('heading', { name: 'L3/L4 节点' })).toBeVisible();
  await expect(nodeHierarchy.getByRole('heading', { name: 'Backup Power', exact: true })).toBeVisible();
  await expect(nodeHierarchy.getByRole('columnheader', { name: 'L4 节点' }).first()).toBeVisible();
  await expect(nodeHierarchy.getByText('Automatic Transfer Switching', { exact: true })).toBeVisible();

  const linkedTheme = page.getByLabel('关联主题');
  await expect(linkedTheme.getByText('ai_power_value_capture_v1', { exact: true })).toBeVisible();
  const openLinkedTheme = linkedTheme.getByRole('button', {
    name: '打开关联主题 ai_power_value_capture_v1'
  });
  await expect(openLinkedTheme).toBeVisible();

  const coreRegion = page.locator('.industry-catalog-detail-grid');
  const coreBox = await coreRegion.boundingBox();
  expect(coreBox).not.toBeNull();
  expect(coreBox!.width).toBeGreaterThan(900);
  expect(coreBox!.height).toBeGreaterThan(1_000);
  expect((await coreRegion.innerText()).trim().length).toBeGreaterThan(2_000);
  await expectNoPageOverflow(page);
  await page.screenshot({ path: desktopScreenshot, fullPage: true });

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

test('mobile catalog detail remains usable without page overflow or overlapping controls', async ({ page }) => {
  test.setTimeout(120_000);
  await prepareDashboard(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/theme-research/catalog/ai_data_center_power');

  await expect(page).toHaveURL(/\/theme-research\/catalog\/ai_data_center_power$/);
  const heading = page.getByRole('heading', { name: 'AI Data Center Power', exact: true });
  await expect(heading).toBeVisible();
  await expect(page.getByText(/Application-chain view of the electrical, thermal, software/)).toBeVisible();

  const combinedNavigation = page.getByRole('navigation', { name: '主题研究与产业目录视图' });
  const themeResearchButton = combinedNavigation.getByRole('button', { name: '主题研究' });
  const catalogButton = combinedNavigation.getByRole('button', { name: '产业目录' });
  await expect(themeResearchButton).toBeVisible();
  await expect(catalogButton).toBeVisible();
  await expect(catalogButton).toHaveAttribute('aria-current', 'page');

  const definition = page.getByLabel('产业链定义');
  const nodeHierarchy = page.getByLabel('L3和L4节点');
  await expect(definition.getByRole('heading', { name: '链条定义' })).toBeVisible();
  await expect(definition.getByRole('row', { name: /范围 Covers capacity planning/ })).toBeVisible();
  await expect(nodeHierarchy.getByRole('heading', { name: 'L3/L4 节点' })).toBeVisible();
  await expect(nodeHierarchy.getByRole('heading', { name: 'Backup Power', exact: true })).toBeVisible();
  await expect(nodeHierarchy.getByText('Automatic Transfer Switching', { exact: true })).toBeVisible();

  const backButton = page.getByRole('button', { name: '返回产业目录' });
  const detailStatus = page.locator('.theme-research-title-line .theme-research-status');
  await expect(backButton).toBeVisible();
  await expect(detailStatus).toBeVisible();
  await expectNoOverlap(backButton, heading);
  await expectNoOverlap(heading, detailStatus);
  await expectNoOverlap(themeResearchButton, catalogButton);
  await expectNoOverlap(definition, nodeHierarchy);
  await expectWithinDocumentWidth(page, combinedNavigation);
  await expectWithinDocumentWidth(page, backButton);
  await expectWithinDocumentWidth(page, heading);
  await expectNoPageOverflow(page);

  await page.screenshot({ path: mobileScreenshot, fullPage: true });

  await backButton.click();
  await expect(page).toHaveURL(/\/theme-research\/catalog$/);
  await expect(page.getByRole('heading', { name: '科技产业目录' })).toBeVisible();
});
