import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
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
  fetchDailyBars: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn(),
  fetchAssetDecisions: vi.fn(),
  fetchAssetOutcomes: vi.fn(),
  fetchExperimentProposals: vi.fn(),
  fetchExperimentReplay: vi.fn(),
  fetchOutcomeAnalytics: vi.fn(),
  fetchShadowAnalyticsReview: vi.fn(),
  fetchShadowFollowUpQueue: vi.fn(),
  fetchShadowFollowUpResolution: vi.fn(),
  fetchShadowReviewDecisions: vi.fn(),
  fetchShadowOutcomeAnalytics: vi.fn(),
  fetchShadowOutcomes: vi.fn(),
  fetchShadowWatchlist: vi.fn(),
  fetchFactorLibrary: vi.fn(),
  fetchFactorScorePreview: vi.fn(),
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
    apiMocks.fetchDailyBars.mockResolvedValue(makeBars(1));
    apiMocks.fetchAssetScore.mockResolvedValue(makeScore());
    apiMocks.fetchAssetSignals.mockResolvedValue(makeSignals());
    apiMocks.fetchAssetDecisions.mockResolvedValue(makeDecisions());
    apiMocks.fetchAssetOutcomes.mockResolvedValue(makeOutcomes());
    apiMocks.fetchOutcomeAnalytics.mockResolvedValue(makeOutcomeAnalytics());
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
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the stock research cockpit shell title', async () => {
    render(<App />);

    expect(screen.getByText('Stock Research')).toBeVisible();
    expect(await screen.findByRole('heading', { name: 'Research Cockpit' })).toBeVisible();
    expect(screen.getByText('Latest Market Data')).toBeVisible();
    expect(screen.getByText('LHB Shortline Combo')).toBeVisible();
    expect(screen.queryByText('Manual V1 TopN Rotation')).not.toBeInTheDocument();
    expect(screen.getByText('manual_v1 factor-score candidate pool, not a combo strategy result')).toBeVisible();
  });

  it('navigates between planned platform workspaces', async () => {
    render(<App />);
    await screen.findByRole('heading', { name: 'Research Cockpit' });
    const navigation = within(screen.getByRole('complementary', { name: 'Workspace navigation' }));

    fireEvent.click(navigation.getByRole('button', { name: 'Open Factor Lab workspace' }));
    expect(await screen.findByRole('heading', { name: 'Factor Lab' })).toBeVisible();

    fireEvent.click(navigation.getByRole('button', { name: 'Open Backtest Lab workspace' }));
    expect(await screen.findByRole('heading', { name: 'Backtest Lab' })).toBeVisible();

    fireEvent.click(navigation.getByRole('button', { name: 'Open Reports workspace' }));
    expect(await screen.findByRole('heading', { name: 'Reports', level: 1 })).toBeVisible();
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

    fireEvent.click(navigation.getByRole('button', { name: 'Open Strategy Validation workspace' }));

    await waitFor(() => expect(screen.getByText('LHB Shortline')).toBeInTheDocument());
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
