import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { ShadowAnalyticsReviewPanel } from '../src/components/ShadowAnalyticsReviewPanel';
import { ShadowReviewDecisionsPanel } from '../src/components/ShadowReviewDecisionsPanel';
import { ShadowFollowUpQueuePanel } from '../src/components/ShadowFollowUpQueuePanel';
import { ShadowFollowUpResolutionPanel } from '../src/components/ShadowFollowUpResolutionPanel';
import { ShadowOutcomeAnalyticsPanel } from '../src/components/ShadowOutcomeAnalyticsPanel';
import { ShadowOutcomesPanel } from '../src/components/ShadowOutcomesPanel';
import type {
  BarPoint,
  AssetProfile,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
  MarketMonitorPayload,
  GlobalSearchResponse,
  GlobalSearchResult,
  OutcomeAnalyticsRow,
  ScoreRow,
  ShadowAnalyticsReviewRow,
  ShadowFollowUpRow,
  ShadowFollowUpResolutionRow,
  ShadowReviewDecisionRow,
  ShadowOutcomeAnalyticsRow,
  ShadowOutcomeRow,
  ShadowWatchlistRow,
  WatchlistSignalRow
} from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchPlatformSummary: vi.fn(),
  fetchStrategyCatalog: vi.fn(),
  fetchOverview: vi.fn(),
  fetchAssetProfile: vi.fn(),
  fetchAssetNews: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn(),
  fetchAssetDecisions: vi.fn(),
  fetchAssetOutcomes: vi.fn(),
  fetchExperimentProposals: vi.fn(),
  fetchExperimentReplay: vi.fn(),
  fetchOutcomeAnalytics: vi.fn(),
  fetchPublicNews: vi.fn(),
  fetchPublicNewsStatus: vi.fn(),
  refreshPublicNews: vi.fn(),
  fetchGlobalSearch: vi.fn(),
  searchAssets: vi.fn(),
  fetchShadowAnalyticsReview: vi.fn(),
  fetchShadowFollowUpQueue: vi.fn(),
  fetchShadowFollowUpResolution: vi.fn(),
  fetchShadowReviewDecisions: vi.fn(),
  fetchShadowOutcomeAnalytics: vi.fn(),
  fetchShadowOutcomes: vi.fn(),
  fetchShadowWatchlist: vi.fn(),
  fetchFactorLibrary: vi.fn(),
  fetchFactorScorePreview: vi.fn(),
  fetchMarketMonitorEod: vi.fn(),
  fetchResearchReportSummary: vi.fn(),
  fetchResearchReports: vi.fn(),
  fetchAssetResearchReports: vi.fn(),
  fetchStrategyValidationRuns: vi.fn(),
  fetchStrategyValidationReplay: vi.fn(),
  fetchBacktestStrategies: vi.fn(),
  runBacktest: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars }: { bars: unknown[] }) => <div data-testid="asset-chart">{bars.length} bars</div>
}));

function makeOverview(overrides: Partial<DashboardOverview> = {}): DashboardOverview {
  return {
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
        asset_id: '000002.SZ',
        stock_code: '000002',
        stock_name: 'Vanke',
        priority: 5,
        signal_score: 72,
        primary_signal: 'observe',
        signal_tags: ['trend_ok'],
        risk_tags: ['high_volatility'],
        must_watch: true,
        reason_json: {}
      }
    ],
    reports: [
      {
        report_type: 'daily',
        title: 'Daily Review',
        path: '/reports/daily.html',
        format: 'html',
        trade_date: '2026-05-29'
      }
    ],
    ...overrides
  };
}

function makeScore(assetId = '000001.SZ'): ScoreRow {
  return {
    trade_date: '2026-05-29',
    asset_id: assetId,
    rank: 1,
    score_total: 91.2,
    score_version: 'manual_v1',
    score_components: {}
  };
}

function makeSignals(assetId = '000001.SZ'): WatchlistSignalRow[] {
  return [
    {
      watchlist_id: 'default',
      trade_date: '2026-05-29',
      asset_id: assetId,
      stock_code: assetId.slice(0, 6),
      stock_name: 'Ping An Bank',
      priority: 10,
      signal_score: 80,
      primary_signal: 'watch',
      signal_tags: [],
      risk_tags: ['gap_risk'],
      must_watch: false,
      reason_json: {}
    }
  ];
}

function makeBars(count: number): BarPoint[] {
  return Array.from({ length: count }, (_, index) => ({
    time: `2026-05-${String(29 - index).padStart(2, '0')}`,
    open: 10,
    high: 11,
    low: 9,
    close: 10.5,
    volume: 100,
    amount: 1000
  }));
}

function makeAssetProfile(assetId = 'CN:SH:600519'): AssetProfile {
  return {
    asset_id: assetId,
    canonical_asset_id: assetId,
    asset: {
      asset_id: assetId,
      symbol: '600519',
      name: '贵州茅台',
      exchange: 'SH',
      board: null,
      is_active: true
    },
    bars: makeBars(1),
    score: makeScore(assetId),
    signals: [],
    decisions: [],
    outcomes: [],
    factor_values: [],
    coverage: {}
  };
}

function makeGlobalSearchResult(overrides: Partial<GlobalSearchResult> = {}): GlobalSearchResult {
  return {
    type: 'asset',
    id: 'CN:SH:600519',
    title: '贵州茅台',
    subtitle: '600519.SH',
    metadata: {},
    target: { workspace: 'stock', asset_id: 'CN:SH:600519' },
    match_reason: 'Exact code match',
    match_fields: ['symbol'],
    ...overrides
  };
}

function makeGlobalSearchPayload(result: GlobalSearchResult, query = '茅台'): GlobalSearchResponse {
  return {
    query,
    groups: [{ key: 'test', label: 'Results', items: [result] }],
    warnings: []
  };
}

const marketEmotionFixture = {
  summary: {
    score: 73.6,
    state: 'hot',
    risk_state: 'medium',
    style_signal_hint: 'growth_favorable',
    position_budget_hint: 'reduced',
    status: 'available'
  },
  components: [
    { key: 'breadth', label: '涨跌家数', score: 68.2 },
    { key: 'limit', label: '涨停表现', score: 75.4 },
    { key: 'relay', label: '连板接力', score: 71.1 },
    { key: 'feedback', label: '赚钱效应', score: 66.8 },
    { key: 'liquidity', label: '市场量能', score: 82.0 }
  ],
  breadth: {
    traded_count: 5207,
    up_count: 3610,
    down_count: 1492,
    strong_up_count: 269,
    strong_down_count: 55,
    status: 'available'
  },
  liquidity: {
    total_amount: 1280000000000,
    amount_ratio_5_20: 1.18,
    status: 'available'
  },
  limit_performance: {
    limit_up_count: 90,
    limit_down_count: 10,
    broken_limit_up_count: 55,
    broken_limit_up_rate: 0.3793,
    first_board_count: 58,
    second_board_count: 21,
    third_board_plus_count: 11,
    high_board_height: 6,
    status: 'available'
  },
  profit_effect: {
    limit_up_success_rate: 0.7361,
    limit_up_profit_rate: 0.026,
    limit_up_limit_down_rate: 0.026,
    relay_profit_rate: 0.018,
    relay_success_rate: 0.615,
    relay_continue_rate: 0.312,
    broken_profit_rate: 0.007,
    broken_success_rate: 0.564,
    broken_limit_down_rate: 0.073,
    status: 'available'
  },
  drawdown_pressure: {
    strong_down_count: 55,
    limit_down_count: 10,
    broken_limit_up_rate: 0.3793,
    yesterday_limit_up_limit_down_rate: 0.026,
    status: 'available'
  },
  weight_performance: { status: 'pending_source' }
};

