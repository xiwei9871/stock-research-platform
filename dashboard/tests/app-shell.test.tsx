import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { AppShell } from '../src/components/AppShell';
import { ShadowAnalyticsReviewPanel } from '../src/components/ShadowAnalyticsReviewPanel';
import { ShadowReviewDecisionsPanel } from '../src/components/ShadowReviewDecisionsPanel';
import { ShadowFollowUpQueuePanel } from '../src/components/ShadowFollowUpQueuePanel';
import { ShadowFollowUpResolutionPanel } from '../src/components/ShadowFollowUpResolutionPanel';
import { ShadowOutcomeAnalyticsPanel } from '../src/components/ShadowOutcomeAnalyticsPanel';
import { ShadowOutcomesPanel } from '../src/components/ShadowOutcomesPanel';
import type { StockEntryContext } from '../src/components/StockWorkspace';
import { stockPath } from '../src/navigation/platformRoutes';
import type {
  BarPoint,
  AssetProfile,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
  MarketAnomalyContextPayload,
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
  StockMarketContextHeatmapPayload,
  WatchlistSignalRow
} from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchCurrentUser: vi.fn(),
  fetchAdminUsers: vi.fn(),
  loginDashboardUser: vi.fn(),
  logoutDashboardUser: vi.fn(),
  fetchPlatformReadiness: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchStrategyScoreAudit: vi.fn(),
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
  fetchWatchlistSignals: vi.fn(),
  fetchFactorLibrary: vi.fn(),
  fetchFactorScorePreview: vi.fn(),
  fetchMarketMonitorEod: vi.fn(),
  fetchMarketAnomalyContext: vi.fn(),
  fetchMarketOverview: vi.fn(),
  fetchSectorHeatmap: vi.fn(),
  fetchSectorFundFlow: vi.fn(),
  fetchSectorDetail: vi.fn(),
  fetchResearchReportSummary: vi.fn(),
  fetchResearchReports: vi.fn(),
  fetchResearchReportDocument: vi.fn(),
  fetchAssetResearchReports: vi.fn(),
  fetchStockMarketContextHeatmap: vi.fn(),
  fetchResearchCases: vi.fn(),
  fetchResearchCaseDetail: vi.fn(),
  fetchResearchQueueHealth: vi.fn(),
  fetchResearchPublishGate: vi.fn(),
  fetchResearchPublicationPreview: vi.fn(),
  fetchResearchPublicationSnapshots: vi.fn(),
  fetchResearchExternalDeliveryPlan: vi.fn(),
  fetchResearchExternalDeliveryAttempts: vi.fn(),
  fetchResearchEvidence: vi.fn(),
  fetchEvidenceDigest: vi.fn(),
  fetchReviewQueue: vi.fn(),
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

function makeMarketOverviewResponse(overrides: Record<string, unknown> = {}) {
  return {
    trade_date: '2026-06-10',
    updated_at: '2026-06-10 15:10',
    source: 'api',
    data_status: 'completed',
    warnings: [],
    indices: [
      {
        code: '000001',
        name: '上证指数',
        close: 3168.44,
        change_pct: 0.0087
      }
    ],
    total_amount: 1526000000000,
    up_count: 3612,
    down_count: 1491,
    limit_up_count: 90,
    limit_down_count: 10,
    ...overrides
  };
}

function makeSectorHeatmapResponse(sectorType: 'industry' | 'concept', tradeDate = '2026-06-10') {
  return {
    trade_date: tradeDate,
    updated_at: `${tradeDate} 15:10`,
    source: 'api',
    data_status: 'completed',
    warnings: [],
    items: [
      {
        sector_id: sectorType === 'concept' ? 'concept-ai-compute' : 'industry-semiconductor',
        sector_name: sectorType === 'concept' ? 'AI算力' : '半导体',
        sector_type: sectorType,
        change_pct: sectorType === 'concept' ? 0.0432 : 0.0321,
        amount: sectorType === 'concept' ? 198400000000 : 145800000000,
        up_count: sectorType === 'concept' ? 128 : 112,
        down_count: sectorType === 'concept' ? 22 : 18,
        main_net_inflow: sectorType === 'concept' ? 32200000000 : 24800000000,
        stock_count: sectorType === 'concept' ? 150 : 130
      }
    ]
  };
}

function makeSectorFundFlowResponse(sectorType: 'industry' | 'concept', tradeDate = '2026-06-10') {
  const item = makeSectorHeatmapResponse(sectorType, tradeDate).items[0];
  return {
    trade_date: tradeDate,
    updated_at: `${tradeDate} 15:10`,
    source: 'api',
    data_status: 'completed',
    warnings: [],
    inflow: [
      {
        rank: 1,
        sector_id: item.sector_id,
        sector_name: item.sector_name,
        sector_type: item.sector_type,
        change_pct: item.change_pct,
        amount: item.amount,
        main_net_inflow: item.main_net_inflow,
        main_net_inflow_ratio: 0.153,
        leading_stock_name: sectorType === 'concept' ? '中际旭创' : '北方华创'
      }
    ],
    outflow: []
  };
}

function makeSectorDetailResponse(overrides: Record<string, unknown> = {}) {
  return {
    trade_date: '2026-06-10',
    updated_at: '2026-06-10 15:10',
    source: 'api',
    data_status: 'completed',
    warnings: [],
    sector_id: 'industry-semiconductor',
    sector_name: '半导体',
    sector_type: 'industry',
    change_pct: 0.0321,
    amount: 145800000000,
    up_count: 112,
    down_count: 18,
    main_net_inflow: 24800000000,
    main_net_inflow_ratio: 0.1701,
    leading_stocks: [
      {
        asset_id: 'CN:SZ:002371',
        name: '北方华创',
        change_pct: 0.0642
      }
    ],
    ...overrides
  };
}

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

function makeMarketAnomalyContextPayload(
  overrides: Partial<MarketAnomalyContextPayload> = {}
): MarketAnomalyContextPayload {
  return {
    trade_date: '2026-06-10',
    data_status: 'complete',
    summary: {
      hot_industry_count: 0,
      hot_stock_count: 0,
      volume_spike_count: 0,
      strong_move_count: 0
    },
    hot_industries: [],
    hot_stocks: [],
    warnings: [],
    ...overrides
  };
}

