import { expect, test } from '@playwright/test';

test('renders the Daily Review Lite smoke path from a mocked API payload', async ({ page }) => {
  let requestUrl: string | null = null;
  const artifactHref =
    '/api/daily-review-lite/artifacts/2026-06-20/daily_review_json?run_id=daily_review_v1%3A2026-06-20%3Aabc123';

  await page.route('/api/daily-review-lite**', async (route) => {
    requestUrl = route.request().url();
    await route.fulfill({
      json: {
        trade_date: '2026-06-20',
        state: 'ready',
        selected_run: {
          run_id: 'daily_review_v1:2026-06-20:abc123',
          report_type: 'daily_review_v1',
          status: 'success',
          updated_at: '2026-06-20T22:00:00Z',
          source: 'fallback',
          artifact_health: 'healthy',
          artifact_health_detail: {
            daily_review_json: 'healthy'
          }
        },
        summary: {
          market_status: 'neutral',
          overall_position_bias: 'balanced',
          lhb_conclusion: 'observe',
          mid_trend_conclusion: 'hold',
          technical_bottleneck_conclusion: 'watch',
          must_review_asset_ids: [],
          warning_count: 0
        },
        warnings: [],
        missing_sources: [],
        sections: {
          data_readiness: {
            status: 'success',
            warnings: [],
            sources: {}
          },
          market_review: {
            status: 'success',
            warnings: [],
            payload: {}
          },
          strategy_summaries: {
            lhb: {
              strategy_id: 'lhb',
              status: 'success',
              warnings: [],
              summary: {},
              top_items: []
            },
            mid_trend: {
              strategy_id: 'mid_trend',
              status: 'success',
              warnings: [],
              summary: {},
              top_items: []
            },
            technical_bottleneck: {
              strategy_id: 'technical_bottleneck',
              status: 'success',
              warnings: [],
              summary: {},
              top_items: []
            }
          },
          holding_review: {
            status: 'empty',
            warnings: [],
            items: []
          },
          operator_plan: {
            status: 'success',
            warnings: [],
            payload: {}
          },
          next_day_checklist: {
            status: 'success',
            warnings: [],
            must_review_items: [],
            forbidden_actions: [],
            data_warnings: []
          }
        },
        artifacts: [
          {
            key: 'daily_review_json',
            label: 'Daily Review JSON',
            kind: 'json',
            required: true,
            available: true,
            filename: 'daily_review.json',
            content_type: 'application/json',
            url: artifactHref
          }
        ]
      }
    });
  });

  await page.goto('/?trade_date=2026-06-20');

  await expect(page.getByRole('heading', { name: 'Daily Review Lite' })).toBeVisible();
  await expect(page.getByText('Loaded from fallback package scan')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Strategy Summaries' })).toBeVisible();
  const artifactLink = page.getByRole('link', { name: 'Daily Review JSON' });
  await expect(artifactLink).toBeVisible();
  await expect(artifactLink).toHaveAttribute('href', artifactHref);

  expect(requestUrl).not.toBeNull();
  expect(new URL(requestUrl!).searchParams.get('trade_date')).toBe('2026-06-20');
});