const emotionStockListsFixture = {
  auction_status: 'pending_source',
  auction: [],
  limit_up: [
    {
      name: '金钼股份',
      asset_id: 'CN:SH:601958',
      symbol: '601958',
      amount: 3038000000,
      pct_chg: 10,
      board: '金属钼',
      tab: 'limit_up',
      limit_up_streak: 1
    }
  ],
  broken_limit_up: [],
  limit_down: []
};

function makeMarketMonitorPayload(overrides: Partial<MarketMonitorPayload> = {}): MarketMonitorPayload {
  return {
    trade_date: '2026-06-10',
    freshness: {
      mode: 'eod',
      label: 'Last Completed Trading Day',
      is_realtime: false,
      latest_market_date: '2026-06-10',
      latest_factor_date: '2026-06-10',
      latest_score_date: '2026-06-10'
    },
    coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
    market_breadth: {
      advancers: null,
      decliners: null,
      limit_up: null,
      limit_down: null,
      advancing_ratio: null,
      turnover_change_pct: null,
      status: 'pending_source'
    },
    index_snapshot: [],
    sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
    unusual_moves: [],
    watchlist_alerts: [],
    strategy_signal_summary: {
      topn_preview_count: 1,
      topn_preview: [
        {
          trade_date: '2026-06-10',
          asset_id: '000001.SZ',
          rank: 1,
          score_total: 91.2,
          score_version: 'manual_v1',
          score_components: {}
        }
      ],
      risk_filter_counts: {}
    },
    generated_reports: [
      {
        report_type: 'daily_topn_report',
        title: 'daily_topn.md',
        path: '/reports/topn.md',
        format: 'md',
        trade_date: '2026-06-10'
      }
    ],
    market_emotion: marketEmotionFixture,
    emotion_stock_lists: emotionStockListsFixture,
    warnings: ['market breadth source pending'],
    ...overrides
  };
}

function makeDecisions(assetId = '000001.SZ'): DecisionEventRow[] {
  return [
    {
      review_date: '2026-05-30',
      review_session_id: 'morning-review',
      event_id: 'operator_decision:morning-review:0:abc',
      asset_id: assetId,
      stock_code: assetId,
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
  ];
}

function makeOutcomes(assetId = '000001.SZ'): DecisionOutcomeRow[] {
  return [
    {
      outcome_event_id: 'operator_decision_outcome:p8:abc',
      run_id: 'p8-outcome-2026-05-01-2026-05-30',
      decision_event_id: 'operator_decision:morning-review:0:abc',
      review_session_id: 'morning-review',
      review_date: '2026-05-30',
      asset_id: assetId,
      stock_code: assetId,
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
  ];
}

function makeOutcomeAnalytics(): OutcomeAnalyticsRow[] {
  return [
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
          forward_return_median: 0.15,
          forward_win_rate: 1,
          max_high_return_mean: 0.2,
          max_low_drawdown_mean: -0.06,
          max_low_drawdown_worst: -0.08
        }
      },
      analytics_artifact_path: 'outputs/p9/operator_decision_outcome_analytics.json',
      manual_review_required: true,
      auto_trade_enabled: false
    }
  ];
}

function makeExperimentProposals(): ExperimentProposalRow[] {
  return [
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
  ];
}

function makeExperimentReplay(): ExperimentReplayRow[] {
  return [
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
  ];
}

function makeResearchReport() {
  return {
    event_key: 'app-shell-r1:000001.SZ',
    report_id: 'app-shell-r1',
    asset_id: 'CN:SZ:000001',
    ts_code: '000001.SZ',
    stock_name: 'Ping An Bank',
    industry_name: 'Banking',
    report_title: 'Ping An Bank Initiation',
    publish_date: '2026-06-03',
    report_date: '2026-06-03',
    broker: 'Example Securities',
    analyst: 'Analyst A',
    rating: 'Buy',
    rating_change: 'Maintain',
    target_price: 15.5,
    target_upside: 0.12,
    source_type: 'public_web_search_result',
    source_name: 'example_source',
    source_confidence: 0.8,
    public_access: true,
    copyright_note: 'metadata only',
    source_url: 'https://example.com/report',
    raw_summary: 'summary',
    company_view: 'company view',
    industry_view: 'industry view',
    risk_summary: 'risk',
    metadata: {}
  };
}

function makeShadowWatchlist(): ShadowWatchlistRow[] {
  return [
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
  ];
}

function makeShadowOutcomes(): ShadowOutcomeRow[] {
  return [
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
  ];
}

function makeShadowOutcomesWithInvalidMetrics(): ShadowOutcomeRow[] {
  return [
    {
      ...makeShadowOutcomes()[0],
      forward_returns: { '5': 'bad', '20': null } as unknown as Record<string, number | null>,
      max_low_drawdowns: { '20': 'bad' } as unknown as Record<string, number | null>
    }
  ];
}

function makeShadowOutcomeAnalytics(): ShadowOutcomeAnalyticsRow[] {
  return [
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
  ];
}

function makeShadowAnalyticsReview(): ShadowAnalyticsReviewRow[] {
  return [
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
  ];
}

function makeShadowReviewDecisions(): ShadowReviewDecisionRow[] {
  return [
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
  ];
}

function makeShadowFollowUpQueue(): ShadowFollowUpRow[] {
  return [
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
  ];
}

function makeShadowFollowUpResolution(): ShadowFollowUpResolutionRow[] {
  return [
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
  ];
}

