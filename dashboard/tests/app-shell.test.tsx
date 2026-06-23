import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import { DashboardRoot } from '../src/DashboardRoot';
import { ShadowAnalyticsReviewPanel } from '../src/components/ShadowAnalyticsReviewPanel';
import { ShadowReviewDecisionsPanel } from '../src/components/ShadowReviewDecisionsPanel';
import { ShadowFollowUpQueuePanel } from '../src/components/ShadowFollowUpQueuePanel';
import { ShadowFollowUpResolutionPanel } from '../src/components/ShadowFollowUpResolutionPanel';
import { ShadowOutcomeAnalyticsPanel } from '../src/components/ShadowOutcomeAnalyticsPanel';
import type {
  BarPoint,
  CurrentUser,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  ExperimentProposalRow,
  ExperimentReplayRow,
  OutcomeAnalyticsRow,
  PublicNewsItem,
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
  fetchOverview: vi.fn(),
  fetchCurrentUser: vi.fn(),
  login: vi.fn(),
  logout: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn(),
  fetchAssetDecisions: vi.fn(),
  fetchAssetOutcomes: vi.fn(),
  fetchExperimentProposals: vi.fn(),
  fetchExperimentReplay: vi.fn(),
  fetchOutcomeAnalytics: vi.fn(),
  fetchPublicNews: vi.fn(),
  refreshPublicNews: vi.fn(),
  fetchShadowAnalyticsReview: vi.fn(),
  fetchShadowFollowUpQueue: vi.fn(),
  fetchShadowFollowUpResolution: vi.fn(),
  fetchShadowReviewDecisions: vi.fn(),
  fetchShadowOutcomeAnalytics: vi.fn(),
  fetchShadowOutcomes: vi.fn(),
  fetchShadowWatchlist: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

vi.mock('../src/charts/AssetChart', () => ({
  AssetChart: ({ bars }: { bars: unknown[] }) => <div data-testid="asset-chart">{bars.length} bars</div>
}));

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, resolve, reject };
}

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

