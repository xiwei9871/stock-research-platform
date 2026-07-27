import { expect, test, type Page } from '@playwright/test';

async function mockDashboardApi(page: Page) {
  const conceptStItem = {
    sector_id: 'concept-st',
    sector_name: 'ST板块',
    sector_type: 'concept',
    change_pct: 0.0989,
    amount: 2923611417.92,
    up_count: 5,
    down_count: 12,
    stock_count: 20,
    main_net_inflow: null
  };
  const conceptDownItem = {
    sector_id: 'concept-down',
    sector_name: '概念回调',
    sector_type: 'concept',
    change_pct: -0.02,
    amount: 1500000000,
    up_count: 2,
    down_count: 18,
    stock_count: 20,
    main_net_inflow: -100000000
  };

  await page.route('/api/auth/me', async (route) => {
    await route.fulfill({
      json: {
        user: {
          user_id: 'app-smoke-e2e',
          username: 'app_smoke_e2e',
          display_name: 'App Smoke E2E',
          role: 'admin',
          is_active: true
        }
      }
    });
  });

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
        latest_market_date: '2026-06-18',
        latest_score_date: '2026-06-18',
        latest_factor_date: '2026-06-18',
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

  await page.route('/api/platform/readiness**', async (route) => {
    await route.fulfill({
      json: {
        status: 'OK',
        latest_market_date: '2026-06-18',
        latest_trade_date: '2026-06-18',
        display_trade_date: '2026-06-18',
        policy: { status: 'ready', ready_for_dashboard: true, ready_for_publication: true, blocking_reasons: [], warnings: [] },
        warnings: []
      }
    });
  });

  await page.route('/api/market-monitor/eod**', async (route) => {
    await route.fulfill({
      json: {
        trade_date: '2026-06-10',
        freshness: {
          mode: 'eod',
          label: 'Last completed trading day',
          is_realtime: false,
          latest_market_date: '2026-06-10',
          latest_factor_date: '2026-06-08',
          latest_score_date: '2026-06-08'
        },
        coverage: {
          market_assets: 5195,
          score_assets: 231,
          factor_count: 41
        },
        market_breadth: {
          advancers: 2400,
          decliners: 2100,
          limit_up: 42,
          limit_down: 8,
          advancing_ratio: 0.53,
          turnover_change_pct: 0.04,
          status: 'ok'
        },
        index_snapshot: [],
        sector_strength: { strongest: [], weakest: [], status: 'ok' },
        unusual_moves: [],
        watchlist_alerts: [],
        strategy_signal_summary: {
          topn_preview_count: 1,
          topn_preview: [],
          risk_filter_counts: {}
        },
        generated_reports: [],
        warnings: []
      }
    });
  });

  await page.route('/api/market-monitor/overview**', async (route) => {
    await route.fulfill({
      json: {
        trade_date: '2026-07-24',
        updated_at: '2026-07-24 15:10',
        source: 'fixture',
        data_status: 'completed',
        warnings: [],
        indices: [],
        total_amount: 10000000000,
        up_count: 532,
        down_count: 4629,
        limit_up_count: 42,
        limit_down_count: 28
      }
    });
  });

  await page.route('/api/market-monitor/sectors/heatmap**', async (route) => {
    const type = new URL(route.request().url()).searchParams.get('type');
    const items = type === 'concept'
      ? [conceptStItem, conceptDownItem]
      : [{ ...conceptStItem, sector_type: 'industry', sector_name: '运输设备制造业' }];
    await route.fulfill({
      json: {
        trade_date: '2026-07-24',
        updated_at: '2026-07-24 15:10',
        source: 'fixture',
        data_status: 'completed',
        warnings: [],
        items
      }
    });
  });

  await page.route('/api/market-monitor/sectors/fund-flow**', async (route) => {
    await route.fulfill({
      json: {
        trade_date: '2026-07-24',
        updated_at: '2026-07-24 15:10',
        source: 'fixture',
        data_status: 'completed',
        warnings: [],
        inflow: [],
        outflow: []
      }
    });
  });

  await page.route(/\/api\/market-monitor\/sectors\/concept-st\?/, async (route) => {
    await route.fulfill({
      json: {
        trade_date: '2026-07-24',
        updated_at: '2026-07-24 15:10',
        source: 'fixture',
        data_status: 'completed',
        warnings: ['ST板块 fixture'],
        ...conceptStItem,
        main_net_inflow_ratio: null,
        leading_stocks: []
      }
    });
  });

  await page.route('/api/public-news**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            news_id: 'news-1',
            source: 'sina_finance',
            source_channel: 'market',
            category: 'market',
            title: '600000 浦发银行公告',
            summary: 'fixture news',
            url: 'https://example.com/news/1',
            published_at: '2026-06-10T09:30:00',
            collected_at: '2026-06-10T09:31:00',
            raw_id: 'news-1',
            raw_payload: {},
            status: 'active'
          }
        ],
        warnings: []
      }
    });
  });

  await page.route('/api/search?**', async (route) => {
    await route.fulfill({
      json: {
        query: '600519',
        groups: [
          {
            key: 'assets',
            label: 'Stocks',
            items: [
              {
                type: 'asset',
                id: 'CN:SH:600519',
                title: '贵州茅台',
                subtitle: '600519 SH',
                score: 95,
                match_reason: 'Exact code match',
                match_fields: ['symbol'],
                metadata: { symbol: '600519', exchange: 'SH' },
                target: { workspace: 'stock', asset_id: 'CN:SH:600519' }
              }
            ]
          }
        ],
        warnings: []
      }
    });
  });

  await page.route('/api/assets/search?**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            asset_id: 'CN:SH:600519',
            symbol: '600519',
            name: '贵州茅台',
            exchange: 'SH',
            board: null,
            is_active: true
          }
        ]
      }
    });
  });

  await page.route('/api/assets/*/profile**', async (route) => {
    await route.fulfill({
      json: {
        asset_id: 'CN:SH:600519',
        canonical_asset_id: 'CN:SH:600519',
        asset: {
          asset_id: 'CN:SH:600519',
          symbol: '600519',
          name: '贵州茅台',
          exchange: 'SH',
          board: null,
          is_active: true
        },
        bars: [{ time: '2026-05-28', open: 10, high: 11, low: 9, close: 10.5, volume: 100, amount: 1000 }],
        score: {
          trade_date: '2026-05-29',
          asset_id: 'CN:SH:600519',
          rank: 1,
          score_total: 91.2,
          score_version: 'manual_v1',
          score_components: {}
        },
        signals: [],
        decisions: [],
        outcomes: [],
        factor_values: [],
        coverage: {}
      }
    });
  });

  await page.route('/api/assets/*/news**', async (route) => {
    await route.fulfill({
      json: {
        asset_id: 'CN:SH:600519',
        items: [],
        summary: {
          news_count_1d: 0,
          news_count_3d: 0,
          news_count_7d: 0,
          latest_published_at: undefined,
          source_count: 0,
          category_counts: []
        },
        warnings: []
      }
    });
  });

  await page.route('/api/assets/*/research-reports**', async (route) => {
    await route.fulfill({
      json: {
        asset_id: 'CN:SH:600519',
        summary: { report_count_90d: 0 },
        items: [],
        warnings: []
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

  await page.route('/api/backtests/strategies**', async (route) => {
    await route.fulfill({
      json: {
        items: [
          {
            strategy_id: 'lhb_shortline',
            strategy_name: 'LHB Shortline Combo',
            status: 'runnable',
            description: 'LHB combo',
            factor_groups: ['资金行为'],
            signal_inputs: ['龙虎榜'],
            default_parameters: { top_n: 20 },
            latest_evidence: '',
            primary_action: 'Run backtest'
          },
          {
            strategy_id: 'mid_trend',
            strategy_name: 'Mid Trend Combo',
            status: 'runnable',
            description: 'Mid trend combo',
            factor_groups: ['趋势强度'],
            signal_inputs: ['趋势'],
            default_parameters: { top_n: 5 },
            latest_evidence: '',
            primary_action: 'Run backtest'
          },
          {
            strategy_id: 'tech_bottleneck',
            strategy_name: 'Tech Bottleneck Combo',
            status: 'runnable',
            description: 'Tech bottleneck combo',
            factor_groups: ['技术形态'],
            signal_inputs: ['技术'],
            default_parameters: { top_n: 5 },
            latest_evidence: '',
            primary_action: 'Run backtest'
          }
        ]
      }
    });
  });

  await page.route('/api/assets/*/bars**', async (route) => {
    const resolution = new URL(route.request().url()).searchParams.get('resolution') ?? '1D';
    const items = Array.from({ length: 120 }, (_, index) => {
      const day = new Date(Date.UTC(2026, 0, 1 + index));
      const date = day.toISOString().slice(0, 10);
      const time = ['1D', '1W', '1M'].includes(resolution) ? date : `${date}T09:30:00+08:00`;
      return {
        time,
        open: 10 + index * 0.01,
        high: 10.2 + index * 0.01,
        low: 9.8 + index * 0.01,
        close: 10.1 + index * 0.01,
        volume: 100000 + index * 100,
        amount: 1000000 + index * 1000
      };
    });
    await route.fulfill({
      json: {
        asset_id: '000001.SZ',
        resolution,
        items
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

  await expect(page.getByText('A股策略研究')).toBeVisible();
  await expect(page.getByRole('heading', { name: '策略指挥中心' })).toBeVisible();
  await expect(page.getByText('平台日期')).toBeVisible();
  const activeStrategies = page.getByRole('region', { name: '启用策略表现' });
  await expect(activeStrategies.getByText('LHB Shortline Combo', { exact: true })).toBeVisible();
  await expect(activeStrategies.getByText('Mid Trend Combo', { exact: true })).toBeVisible();
  await expect(activeStrategies.getByText('Tech Bottleneck Combo', { exact: true })).toBeVisible();
  await expect(page.getByText('Manual V1 TopN Rotation')).toHaveCount(0);
  const strategySignals = page.getByRole('region', { name: '策略持仓状态' });
  await expect(strategySignals).toBeVisible();
  await expect(strategySignals.getByText(/最新持仓|持仓明细暂无/)).toHaveCount(3);
  await expect(page.getByText('CN:SZ:300951')).toHaveCount(0);
  await expect(page.getByText(/promote/i)).toHaveCount(0);
  await expect(page.getByText(/trade/i)).toHaveCount(0);
  await expect(page.getByText(/write/i)).toHaveCount(0);

  await page.getByRole('button', { name: 'Open Strategy Lab workspace' }).click();
  await page.getByRole('tab', { name: 'Validation Replay' }).click();
  await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toContainText('LHB Shortline');
  await expect(page.getByRole('button', { name: 'Replay' })).toBeVisible();

  await page.getByLabel('Global search').fill('600519');
  await page.getByRole('option', { name: /贵州茅台/ }).click();
  await expect(page.getByRole('heading', { name: /Stock Workspace|贵州茅台/ })).toBeVisible();

  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(horizontalOverflow).toBe(false);
});

test('dashboard shell stacks without horizontal overflow on mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDashboardApi(page);

  await page.goto('/');

  await expect(page.getByText('A股策略研究')).toBeVisible();
  await expect(page.getByRole('heading', { name: '策略指挥中心' })).toBeVisible();
  await expect(page.getByText('启用策略表现')).toBeVisible();
  await expect(page.getByText('策略持仓状态')).toBeVisible();
  await page.getByRole('button', { name: 'Open Strategy Lab workspace' }).click();
  await page.getByRole('tab', { name: 'Validation Replay' }).click();
  await expect(page.getByRole('combobox', { name: 'strategy validation run' })).toContainText('LHB Shortline');
  await expect(page.getByRole('button', { name: 'Replay' })).toBeVisible();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(horizontalOverflow).toBe(false);
});

test('concept heatmap exposes complete hover information and click detail', async ({ page }) => {
  await mockDashboardApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Open Market Monitor workspace' }).click();
  const sectorToolbar = page.getByRole('toolbar', { name: '板块类型切换' });
  await sectorToolbar.getByRole('button', { name: '概念', exact: true }).click();

  const tile = page.getByRole('button', { name: '兼容热力块 上涨 ST板块' });
  await expect(tile).toBeVisible();
  await tile.hover();

  const tooltip = page.getByRole('tooltip', { name: '板块数据' });
  await expect(tooltip).toContainText('ST板块');
  await expect(tooltip).toContainText('涨跌幅 +9.89%');
  await expect(tooltip).toContainText('成交额 29.24亿');
  await expect(tooltip).toContainText('上涨/下跌 5/12');
  await expect(tooltip).toContainText('成分股 20');
  await expect(tooltip).toContainText('主力净流入 --');

  await tile.click();
  await expect(page.getByRole('heading', { level: 3, name: 'ST板块' })).toBeVisible();
});

async function hoverRightmostChartBar(page: Page) {
  const chart = page.locator('.asset-chart');
  await chart.scrollIntoViewIfNeeded();
  const chartBox = await chart.boundingBox();
  expect(chartBox).not.toBeNull();
  const tooltip = page.getByRole('tooltip', { name: 'K线数据' });
  for (const offset of [36, 48, 60, 72, 84, 96, 108, 120]) {
    await page.mouse.move(chartBox!.x + chartBox!.width - offset, chartBox!.y + 200);
    if (await tooltip.waitFor({ state: 'visible', timeout: 400 }).then(() => true).catch(() => false)) {
      return chartBox!;
    }
  }
  throw new Error('rightmost chart bar did not emit a tooltip');
}

test('rightmost stock bars keep the full tooltip inside the chart', async ({ page }) => {
  await mockDashboardApi(page);
  await page.goto('/');
  await page.getByLabel('Global search').fill('600519');
  await page.getByRole('option', { name: /贵州茅台/ }).click();
  await expect(page.getByRole('heading', { name: /贵州茅台/ })).toBeVisible();
  await expect(page.locator('.stock-price-behavior')).toBeVisible();
  await expect(page.getByRole('group', { name: '时间窗口' })).toContainText('120 bars');

  for (const period of ['日K', '周K', '月K', '分时']) {
    if (period !== '日K') {
      await page.getByRole('button', { name: period, exact: true }).click();
    }
    await expect(page.getByRole('button', { name: period, exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('group', { name: '时间窗口' })).toContainText('120 bars');
    const chartBox = await hoverRightmostChartBar(page);
    const tooltip = page.getByRole('tooltip', { name: 'K线数据' });
    const tooltipBox = await tooltip.boundingBox();
    expect(tooltipBox).not.toBeNull();
    expect(tooltipBox!.x).toBeGreaterThanOrEqual(chartBox.x);
    expect(tooltipBox!.x + tooltipBox!.width).toBeLessThanOrEqual(chartBox.x + chartBox.width);
    for (const label of ['开', '高', '低', '收', '量', '额']) {
      await expect(tooltip).toContainText(label);
    }
  }
});