describe('dashboard app shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.fetchPlatformSummary.mockResolvedValue({
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
    });
    apiMocks.fetchStrategyCatalog.mockResolvedValue([
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
    ]);
    apiMocks.fetchBacktestStrategies.mockResolvedValue([
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
      }
    ]);
    apiMocks.runBacktest.mockResolvedValue({
      strategy_id: 'manual_v1_topn_rotation',
      strategy_name: 'Manual V1 TopN Rotation',
      read_only: true,
      config: {},
      summary: {},
      equity_curve: [],
      positions: [],
      trades: []
    });
    apiMocks.fetchOverview.mockResolvedValue(makeOverview());
    apiMocks.fetchAssetProfile.mockResolvedValue(makeAssetProfile('000001.SZ'));
    apiMocks.fetchAssetNews.mockResolvedValue({
      asset_id: '000001.SZ',
      items: [],
      summary: { news_count_1d: 0, news_count_3d: 0, news_count_7d: 0, source_count: 0 },
      warnings: []
    });
    apiMocks.searchAssets.mockResolvedValue([]);
    apiMocks.fetchDailyBars.mockResolvedValue(makeBars(1));
    apiMocks.fetchAssetScore.mockResolvedValue(makeScore());
    apiMocks.fetchAssetSignals.mockResolvedValue(makeSignals());
    apiMocks.fetchAssetDecisions.mockResolvedValue(makeDecisions());
    apiMocks.fetchAssetOutcomes.mockResolvedValue(makeOutcomes());
    apiMocks.fetchOutcomeAnalytics.mockResolvedValue(makeOutcomeAnalytics());
    apiMocks.fetchPublicNews.mockResolvedValue({
      items: [
        {
          news_id: 'news-live-1',
          source: 'sina_finance',
          source_channel: '7x24',
          category: 'live',
          title: '全球快讯',
          summary: '全球财经快讯摘要',
          url: 'https://finance.sina.com.cn/live/1',
          published_at: '2026-06-11 09:00:00',
          collected_at: '2026-06-11T09:01:00+00:00',
          raw_id: '',
          raw_payload: {},
          status: 'available'
        }
      ],
      warnings: []
    });
    apiMocks.fetchPublicNewsStatus.mockResolvedValue({
      enabled: true,
      running: false,
      interval_seconds: 1800,
      next_run_at: '2026-06-11T09:30:00+00:00'
    });
    apiMocks.refreshPublicNews.mockResolvedValue({
      received: 1,
      stored: 1,
      items_received: 1,
      counts_by_category: { live: 1 },
      warnings: []
    });
    apiMocks.fetchGlobalSearch.mockResolvedValue({
      query: '茅台',
      groups: [],
      warnings: []
    });
    apiMocks.fetchExperimentProposals.mockResolvedValue(makeExperimentProposals());
    apiMocks.fetchExperimentReplay.mockResolvedValue(makeExperimentReplay());
    apiMocks.fetchShadowWatchlist.mockResolvedValue(makeShadowWatchlist());
    apiMocks.fetchShadowOutcomes.mockResolvedValue(makeShadowOutcomes());
    apiMocks.fetchShadowOutcomeAnalytics.mockResolvedValue(makeShadowOutcomeAnalytics());
    apiMocks.fetchShadowAnalyticsReview.mockResolvedValue(makeShadowAnalyticsReview());
    apiMocks.fetchShadowReviewDecisions.mockResolvedValue(makeShadowReviewDecisions());
    apiMocks.fetchShadowFollowUpQueue.mockResolvedValue(makeShadowFollowUpQueue());
    apiMocks.fetchShadowFollowUpResolution.mockResolvedValue(makeShadowFollowUpResolution());
    apiMocks.fetchFactorLibrary.mockResolvedValue([]);
    apiMocks.fetchFactorScorePreview.mockResolvedValue({ trade_date: '2026-06-08', selected_factors: [], items: [] });
    apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload());
    apiMocks.fetchResearchReportSummary.mockResolvedValue({
      total_reports: 1,
      covered_stocks: 1,
      latest_publish_date: '2026-06-03',
      latest_feature_date: '2026-06-02',
      source_count: 1,
      source_counts: [{ source_name: 'example_source', rows: 1 }],
      rating_counts: [{ rating: 'Buy', rows: 1 }],
      broker_counts: [{ broker: 'Example Securities', rows: 1 }]
    });
    apiMocks.fetchResearchReports.mockResolvedValue({
      items: [makeResearchReport()],
      total: 1,
      limit: 50,
      offset: 0,
      warnings: []
    });
    apiMocks.fetchAssetResearchReports.mockResolvedValue({
      asset_id: 'CN:SZ:000001',
      summary: {
        report_count_30d: 0,
        report_count_90d: 0,
        broker_coverage_count_90d: 0,
        latest_report_date: null,
        latest_rating: null,
        latest_target_price: null
      },
      items: [],
      warnings: []
    });
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the stock research cockpit shell title', async () => {
    render(<App />);

    expect(screen.getByText('Stock Research')).toBeVisible();
    expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
    expect(screen.getByText('Market Date')).toBeVisible();
    expect(screen.getByText('Today Focus')).toBeVisible();
    expect(screen.getByText('Market Pulse')).toBeVisible();
    expect(screen.getByText('News Flow')).toBeVisible();
    expect(screen.getByText('Strategy Health')).toBeVisible();
    expect(screen.getByText('LHB Shortline Combo')).toBeVisible();
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
  });

  it('renders the redesigned home cockpit sections', async () => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce({
      trade_date: '2026-06-10',
      freshness: { mode: 'eod', label: 'Last Completed Trading Day', is_realtime: false },
      coverage: { market_assets: 5300, score_assets: 3100, factor_count: 42 },
      market_breadth: {
        advancers: null,
        decliners: null,
        limit_up: null,
        limit_down: null,
        advancing_ratio: null,
        turnover_change_pct: null,
        status: 'pending_source'
      },
      index_snapshot: [],
      sector_strength: { strongest: [], weakest: [], status: 'pending_source' },
      unusual_moves: [],
      watchlist_alerts: [],
      strategy_signal_summary: {
        topn_preview_count: 1,
        topn_preview: [
          {
            trade_date: '2026-06-10',
            asset_id: '000001.SZ',
            rank: 1,
            score_total: 91.2,
            score_version: 'manual_v1',
            score_components: {}
          }
        ],
        risk_filter_counts: {}
      },
      generated_reports: [],
      warnings: []
    });
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [
        {
          news_id: 'news-home-1',
          source: 'sina_finance',
          source_channel: '7x24',
          category: 'live',
          title: '首页新闻',
          summary: '',
          url: '',
          published_at: '2026-06-11 10:00:00',
          collected_at: '2026-06-11T02:00:00Z',
          raw_id: '',
          raw_payload: {},
          status: 'available'
        }
      ],
      warnings: []
    });

    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeInTheDocument();
    expect(screen.getByText('Today Focus')).toBeInTheDocument();
    expect(screen.getByText('Market Pulse')).toBeInTheDocument();
    expect(screen.getByText('News Flow')).toBeInTheDocument();
    expect(screen.getByText('Strategy Health')).toBeInTheDocument();
    expect(screen.getByText('首页新闻')).toBeInTheDocument();
  });

  it('exposes the redesigned research cockpit navigation', async () => {
    render(<App />);

    expect(screen.getByRole('button', { name: 'Open Market Monitor workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Research Reports workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Stock Workspace workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Watchlist workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Strategy Lab workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Generated Reports workspace' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open Reports workspace' })).not.toBeInTheDocument();
  });

  it('opens redesigned workspaces from navigation', async () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'Open Research Reports workspace' }));
    expect(await screen.findByRole('heading', { name: 'Research Reports' })).toBeInTheDocument();
    expect(screen.getByText('Total Reports')).toBeInTheDocument();
    expect(await screen.findByText('Ping An Bank Initiation')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
    expect(await screen.findByRole('heading', { name: 'Stock Workspace' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open Watchlist workspace' }));
    expect(await screen.findByRole('heading', { name: 'Watchlist' })).toBeInTheDocument();
  });

  it('opens the Stock workspace from a global search stock result', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
        makeGlobalSearchPayload(makeGlobalSearchResult(), '600519')
      );
      apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeAssetProfile('CN:SH:600519'));

      render(<App />);

      fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      fireEvent.click(await screen.findByRole('option', { name: /贵州茅台 600519.SH/ }));

      expect(await screen.findByRole('heading', { name: /贵州茅台 CN:SH:600519/ })).toBeInTheDocument();
      expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
        'CN:SH:600519',
        '2026-06-08',
        '2025-12-10',
        '2026-06-08',
        'manual_v1',
        'qfq'
      );
    } finally {
      vi.useRealTimers();
    }
  });

  type MockWorkspaceRender = {
    initialQuery?: string;
    initialTradeDate?: string;
    initialNewsId?: string;
    initialEventKey?: string;
    initialReportId?: string;
    initialPath?: string;
    mountId?: number;
  };

  async function renderMockedAppShellForHandoff() {
    vi.resetModules();

    const newsResult = makeGlobalSearchResult({
      type: 'news',
      id: 'news-1',
      title: '贵州茅台新闻',
      subtitle: '7x24',
      target: {
        workspace: 'news',
        q: '茅台',
        news_id: 'news-1',
        asset_id: 'CN:SH:600519'
      } as GlobalSearchResult['target']
    });
    const researchResult = makeGlobalSearchResult({
      type: 'research_report',
      id: 'report-1',
      title: '茅台深度',
      subtitle: 'example broker',
      target: {
        workspace: 'researchReports',
        q: '茅台',
        event_key: 'evt-1',
        report_id: 'report-1',
        asset_id: 'CN:SH:600519'
      } as GlobalSearchResult['target']
    });
    const generatedResult = makeGlobalSearchResult({
      type: 'generated_report',
      id: 'generated:/reports/daily-topn.html',
      title: 'Daily TopN',
      subtitle: 'daily_topn_report',
      trade_date: '2026-06-10',
      target: {
        workspace: 'generatedReports',
        q: 'Daily',
        trade_date: '2026-06-10',
        path: '/reports/daily-topn.html'
      } as GlobalSearchResult['target']
    });

    const newsRenders: MockWorkspaceRender[] = [];
    const researchRenders: MockWorkspaceRender[] = [];
    const generatedRenders: MockWorkspaceRender[] = [];
    let newsMountId = 0;

    vi.doMock('../src/components/GlobalSearchBox', () => ({
      GlobalSearchBox: ({ onOpenResult }: { onOpenResult: (result: GlobalSearchResult) => void }) => (
        <div>
          <button type="button" onClick={() => onOpenResult(newsResult)}>
            Mock open news
          </button>
          <button type="button" onClick={() => onOpenResult(researchResult)}>
            Mock open research
          </button>
          <button type="button" onClick={() => onOpenResult(generatedResult)}>
            Mock open generated
          </button>
        </div>
      )
    }));
    vi.doMock('../src/components/DataExplorerWorkspace', () => ({ DataExplorerWorkspace: () => <div>data workspace</div> }));
    vi.doMock('../src/components/FactorLabWorkspace', () => ({ FactorLabWorkspace: () => <div>factor workspace</div> }));
    vi.doMock('../src/components/HomeCockpit', () => ({ HomeCockpit: () => <div>home workspace</div> }));
    vi.doMock('../src/components/MarketMonitorWorkspace', () => ({ MarketMonitorWorkspace: () => <div>market workspace</div> }));
    vi.doMock('../src/components/StockWorkspace', () => ({ StockWorkspace: () => <div>stock workspace</div> }));
    vi.doMock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>strategy workspace</div> }));
    vi.doMock('../src/components/WatchlistWorkspace', () => ({ WatchlistWorkspace: () => <div>watchlist workspace</div> }));
    vi.doMock('../src/components/NewsWorkspace', async () => {
      const React = await import('react');
      return {
        NewsWorkspace: ({
          initialQuery,
          initialNewsId
        }: {
          initialQuery?: string;
          initialNewsId?: string;
        }) => {
          const [mountId] = React.useState(() => {
            newsMountId += 1;
            return newsMountId;
          });
          newsRenders.push({ initialQuery, initialNewsId, mountId });
          return (
            <div data-testid="mock-news-workspace">
              {initialQuery}:{initialNewsId ?? 'none'}:{mountId}
            </div>
          );
        }
      };
    });
    vi.doMock('../src/components/ResearchReportsWorkspace', () => ({
      ResearchReportsWorkspace: ({
        initialQuery,
        initialEventKey,
        initialReportId
      }: {
        initialQuery?: string;
        initialEventKey?: string;
        initialReportId?: string;
      }) => {
        researchRenders.push({ initialQuery, initialEventKey, initialReportId });
        return (
          <div data-testid="mock-research-workspace">
            {initialQuery}:{initialEventKey ?? 'none'}:{initialReportId ?? 'none'}
          </div>
        );
      }
    }));
    vi.doMock('../src/components/GeneratedReportsWorkspace', () => ({
      GeneratedReportsWorkspace: ({
        initialQuery,
        initialTradeDate,
        initialPath
      }: {
        initialQuery?: string;
        initialTradeDate?: string;
        initialPath?: string;
      }) => {
        generatedRenders.push({ initialQuery, initialTradeDate, initialPath });
        return (
          <div data-testid="mock-generated-workspace">
            {initialQuery}:{initialTradeDate ?? 'none'}:{initialPath ?? 'none'}
          </div>
        );
      }
    }));

    const { AppShell } = await import('../src/components/AppShell');
    render(<AppShell />);

    return { generatedRenders, newsRenders, researchRenders };
  }

  it('preserves news handoff context and remounts on the same result', async () => {
    const { newsRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open news' }));
    expect(await screen.findByTestId('mock-news-workspace')).toHaveTextContent('茅台:news-1:1');
    expect(newsRenders.at(-1)).toMatchObject({
      initialQuery: '茅台',
      initialNewsId: 'news-1',
      mountId: 1
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mock open news' }));
    expect(await screen.findByTestId('mock-news-workspace')).toHaveTextContent('茅台:news-1:2');
    expect(newsRenders.at(-1)).toMatchObject({
      initialQuery: '茅台',
      initialNewsId: 'news-1',
      mountId: 2
    });
  });

  it('preserves research report handoff context', async () => {
    const { researchRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open research' }));
    expect(await screen.findByTestId('mock-research-workspace')).toHaveTextContent('茅台:evt-1:report-1');
    expect(researchRenders.at(-1)).toMatchObject({
      initialQuery: '茅台',
      initialEventKey: 'evt-1',
      initialReportId: 'report-1'
    });
  });

  it('preserves generated report handoff context', async () => {
    const { generatedRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open generated' }));
    expect(await screen.findByTestId('mock-generated-workspace')).toHaveTextContent(
      'Daily:2026-06-10:/reports/daily-topn.html'
    );
    expect(generatedRenders.at(-1)).toMatchObject({
      initialQuery: 'Daily',
      initialTradeDate: '2026-06-10',
      initialPath: '/reports/daily-topn.html'
    });
  });

  it('opens the News workspace with the global search result query', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
        makeGlobalSearchPayload(
          makeGlobalSearchResult({
            type: 'news',
            id: 'news-1',
            title: '贵州茅台新闻',
            subtitle: '7x24',
            target: { workspace: 'news', q: '茅台' }
          })
        )
      );
      apiMocks.fetchPublicNews.mockResolvedValue({
        items: [
          {
            news_id: 'news-1',
            source: 'sina_finance',
            source_channel: '7x24',
            category: 'live',
            title: '贵州茅台新闻',
            summary: '茅台公告摘要',
            url: 'https://finance.sina.com.cn/live/maotai',
            published_at: '2026-06-11 09:00:00',
            collected_at: '2026-06-11T09:01:00+00:00',
            raw_id: '',
            raw_payload: {},
            status: 'available'
          }
        ],
        warnings: []
      });

      render(<App />);

      fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '茅台' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      fireEvent.click(await screen.findByRole('option', { name: /贵州茅台新闻 7x24/ }));

      expect(await screen.findByRole('heading', { name: 'News', level: 1 })).toBeVisible();
      expect(screen.getByLabelText('news search')).toHaveValue('茅台');
    } finally {
      vi.useRealTimers();
    }
  });

  it('reapplies the News query when selecting the same global search result again', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const newsResult = makeGlobalSearchResult({
        type: 'news',
        id: 'news-1',
        title: '贵州茅台新闻',
        subtitle: '7x24',
        target: { workspace: 'news', q: '茅台' }
      });
      apiMocks.fetchGlobalSearch
        .mockResolvedValueOnce(makeGlobalSearchPayload(newsResult))
        .mockResolvedValueOnce(makeGlobalSearchPayload(newsResult));
      apiMocks.fetchPublicNews.mockResolvedValue({
        items: [
          {
            news_id: 'news-1',
            source: 'sina_finance',
            source_channel: '7x24',
            category: 'live',
            title: '贵州茅台新闻',
            summary: '茅台公告摘要',
            url: 'https://finance.sina.com.cn/live/maotai',
            published_at: '2026-06-11 09:00:00',
            collected_at: '2026-06-11T09:01:00+00:00',
            raw_id: '',
            raw_payload: {},
            status: 'available'
          }
        ],
        warnings: []
      });

      render(<App />);

      fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '茅台' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      fireEvent.click(await screen.findByRole('option', { name: /贵州茅台新闻 7x24/ }));

      const newsSearch = await screen.findByLabelText('news search');
      expect(newsSearch).toHaveValue('茅台');

      fireEvent.change(newsSearch, { target: { value: '别的' } });
      expect(newsSearch).toHaveValue('别的');

      fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '茅台' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      fireEvent.click(await screen.findByRole('option', { name: /贵州茅台新闻 7x24/ }));

      expect(screen.getByLabelText('news search')).toHaveValue('茅台');
    } finally {
      vi.useRealTimers();
    }
  });

  it('opens Generated Reports with the global search result trade date', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
        makeGlobalSearchPayload(
          makeGlobalSearchResult({
            type: 'generated_report',
            id: 'generated:/reports/daily-topn.html',
            title: 'Daily TopN',
            subtitle: 'daily_topn_report',
            target: {
              workspace: 'generatedReports',
              q: 'Daily',
              trade_date: '2026-06-10'
            } as GlobalSearchResult['target']
          }),
          'Daily'
        )
      );
      apiMocks.fetchOverview.mockResolvedValue({
        ...makeOverview({ trade_date: '2026-06-10' }),
        reports: [
          {
            report_type: 'daily_topn_report',
            title: 'Daily TopN',
            path: '/reports/daily-topn.html',
            format: 'html',
            trade_date: '2026-06-10'
          }
        ]
      });

      render(<App />);

      fireEvent.change(screen.getByLabelText('Global search'), { target: { value: 'Daily' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      fireEvent.click(await screen.findByRole('option', { name: /Daily TopN daily_topn_report/ }));

      expect(await screen.findByRole('heading', { name: 'Generated Reports', level: 1 })).toBeVisible();
      expect(screen.getByLabelText('generated reports search')).toHaveValue('Daily');
      await waitFor(() =>
        expect(apiMocks.fetchOverview).toHaveBeenLastCalledWith({
          tradeDate: '2026-06-10',
          scoreVersion: 'manual_v1',
          watchlistId: 'default',
          topN: 5
        })
      );
      expect(await screen.findByText('Daily TopN')).toBeVisible();
    } finally {
      vi.useRealTimers();
    }
  });

  it('renders EOD market monitor data without implying realtime data', async () => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(makeMarketMonitorPayload());

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    expect(screen.getByText('Last Completed Trading Day')).toBeInTheDocument();
    expect(screen.getByText('2026-06-10')).toBeInTheDocument();
    expect(screen.getByText('综合强度')).toBeInTheDocument();
    expect(screen.getByText('73.6')).toBeInTheDocument();
    expect(screen.getByText('hot')).toBeInTheDocument();
    expect(screen.getAllByText('涨跌家数').length).toBeGreaterThan(0);
    expect(screen.getByText('3,610')).toBeInTheDocument();
    expect(screen.getAllByText('市场量能').length).toBeGreaterThan(0);
    expect(screen.getByText('1.18x')).toBeInTheDocument();
    expect(screen.getAllByText('涨停表现').length).toBeGreaterThan(0);
    expect(screen.getByText('最高 6 板')).toBeInTheDocument();
    expect(screen.getAllByText('赚钱效应').length).toBeGreaterThan(0);
    expect(screen.getByText('73.61%')).toBeInTheDocument();
    expect(screen.getByText('2.60%')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '竞价 0' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '涨停 1' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '炸板 0' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '跌停 0' })).toBeInTheDocument();
    expect(screen.getByText('金钼股份')).toBeInTheDocument();
    expect(screen.getByText('30.38亿')).toBeInTheDocument();
    expect(screen.getByText('权重表现待接入')).toBeInTheDocument();
  });

  it('loads market monitor history for a selected trade date', async () => {
    apiMocks.fetchMarketMonitorEod
      .mockResolvedValueOnce(makeMarketMonitorPayload())
      .mockResolvedValueOnce(makeMarketMonitorPayload())
      .mockResolvedValueOnce(
        makeMarketMonitorPayload({
          trade_date: '2026-06-09',
          freshness: {
            mode: 'eod',
            label: 'Historical EOD',
            is_realtime: false,
            latest_market_date: '2026-06-10',
            latest_factor_date: '2026-06-10',
            latest_score_date: '2026-06-10'
          },
          market_emotion: {
            ...marketEmotionFixture,
            summary: { ...marketEmotionFixture.summary, score: 61.2, state: 'warm' }
          }
        })
      );

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    const tradeDateInput = screen.getByLabelText('Market monitor trade date');
    await waitFor(() => expect(tradeDateInput).toHaveValue('2026-06-10'));

    fireEvent.change(tradeDateInput, { target: { value: '2026-06-09' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Date' }));

    await waitFor(() => expect(apiMocks.fetchMarketMonitorEod).toHaveBeenLastCalledWith({ topN: 5, tradeDate: '2026-06-09' }));
    expect(await screen.findByText('Historical EOD')).toBeInTheDocument();
    expect(screen.getByText('61.2')).toBeInTheDocument();
    expect(tradeDateInput).toHaveValue('2026-06-09');
  });

  it('shows the selected market monitor date while historical data is loading', async () => {
    let resolveHistoricalRequest: (payload: MarketMonitorPayload) => void = () => undefined;
    const historicalRequest = new Promise<MarketMonitorPayload>((resolve) => {
      resolveHistoricalRequest = resolve;
    });
    apiMocks.fetchMarketMonitorEod
      .mockResolvedValueOnce(makeMarketMonitorPayload())
      .mockResolvedValueOnce(makeMarketMonitorPayload())
      .mockReturnValueOnce(historicalRequest);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    const tradeDateInput = screen.getByLabelText('Market monitor trade date');
    await waitFor(() => expect(tradeDateInput).toHaveValue('2026-06-10'));

    fireEvent.change(tradeDateInput, { target: { value: '2026-06-04' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Date' }));

    expect(await screen.findByText('Loading 2026-06-04...')).toBeInTheDocument();
    expect(screen.getByText('2026-06-10')).toBeInTheDocument();

    await act(async () => {
      resolveHistoricalRequest(
        makeMarketMonitorPayload({
          trade_date: '2026-06-04',
          freshness: {
            mode: 'eod',
            label: 'Historical EOD',
            is_realtime: false,
            latest_market_date: '2026-06-10',
            latest_factor_date: '2026-06-10',
            latest_score_date: '2026-06-10'
          }
        })
      );
      await historicalRequest;
    });

    expect(screen.queryByText('Loading 2026-06-04...')).not.toBeInTheDocument();
    expect(tradeDateInput).toHaveValue('2026-06-04');
  });

  it('renders partial EOD market monitor payloads without crashing', async () => {
    apiMocks.fetchMarketMonitorEod
      .mockResolvedValueOnce(makeMarketMonitorPayload())
      .mockResolvedValueOnce({
        trade_date: '2026-06-10'
      } as unknown as MarketMonitorPayload);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    expect(screen.getByText('Last Completed Trading Day')).toBeInTheDocument();
    expect(await screen.findByText('2026-06-10')).toBeInTheDocument();
    expect(screen.getByText('权重表现待接入')).toBeInTheDocument();
    expect(screen.getByText('情绪拆解待接入')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '涨停 0' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('暂无股票')).toBeInTheDocument();
  });

  it('supports keyboard navigation across market monitor stock tabs', async () => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(makeMarketMonitorPayload());

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    await screen.findByRole('heading', { name: 'Market Monitor' });
    const auctionTab = screen.getByRole('tab', { name: '竞价 0' });
    const limitUpTab = screen.getByRole('tab', { name: '涨停 1' });
    const brokenTab = screen.getByRole('tab', { name: '炸板 0' });
    const limitDownTab = screen.getByRole('tab', { name: '跌停 0' });

    expect(limitUpTab).toHaveAttribute('aria-selected', 'true');
    limitUpTab.focus();

    fireEvent.keyDown(limitUpTab, { key: 'ArrowRight' });
    expect(brokenTab).toHaveAttribute('aria-selected', 'true');
    expect(brokenTab).toHaveFocus();

    fireEvent.keyDown(brokenTab, { key: 'Home' });
    expect(auctionTab).toHaveAttribute('aria-selected', 'true');
    expect(auctionTab).toHaveFocus();

    fireEvent.keyDown(auctionTab, { key: 'End' });
    expect(limitDownTab).toHaveAttribute('aria-selected', 'true');
    expect(limitDownTab).toHaveFocus();

    fireEvent.keyDown(limitDownTab, { key: 'ArrowLeft' });
    expect(brokenTab).toHaveAttribute('aria-selected', 'true');
    expect(brokenTab).toHaveFocus();
  });

  it('ignores deferred market monitor responses after navigating away', async () => {
    let resolveMarketMonitor: (payload: MarketMonitorPayload) => void = () => undefined;
    const pendingMarketMonitor = new Promise<MarketMonitorPayload>((resolve) => {
      resolveMarketMonitor = resolve;
    });
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(makeMarketMonitorPayload()).mockReturnValueOnce(pendingMarketMonitor);

    try {
      render(<App />);
      fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));
      expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Open Home workspace' }));
      expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeInTheDocument();

      await act(async () => {
        resolveMarketMonitor(
          makeMarketMonitorPayload({
            strategy_signal_summary: {
              topn_preview_count: 1,
              topn_preview: [
                {
                  trade_date: '2026-06-10',
                  asset_id: 'STALE.MKT',
                  rank: 1,
                  score_total: 99.9,
                  score_version: 'manual_v1',
                  score_components: {}
                }
              ],
              risk_filter_counts: {}
            },
            warnings: ['stale market monitor payload']
          })
        );
        await pendingMarketMonitor;
      });

      await waitFor(() => expect(screen.queryByText('STALE.MKT')).not.toBeInTheDocument());
      expect(screen.queryByText('stale market monitor payload')).not.toBeInTheDocument();
      expect(consoleError).not.toHaveBeenCalled();
    } finally {
      consoleError.mockRestore();
    }
  });

  it('keeps the latest market monitor request when older responses resolve later', async () => {
    let resolveFirstRequest: (payload: MarketMonitorPayload) => void = () => undefined;
    let resolveSecondRequest: (payload: MarketMonitorPayload) => void = () => undefined;
    const firstRequest = new Promise<MarketMonitorPayload>((resolve) => {
      resolveFirstRequest = resolve;
    });
    const secondRequest = new Promise<MarketMonitorPayload>((resolve) => {
      resolveSecondRequest = resolve;
    });
    apiMocks.fetchMarketMonitorEod
      .mockResolvedValueOnce(makeMarketMonitorPayload())
      .mockReturnValueOnce(firstRequest)
      .mockReturnValueOnce(secondRequest);

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));
    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('button', { name: 'Load Latest EOD' }));
    expect(apiMocks.fetchMarketMonitorEod).toHaveBeenCalledTimes(3);

    await act(async () => {
      resolveSecondRequest(
        makeMarketMonitorPayload({
          trade_date: '2026-06-11',
          freshness: {
            mode: 'eod',
            label: 'Last Completed Trading Day',
            is_realtime: false,
            latest_market_date: '2026-06-11',
            latest_factor_date: '2026-06-11',
            latest_score_date: '2026-06-11'
          },
          strategy_signal_summary: {
            topn_preview_count: 1,
            topn_preview: [
              {
                trade_date: '2026-06-11',
                asset_id: '000002.SZ',
                rank: 1,
                score_total: 88.8,
                score_version: 'manual_v1',
                score_components: {}
              }
            ],
            risk_filter_counts: {}
          },
          warnings: []
        })
      );
      await secondRequest;
    });

    expect(await screen.findByText('000002.SZ')).toBeInTheDocument();
    expect(screen.getByText('2026-06-11')).toBeInTheDocument();

    await act(async () => {
      resolveFirstRequest(makeMarketMonitorPayload());
      await firstRequest;
    });

    expect(screen.getByText('000002.SZ')).toBeInTheDocument();
    expect(screen.getByText('2026-06-11')).toBeInTheDocument();
    expect(screen.queryByText('000001.SZ')).not.toBeInTheDocument();
    expect(screen.queryByText('2026-06-10')).not.toBeInTheDocument();
  });

  it('navigates between planned platform workspaces', async () => {
    render(<App />);
    await screen.findByRole('heading', { name: 'Research Cockpit' });
    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));

    fireEvent.click(navigation.getByRole('button', { name: 'Open Factor Lab workspace' }));
    expect(await screen.findByRole('heading', { name: 'Factor Lab' })).toBeVisible();

    fireEvent.click(navigation.getByRole('button', { name: 'Open Strategy Lab workspace' }));
    expect(await screen.findByRole('heading', { name: 'Strategy Lab' })).toBeVisible();
    const runBacktestTab = screen.getByRole('tab', { name: 'Run Backtest' });
    expect(runBacktestTab).toBeVisible();
    expect(runBacktestTab).toHaveClass('active');
    expect(runBacktestTab).toHaveAttribute('id', 'strategy-lab-tab-backtest');
    expect(runBacktestTab).toHaveAttribute('aria-controls', 'strategy-lab-panel-backtest');
    expect(runBacktestTab).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tabpanel', { name: 'Run Backtest' })).toHaveAttribute('id', 'strategy-lab-panel-backtest');

    fireEvent.click(navigation.getByRole('button', { name: 'Open Generated Reports workspace' }));
    expect(await screen.findByRole('heading', { name: 'Generated Reports', level: 1 })).toBeVisible();
    expect(screen.getByRole('region', { name: 'Generated Reports workspace' })).toBeVisible();

    fireEvent.click(navigation.getByRole('button', { name: 'Open News workspace' }));
    expect(await screen.findByRole('heading', { name: 'News', level: 1 })).toBeVisible();
    expect(await screen.findByText('全球快讯')).toBeVisible();
  });

  it('auto-refreshes news and preserves visible rows on refresh failure', async () => {
    vi.useFakeTimers();
    try {
      apiMocks.fetchPublicNews
        .mockResolvedValueOnce({
          items: [
            {
              news_id: 'news-1',
              source: 'sina_finance',
              source_channel: '7x24',
              category: 'live',
              title: '首条快讯',
              summary: '',
              url: '',
              published_at: '2026-06-11 10:00:00',
              collected_at: '2026-06-11T02:00:00Z',
              raw_id: '',
              raw_payload: {},
              status: 'available'
            }
          ],
          warnings: []
        })
        .mockResolvedValueOnce({
          items: [
            {
              news_id: 'news-1',
              source: 'sina_finance',
              source_channel: '7x24',
              category: 'live',
              title: '首条快讯',
              summary: '',
              url: '',
              published_at: '2026-06-11 10:00:00',
              collected_at: '2026-06-11T02:00:00Z',
              raw_id: '',
              raw_payload: {},
              status: 'available'
            }
          ],
          warnings: []
        });
      render(<App />);
      fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));
      await act(async () => {
        await Promise.resolve();
      });

      expect(screen.getByText('首条快讯')).toBeInTheDocument();
      apiMocks.fetchPublicNews.mockRejectedValueOnce(new Error('source timeout'));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30 * 60 * 1000);
      });

      expect(apiMocks.fetchPublicNews).toHaveBeenLastCalledWith({
        source: 'sina_finance',
        limit: 3,
        minQualityScore: 70
      });
      expect(apiMocks.refreshPublicNews).not.toHaveBeenCalled();
      expect(screen.getByText('source timeout')).toBeInTheDocument();
      expect(screen.getByText('首条快讯')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('clears news loading when refresh completes before initial load', async () => {
    let resolveInitialFetch: (payload: Awaited<ReturnType<typeof apiMocks.fetchPublicNews>>) => void = () => undefined;
    const initialFetch = new Promise<Awaited<ReturnType<typeof apiMocks.fetchPublicNews>>>((resolve) => {
      resolveInitialFetch = resolve;
    });

    apiMocks.fetchPublicNews.mockReset();
    apiMocks.refreshPublicNews.mockReset();
    apiMocks.fetchPublicNews
      .mockResolvedValueOnce({ items: [], warnings: [] })
      .mockReturnValueOnce(initialFetch)
      .mockResolvedValueOnce({
        items: [
          {
            news_id: 'news-refresh',
            source: 'sina_finance',
            source_channel: '7x24',
            category: 'live',
            title: '刷新后的快讯',
            summary: '',
            url: '',
            published_at: '2026-06-11 10:03:00',
            collected_at: '2026-06-11T02:03:00Z',
            raw_id: '',
            raw_payload: {},
            status: 'available'
          }
        ],
        warnings: []
      });
    apiMocks.refreshPublicNews.mockResolvedValue({
      received: 1,
      stored: 1,
      items_received: 1,
      counts_by_category: { live: 1 },
      warnings: []
    });

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));
    expect(await screen.findByText('Loading news...')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
    await act(async () => {
      await Promise.resolve();
    });

    expect(screen.queryByText('Loading news...')).not.toBeInTheDocument();
    expect(screen.getByText('刷新后的快讯')).toBeInTheDocument();

    await act(async () => {
      resolveInitialFetch({
        items: [
          {
            news_id: 'news-stale-initial',
            source: 'sina_finance',
            source_channel: '7x24',
            category: 'live',
            title: '过期初始快讯',
            summary: '',
            url: '',
            published_at: '2026-06-11 10:00:00',
            collected_at: '2026-06-11T02:00:00Z',
            raw_id: '',
            raw_payload: {},
            status: 'available'
          }
        ],
        warnings: []
      });
      await initialFetch;
    });

    expect(screen.getByText('刷新后的快讯')).toBeInTheDocument();
    expect(screen.queryByText('过期初始快讯')).not.toBeInTheDocument();
  });

  it('keeps manual news refresh results when an older interval refresh resolves later', async () => {
    let resolveIntervalFetch: (payload: Awaited<ReturnType<typeof apiMocks.fetchPublicNews>>) => void = () => undefined;
    const intervalFetch = new Promise<Awaited<ReturnType<typeof apiMocks.fetchPublicNews>>>((resolve) => {
      resolveIntervalFetch = resolve;
    });

    vi.useFakeTimers();
    try {
      apiMocks.fetchPublicNews.mockReset();
      apiMocks.refreshPublicNews.mockReset();
      apiMocks.fetchPublicNews
        .mockResolvedValueOnce({ items: [], warnings: [] })
        .mockResolvedValueOnce({
          items: [
            {
              news_id: 'news-initial',
              source: 'sina_finance',
              source_channel: '7x24',
              category: 'live',
              title: '初始快讯',
              summary: '',
              url: '',
              published_at: '2026-06-11 10:00:00',
              collected_at: '2026-06-11T02:00:00Z',
              raw_id: '',
              raw_payload: {},
              status: 'available'
            }
          ],
          warnings: []
        })
        .mockReturnValueOnce(intervalFetch)
        .mockResolvedValueOnce({
          items: [
            {
              news_id: 'news-manual',
              source: 'sina_finance',
              source_channel: '7x24',
              category: 'live',
              title: '手动刷新快讯',
              summary: '',
              url: '',
              published_at: '2026-06-11 10:02:00',
              collected_at: '2026-06-11T02:02:00Z',
              raw_id: '',
              raw_payload: {},
              status: 'available'
            }
          ],
          warnings: ['manual warning']
        });
      apiMocks.refreshPublicNews.mockResolvedValue({
        received: 1,
        stored: 1,
        items_received: 1,
        counts_by_category: { live: 1 },
        warnings: []
      });

      render(<App />);
      fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText('初始快讯')).toBeInTheDocument();

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30 * 60 * 1000);
      });
      expect(apiMocks.fetchPublicNews).toHaveBeenCalledTimes(3);

      fireEvent.click(screen.getByRole('button', { name: 'Refresh' }));
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.getByText('手动刷新快讯')).toBeInTheDocument();
      expect(screen.getByText('manual warning')).toBeInTheDocument();

      await act(async () => {
        resolveIntervalFetch({
          items: [
            {
              news_id: 'news-interval',
              source: 'sina_finance',
              source_channel: '7x24',
              category: 'live',
              title: '过期自动刷新快讯',
              summary: '',
              url: '',
              published_at: '2026-06-11 10:01:00',
              collected_at: '2026-06-11T02:01:00Z',
              raw_id: '',
              raw_payload: {},
              status: 'available'
            }
          ],
          warnings: ['stale interval warning']
        });
        await intervalFetch;
      });

      expect(screen.getByText('手动刷新快讯')).toBeInTheDocument();
      expect(screen.getByText('manual warning')).toBeInTheDocument();
      expect(screen.queryByText('过期自动刷新快讯')).not.toBeInTheDocument();
      expect(screen.queryByText('stale interval warning')).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('switches from cockpit to strategy validation mode', async () => {
    apiMocks.fetchStrategyValidationRuns.mockResolvedValue([
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
        warnings: []
      }
    ]);
    apiMocks.fetchStrategyValidationReplay.mockResolvedValue({
      run: null,
      asset_id: '000001.SZ',
      bars: [],
      signals: [],
      trades: [],
      positions: [],
      metrics: [],
      artifacts: []
    });

    render(<App />);
    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));

    fireEvent.click(navigation.getByRole('button', { name: 'Open Strategy Lab workspace' }));
    const validationTab = await screen.findByRole('tab', { name: 'Validation Replay' });
    fireEvent.click(validationTab);

    expect(validationTab).toHaveClass('active');
    expect(validationTab).toHaveAttribute('id', 'strategy-lab-tab-validation');
    expect(validationTab).toHaveAttribute('aria-controls', 'strategy-lab-panel-validation');
    expect(validationTab).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tabpanel', { name: 'Validation Replay' })).toHaveAttribute('id', 'strategy-lab-panel-validation');

    await waitFor(() => expect(screen.getByText('LHB Shortline')).toBeInTheDocument());
  });

  it('supports keyboard navigation between Strategy Lab tabs', async () => {
    render(<App />);
    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));

    fireEvent.click(navigation.getByRole('button', { name: 'Open Strategy Lab workspace' }));

    const runBacktestTab = await screen.findByRole('tab', { name: 'Run Backtest' });
    runBacktestTab.focus();
    expect(runBacktestTab).toHaveFocus();

    fireEvent.keyDown(runBacktestTab, { key: 'ArrowRight' });
    const validationTab = screen.getByRole('tab', { name: 'Validation Replay' });
    expect(validationTab).toHaveClass('active');
    expect(validationTab).toHaveFocus();
    expect(screen.getByRole('tabpanel', { name: 'Validation Replay' })).toHaveAttribute('id', 'strategy-lab-panel-validation');

    fireEvent.keyDown(validationTab, { key: 'ArrowLeft' });
    expect(runBacktestTab).toHaveClass('active');
    expect(runBacktestTab).toHaveFocus();
    expect(screen.getByRole('tabpanel', { name: 'Run Backtest' })).toHaveAttribute('id', 'strategy-lab-panel-backtest');

    fireEvent.keyDown(runBacktestTab, { key: 'End' });
    expect(validationTab).toHaveClass('active');
    expect(validationTab).toHaveFocus();

    fireEvent.keyDown(validationTab, { key: 'Home' });
    expect(runBacktestTab).toHaveClass('active');
    expect(runBacktestTab).toHaveFocus();
  });

  it('renders invalid shadow analytics review metrics as n/a instead of NaN%', async () => {
    render(
      <ShadowAnalyticsReviewPanel
        rows={[
      {
        ...makeShadowAnalyticsReview()[0],
        horizon_metrics: {
          '20': {
            forward_return_mean: Number.NaN,
            max_low_drawdown_worst: Number.POSITIVE_INFINITY
          }
        }
      }
        ]}
      />
    );

    expect(screen.getByText('Shadow Analytics Review')).toBeVisible();
    const panel = screen.getByText('Shadow Analytics Review').closest('section');
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getAllByText(/n\/a/)).toHaveLength(2);
    expect(within(panel as HTMLElement).queryByText(/NaN%/)).not.toBeInTheDocument();
  });

  it('renders repeated shadow analytics review groups with review-scoped keys', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const rows = [
      {
        ...makeShadowAnalyticsReview()[0],
        review_group_id: 'operator_shadow_analytics_review:run-a-trend-ready'
      },
      {
        ...makeShadowAnalyticsReview()[0],
        review_group_id: 'operator_shadow_analytics_review:run-b-trend-ready',
        run_id: 'p15-shadow-analytics-review-2026-09-30',
        review_start_date: '2026-07-31',
        review_end_date: '2026-09-30'
      }
    ] as ShadowAnalyticsReviewRow[];

    render(<ShadowAnalyticsReviewPanel rows={rows} />);

    expect(screen.getAllByText('trend_shadow')).toHaveLength(2);
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('renders repeated shadow review decision groups with decision-scoped keys', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const rows = [
      {
        ...makeShadowReviewDecisions()[0],
        decision_group_id: 'operator_shadow_review_decision:run-a-trend-ready'
      },
      {
        ...makeShadowReviewDecisions()[0],
        decision_group_id: 'operator_shadow_review_decision:run-b-trend-ready',
        run_id: 'p16-shadow-review-decisions-2026-09-30',
        decision_date: '2026-09-30'
      }
    ] as ShadowReviewDecisionRow[];

    render(<ShadowReviewDecisionsPanel rows={rows} />);

    expect(screen.getAllByText('trend_shadow')).toHaveLength(2);
    expect(screen.getAllByText('open_research_follow_up')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /promote|trade|write watchlist|scheduler/i })).not.toBeInTheDocument();
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('renders repeated shadow follow-up queue items with item-scoped keys', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const rows = [
      {
        ...makeShadowFollowUpQueue()[0],
        follow_up_item_id: 'operator_shadow_follow_up:run-a-trend-ready'
      },
      {
        ...makeShadowFollowUpQueue()[0],
        follow_up_item_id: 'operator_shadow_follow_up:run-b-trend-ready',
        run_id: 'p17-shadow-follow-up-queue-2026-09-30',
        follow_up_date: '2026-09-30'
      }
    ] as ShadowFollowUpRow[];

    render(<ShadowFollowUpQueuePanel rows={rows} />);

    expect(screen.getAllByText('trend_shadow')).toHaveLength(2);
    expect(screen.getAllByText('collect_more_evidence')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /promote|trade|write watchlist|scheduler/i })).not.toBeInTheDocument();
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('renders repeated shadow follow-up resolution items with item-scoped keys', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const rows = [
      {
        ...makeShadowFollowUpResolution()[0],
        resolution_item_id: 'operator_shadow_follow_up_resolution:run-a-trend-ready'
      },
      {
        ...makeShadowFollowUpResolution()[0],
        resolution_item_id: 'operator_shadow_follow_up_resolution:run-b-trend-ready',
        run_id: 'p18-shadow-follow-up-resolution-2026-09-30',
        resolution_date: '2026-09-30'
      }
    ] as ShadowFollowUpResolutionRow[];

    render(<ShadowFollowUpResolutionPanel rows={rows} />);

    expect(screen.getAllByText('trend_shadow')).toHaveLength(2);
    expect(screen.getAllByText('stale_unresolved')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /promote|trade|write watchlist|scheduler/i })).not.toBeInTheDocument();
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('renders invalid shadow outcome analytics metrics as n/a instead of NaN%', async () => {
    render(
      <ShadowOutcomeAnalyticsPanel
        rows={[
          {
            ...makeShadowOutcomeAnalytics()[0],
            horizon_metrics: {
              '20': {
                forward_return_mean: Number.NaN,
                forward_win_rate: null,
                max_low_drawdown_worst: Number.POSITIVE_INFINITY
              }
            }
          }
        ]}
      />
    );

    expect(screen.getByText('Shadow Outcome Analytics')).toBeVisible();
    const panel = screen.getByText('Shadow Outcome Analytics').closest('section');
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getAllByText(/n\/a/)).toHaveLength(3);
    expect(within(panel as HTMLElement).queryByText(/NaN%/)).not.toBeInTheDocument();
  });

  it('renders repeated shadow outcome analytics groups with run-scoped keys', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const rows = [
      {
        ...makeShadowOutcomeAnalytics()[0],
        analytics_group_id: 'operator_shadow_outcome_analytics:run-a-trend-ready'
      },
      {
        ...makeShadowOutcomeAnalytics()[0],
        analytics_group_id: 'operator_shadow_outcome_analytics:run-b-trend-ready',
        run_id: 'p14-shadow-outcome-analytics-2026-07-31-2026-09-30',
        review_start_date: '2026-07-31',
        review_end_date: '2026-09-30'
      }
    ] as ShadowOutcomeAnalyticsRow[];

    render(<ShadowOutcomeAnalyticsPanel rows={rows} />);

    expect(screen.getAllByText('trend_shadow')).toHaveLength(2);
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('renders invalid shadow outcome metrics as n/a instead of NaN%', async () => {
    render(<ShadowOutcomesPanel rows={makeShadowOutcomesWithInvalidMetrics()} />);

    expect(screen.getByText('Shadow Outcomes')).toBeVisible();
    const shadowOutcomesPanel = screen.getByText('Shadow Outcomes').closest('section');
    expect(shadowOutcomesPanel).not.toBeNull();
    expect(within(shadowOutcomesPanel as HTMLElement).getAllByText(/n\/a/)).toHaveLength(3);
    expect(within(shadowOutcomesPanel as HTMLElement).queryByText(/NaN%/)).not.toBeInTheDocument();
  });
});
