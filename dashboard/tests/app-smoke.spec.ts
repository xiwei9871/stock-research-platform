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

  await page.route('/api/platform/summary**', async (route) => {
    await route.fulfill({
      json: {
        latest_market_date: '2026-06-08',
        latest_score_date: '2026-06-08',
        latest_factor_date: '2026-06-08',
        market_asset_count: 5207,
        score_asset_count: 5207,
        factor_count: 43,
        score_versions: ['manual_v1'],
        topn_preview: [
          {
            trade_date: '2026-06-08',
            asset_id: 'CN:SZ:300951',
            rank: 1,
            score_total: 89.9,
            score_version: 'manual_v1',
            score_components: {}
          }
        ]
      }
    });
  });

  await page.route('/api/strategies/catalog**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            strategy_id: 'manual_v1_topn_rotation',
            strategy_name: 'Manual V1 TopN Rotation',
            status: 'runnable',
            description: 'TopN rotation',
            factor_groups: ['momentum'],
            signal_inputs: ['factor.stock_score_daily'],
            default_parameters: { top_n: 20 },
            latest_evidence: '',
            primary_action: 'Run backtest'
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

  await page.route('/api/experiment-proposals**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            proposal_id: 'p10-proposal:001',
            run_id: 'p10-proposals-2026-05-31',
            review_date: '2026-05-31',
            proposal_title: 'Replay dashboard top-N',
            hypothesis: 'Dashboard top-N candidates should be replayed offline.',
            source_p9_analytics_run_id: 'p9-outcome-analytics-2026-05-01-2026-05-31',
            source_analytics_group_ids: ['decision_label:candidate'],
            source_diagnostic_refs: ['top_forward_return:5:decision_label:candidate'],
            source_artifact_paths: ['outputs/p9/analytics.json'],
            expected_validation_method: 'offline replay',
            risk_notes: 'No production scoring change in P10.',
            reviewer_id: 'reviewer-a',
            status: 'approved_for_experiment',
            proposal_artifact_path: 'outputs/p10/operator_experiment_proposals_2026-05-31.json',
            manual_review_required: true,
            auto_trade_enabled: false,
            promotion_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/experiment-replay**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            replay_result_id: 'p11-replay:001',
            run_id: 'p11-replay-run-2026-06-30',
            proposal_id: 'p10-proposal:001',
            source_p10_proposal_run_id: 'p10-proposals-2026-06-30',
            source_p9_analytics_run_id: 'p9-outcome-analytics-2026-05-01-2026-05-31',
            replay_start_date: '2026-01-01',
            replay_end_date: '2026-05-31',
            replay_input_artifact_paths: ['inputs/p11/replay_candidates.csv'],
            validation_method: 'offline replay',
            replay_status: 'passed_offline_replay',
            sample_count: 24,
            passed_count: 18,
            failed_count: 6,
            metric_summary: { win_rate: 0.75 },
            failure_reason: '',
            defer_reason: '',
            replay_artifact_path: 'outputs/p11/operator_experiment_replay_2026-01-01_2026-05-31.json',
            manual_review_required: true,
            auto_trade_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/shadow-watchlist**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            shadow_candidate_id: 'p12-shadow:001',
            run_id: 'p12-shadow-watchlist-2026-06-30',
            replay_result_id: 'p11-replay:001',
            source_p11_replay_run_id: 'p11-replay-run-2026-06-30',
            source_p10_proposal_run_id: 'p10-proposals-2026-06-30',
            source_p9_analytics_run_id: 'p9-outcome-analytics-2026-05-01-2026-05-31',
            candidate_date: '2026-06-30',
            asset_id: '000001.SZ',
            stock_code: '000001',
            stock_name: 'Ping An Bank',
            shadow_layer: 'trend_shadow',
            candidate_reason: 'Passed replay with acceptable drawdown.',
            evidence_artifact_paths: ['outputs/p11/replay.json'],
            metric_summary: { win_rate: 0.75 },
            reviewer_id: 'reviewer-a',
            status: 'shadow_ready',
            review_notes: 'Observe only.',
            shadow_artifact_path: 'outputs/p12/operator_shadow_watchlist_2026-06-30.json',
            manual_review_required: true,
            auto_trade_enabled: false,
            production_watchlist_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/shadow-outcomes**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            shadow_outcome_id: 'operator_shadow_outcome:p13:001',
            run_id: 'p13-shadow-outcomes-2026-07-31',
            shadow_candidate_id: 'p12-shadow:001',
            source_p12_shadow_run_id: 'p12-shadow-watchlist-2026-06-30',
            replay_result_id: 'p11-replay:001',
            source_p11_replay_run_id: 'p11-replay-run-2026-06-30',
            source_p10_proposal_run_id: 'p10-proposals-2026-06-30',
            source_p9_analytics_run_id: 'p9-outcome-analytics-2026-05-01-2026-05-31',
            candidate_date: '2026-06-30',
            asset_id: '000001.SZ',
            stock_code: '000001',
            stock_name: 'Ping An Bank',
            shadow_layer: 'trend_shadow',
            shadow_status: 'shadow_ready',
            outcome_status: 'complete',
            available_future_bars: 20,
            base_trade_date: '2026-06-30',
            base_close: 10,
            forward_returns: { '5': 0.5, '20': 1.1 },
            max_high_returns: { '5': 0.6, '20': 1.2 },
            max_low_drawdowns: { '5': -0.1, '20': -0.2 },
            manual_review_required: true,
            auto_trade_enabled: false,
            production_watchlist_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/shadow-outcome-analytics**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            analytics_group_id: 'operator_shadow_outcome_analytics:trend-ready',
            run_id: 'p14-shadow-outcome-analytics-2026-06-30-2026-08-29',
            review_start_date: '2026-06-30',
            review_end_date: '2026-08-29',
            group_key: 'trend_shadow|shadow_ready',
            shadow_layer: 'trend_shadow',
            shadow_status: 'shadow_ready',
            sample_count: 2,
            complete_count: 2,
            insufficient_data_count: 0,
            source_p12_shadow_run_count: 1,
            source_p11_replay_run_count: 1,
            source_p10_proposal_run_count: 1,
            source_p9_analytics_run_count: 1,
            horizon_metrics: {
              '20': {
                forward_return_mean: 0.12,
                forward_win_rate: 1,
                max_low_drawdown_worst: -0.2
              }
            },
            analytics_artifact_path: 'outputs/p14/operator_shadow_outcome_analytics.json',
            manual_review_required: true,
            auto_trade_enabled: false,
            production_watchlist_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/shadow-analytics-review**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            review_group_id: 'operator_shadow_analytics_review:trend-ready',
            run_id: 'p15-shadow-analytics-review-2026-08-31',
            review_start_date: '2026-06-01',
            review_end_date: '2026-08-31',
            group_key: 'trend_shadow|shadow_ready',
            shadow_layer: 'trend_shadow',
            shadow_status: 'shadow_ready',
            sample_count: 4,
            complete_count: 3,
            insufficient_data_count: 1,
            horizon_metrics: {
              '20': {
                forward_return_mean: 0.08,
                max_low_drawdown_worst: -0.15
              }
            },
            review_status: 'research_follow_up_candidate',
            review_bucket: 'needs_more_evidence',
            evidence_summary: 'Positive 20D mean with incomplete samples.',
            risk_notes: 'Observe only until a larger sample is available.',
            next_research_question: 'Can drawdown improve under stricter filters?',
            manual_review_required: true,
            auto_trade_enabled: false,
            production_watchlist_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/shadow-review-decisions**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            decision_group_id: 'operator_shadow_review_decision:trend-ready',
            run_id: 'p16-shadow-review-decisions-2026-08-31',
            decision_date: '2026-08-31',
            source_p15_review_group_id: 'operator_shadow_analytics_review:trend-ready',
            source_p15_review_run_id: 'p15-shadow-analytics-review-2026-08-31',
            source_p14_analytics_group_id: 'operator_shadow_outcome_analytics:trend-ready',
            source_p14_analytics_run_id: 'p14-shadow-outcome-analytics-2026-06-01-2026-08-31',
            group_key: 'trend_shadow|shadow_ready',
            shadow_layer: 'trend_shadow',
            shadow_status: 'shadow_ready',
            sample_count: 4,
            complete_count: 3,
            insufficient_data_count: 1,
            review_status: 'research_follow_up_candidate',
            review_bucket: 'needs_more_evidence',
            decision_status: 'open_research_follow_up',
            decision_bucket: 'research_follow_up',
            decision_reason: 'P15 status maps to follow-up.',
            required_next_action: 'Create a separately scoped research follow-up.',
            evidence_summary: 'Positive 20D mean with incomplete samples.',
            risk_notes: 'Observe only until a larger sample is available.',
            next_research_question: 'Can drawdown improve under stricter filters?',
            manual_review_required: true,
            auto_trade_enabled: false,
            production_watchlist_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/shadow-follow-up-queue**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            follow_up_item_id: 'operator_shadow_follow_up:trend-ready',
            run_id: 'p17-shadow-follow-up-queue-2026-08-31',
            follow_up_date: '2026-08-31',
            source_p16_decision_group_id: 'operator_shadow_review_decision:trend-ready',
            source_p16_decision_run_id: 'p16-shadow-review-decisions-2026-08-31',
            source_p15_review_group_id: 'operator_shadow_analytics_review:trend-ready',
            source_p15_review_run_id: 'p15-shadow-analytics-review-2026-08-31',
            source_p14_analytics_group_id: 'operator_shadow_outcome_analytics:trend-ready',
            source_p14_analytics_run_id: 'p14-shadow-outcome-analytics-2026-06-01-2026-08-31',
            group_key: 'trend_shadow|shadow_ready',
            shadow_layer: 'trend_shadow',
            shadow_status: 'shadow_ready',
            sample_count: 4,
            complete_count: 3,
            insufficient_data_count: 1,
            review_status: 'needs_more_data',
            review_bucket: 'data_needed',
            decision_status: 'request_more_data',
            decision_bucket: 'data_needed',
            follow_up_status: 'collect_more_evidence',
            priority_bucket: 'high',
            required_input: 'Additional outcome or data-quality evidence',
            follow_up_reason: 'P16 status maps to evidence collection.',
            decision_reason: 'P15 status maps to more data.',
            required_next_action: 'Collect additional evidence.',
            evidence_summary: 'Single sample is not enough.',
            risk_notes: 'Data coverage may be incomplete.',
            next_research_question: 'Does the group remain stable with more samples?',
            manual_review_required: true,
            auto_trade_enabled: false,
            production_watchlist_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('/api/shadow-follow-up-resolution**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            resolution_item_id: 'operator_shadow_follow_up_resolution:trend-ready',
            run_id: 'p18-shadow-follow-up-resolution-2026-08-31',
            resolution_date: '2026-08-31',
            source_p17_follow_up_item_id: 'operator_shadow_follow_up:trend-ready',
            source_p17_follow_up_run_id: 'p17-shadow-follow-up-queue-2026-08-31',
            source_p16_decision_group_id: 'operator_shadow_review_decision:trend-ready',
            source_p16_decision_run_id: 'p16-shadow-review-decisions-2026-08-31',
            source_p15_review_group_id: 'operator_shadow_analytics_review:trend-ready',
            source_p15_review_run_id: 'p15-shadow-analytics-review-2026-08-31',
            source_p14_analytics_group_id: 'operator_shadow_outcome_analytics:trend-ready',
            source_p14_analytics_run_id: 'p14-shadow-outcome-analytics-2026-06-01-2026-08-31',
            group_key: 'trend_shadow|shadow_ready',
            shadow_layer: 'trend_shadow',
            shadow_status: 'shadow_ready',
            sample_count: 4,
            complete_count: 3,
            insufficient_data_count: 1,
            review_status: 'needs_more_data',
            review_bucket: 'data_needed',
            decision_status: 'request_more_data',
            decision_bucket: 'data_needed',
            follow_up_status: 'collect_more_evidence',
            priority_bucket: 'high',
            required_input: 'Additional outcome or data-quality evidence',
            resolution_status: 'stale_unresolved',
            resolution_bucket: 'needs_operator_review',
            recommended_resolution_action: 'Review whether requested evidence has been collected.',
            resolution_reason: 'P17 follow-up maps to stale unresolved.',
            follow_up_reason: 'P16 status maps to evidence collection.',
            decision_reason: 'P15 status maps to more data.',
            required_next_action: 'Collect additional evidence.',
            evidence_summary: 'Single sample is not enough.',
            risk_notes: 'Data coverage may be incomplete.',
            next_research_question: 'Does the group remain stable with more samples?',
            manual_review_required: true,
            auto_trade_enabled: false,
            production_watchlist_enabled: false,
            production_write_enabled: false
          }
        ]
      }
    });
  });

  await page.route('**/api/strategy-validation/runs', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            run_id: 'lhb_shortline:fixture:phase16',
            strategy_id: 'lhb_shortline',
            strategy_name: 'LHB Shortline',
            strategy_version: 'phase16',
            run_type: 'replay',
            start_date: '2026-06-01',
            end_date: '2026-06-08',
            created_at: '2026-06-08T20:30:00+08:00',
            benchmark: '000300.SH',
            universe: 'a_share',
            data_window: {},
            cost_config: {},
            slippage_config: {},
            risk_config: {},
            position_config: {},
            source_artifact_paths: [],
            summary_metrics: {},
            warnings: ['fixture-backed run']
          }
        ]
      }
    });
  });

  await page.route('**/api/strategy-validation/runs/*/assets/*/replay?*', async (route) => {
    await route.fulfill({
      json: {
        run: null,
        asset_id: '000001.SZ',
        bars: [{ time: '2026-06-03', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }],
        signals: [],
        trades: [],
        positions: [],
        metrics: [],
        artifacts: []
      }
    });
  });
}