function makeStockMarketContextHeatmapPayload(
  overrides: Partial<StockMarketContextHeatmapPayload> = {}
): StockMarketContextHeatmapPayload {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: '000001.SZ',
    trade_date: '2026-06-18',
    industry: null,
    selected: null,
    summary: {
      peer_count: 0,
      up_count: 0,
      flat_count: 0,
      down_count: 0,
      total_amount: 0,
      selected_in_peer_set: false
    },
    peers: [],
    data_status: 'missing',
    warnings: [],
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

function makeReviewQueue() {
  return {
    trade_date: '2026-06-08',
    score_version: 'strategy_topn',
    review_mode: 'strategy_topn',
    generated_at: '2026-06-08T00:00:00+00:00',
    groups: [
      {
        bucket: 'strategy:mid_trend',
        label: 'Mid Trend Combo',
        count: 1,
        items: [
          {
            queue_id: '2026-06-08:strategy_topn:000001.SZ',
            asset_id: '000001.SZ',
            canonical_asset_id: '000001.SZ',
            trade_date: '2026-06-10',
            score_version: 'strategy_topn',
            display_name: '平安银行',
            rank: 1,
            score: 89.9,
            source_type: 'strategy_topn',
            source_name: 'Mid Trend Combo',
            source_rank: 1,
            strategy_id: 'mid_trend',
            strategy_name: 'Mid Trend Combo',
            strategy_run_id: 'mid_trend:run',
            review_tier: 'top5_focus',
            digest_title: 'Strong evidence',
            bucket: 'strong',
            source_kinds: ['strategy'],
            risk_count: 0,
            warning_count: 0,
            next_action_count: 1,
            digest: {
              asset_id: '000001.SZ',
              canonical_asset_id: '000001.SZ',
              trade_date: '2026-06-10',
              title: 'Strong evidence',
              score: 81,
              bucket: 'strong',
              facts: [{ kind: 'strategy', label: 'TopN candidate' }],
              risk_flags: [],
              source_refs: {},
              next_actions: [
                {
                  key: 'review_stock',
                  label: 'Review Stock',
                  workspace: 'stock',
                  asset_id: '000001.SZ',
                  query: '平安银行'
                }
              ],
              warnings: []
            }
          }
        ]
      },
      { bucket: 'strategy:tech_bottleneck', label: 'Tech Bottleneck Combo', count: 0, items: [] }
    ],
    warnings: []
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

const TEST_ADMIN_USER = { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin' as const, is_active: true };

describe('dashboard app shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.replaceState({}, '', '/');
    apiMocks.fetchCurrentUser.mockResolvedValue({
      user: { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin', is_active: true }
    });
    apiMocks.fetchAdminUsers.mockResolvedValue({ items: [] });
    apiMocks.fetchPlatformReadiness.mockResolvedValue({
      mode: 'eod_local',
      status: 'ready',
      as_of: '2026-06-15T08:30:00+08:00',
      latest_market_date: '2026-06-12',
      checks: [],
      warnings: []
    });
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
    apiMocks.fetchStrategyScoreAudit.mockResolvedValue({
      trade_date: '2026-06-08',
      status: 'success',
      overall_status: 'warning',
      summary_path: '/tmp/strategy_score_audit_summary.json',
      detail_path: '/tmp/strategy_score_audit_detail.csv',
      total_rows: 15,
      selected_rows: 15,
      anomaly_row_count: 2,
      anomaly_counts_by_type: {
        mapped_score_without_raw_score: 1,
        display_score_mismatch: 1
      },
      strategies: [
        { strategy_id: 'lhb_shortline', anomaly_count: 1 },
        { strategy_id: 'mid_trend', anomaly_count: 1 }
      ],
      sample_rows: []
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
    apiMocks.fetchWatchlistSignals.mockResolvedValue(makeOverview().watchlist_signals);
    apiMocks.fetchShadowOutcomes.mockResolvedValue(makeShadowOutcomes());
    apiMocks.fetchShadowOutcomeAnalytics.mockResolvedValue(makeShadowOutcomeAnalytics());
    apiMocks.fetchShadowAnalyticsReview.mockResolvedValue(makeShadowAnalyticsReview());
    apiMocks.fetchShadowReviewDecisions.mockResolvedValue(makeShadowReviewDecisions());
    apiMocks.fetchShadowFollowUpQueue.mockResolvedValue(makeShadowFollowUpQueue());
    apiMocks.fetchShadowFollowUpResolution.mockResolvedValue(makeShadowFollowUpResolution());
    apiMocks.fetchFactorLibrary.mockResolvedValue([]);
    apiMocks.fetchFactorScorePreview.mockResolvedValue({ trade_date: '2026-06-08', selected_factors: [], items: [] });
    apiMocks.fetchMarketMonitorEod.mockResolvedValue(makeMarketMonitorPayload());
    apiMocks.fetchMarketAnomalyContext.mockImplementation((tradeDate: string) =>
      Promise.resolve(makeMarketAnomalyContextPayload({ trade_date: tradeDate }))
    );
    apiMocks.fetchMarketOverview.mockImplementation((tradeDate: string) =>
      Promise.resolve(makeMarketOverviewResponse({ trade_date: tradeDate, updated_at: `${tradeDate} 15:10` }))
    );
    apiMocks.fetchSectorHeatmap.mockImplementation((tradeDate: string, sectorType: 'industry' | 'concept') =>
      Promise.resolve(makeSectorHeatmapResponse(sectorType, tradeDate))
    );
    apiMocks.fetchSectorFundFlow.mockImplementation((tradeDate: string, sectorType: 'industry' | 'concept') =>
      Promise.resolve(makeSectorFundFlowResponse(sectorType, tradeDate))
    );
    apiMocks.fetchSectorDetail.mockResolvedValue(makeSectorDetailResponse());
    apiMocks.fetchResearchReportSummary.mockResolvedValue({
      total_reports: 1,
      readable_report_count: 1,
      pdf_report_count: 1,
      web_index_report_count: 0,
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
    apiMocks.fetchResearchReportDocument.mockResolvedValue({
      report_id: 'report-1',
      report_title: 'Research Report',
      has_pdf: false,
      pdf_url: '',
      source_url: 'https://example.com/report',
      file_name: '',
      public_access: true,
      copyright_note: 'metadata only',
      warnings: ['local pdf is unavailable or outside allowed report directories']
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
    apiMocks.fetchStockMarketContextHeatmap.mockResolvedValue(makeStockMarketContextHeatmapPayload());
    apiMocks.fetchResearchCases.mockResolvedValue({ items: [] });
    apiMocks.fetchResearchEvidence.mockResolvedValue({ items: [] });
    apiMocks.fetchResearchQueueHealth.mockResolvedValue({
      trade_date: '2026-06-08',
      status: 'empty',
      can_review: false,
      can_publish_research_queue: false,
      publish_gate_status: 'empty',
      research_ready_for_publication: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      summary: {
        case_count: 0,
        open_case_count: 0,
        claim_count: 0,
        evidence_artifact_count: 0,
        evidence_link_count: 0,
        evidence_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      last_refresh: null,
      warnings: []
    });
    apiMocks.fetchResearchPublishGate.mockResolvedValue({
      trade_date: '2026-06-08',
      status: 'empty',
      research_ready_for_publication: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      publication_entrypoint_status: 'scaffolded',
      summary: {
        case_count: 0,
        open_case_count: 0,
        claim_count: 0,
        evidence_artifact_count: 0,
        evidence_link_count: 0,
        evidence_gap_count: 0,
        pending_gap_count: 0,
        reviewed_gap_count: 0,
        request_more_evidence_count: 0,
        deferred_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      blockers: [],
      warnings: [],
      top_blocked_cases: []
    });
    apiMocks.fetchResearchPublicationPreview.mockResolvedValue({
      trade_date: '2026-06-08',
      package_id: 'research_publication_package:empty',
      publishable: false,
      actual_publish_enabled: false,
      internal_snapshot_enabled: false,
      external_delivery_enabled: false,
      gate: {
        status: 'empty',
        research_ready_for_publication: false,
        actual_publish_enabled: false,
        internal_snapshot_enabled: false,
        external_delivery_enabled: false
      },
      summary: {
        case_count: 0,
        claim_count: 0,
        evidence_count: 0,
        evidence_link_count: 0,
        gap_count: 0,
        reviewed_gap_count: 0,
        pending_gap_count: 0,
        request_more_evidence_count: 0,
        deferred_gap_count: 0,
        unmatched_digest_count: 0,
        error_count: 0
      },
      sections: [],
      warnings: [],
      blockers: []
    });
    apiMocks.fetchResearchPublicationSnapshots.mockResolvedValue({ items: [] });
    apiMocks.fetchResearchExternalDeliveryAttempts.mockResolvedValue({ items: [] });
    apiMocks.fetchEvidenceDigest.mockResolvedValue({
      asset_id: 'CN:SZ:300951',
      canonical_asset_id: 'CN:SZ:300951',
      trade_date: '2026-06-08',
      title: 'Strong evidence',
      score: 81,
      bucket: 'strong',
      facts: [],
      risk_flags: [],
      source_refs: {},
      next_actions: [],
      warnings: []
    });
    apiMocks.fetchReviewQueue.mockResolvedValue(makeReviewQueue());
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the stock research cockpit shell title', async () => {
    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(await screen.findByText('A股策略研究')).toBeVisible();
    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeVisible();
    expect(screen.getByText('平台日期')).toBeVisible();
    expect(screen.getByText('启用策略表现')).toBeVisible();
    expect(screen.getByText('策略持仓状态')).toBeVisible();
    expect(screen.getByText('市场环境')).toBeVisible();
    expect(screen.getByText('高质量新闻')).toBeVisible();
    expect(screen.getAllByText('LHB Shortline Combo')[0]).toBeVisible();
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
  });

  it('shows the signed-in user and logout control in the top bar', () => {
    const onLogout = vi.fn();

    render(<AppShell currentUser={TEST_ADMIN_USER} onLogout={onLogout} />);

    const topbar = document.querySelector<HTMLElement>('.platform-topbar');
    expect(topbar).not.toBeNull();
    if (!topbar) throw new Error('platform top bar missing');
    expect(within(topbar).getByText('Admin')).toBeVisible();
    fireEvent.click(within(topbar).getByRole('button', { name: '退出登录' }));
    expect(onLogout).toHaveBeenCalledTimes(1);
  });

  it('falls back to the username and exposes pending logout errors', () => {
    const currentUser = { ...TEST_ADMIN_USER, username: 'admin-fallback', display_name: '' };

    render(
      <AppShell
        currentUser={currentUser}
        onLogout={vi.fn()}
        logoutPending
        logoutError="退出登录失败：network unavailable"
      />
    );

    const topbar = document.querySelector<HTMLElement>('.platform-topbar');
    expect(topbar).not.toBeNull();
    if (!topbar) throw new Error('platform top bar missing');
    expect(within(topbar).getByText('admin-fallback')).toBeVisible();
    expect(within(topbar).getByRole('button', { name: '退出登录' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('退出登录失败：network unavailable');
  });

  it('shows user management navigation only for admins', async () => {
    const admin = { user_id: 'user:1', username: 'admin', display_name: 'Admin', role: 'admin' as const, is_active: true };
    const regular = { user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user' as const, is_active: true };

    const { rerender } = render(<AppShell currentUser={regular} />);

    expect(screen.queryByRole('button', { name: 'Open User Management workspace' })).not.toBeInTheDocument();
    rerender(<AppShell currentUser={admin} />);
    expect(screen.getByRole('button', { name: 'Open User Management workspace' })).toBeVisible();
  });

  it('keeps the admin route behind the existing admin workspace gate', () => {
    const regular = { user_id: 'user:2', username: 'analyst', display_name: 'Analyst', role: 'user' as const, is_active: true };
    window.history.replaceState({}, '', '/admin/users');

    render(<AppShell currentUser={regular} />);

    expect(screen.getByRole('button', { name: 'Open Home workspace' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('button', { name: 'Open User Management workspace' })).not.toBeInTheDocument();
  });

  it('initializes the home search only from a string history-state query', () => {
    window.history.replaceState({ searchQuery: '600519' }, '', '/');
    const firstRender = render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(screen.getByLabelText('Global search')).toHaveValue('600519');

    firstRender.unmount();
    window.history.replaceState({ searchQuery: { unsafe: true } }, '', '/');
    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(screen.getByLabelText('Global search')).toHaveValue('');
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

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeInTheDocument();
    const homeStatus = within(screen.getByRole('region', { name: '首页状态' }));
    const scoreAuditCell = homeStatus.getByText('策略打分审计').closest('div');
    expect(scoreAuditCell).not.toBeNull();
    await waitFor(() => expect(within(scoreAuditCell as HTMLDivElement).getByText('需关注')).toBeInTheDocument());
    expect(within(scoreAuditCell as HTMLDivElement).getByText('2 条异常')).toBeInTheDocument();
    expect(screen.getByText('启用策略表现')).toBeInTheDocument();
    expect(screen.getByText('策略持仓状态')).toBeInTheDocument();
    expect(screen.getByText('市场环境')).toBeInTheDocument();
    expect(screen.getByText('高质量新闻')).toBeInTheDocument();
    expect(screen.getByText('首页新闻')).toBeInTheDocument();
    expect(apiMocks.fetchStrategyScoreAudit).toHaveBeenCalledWith('2026-06-12');
  });

  it('exposes the redesigned research cockpit navigation', async () => {
    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(screen.getByRole('button', { name: 'Open Market Monitor workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Research Reports workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Stock Workspace workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Watchlist workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Strategy Lab workspace' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Generated Reports workspace' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open Reports workspace' })).not.toBeInTheDocument();
  });

  it('opens redesigned workspaces from navigation', async () => {
    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    fireEvent.click(screen.getByRole('button', { name: 'Open Research Reports workspace' }));
    expect(window.location.pathname).toBe('/research-reports');
    expect(await screen.findByRole('heading', { name: '研报' })).toBeInTheDocument();
    expect(screen.getByText('可读研报')).toBeInTheDocument();
    expect(await screen.findByText('Ping An Bank Initiation')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
    expect(window.location.pathname).toBe('/stock/000001.SZ');
    expect(await screen.findByRole('heading', { name: /贵州茅台|个股复盘工作台/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open Watchlist workspace' }));
    expect(window.location.pathname).toBe('/watchlist');
    expect(await screen.findByRole('heading', { name: '观察池' })).toBeInTheDocument();
  });

  it('does not add a duplicate history entry when the active workspace is clicked', async () => {
    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));
    expect(window.location.pathname).toBe('/news');
    expect(screen.getByRole('button', { name: 'Open News workspace' })).toHaveAttribute('aria-current', 'page');

    fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));
    act(() => window.history.back());

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Open Home workspace' })).toHaveAttribute('aria-current', 'page')
    );
  });

  it('preserves theme research source context on direct canonical stock routes', async () => {
    window.history.replaceState({}, '', '/stock/002837.SZ?source=theme_research');
    apiMocks.fetchAssetProfile.mockResolvedValue(makeAssetProfile('002837.SZ'));

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(
      await screen.findByText((_content, element) => element?.textContent === '来源工作台：Theme Research')
    ).toBeInTheDocument();
  });

  it('preserves theme research source context on direct legacy stock routes', async () => {
    window.history.replaceState({}, '', '/tech-bottleneck/stock/002837.SZ?source=theme_research');
    apiMocks.fetchAssetProfile.mockResolvedValue(makeAssetProfile('002837.SZ'));

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(
      await screen.findByText((_content, element) => element?.textContent === '来源工作台：Theme Research')
    ).toBeInTheDocument();
    expect(screen.queryByText(/科技卡脖子来源\s+theme_research/)).not.toBeInTheDocument();
  });

  it('restores primary routes and reparses the complete stock location on popstate', async () => {
    window.history.replaceState({}, '', '/review-queue');
    apiMocks.fetchAssetProfile.mockResolvedValue(makeAssetProfile('600519.SH'));

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    expect(screen.getByRole('button', { name: 'Open Review Queue workspace' })).toHaveAttribute('aria-current', 'page');

    act(() => {
      window.history.pushState({}, '', '/daily-review');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Open Daily Review workspace' })).toHaveAttribute('aria-current', 'page')
    );

    act(() => {
      window.history.pushState({}, '', '/stock/600519.SH?source=search&q=%E8%B4%B5%E5%B7%9E%E8%8C%85%E5%8F%B0');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Open Stock Workspace workspace' })).toHaveAttribute('aria-current', 'page')
    );
    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
        '600519.SH',
        expect.anything(),
        expect.anything(),
        expect.anything(),
        'manual_v1',
        'qfq'
      )
    );
    expect(screen.getByText((_content, element) => element?.textContent === '来源工作台：Search')).toBeInTheDocument();

    act(() => {
      window.history.pushState({}, '', '/stock/002837.SZ?source=theme_research');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await waitFor(() =>
      expect(
        screen.getByText((_content, element) => element?.textContent === '来源工作台：Theme Research')
      ).toBeInTheDocument()
    );
  });

  it('replaces the legacy review route with its canonical path once', () => {
    window.history.pushState({}, '', '/tech-bottleneck/watchlist-review');
    const replaceState = vi.spyOn(window.history, 'replaceState');

    try {
      render(<AppShell currentUser={TEST_ADMIN_USER} />);

      expect(replaceState).toHaveBeenCalledTimes(1);
      expect(replaceState).toHaveBeenCalledWith({}, '', '/research/tech-bottleneck/review-universe');
    } finally {
      replaceState.mockRestore();
    }
  });

  it('switches stock workspace chart to intraday bars', async () => {
    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
    expect(await screen.findByRole('heading', { name: /贵州茅台|Stock Workspace/ })).toBeInTheDocument();
    expect(await screen.findByTestId('asset-chart')).toHaveTextContent('1 bars');

    apiMocks.fetchDailyBars.mockClear();
    apiMocks.fetchDailyBars.mockImplementation(
      (
        _assetId: string,
        _startDate: string,
        _endDate: string,
        options?: { resolution?: string; adjustType?: string }
      ) => Promise.resolve(options?.resolution === '30m' ? makeBars(3) : makeBars(1))
    );
    fireEvent.click(screen.getByRole('button', { name: '分时' }));
    fireEvent.click(screen.getByRole('button', { name: '30m' }));

    await waitFor(() =>
      expect(apiMocks.fetchDailyBars).toHaveBeenCalledWith('000001.SZ', '2025-12-14', '2026-06-12', {
        resolution: '30m',
        adjustType: 'raw'
      })
    );
    await waitFor(() => expect(screen.getByTestId('asset-chart')).toHaveTextContent('3 bars'));
    expect(screen.getByRole('button', { name: '30m' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens Review Queue from navigation and follows review stock action', async () => {
    apiMocks.fetchAssetProfile.mockResolvedValueOnce({
      ...makeAssetProfile('000001.SZ'),
      asset: {
        asset_id: '000001.SZ',
        symbol: '000001',
        name: '平安银行',
        exchange: 'SZ',
        board: 'main',
        is_active: true
      }
    });

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open Review Queue workspace' }));
    expect(await screen.findByRole('heading', { name: '策略复盘队列' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Review Stock' }));

    expect(await screen.findByRole('heading', { name: /平安银行/ })).toBeInTheDocument();
    expect(screen.getByText((_content, element) => element?.textContent === '来源工作台：Review Queue')).toBeInTheDocument();
    await waitFor(() =>
      expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
        '000001.SZ',
        '2026-06-10',
        '2025-12-12',
        '2026-06-10',
        'manual_v1',
        'qfq'
      )
    );
    await waitFor(() =>
      expect(apiMocks.fetchEvidenceDigest).toHaveBeenCalledWith('000001.SZ', {
        tradeDate: '2026-06-10',
        lookbackDays: 90
      })
    );
  });

  it('opens the Stock workspace from a global search stock result', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
        makeGlobalSearchPayload(makeGlobalSearchResult(), '600519')
      );
      apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeAssetProfile('CN:SH:600519'));

      render(<AppShell currentUser={TEST_ADMIN_USER} />);

      fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(250);
      });
      fireEvent.click(await screen.findByRole('option', { name: /贵州茅台 600519.SH/ }));

      expect(`${window.location.pathname}${window.location.search}`).toBe(
        stockPath('CN:SH:600519', {
          sourceWorkspace: 'search',
          query: '600519',
          matchReason: 'Exact code match'
        })
      );
      expect(await screen.findByRole('heading', { name: /贵州茅台 CN:SH:600519/ })).toBeInTheDocument();
      expect(apiMocks.fetchAssetProfile).toHaveBeenCalledWith(
        'CN:SH:600519',
        '2026-06-12',
        '2025-12-14',
        '2026-06-12',
        'manual_v1',
        'qfq'
      );
    } finally {
      vi.useRealTimers();
    }
  });

  it('restores the home search query and refetches results after actual browser Back', async () => {
    window.history.replaceState({ existing: 'keep' }, '', '/');
    apiMocks.fetchGlobalSearch.mockResolvedValue(makeGlobalSearchPayload(makeGlobalSearchResult(), '600519'));
    apiMocks.fetchAssetProfile.mockResolvedValueOnce(makeAssetProfile('CN:SH:600519'));

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
    fireEvent.click(await screen.findByRole('option', { name: /贵州茅台 600519.SH/ }));
    expect(window.location.pathname).toBe('/stock/CN%3ASH%3A600519');
    expect(screen.getByLabelText('Global search')).toHaveValue('');

    act(() => window.history.back());

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(window.history.state).toEqual({ existing: 'keep', searchQuery: '600519' });
    expect(screen.getByLabelText('Global search')).toHaveValue('600519');
    expect(await screen.findByRole('option', { name: /贵州茅台 600519.SH/ })).toBeInTheDocument();
    expect(apiMocks.fetchGlobalSearch).toHaveBeenCalledTimes(2);

    act(() => window.history.forward());

    await waitFor(() => expect(window.location.pathname).toBe('/stock/CN%3ASH%3A600519'));
    expect(screen.getByLabelText('Global search')).toHaveValue('');
  });

  it('restores home search state after opening a non-stock global result', async () => {
    window.history.replaceState({ existing: 'keep' }, '', '/');
    const newsResult = makeGlobalSearchResult({
      type: 'news',
      id: 'news-1',
      title: '贵州茅台新闻',
      subtitle: '7x24',
      target: { workspace: 'news', q: '茅台', news_id: 'news-1' }
    });
    apiMocks.fetchGlobalSearch.mockResolvedValue(makeGlobalSearchPayload(newsResult, '茅台'));

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '茅台' } });
    fireEvent.click(await screen.findByRole('option', { name: /贵州茅台新闻 7x24/ }));
    expect(window.location.pathname).toBe('/news');
    expect(screen.getByLabelText('Global search')).toHaveValue('');

    act(() => window.history.back());

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(window.history.state).toEqual({ existing: 'keep', searchQuery: '茅台' });
    expect(screen.getByLabelText('Global search')).toHaveValue('茅台');
    expect(await screen.findByRole('option', { name: /贵州茅台新闻 7x24/ })).toBeInTheDocument();
    expect(apiMocks.fetchGlobalSearch).toHaveBeenCalledTimes(2);
  });

  it('snapshots and clears home search state when sidebar navigation leaves home', async () => {
    window.history.replaceState({ existing: 'keep' }, '', '/');
    apiMocks.fetchGlobalSearch.mockResolvedValue(makeGlobalSearchPayload(makeGlobalSearchResult(), '600519'));

    render(<AppShell currentUser={TEST_ADMIN_USER} />);

    fireEvent.change(screen.getByLabelText('Global search'), { target: { value: '600519' } });
    expect(await screen.findByRole('option', { name: /贵州茅台 600519.SH/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open Daily Review workspace' }));
    expect(window.location.pathname).toBe('/daily-review');
    expect(screen.getByLabelText('Global search')).toHaveValue('');

    act(() => window.history.back());

    await waitFor(() => expect(window.location.pathname).toBe('/'));
    expect(window.history.state).toEqual({ existing: 'keep', searchQuery: '600519' });
    expect(screen.getByLabelText('Global search')).toHaveValue('600519');
    expect(await screen.findByRole('option', { name: /贵州茅台 600519.SH/ })).toBeInTheDocument();
    expect(apiMocks.fetchGlobalSearch).toHaveBeenCalledTimes(2);
  });

  type MockWorkspaceRender = {
    initialAssetId?: string;
    defaultTradeDate?: string;
    entryContext?: {
      assetId?: string;
      sourceWorkspace?: string;
      query?: string;
      matchReason?: string;
      newsId?: string;
      eventKey?: string;
      reportId?: string;
      tradeDate?: string;
      monitorTab?: string;
    };
    initialQuery?: string;
    initialTradeDate?: string;
    initialMonitorTab?: string;
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
    const stockResult = makeGlobalSearchResult({
      type: 'asset',
      id: 'CN:SH:600519',
      title: '贵州茅台',
      subtitle: '600519.SH',
      target: {
        workspace: 'stock',
        q: '600519',
        asset_id: 'CN:SH:600519'
      } as GlobalSearchResult['target'],
      match_reason: 'Exact code match'
    });

    const newsRenders: MockWorkspaceRender[] = [];
    const researchRenders: MockWorkspaceRender[] = [];
    const generatedRenders: MockWorkspaceRender[] = [];
    const marketRenders: MockWorkspaceRender[] = [];
    const stockRenders: MockWorkspaceRender[] = [];
    let newsMountId = 0;
    let stockMountId = 0;

    vi.doMock('../src/components/GlobalSearchBox', () => ({
      GlobalSearchBox: ({ onOpenResult }: { onOpenResult: (result: GlobalSearchResult) => void }) => (
        <div>
          <button type="button" onClick={() => onOpenResult(stockResult)}>
            Mock open stock search
          </button>
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
    vi.doMock('../src/components/DailyReviewLiteWorkspace', () => ({
      DailyReviewLiteWorkspace: ({ initialTradeDate }: { initialTradeDate?: string }) => (
        <div data-testid="mock-daily-review-workspace">daily review:{initialTradeDate ?? 'none'}</div>
      )
    }));
    vi.doMock('../src/components/MarketMonitorWorkspace', () => ({
      MarketMonitorWorkspace: ({
        initialTradeDate,
        initialMonitorTab,
        initialAssetId,
        onOpenAsset
      }: {
        initialTradeDate?: string;
        initialMonitorTab?: string;
        initialAssetId?: string;
        onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
      }) => {
        marketRenders.push({ initialTradeDate, initialMonitorTab, initialAssetId });
        return (
          <div data-testid="mock-market-workspace">
            market workspace:{initialTradeDate ?? 'none'}:{initialMonitorTab ?? 'none'}:{initialAssetId ?? 'none'}
            <button
              type="button"
              onClick={() =>
                onOpenAsset?.('CN:SH:600519', {
                  sourceWorkspace: 'market',
                  assetId: 'CN:SH:600519',
                  tradeDate: '2026-06-12',
                  monitorTab: 'stock_heatmap',
                  query: '贵州茅台',
                  matchReason: 'stock_heatmap'
                })
              }
            >
              Mock market open asset
            </button>
          </div>
        );
      }
    }));
    vi.doMock('../src/components/StockWorkspace', async () => {
      const React = await import('react');
      return {
        StockWorkspace: ({
          initialAssetId,
          defaultTradeDate,
          entryContext,
          onOpenNews,
          onOpenResearchReports,
          onOpenMarketMonitor
        }: {
          initialAssetId?: string;
          defaultTradeDate?: string;
          entryContext?: {
            assetId?: string;
            sourceWorkspace?: string;
            query?: string;
            matchReason?: string;
            newsId?: string;
            eventKey?: string;
            reportId?: string;
            tradeDate?: string;
            monitorTab?: string;
          };
          onOpenNews?: (context: NonNullable<MockWorkspaceRender['entryContext']>) => void;
          onOpenResearchReports?: (context: NonNullable<MockWorkspaceRender['entryContext']>) => void;
          onOpenMarketMonitor?: (context: NonNullable<MockWorkspaceRender['entryContext']>) => void;
        }) => {
          const [mountId] = React.useState(() => {
            stockMountId += 1;
            return stockMountId;
          });
          stockRenders.push({ initialAssetId, defaultTradeDate, entryContext, mountId });
          return (
            <div data-testid="mock-stock-workspace">
              {initialAssetId}:{entryContext?.sourceWorkspace ?? 'none'}:{entryContext?.query ?? 'none'}:
              {entryContext?.matchReason ?? 'none'}:{entryContext?.newsId ?? 'none'}:{mountId}
              <button
                type="button"
                onClick={() => onOpenNews?.({ ...entryContext, query: '600519', newsId: 'stock-news-1' })}
              >
                Mock stock open news
              </button>
              <button
                type="button"
                onClick={() =>
                  onOpenResearchReports?.({
                    ...entryContext,
                    query: '600519',
                    eventKey: 'stock-event-1',
                    reportId: 'stock-report-1'
                  })
                }
              >
                Mock stock open research
              </button>
              <button
                type="button"
                onClick={() =>
                  onOpenMarketMonitor?.({
                    ...entryContext,
                    assetId: initialAssetId,
                    query: '600519',
                    tradeDate: '2026-06-12',
                    monitorTab: 'broken_limit_up'
                  })
                }
              >
                Mock stock open market
              </button>
              <button type="button" onClick={() => onOpenNews?.({ ...entryContext })}>
                Mock stock return current news
              </button>
              <button type="button" onClick={() => onOpenResearchReports?.({ ...entryContext })}>
                Mock stock return current research
              </button>
              <button type="button" onClick={() => onOpenMarketMonitor?.({ ...entryContext })}>
                Mock stock return current market
              </button>
            </div>
          );
        }
      };
    });
    vi.doMock('../src/components/StrategyLabWorkspace', () => ({ StrategyLabWorkspace: () => <div>strategy workspace</div> }));
    vi.doMock('../src/components/WatchlistWorkspace', () => ({
      WatchlistWorkspace: ({ onOpenAsset }: { onOpenAsset?: (assetId: string) => void }) => (
        <button type="button" onClick={() => onOpenAsset?.('000002.SZ')}>
          Mock open watchlist asset
        </button>
      )
    }));
    vi.doMock('../src/components/NewsWorkspace', async () => {
      const React = await import('react');
      return {
        NewsWorkspace: ({
          initialQuery,
          initialNewsId,
          initialTradeDate,
          onOpenAsset
        }: {
          initialQuery?: string;
          initialNewsId?: string;
          initialTradeDate?: string;
          onOpenAsset?: (
            assetId: string,
            context: { sourceWorkspace: 'news'; assetId: string; newsId: string; query: string; tradeDate?: string }
          ) => void;
        }) => {
          const [mountId] = React.useState(() => {
            newsMountId += 1;
            return newsMountId;
          });
          newsRenders.push({ initialQuery, initialNewsId, initialTradeDate, mountId });
          return (
            <div data-testid="mock-news-workspace">
              {initialQuery}:{initialNewsId ?? 'none'}:{mountId}
              <button
                type="button"
                onClick={() =>
                  onOpenAsset?.('CN:SH:600519', {
                    sourceWorkspace: 'news',
                    assetId: 'CN:SH:600519',
                    newsId: 'news-row-1',
                    query: '贵州茅台经营快讯',
                    tradeDate: initialTradeDate ?? '2026-06-10'
                  })
                }
              >
                Mock open news asset
              </button>
            </div>
          );
        }
      };
    });
    vi.doMock('../src/components/ResearchReportsWorkspace', () => ({
      ResearchReportsWorkspace: ({
        initialQuery,
        initialEventKey,
        initialReportId,
        initialTradeDate,
        onOpenAsset
      }: {
        initialQuery?: string;
        initialEventKey?: string;
        initialReportId?: string;
        initialTradeDate?: string;
        onOpenAsset?: (assetId: string, context: StockEntryContext) => void;
      }) => {
        researchRenders.push({ initialQuery, initialEventKey, initialReportId, initialTradeDate });
        return (
          <div data-testid="mock-research-workspace">
            {initialQuery}:{initialEventKey ?? 'none'}:{initialReportId ?? 'none'}
            <button
              type="button"
              onClick={() =>
                onOpenAsset?.('CN:SH:600519', {
                  sourceWorkspace: 'researchReports',
                  assetId: 'CN:SH:600519',
                  eventKey: 'r1:600519.SH',
                  reportId: 'r1',
                  query: '贵州茅台深度报告',
                  tradeDate: initialTradeDate ?? '2026-06-11'
                })
              }
            >
              mocked report stock
            </button>
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

    return { generatedRenders, marketRenders, newsRenders, researchRenders, stockRenders };
  }

  it('preserves stock handoff context from global search and remounts on the same stock', async () => {
    const { stockRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open stock search' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:search:600519:Exact code match:none:1'
    );
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      entryContext: {
        sourceWorkspace: 'search',
        query: '600519',
        matchReason: 'Exact code match'
      },
      mountId: 1
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mock open stock search' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:search:600519:Exact code match:none:2'
    );
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      entryContext: {
        sourceWorkspace: 'search',
        query: '600519',
        matchReason: 'Exact code match'
      },
      mountId: 2
    });
  });

  it('reconstructs canonical stock route context on direct refresh', async () => {
    window.history.replaceState(
      {},
      '',
      stockPath('CN:SH:600519', {
        sourceWorkspace: 'search',
        query: '600519',
        matchReason: 'Exact code match'
      })
    );

    const { stockRenders } = await renderMockedAppShellForHandoff();

    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      entryContext: {
        assetId: 'CN:SH:600519',
        sourceWorkspace: 'search',
        query: '600519',
        matchReason: 'Exact code match'
      }
    });
  });

  it('uses the latest market date rather than the gated display date for stock workspace defaults', async () => {
    apiMocks.fetchPlatformReadiness.mockResolvedValueOnce({
      mode: 'eod_local',
      status: 'BLOCKED',
      as_of: '2026-07-02T16:00:00+08:00',
      display_trade_date: '2026-06-30',
      latest_trade_date: '2026-07-02',
      latest_market_date: '2026-07-02',
      display_gate: {
        display_trade_date: '2026-06-30',
        latest_market_date: '2026-07-02',
        candidate_trade_date: '2026-07-02',
        candidate_status: 'before_cutoff',
        display_status: 'ready'
      },
      checks: [],
      warnings: []
    });
    apiMocks.fetchPlatformSummary.mockResolvedValueOnce({
      latest_market_date: '2026-07-02',
      latest_score_date: '2026-07-01',
      latest_factor_date: '2026-07-01',
      market_asset_count: 5207,
      score_asset_count: 5207,
      factor_count: 43,
      score_versions: ['manual_v1'],
      topn_preview: []
    });

    const { stockRenders } = await renderMockedAppShellForHandoff();

    await waitFor(() => expect(apiMocks.fetchPlatformReadiness).toHaveBeenCalled());
    fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));

    await waitFor(() => expect(stockRenders.at(-1)?.defaultTradeDate).toBe('2026-07-02'));
  });

  it('resets stale stock source context when opening stock from plain navigation', async () => {
    const { stockRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open news' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock open news asset' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:news:贵州茅台经营快讯:none:news-row-1:1'
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open News workspace' }));
    expect(await screen.findByTestId('mock-news-workspace')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:none:none:none:none:2'
    );
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      mountId: 2
    });
    expect(stockRenders.at(-1)?.entryContext?.sourceWorkspace).toBeUndefined();
    expect(stockRenders.at(-1)?.entryContext?.newsId).toBeUndefined();
  });

  it('opens stock handoffs from news and watchlist with source context', async () => {
    const { stockRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open news' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock open news asset' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:news:贵州茅台经营快讯:none:news-row-1:1'
    );
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      entryContext: {
        sourceWorkspace: 'news',
        query: '贵州茅台经营快讯',
        newsId: 'news-row-1',
        tradeDate: '2026-06-10'
      },
      mountId: 1
    });

    fireEvent.click(screen.getByRole('button', { name: 'Open Watchlist workspace' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock open watchlist asset' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent('000002.SZ:watchlist:none:none:none:2');
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: '000002.SZ',
      entryContext: {
        sourceWorkspace: 'watchlist'
      },
      mountId: 2
    });
  });

  it('shows daily review as an independent workspace after review queue', async () => {
    await renderMockedAppShellForHandoff();

    const reviewQueue = screen.getByRole('button', { name: 'Open Review Queue workspace' });
    const dailyReview = screen.getByRole('button', { name: 'Open Daily Review workspace' });
    const marketMonitor = screen.getByRole('button', { name: 'Open Market Monitor workspace' });

    expect(reviewQueue.compareDocumentPosition(dailyReview) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(dailyReview.compareDocumentPosition(marketMonitor) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    fireEvent.click(dailyReview);

    expect(await screen.findByTestId('mock-daily-review-workspace')).toHaveTextContent('daily review:2026-06-12');
  });

  it('uses news row context when news opens a stock asset', async () => {
    const { stockRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open news' }));
    expect(await screen.findByTestId('mock-news-workspace')).toHaveTextContent('茅台:news-1:1');

    fireEvent.click(screen.getByRole('button', { name: 'Mock open news asset' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:news:贵州茅台经营快讯:none:news-row-1:1'
    );
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      entryContext: {
        sourceWorkspace: 'news',
        query: '贵州茅台经营快讯',
        newsId: 'news-row-1',
        tradeDate: '2026-06-10'
      },
      mountId: 1
    });
  });

  it('opens destination workspaces from stock detail context actions', async () => {
    const { marketRenders, newsRenders, researchRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open stock search' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:search:600519:Exact code match:none:1'
    );

    fireEvent.click(screen.getByRole('button', { name: 'Mock stock open news' }));
    expect(await screen.findByTestId('mock-news-workspace')).toHaveTextContent('600519:stock-news-1:1');
    expect(newsRenders.at(-1)).toMatchObject({
      initialQuery: '600519',
      initialNewsId: 'stock-news-1',
      mountId: 1
    });

    fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock stock open research' }));
    expect(await screen.findByTestId('mock-research-workspace')).toHaveTextContent(
      '600519:stock-event-1:stock-report-1'
    );
    expect(researchRenders.at(-1)).toMatchObject({
      initialQuery: '600519',
      initialEventKey: 'stock-event-1',
      initialReportId: 'stock-report-1'
    });

    fireEvent.click(screen.getByRole('button', { name: 'Open Stock Workspace workspace' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock stock open market' }));
    expect(await screen.findByTestId('mock-market-workspace')).toHaveTextContent(
      'market workspace:2026-06-12:industry:CN:SH:600519'
    );
    expect(marketRenders.at(-1)).toMatchObject({
      initialTradeDate: '2026-06-12',
      initialMonitorTab: 'industry',
      initialAssetId: 'CN:SH:600519'
    });
  });

  it('returns from stock detail actions with the current source context', async () => {
    const { marketRenders, newsRenders, researchRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open news' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock open news asset' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:news:贵州茅台经营快讯:none:news-row-1:1'
    );

    fireEvent.click(screen.getByRole('button', { name: 'Mock stock return current news' }));
    expect(await screen.findByTestId('mock-news-workspace')).toHaveTextContent('贵州茅台经营快讯:news-row-1:2');
    expect(newsRenders.at(-1)).toMatchObject({
      initialQuery: '贵州茅台经营快讯',
      initialNewsId: 'news-row-1',
      initialTradeDate: '2026-06-10'
    });

    fireEvent.click(screen.getByRole('button', { name: 'Mock open research' }));
    fireEvent.click(await screen.findByRole('button', { name: 'mocked report stock' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:researchReports:贵州茅台深度报告:none:none:2'
    );

    fireEvent.click(screen.getByRole('button', { name: 'Mock stock return current research' }));
    expect(await screen.findByTestId('mock-research-workspace')).toHaveTextContent(
      '贵州茅台深度报告:r1:600519.SH:r1'
    );
    expect(researchRenders.at(-1)).toMatchObject({
      initialQuery: '贵州茅台深度报告',
      initialEventKey: 'r1:600519.SH',
      initialReportId: 'r1',
      initialTradeDate: '2026-06-11'
    });

    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock market open asset' }));
    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:market:贵州茅台:stock_heatmap:none:3'
    );

    fireEvent.click(screen.getByRole('button', { name: 'Mock stock return current market' }));
    expect(await screen.findByTestId('mock-market-workspace')).toHaveTextContent(
      'market workspace:2026-06-12:industry:CN:SH:600519'
    );
    expect(marketRenders.at(-1)).toMatchObject({
      initialTradeDate: '2026-06-12',
      initialMonitorTab: 'industry',
      initialAssetId: 'CN:SH:600519'
    });
  });

  it('opens stock handoff from market monitor with market context', async () => {
    const { stockRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Mock market open asset' }));

    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:market:贵州茅台:stock_heatmap:none:1'
    );
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      entryContext: {
        sourceWorkspace: 'market',
        query: '贵州茅台',
        tradeDate: '2026-06-12',
        monitorTab: 'stock_heatmap',
        matchReason: 'stock_heatmap'
      },
      mountId: 1
    });
  });

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

  it('opens stock handoff from research reports with report context', async () => {
    const { stockRenders } = await renderMockedAppShellForHandoff();

    fireEvent.click(screen.getByRole('button', { name: 'Mock open research' }));
    fireEvent.click(await screen.findByRole('button', { name: 'mocked report stock' }));

    expect(await screen.findByTestId('mock-stock-workspace')).toHaveTextContent(
      'CN:SH:600519:researchReports:贵州茅台深度报告:none:none:1'
    );
    expect(stockRenders.at(-1)).toMatchObject({
      initialAssetId: 'CN:SH:600519',
      entryContext: {
        sourceWorkspace: 'researchReports',
        query: '贵州茅台深度报告',
        eventKey: 'r1:600519.SH',
        reportId: 'r1',
        tradeDate: '2026-06-11'
      },
      mountId: 1
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

      render(<AppShell currentUser={TEST_ADMIN_USER} />);

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

      render(<AppShell currentUser={TEST_ADMIN_USER} />);

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

      render(<AppShell currentUser={TEST_ADMIN_USER} />);

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

  it('explains why Generated Reports can be empty', async () => {
    apiMocks.fetchOverview.mockResolvedValue({ ...makeOverview(), reports: [] });

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));

    fireEvent.click(navigation.getByRole('button', { name: 'Open Generated Reports workspace' }));

    expect(await screen.findByRole('heading', { name: 'Generated Reports', level: 1 })).toBeVisible();
    expect(await screen.findByText('当前日期没有生成报告。')).toBeVisible();
    expect(screen.getByText('可能是报告生成任务尚未运行，或报告目录没有命中该日期。')).toBeVisible();
  });

  it('renders EOD market monitor data without implying realtime data', async () => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(makeMarketMonitorPayload());

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    expect(screen.getByText('Last Completed Trading Day')).toBeInTheDocument();
    expect(screen.queryByText('Realtime')).not.toBeInTheDocument();
    expect(screen.getByText('Data Mode')).toBeInTheDocument();
    expect(screen.getByText('EOD Snapshot')).toBeInTheDocument();
    expect(screen.getAllByText('2026-06-10').length).toBeGreaterThan(0);
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
    screen.getAllByRole('tab').forEach((tab) => {
      const panelId = tab.getAttribute('aria-controls');
      expect(panelId).toBeTruthy();
      expect(document.getElementById(panelId as string)).toBeInTheDocument();
    });
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

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
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

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    const tradeDateInput = screen.getByLabelText('Market monitor trade date');
    await waitFor(() => expect(tradeDateInput).toHaveValue('2026-06-10'));

    fireEvent.change(tradeDateInput, { target: { value: '2026-06-04' } });
    fireEvent.click(screen.getByRole('button', { name: 'Load Date' }));

    expect(await screen.findByText('Loading 2026-06-04...')).toBeInTheDocument();
    expect(screen.getAllByText('2026-06-10').length).toBeGreaterThan(0);

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

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
    fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));

    expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();
    expect(screen.getByText('Last Completed Trading Day')).toBeInTheDocument();
    expect(await screen.findByText('2026-06-10')).toBeInTheDocument();
    expect(screen.getByText('权重表现待接入')).toBeInTheDocument();
    expect(screen.getByText('情绪拆解待接入')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: '涨停 0' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByText('股票名单源未接入。')).toBeInTheDocument();
  });

  it('supports keyboard navigation across market monitor stock tabs', async () => {
    apiMocks.fetchMarketMonitorEod.mockResolvedValueOnce(makeMarketMonitorPayload());

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
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
      render(<AppShell currentUser={TEST_ADMIN_USER} />);
      fireEvent.click(screen.getByRole('button', { name: 'Open Market Monitor workspace' }));
      expect(await screen.findByRole('heading', { name: 'Market Monitor' })).toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: 'Open Home workspace' }));
      expect(await screen.findByRole('heading', { name: '策略指挥中心' })).toBeInTheDocument();

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

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
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
    expect(screen.getAllByText('2026-06-11').length).toBeGreaterThan(0);

    await act(async () => {
      resolveFirstRequest(makeMarketMonitorPayload());
      await firstRequest;
    });

    expect(screen.getByText('000002.SZ')).toBeInTheDocument();
    expect(screen.getAllByText('2026-06-11').length).toBeGreaterThan(0);
    expect(screen.queryByText('000001.SZ')).not.toBeInTheDocument();
    expect(screen.queryByText('2026-06-10')).not.toBeInTheDocument();
  });

  it('navigates between planned platform workspaces', async () => {
    render(<AppShell currentUser={TEST_ADMIN_USER} />);
    await screen.findByRole('heading', { name: '策略指挥中心' });
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
      render(<AppShell currentUser={TEST_ADMIN_USER} />);
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
        limit: 100,
        minQualityScore: 65,
        startTime: expect.stringContaining('T00:00:00')
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

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
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

      render(<AppShell currentUser={TEST_ADMIN_USER} />);
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

    render(<AppShell currentUser={TEST_ADMIN_USER} />);
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
    render(<AppShell currentUser={TEST_ADMIN_USER} />);
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
