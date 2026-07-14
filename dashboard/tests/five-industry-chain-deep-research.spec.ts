import { expect, test, type Page } from '@playwright/test';

const themes = [
  ['ai_power_value_capture_v1', 'ai_data_center_power', 'AI供电产业链：谁在拿走价值量'],
  ['semiconductor_manufacturing_equipment_value_chain_v1', 'semiconductor_manufacturing_equipment', '半导体制造设备：工艺环节、瓶颈与国产化'],
  ['humanoid_robotics_head_to_toe_v1', 'humanoid_robots_embodied_intelligence', '人形机器人：从头到脚的价值链与受益环节'],
  ['ai_compute_infrastructure_value_chain_v1', 'ai_compute_infrastructure', 'AI算力基础设施：从芯片到集群利用率'],
  ['new_energy_storage_value_chain_v1', 'new_energy_storage', '新型储能：设备、系统集成与运营收益']
] as const;

const sectionNames = [
  '研究结论',
  '价值链',
  '利润池与竞争壁垒',
  '催化、验证信号与风险',
  '受益公司',
  '来源证据',
  '证据缺口与更新'
];

async function prepareDashboard(page: Page) {
  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      json: {
        user: {
          user_id: 'five-theme-acceptance',
          username: 'five_theme_acceptance',
          display_name: 'Five Theme Acceptance',
          role: 'user',
          is_active: true
        }
      }
    });
  });
}

async function expectNoPageOverflow(page: Page) {
  expect(await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth
  )).toBeLessThanOrEqual(1);
}

test('five selected chains expose complete readable desktop research', async ({ page }) => {
  test.setTimeout(120_000);
  await prepareDashboard(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/theme-research');
  await expect(page.getByText('5 个主题')).toBeVisible();

  for (const [themeId, chainId, title] of themes) {
    const [detailResponse, companiesResponse] = await Promise.all([
      page.request.get(`/api/research/theme-decomposition/themes/${themeId}`),
      page.request.get(`/api/research/theme-decomposition/themes/${themeId}/companies`)
    ]);
    expect(detailResponse.ok()).toBe(true);
    expect(companiesResponse.ok()).toBe(true);
    expect((await companiesResponse.json()).total).toBeGreaterThanOrEqual(8);

    await page.goto(`/theme-research/${themeId}`);
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    for (const sectionName of sectionNames) {
      await expect(page.getByRole('heading', { name: sectionName, exact: true })).toBeVisible();
    }
    await expect(page.getByText('仅用于研究，不构成投资建议。')).toBeVisible();
    await expectNoPageOverflow(page);

    await page.goto(`/theme-research/catalog/${chainId}`);
    const deepResearchButton = page.getByRole('button', { name: '进入深度研究' });
    await expect(deepResearchButton).toHaveCount(1);
    await expect(deepResearchButton).toBeVisible();
  }
});

test('all five deep themes remain contained on mobile', async ({ page }) => {
  test.setTimeout(120_000);
  await prepareDashboard(page);
  await page.setViewportSize({ width: 390, height: 844 });

  for (const [themeId, , title] of themes) {
    await page.goto(`/theme-research/${themeId}`);
    await expect(page.getByRole('heading', { name: title })).toBeVisible();
    await expect(page.getByRole('heading', { name: '研究结论', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '受益公司', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: '来源证据', exact: true })).toBeVisible();
    await expectNoPageOverflow(page);
  }
});