test('dashboard shell renders with mocked API responses', async ({ page }) => {
  await mockDashboardApi(page);

  await page.goto('/');

  await expect(page.getByText('Stock Research')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
  await expect(page.getByText('Latest Market Data')).toBeVisible();
  await expect(page.getByText('Manual V1 TopN Rotation')).toBeVisible();
  await expect(page.getByText('candidate pool, not buy signal')).toBeVisible();
  await expect(page.getByText('CN:SZ:300951')).toBeVisible();
  await expect(page.getByText(/promote/i)).toHaveCount(0);
  await expect(page.getByText(/trade/i)).toHaveCount(0);
  await expect(page.getByText(/write/i)).toHaveCount(0);

  await page.getByRole('button', { name: 'Open Strategy Validation workspace' }).click();
  await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toContainText('LHB Shortline');
  await expect(page.getByRole('button', { name: 'Replay' })).toBeVisible();

  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(horizontalOverflow).toBe(false);
});

test('dashboard shell stacks without horizontal overflow on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDashboardApi(page);

  await page.goto('/');

  await expect(page.getByText('Stock Research')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
  await expect(page.getByText('candidate pool, not buy signal')).toBeVisible();
  await page.getByRole('button', { name: 'Open Strategy Validation workspace' }).click();
  await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toContainText('LHB Shortline');
  await expect(page.getByRole('button', { name: 'Replay' })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(horizontalOverflow).toBe(false);
});