function makeCurrentUser(
  overrides: Partial<CurrentUser> = {}
): CurrentUser {
  return {
    id: 1,
    username: 'admin',
    display_name: 'Admin User',
    role: 'admin',
    is_active: true,
    ...overrides
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

function makePublicNews(): PublicNewsItem[] {
  return [
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
    },
    {
      news_id: 'news-macro-1',
      source: 'sina_finance',
      source_channel: '宏观',
      category: 'macro',
      title: '宏观政策更新',
      summary: '政策摘要',
      url: 'https://finance.sina.com.cn/macro/1',
      published_at: '2026-06-11 08:00:00',
      collected_at: '2026-06-11T08:01:00+00:00',
      raw_id: '',
      raw_payload: {},
      status: 'available'
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
    window.history.replaceState({}, '', '/');
    apiMocks.fetchCurrentUser.mockResolvedValue(makeCurrentUser());
    apiMocks.login.mockResolvedValue(makeCurrentUser());
    apiMocks.logout.mockResolvedValue({ ok: true });
    apiMocks.fetchOverview.mockResolvedValue(makeOverview());
    apiMocks.fetchDailyBars.mockResolvedValue(makeBars(1));
    apiMocks.fetchAssetScore.mockResolvedValue(makeScore());
    apiMocks.fetchAssetSignals.mockResolvedValue(makeSignals());
    apiMocks.fetchAssetDecisions.mockResolvedValue(makeDecisions());
    apiMocks.fetchAssetOutcomes.mockResolvedValue(makeOutcomes());
    apiMocks.fetchOutcomeAnalytics.mockResolvedValue(makeOutcomeAnalytics());
    apiMocks.fetchPublicNews.mockResolvedValue({ items: makePublicNews(), warnings: [] });
    apiMocks.refreshPublicNews.mockResolvedValue({
      received: 2,
      stored: 2,
      items_received: 2,
      counts_by_category: { live: 1, macro: 1 },
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
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the stock research shell title', async () => {
    render(<App />);

    expect(screen.getByText('Stock Research')).toBeVisible();
    await screen.findByText('TopN');
  });

  it('loads overview, selected asset review, and chart data', async () => {
    render(<App />);

    expect(await screen.findByText('000001.SZ')).toBeVisible();
    expect(screen.getAllByText('91.2')).toHaveLength(2);
    expect(screen.getByText('必看')).toBeVisible();
    expect(screen.getByText('Daily Review')).toBeVisible();
    expect(screen.getByText('Decision History')).toBeVisible();
    expect(screen.getAllByText('candidate')).toHaveLength(3);
    expect(screen.getByText('Outcome History')).toBeVisible();
    expect(screen.getByText(/5D\s+\+20.0%/)).toBeVisible();
    expect(screen.getByText('Outcome Analytics')).toBeVisible();
    expect(screen.getByText(/5D\s+\+15.0%/)).toBeVisible();
    expect(screen.getByText('Public News')).toBeVisible();
    expect(screen.getByText('全球快讯')).toBeVisible();
    expect(screen.getByText('宏观政策更新')).toBeVisible();
    expect(screen.getByText('Experiment Proposals')).toBeVisible();
    expect(screen.getByText('Replay dashboard top-N')).toBeVisible();
    expect(screen.getByText('Experiment Replay')).toBeVisible();
    expect(screen.getByText('passed_offline_replay')).toBeVisible();
    expect(screen.getByText('Shadow Watchlist')).toBeVisible();
    const shadowWatchlistPanel = screen.getByText('Shadow Watchlist').closest('section');
    expect(shadowWatchlistPanel).not.toBeNull();
    expect(within(shadowWatchlistPanel as HTMLElement).getByText('shadow_ready')).toBeVisible();
    expect(screen.getByText('Shadow Outcomes')).toBeVisible();
    expect(screen.getByText('complete')).toBeVisible();
    expect(screen.getByText(/5D\s+\+50.0%/)).toBeVisible();
    expect(screen.getByText('Shadow Outcome Analytics')).toBeVisible();
    const shadowOutcomeAnalyticsPanel = screen.getByText('Shadow Outcome Analytics').closest('section');
    expect(shadowOutcomeAnalyticsPanel).not.toBeNull();
    expect(within(shadowOutcomeAnalyticsPanel as HTMLElement).getByText('trend_shadow')).toBeVisible();
    expect(screen.getByText(/20D\s+\+12.0%/)).toBeVisible();
    expect(screen.getByText('Shadow Analytics Review')).toBeVisible();
    const shadowAnalyticsReviewPanel = screen.getByText('Shadow Analytics Review').closest('section');
    expect(shadowAnalyticsReviewPanel).not.toBeNull();
    expect(within(shadowAnalyticsReviewPanel as HTMLElement).getByText('research_follow_up_candidate')).toBeVisible();
    expect(within(shadowAnalyticsReviewPanel as HTMLElement).getByText('needs_more_evidence')).toBeVisible();
    expect(screen.getByText('Shadow Review Decisions')).toBeVisible();
    const shadowReviewDecisionsPanel = screen.getByText('Shadow Review Decisions').closest('section');
    expect(shadowReviewDecisionsPanel).not.toBeNull();
    expect(within(shadowReviewDecisionsPanel as HTMLElement).getByText('open_research_follow_up')).toBeVisible();
    expect(within(shadowReviewDecisionsPanel as HTMLElement).getByText('Create a separately scoped research follow-up.')).toBeVisible();
    expect(screen.getByText('Shadow Follow-up Queue')).toBeVisible();
    const shadowFollowUpPanel = screen.getByText('Shadow Follow-up Queue').closest('section');
    expect(shadowFollowUpPanel).not.toBeNull();
    expect(within(shadowFollowUpPanel as HTMLElement).getByText('collect_more_evidence')).toBeVisible();
    expect(within(shadowFollowUpPanel as HTMLElement).getByText('Additional outcome or data-quality evidence')).toBeVisible();
    expect(screen.getByText('Shadow Follow-up Resolution')).toBeVisible();
    const shadowFollowUpResolutionPanel = screen.getByText('Shadow Follow-up Resolution').closest('section');
    expect(shadowFollowUpResolutionPanel).not.toBeNull();
    expect(within(shadowFollowUpResolutionPanel as HTMLElement).getByText('stale_unresolved')).toBeVisible();
    expect(
      within(shadowFollowUpResolutionPanel as HTMLElement).getByText(
        'Review whether requested evidence has been collected.'
      )
    ).toBeVisible();
    expect(screen.getByText('p12-shadow-watchlist-2026-06-30')).toBeVisible();
    expect(screen.getAllByText('p11-replay-run-2026-06-30')).toHaveLength(2);
    expect(screen.queryByRole('button', { name: /promote|trade|write watchlist|scheduler/i })).not.toBeInTheDocument();
    expect(screen.getByTestId('asset-chart')).toHaveTextContent('1 bars');
    expect(apiMocks.fetchOverview).toHaveBeenCalledWith({
      tradeDate: '2026-05-29',
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 30
    });
  });

  it('renders the login view when there is no active session', async () => {
    apiMocks.fetchCurrentUser.mockRejectedValue(new Error('GET /api/auth/me failed with 401: Unauthorized'));
    window.history.replaceState({}, '', '/');

    render(<DashboardRoot />);

    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
    expect(screen.getByLabelText('用户名或邮箱')).toBeVisible();
    expect(screen.getByLabelText('密码')).toBeVisible();
    expect(window.location.pathname).toBe('/');
    expect(window.location.search).toBe('');
    expect(screen.queryByText('Stock Research')).not.toBeInTheDocument();
  });

  it('renders grouped admin navigation and updates the URL when switching views', async () => {
    const replaceStateSpy = vi.spyOn(window.history, 'replaceState');
    window.history.replaceState({}, '', '/dashboard-root?foo=1');

    render(<DashboardRoot />);

    expect(await screen.findByText('Stock Research')).toBeVisible();
    expect(screen.getByRole('heading', { name: '官方' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '我的' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '管理' })).toBeVisible();
    expect(screen.getByRole('button', { name: '我的观察池' })).toBeVisible();
    expect(screen.getByRole('button', { name: '用户管理' })).toBeVisible();
    expect(window.location.pathname).toBe('/dashboard-root');
    expect(window.location.search).toBe('?foo=1&view=official');

    fireEvent.click(screen.getByRole('button', { name: '我的复盘' }));

    await screen.findByRole('heading', { name: '我的复盘' });
    expect(replaceStateSpy).toHaveBeenLastCalledWith({}, '', '/dashboard-root?foo=1&view=my-reviews');
    expect(window.location.pathname).toBe('/dashboard-root');
    expect(window.location.search).toBe('?foo=1&view=my-reviews');
    expect(screen.queryByText('Stock Research')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '官方工作台' }));

    expect(await screen.findByText('Stock Research')).toBeVisible();
    expect(replaceStateSpy).toHaveBeenLastCalledWith({}, '', '/dashboard-root?foo=1&view=official');
    expect(window.location.pathname).toBe('/dashboard-root');
    expect(window.location.search).toBe('?foo=1&view=official');

    replaceStateSpy.mockRestore();
  });

  it('hides the 管理 navigation section for non-admin users', async () => {
    apiMocks.fetchCurrentUser.mockResolvedValue(makeCurrentUser({ role: 'user' }));

    render(<DashboardRoot />);

    expect(await screen.findByText('Stock Research')).toBeVisible();
    expect(screen.getByRole('heading', { name: '官方' })).toBeVisible();
    expect(screen.getByRole('heading', { name: '我的' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: '管理' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '用户管理' })).not.toBeInTheDocument();
  });

  it('uses the requested view from the URL when it is allowed', async () => {
    window.history.replaceState({}, '', '/?view=my-reviews');

    render(<DashboardRoot />);

    expect(await screen.findByRole('heading', { name: '我的复盘' })).toBeVisible();
    expect(window.location.search).toBe('?view=my-reviews');
    expect(screen.queryByText('Stock Research')).not.toBeInTheDocument();
  });

  it('logs out from the authenticated shell back to the login view', async () => {
    render(<DashboardRoot />);

    expect(await screen.findByText('Stock Research')).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: '退出登录' }));

    await waitFor(() => {
      expect(apiMocks.logout).toHaveBeenCalledTimes(1);
    });
    expect(await screen.findByRole('heading', { name: '登录' })).toBeVisible();
    expect(screen.queryByText('Stock Research')).not.toBeInTheDocument();
  });

  it('shows a bootstrap error for non-401 auth failures instead of the login form', async () => {
    apiMocks.fetchCurrentUser.mockRejectedValue(
      new Error('GET /api/auth/me failed with 503: Server unavailable')
    );

    render(<DashboardRoot />);

    expect(await screen.findByText('Unable to load dashboard.')).toBeVisible();
    expect(screen.getByText('GET /api/auth/me failed with 503: Server unavailable')).toBeVisible();
    expect(screen.queryByRole('heading', { name: '登录' })).not.toBeInTheDocument();
  });

  it('switches the asset chart between daily and intraday resolutions', async () => {
    apiMocks.fetchDailyBars
      .mockResolvedValueOnce(makeBars(1))
      .mockResolvedValueOnce([
        {
          time: '2026-05-29 10:00:00',
          open: 10,
          high: 11,
          low: 9,
          close: 10.5,
          volume: 300,
          amount: 3000
        },
        {
          time: '2026-05-29 10:30:00',
          open: 10.5,
          high: 12,
          low: 10,
          close: 11.5,
          volume: 400,
          amount: 4000
        }
      ]);

    render(<App />);

    expect(await screen.findByTestId('asset-chart')).toHaveTextContent('1 bars');
    fireEvent.click(screen.getByRole('button', { name: '30m' }));

    await waitFor(() => {
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000001.SZ', undefined, '2026-05-29', {
        resolution: '30m',
        adjustType: 'raw'
      });
      expect(screen.getByTestId('asset-chart')).toHaveTextContent('2 bars');
    });
    expect(screen.getByRole('button', { name: '30m' })).toHaveAttribute('aria-pressed', 'true');
  });

  it('filters, searches, and refreshes public news', async () => {
    render(<App />);

    const panel = (await screen.findByText('Public News')).closest('section');
    expect(panel).not.toBeNull();
    expect(within(panel as HTMLElement).getByText('全球快讯')).toBeVisible();
    expect(within(panel as HTMLElement).getByText('宏观政策更新')).toBeVisible();

    fireEvent.click(within(panel as HTMLElement).getByRole('button', { name: '宏观' }));
    expect(within(panel as HTMLElement).queryByText('全球快讯')).not.toBeInTheDocument();
    expect(within(panel as HTMLElement).getByText('宏观政策更新')).toBeVisible();

    fireEvent.change(within(panel as HTMLElement).getByLabelText('news search'), {
      target: { value: '全球' }
    });
    expect(within(panel as HTMLElement).getByText('No public news for current filters.')).toBeVisible();

    fireEvent.click(within(panel as HTMLElement).getByRole('button', { name: 'Refresh news' }));
    await waitFor(() => {
      expect(apiMocks.refreshPublicNews).toHaveBeenCalled();
    });
    expect(apiMocks.fetchPublicNews).toHaveBeenCalled();
  });

  it('shows loading states while overview and selected asset data are pending', async () => {
    const overview = createDeferred<DashboardOverview>();
    const bars = createDeferred<BarPoint[]>();
    const score = createDeferred<ScoreRow | null>();
    const signals = createDeferred<WatchlistSignalRow[]>();
    const decisions = createDeferred<DecisionEventRow[]>();
    const outcomes = createDeferred<DecisionOutcomeRow[]>();
    const analytics = createDeferred<OutcomeAnalyticsRow[]>();
    const proposals = createDeferred<ExperimentProposalRow[]>();
    const replay = createDeferred<ExperimentReplayRow[]>();
    const shadow = createDeferred<ShadowWatchlistRow[]>();
    const shadowOutcomes = createDeferred<ShadowOutcomeRow[]>();
    const shadowOutcomeAnalytics = createDeferred<ShadowOutcomeAnalyticsRow[]>();
    const shadowAnalyticsReview = createDeferred<ShadowAnalyticsReviewRow[]>();
    const shadowReviewDecisions = createDeferred<ShadowReviewDecisionRow[]>();
    const shadowFollowUpQueue = createDeferred<ShadowFollowUpRow[]>();
    const shadowFollowUpResolution = createDeferred<ShadowFollowUpResolutionRow[]>();

    apiMocks.fetchOverview.mockReturnValueOnce(overview.promise);
    apiMocks.fetchDailyBars.mockReturnValueOnce(bars.promise);
    apiMocks.fetchAssetScore.mockReturnValueOnce(score.promise);
    apiMocks.fetchAssetSignals.mockReturnValueOnce(signals.promise);
    apiMocks.fetchAssetDecisions.mockReturnValueOnce(decisions.promise);
    apiMocks.fetchAssetOutcomes.mockReturnValueOnce(outcomes.promise);
    apiMocks.fetchOutcomeAnalytics.mockReturnValueOnce(analytics.promise);
    apiMocks.fetchExperimentProposals.mockReturnValueOnce(proposals.promise);
    apiMocks.fetchExperimentReplay.mockReturnValueOnce(replay.promise);
    apiMocks.fetchShadowWatchlist.mockReturnValueOnce(shadow.promise);
    apiMocks.fetchShadowOutcomes.mockReturnValueOnce(shadowOutcomes.promise);
    apiMocks.fetchShadowOutcomeAnalytics.mockReturnValueOnce(shadowOutcomeAnalytics.promise);
    apiMocks.fetchShadowAnalyticsReview.mockReturnValueOnce(shadowAnalyticsReview.promise);
    apiMocks.fetchShadowReviewDecisions.mockReturnValueOnce(shadowReviewDecisions.promise);
    apiMocks.fetchShadowFollowUpQueue.mockReturnValueOnce(shadowFollowUpQueue.promise);
    apiMocks.fetchShadowFollowUpResolution.mockReturnValueOnce(shadowFollowUpResolution.promise);

    render(<App />);

    expect(screen.getByText('Loading TopN...')).toBeVisible();
    expect(screen.getByText('Loading watchlist...')).toBeVisible();
    expect(screen.getByText('Loading reports...')).toBeVisible();
    expect(screen.getByText('Loading asset review...')).toBeVisible();
    expect(screen.getByText('Loading experiment replay...')).toBeVisible();
    expect(screen.getByText('Loading shadow watchlist...')).toBeVisible();
    expect(screen.getByText('Loading shadow outcomes...')).toBeVisible();
    expect(screen.getByText('Loading shadow outcome analytics...')).toBeVisible();
    expect(screen.getByText('Loading shadow analytics review...')).toBeVisible();
    expect(screen.getByText('Loading shadow review decisions...')).toBeVisible();
    expect(screen.getByText('Loading shadow follow-up queue...')).toBeVisible();
    expect(screen.getByText('Loading shadow follow-up resolution...')).toBeVisible();

    await act(async () => {
      overview.resolve(makeOverview());
      bars.resolve(makeBars(1));
      score.resolve(makeScore());
      signals.resolve(makeSignals());
      decisions.resolve(makeDecisions());
      outcomes.resolve(makeOutcomes());
      analytics.resolve(makeOutcomeAnalytics());
      proposals.resolve(makeExperimentProposals());
      replay.resolve(makeExperimentReplay());
      shadow.resolve(makeShadowWatchlist());
      shadowOutcomes.resolve(makeShadowOutcomes());
      shadowOutcomeAnalytics.resolve(makeShadowOutcomeAnalytics());
      shadowAnalyticsReview.resolve(makeShadowAnalyticsReview());
      shadowReviewDecisions.resolve(makeShadowReviewDecisions());
      shadowFollowUpQueue.resolve(makeShadowFollowUpQueue());
      shadowFollowUpResolution.resolve(makeShadowFollowUpResolution());
    });

    await waitFor(() => {
      expect(screen.queryByText('Loading TopN...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading watchlist...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading reports...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading asset review...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading experiment replay...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading shadow watchlist...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading shadow outcomes...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading shadow outcome analytics...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading shadow analytics review...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading shadow review decisions...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading shadow follow-up queue...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading shadow follow-up resolution...')).not.toBeInTheDocument();
    });
  });

  it('shows empty states for dashboard lists and reports', async () => {
    apiMocks.fetchOverview.mockResolvedValueOnce(
      makeOverview({
        top_scores: [],
        watchlist_signals: [],
        reports: []
      })
    );
    apiMocks.fetchDailyBars.mockResolvedValueOnce([]);
    apiMocks.fetchAssetScore.mockResolvedValueOnce(null);
    apiMocks.fetchAssetSignals.mockResolvedValueOnce([]);
    apiMocks.fetchAssetDecisions.mockResolvedValueOnce([]);
    apiMocks.fetchAssetOutcomes.mockResolvedValueOnce([]);
    apiMocks.fetchOutcomeAnalytics.mockResolvedValueOnce([]);
    apiMocks.fetchExperimentProposals.mockResolvedValueOnce([]);
    apiMocks.fetchExperimentReplay.mockResolvedValueOnce([]);
    apiMocks.fetchShadowWatchlist.mockResolvedValueOnce([]);
    apiMocks.fetchShadowOutcomes.mockResolvedValueOnce([]);
    apiMocks.fetchShadowOutcomeAnalytics.mockResolvedValueOnce([]);
    apiMocks.fetchShadowAnalyticsReview.mockResolvedValueOnce([]);
    apiMocks.fetchShadowReviewDecisions.mockResolvedValueOnce([]);
    apiMocks.fetchShadowFollowUpQueue.mockResolvedValueOnce([]);
    apiMocks.fetchShadowFollowUpResolution.mockResolvedValueOnce([]);

    render(<App />);

    expect(await screen.findByText('No TopN rows for selected date.')).toBeVisible();
    expect(screen.getByText('No watchlist signals for selected date.')).toBeVisible();
    expect(screen.getByText('No reports for selected date.')).toBeVisible();
    expect(screen.getByText('No score for selected date.')).toBeVisible();
    expect(screen.getByText('No decision history for selected range.')).toBeVisible();
    expect(screen.getByText('No outcome history for selected range.')).toBeVisible();
    expect(screen.getByText('No outcome analytics for selected range.')).toBeVisible();
    expect(screen.getByText('No experiment proposals for selected range.')).toBeVisible();
    expect(screen.getByText('No experiment replay results for selected range.')).toBeVisible();
    expect(screen.getByText('No shadow watchlist candidates for selected range.')).toBeVisible();
    expect(screen.getByText('No shadow outcomes for selected range.')).toBeVisible();
    expect(screen.getByText('No shadow outcome analytics for selected range.')).toBeVisible();
    expect(screen.getByText('No shadow analytics review rows for selected range.')).toBeVisible();
    expect(screen.getByText('No shadow review decisions for selected range.')).toBeVisible();
    expect(screen.getByText('No shadow follow-up queue items for selected range.')).toBeVisible();
    expect(screen.getByText('No shadow follow-up resolution items for selected range.')).toBeVisible();
    expect(screen.getByText('No chart bars for selected range.')).toBeVisible();
  });

  it('renders invalid shadow analytics review metrics as n/a instead of NaN%', async () => {
    apiMocks.fetchShadowAnalyticsReview.mockResolvedValueOnce([
      {
        ...makeShadowAnalyticsReview()[0],
        horizon_metrics: {
          '20': {
            forward_return_mean: Number.NaN,
            max_low_drawdown_worst: Number.POSITIVE_INFINITY
          }
        }
      }
    ]);

    render(<App />);

    expect(await screen.findByText('Shadow Analytics Review')).toBeVisible();
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
    apiMocks.fetchShadowOutcomeAnalytics.mockResolvedValueOnce([
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
    ]);

    render(<App />);

    expect(await screen.findByText('Shadow Outcome Analytics')).toBeVisible();
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
    apiMocks.fetchShadowOutcomes.mockResolvedValueOnce(makeShadowOutcomesWithInvalidMetrics());

    render(<App />);

    expect(await screen.findByText('Shadow Outcomes')).toBeVisible();
    const shadowOutcomesPanel = screen.getByText('Shadow Outcomes').closest('section');
    expect(shadowOutcomesPanel).not.toBeNull();
    expect(within(shadowOutcomesPanel as HTMLElement).getAllByText(/n\/a/)).toHaveLength(3);
    expect(within(shadowOutcomesPanel as HTMLElement).queryByText(/NaN%/)).not.toBeInTheDocument();
  });

  it('selects an asset from the watchlist', async () => {
    render(<App />);

    fireEvent.click(await screen.findByText('Vanke'));

    await waitFor(() => {
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000002.SZ', undefined, '2026-05-29', {
        resolution: '1D',
        adjustType: 'qfq'
      });
      expect(apiMocks.fetchAssetDecisions).toHaveBeenLastCalledWith('000002.SZ', expect.any(String), '2026-05-29');
      expect(apiMocks.fetchAssetOutcomes).toHaveBeenLastCalledWith('000002.SZ', expect.any(String), '2026-05-29');
    });
  });

  it('uses timezone-stable calendar math for the chart start date', async () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText('trade date'), { target: { value: '2026-03-01' } });

    await waitFor(() => {
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000001.SZ', undefined, '2026-03-01', {
        resolution: '1D',
        adjustType: 'qfq'
      });
    });
  });

  it('ignores stale selected asset responses that resolve after a newer selection', async () => {
    const firstBars = createDeferred<BarPoint[]>();
    const firstScore = createDeferred<ScoreRow | null>();
    const firstSignals = createDeferred<WatchlistSignalRow[]>();
    const firstDecisions = createDeferred<DecisionEventRow[]>();
    const firstOutcomes = createDeferred<DecisionOutcomeRow[]>();
    const secondBars = createDeferred<BarPoint[]>();
    const secondScore = createDeferred<ScoreRow | null>();
    const secondSignals = createDeferred<WatchlistSignalRow[]>();
    const secondDecisions = createDeferred<DecisionEventRow[]>();
    const secondOutcomes = createDeferred<DecisionOutcomeRow[]>();

    apiMocks.fetchDailyBars.mockReturnValueOnce(firstBars.promise).mockReturnValueOnce(secondBars.promise);
    apiMocks.fetchAssetScore.mockReturnValueOnce(firstScore.promise).mockReturnValueOnce(secondScore.promise);
    apiMocks.fetchAssetSignals.mockReturnValueOnce(firstSignals.promise).mockReturnValueOnce(secondSignals.promise);
    apiMocks.fetchAssetDecisions
      .mockReturnValueOnce(firstDecisions.promise)
      .mockReturnValueOnce(secondDecisions.promise);
    apiMocks.fetchAssetOutcomes
      .mockReturnValueOnce(firstOutcomes.promise)
      .mockReturnValueOnce(secondOutcomes.promise);

    render(<App />);

    fireEvent.click(await screen.findByText('Vanke'));

    await act(async () => {
      secondBars.resolve(makeBars(2));
      secondScore.resolve(makeScore('000002.SZ'));
      secondSignals.resolve(makeSignals('000002.SZ'));
      secondDecisions.resolve(makeDecisions('000002.SZ'));
      secondOutcomes.resolve(makeOutcomes('000002.SZ'));
    });
    await waitFor(() => expect(screen.getByTestId('asset-chart')).toHaveTextContent('2 bars'));

    await act(async () => {
      firstBars.resolve(makeBars(1));
      firstScore.resolve(makeScore('000001.SZ'));
      firstSignals.resolve(makeSignals('000001.SZ'));
      firstDecisions.resolve(makeDecisions('000001.SZ'));
      firstOutcomes.resolve(makeOutcomes('000001.SZ'));
    });

    expect(screen.getByTestId('asset-chart')).toHaveTextContent('2 bars');
  });

  it('ignores stale overview errors after the trade date changes', async () => {
    const firstOverview = createDeferred<DashboardOverview>();
    apiMocks.fetchOverview
      .mockReturnValueOnce(firstOverview.promise)
      .mockResolvedValueOnce(makeOverview({ trade_date: '2026-03-01' }));

    render(<App />);

    fireEvent.change(screen.getByLabelText('trade date'), { target: { value: '2026-03-01' } });
    await waitFor(() => {
      expect(apiMocks.fetchOverview).toHaveBeenLastCalledWith({
        tradeDate: '2026-03-01',
        scoreVersion: 'manual_v1',
        watchlistId: 'default',
        topN: 30
      });
    });

    await act(async () => {
      firstOverview.reject(new Error('stale overview failed'));
    });

    expect(screen.queryByText('stale overview failed')).not.toBeInTheDocument();
  });
});
