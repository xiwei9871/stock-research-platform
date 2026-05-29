import { expect, test, type Page } from '@playwright/test';

async function mockDashboardApi(page: Page) {
  await page.route('/api/dashboard/overview**', async (route) => {
    await route.fulfill({
      json: {
        trade_date: '2026-05-29',
        score_version: 'manual_v1',
        watchlist_id: 'default',
        top_scores: [
          {
            trade_date: '2026-05-29',
            asset_id: '000001.SZ',
            rank: 1,
            score_total: 91.2,
            score_version: 'manual_v1',
            score_components: {}
          }
        ],
        watchlist_signals: [
          {
            watchlist_id: 'default',
            trade_date: '2026-05-29',
            asset_id: '000001.SZ',
            stock_code: '000001',
            stock_name: 'Ping An Bank',
            priority: 1,
            signal_score: 91.2,
            primary_signal: 'breakout',
            signal_tags: ['momentum'],
            risk_tags: ['watch volatility'],
            must_watch: true,
            reason_json: {}
          }
        ],
        reports: [
          {
            report_type: 'daily',
            title: 'Daily Market Review',
            path: '/reports/daily.html',
            format: 'html',
            trade_date: '2026-05-29'
          }
        ]
      }
    });
  });

  await page.route('/api/assets/*/bars**', async (route) => {
    await route.fulfill({
      json: {
        asset_id: '000001.SZ',
        resolution: '1D',
        items: [{ time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }]
      }
    });
  });

  await page.route('/api/assets/*/scores**', async (route) => {
    await route.fulfill({
      json: {
        item: {
          trade_date: '2026-05-29',
          asset_id: '000001.SZ',
          rank: 1,
          score_total: 91.2,
          score_version: 'manual_v1',
          score_components: {}
        }
      }
    });
  });

  await page.route('/api/assets/*/signals**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            watchlist_id: 'default',
            trade_date: '2026-05-29',
            asset_id: '000001.SZ',
            stock_code: '000001',
            stock_name: 'Ping An Bank',
            priority: 1,
            signal_score: 91.2,
            primary_signal: 'breakout',
            signal_tags: ['momentum'],
            risk_tags: ['watch volatility'],
            must_watch: true,
            reason_json: {}
          }
        ]
      }
    });
  });
}

test('dashboard shell renders with mocked API responses', async ({ page }) => {
  await mockDashboardApi(page);

  await page.goto('/');

  await expect(page.getByText('Stock Research')).toBeVisible();
  await expect(page.getByLabel('asset id')).toHaveValue('000001.SZ');
  await expect(page.getByRole('heading', { name: 'Asset Review' })).toBeVisible();
  await expect(
    page
      .locator('.inspector-section')
      .filter({ has: page.getByRole('heading', { name: 'Asset Review' }) })
      .getByText('Score')
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
  await expect(page.getByRole('link', { name: /Daily Market Review/ })).toBeVisible();

  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(horizontalOverflow).toBe(false);
});

test('dashboard shell stacks without horizontal overflow on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDashboardApi(page);

  await page.goto('/');

  await expect(page.getByText('Stock Research')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'TopN' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Asset Review' })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(horizontalOverflow).toBe(false);
});
