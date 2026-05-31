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

  await page.route('/api/assets/*/decisions**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            review_date: '2026-05-30',
            review_session_id: 'morning-review',
            event_id: 'operator_decision:morning-review:0:abc',
            asset_id: '000001.SZ',
            stock_code: '000001',
            stock_name: 'Ping An Bank',
            decision_label: 'candidate',
            evidence_artifact_id: 'dashboard:topn:2026-05-30',
            evidence_path: 'outputs/p6/topn.json',
            source_context: 'dashboard_topn',
            requires_follow_up: true,
            follow_up_note: 'check next close strength',
            notes: 'strong score',
            manual_review_required: true,
            auto_trade_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/assets/*/outcomes**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            outcome_event_id: 'operator_decision_outcome:p8:abc',
            run_id: 'p8-outcome-2026-05-01-2026-05-30',
            decision_event_id: 'operator_decision:morning-review:0:abc',
            review_session_id: 'morning-review',
            review_date: '2026-05-30',
            asset_id: '000001.SZ',
            stock_code: '000001',
            stock_name: 'Ping An Bank',
            decision_label: 'candidate',
            source_context: 'dashboard_topn',
            outcome_status: 'complete',
            available_future_bars: 20,
            base_trade_date: '2026-05-30',
            base_close: 10,
            forward_returns: { '1': 0.1, '5': 0.2 },
            max_high_returns: { '1': 0.12, '5': 0.25 },
            max_low_drawdowns: { '1': 0, '5': -0.04 },
            manual_review_required: true,
            auto_trade_enabled: false,
            source_artifact_path: 'outputs/p7/operator_decision_journal.json',
            outcome_artifact_path: 'outputs/p8/operator_decision_outcome_review.json'
          }
        ]
      }
    });
  });

  await page.route('/api/outcome-analytics**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            run_id: 'p9-outcome-analytics-2026-05-01-2026-06-30',
            review_start_date: '2026-05-01',
            review_end_date: '2026-06-30',
            analytics_level: 'decision_label',
            group_value: 'candidate',
            sample_count: 2,
            complete_count: 2,
            insufficient_data_count: 0,
            follow_up_required_rate: 0.5,
            horizon_metrics: {
              '5': {
                forward_return_mean: 0.15,
                forward_win_rate: 1.0,
                max_low_drawdown_worst: -0.08
              }
            },
            analytics_artifact_path: 'outputs/p9/operator_decision_outcome_analytics.json',
            manual_review_required: true,
            auto_trade_enabled: false
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
  await expect(page.getByRole('heading', { name: 'Decision History' })).toBeVisible();
  await expect(page.getByText('candidate')).toHaveCount(3);
  await expect(page.getByRole('heading', { name: 'Outcome History' })).toBeVisible();
  await expect(page.getByText(/5D\s+\+20.0%/)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Outcome Analytics' })).toBeVisible();
  await expect(page.getByText(/5D\s+\+15.0%/)).toBeVisible();
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
