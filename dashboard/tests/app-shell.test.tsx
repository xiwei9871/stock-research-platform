import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App } from '../src/App';
import type {
  BarPoint,
  DashboardOverview,
  DecisionEventRow,
  DecisionOutcomeRow,
  OutcomeAnalyticsRow,
  ScoreRow,
  WatchlistSignalRow
} from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchOverview: vi.fn(),
  fetchDailyBars: vi.fn(),
  fetchAssetScore: vi.fn(),
  fetchAssetSignals: vi.fn(),
  fetchAssetDecisions: vi.fn(),
  fetchAssetOutcomes: vi.fn(),
  fetchOutcomeAnalytics: vi.fn()
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

describe('dashboard app shell', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiMocks.fetchOverview.mockResolvedValue(makeOverview());
    apiMocks.fetchDailyBars.mockResolvedValue(makeBars(1));
    apiMocks.fetchAssetScore.mockResolvedValue(makeScore());
    apiMocks.fetchAssetSignals.mockResolvedValue(makeSignals());
    apiMocks.fetchAssetDecisions.mockResolvedValue(makeDecisions());
    apiMocks.fetchAssetOutcomes.mockResolvedValue(makeOutcomes());
    apiMocks.fetchOutcomeAnalytics.mockResolvedValue(makeOutcomeAnalytics());
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
    expect(screen.getByTestId('asset-chart')).toHaveTextContent('1 bars');
    expect(apiMocks.fetchOverview).toHaveBeenCalledWith({
      tradeDate: '2026-05-29',
      scoreVersion: 'manual_v1',
      watchlistId: 'default',
      topN: 30
    });
  });

  it('shows loading states while overview and selected asset data are pending', async () => {
    const overview = createDeferred<DashboardOverview>();
    const bars = createDeferred<BarPoint[]>();
    const score = createDeferred<ScoreRow | null>();
    const signals = createDeferred<WatchlistSignalRow[]>();
    const decisions = createDeferred<DecisionEventRow[]>();
    const outcomes = createDeferred<DecisionOutcomeRow[]>();
    const analytics = createDeferred<OutcomeAnalyticsRow[]>();

    apiMocks.fetchOverview.mockReturnValueOnce(overview.promise);
    apiMocks.fetchDailyBars.mockReturnValueOnce(bars.promise);
    apiMocks.fetchAssetScore.mockReturnValueOnce(score.promise);
    apiMocks.fetchAssetSignals.mockReturnValueOnce(signals.promise);
    apiMocks.fetchAssetDecisions.mockReturnValueOnce(decisions.promise);
    apiMocks.fetchAssetOutcomes.mockReturnValueOnce(outcomes.promise);
    apiMocks.fetchOutcomeAnalytics.mockReturnValueOnce(analytics.promise);

    render(<App />);

    expect(screen.getByText('Loading TopN...')).toBeVisible();
    expect(screen.getByText('Loading watchlist...')).toBeVisible();
    expect(screen.getByText('Loading reports...')).toBeVisible();
    expect(screen.getByText('Loading asset review...')).toBeVisible();

    await act(async () => {
      overview.resolve(makeOverview());
      bars.resolve(makeBars(1));
      score.resolve(makeScore());
      signals.resolve(makeSignals());
      decisions.resolve(makeDecisions());
      outcomes.resolve(makeOutcomes());
      analytics.resolve(makeOutcomeAnalytics());
    });

    await waitFor(() => {
      expect(screen.queryByText('Loading TopN...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading watchlist...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading reports...')).not.toBeInTheDocument();
      expect(screen.queryByText('Loading asset review...')).not.toBeInTheDocument();
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

    render(<App />);

    expect(await screen.findByText('No TopN rows for selected date.')).toBeVisible();
    expect(screen.getByText('No watchlist signals for selected date.')).toBeVisible();
    expect(screen.getByText('No reports for selected date.')).toBeVisible();
    expect(screen.getByText('No score for selected date.')).toBeVisible();
    expect(screen.getByText('No decision history for selected range.')).toBeVisible();
    expect(screen.getByText('No outcome history for selected range.')).toBeVisible();
    expect(screen.getByText('No outcome analytics for selected range.')).toBeVisible();
    expect(screen.getByText('No chart bars for selected range.')).toBeVisible();
  });

  it('selects an asset from the watchlist', async () => {
    render(<App />);

    fireEvent.click(await screen.findByText('Vanke'));

    await waitFor(() => {
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000002.SZ', expect.any(String), '2026-05-29');
      expect(apiMocks.fetchAssetDecisions).toHaveBeenLastCalledWith('000002.SZ', expect.any(String), '2026-05-29');
      expect(apiMocks.fetchAssetOutcomes).toHaveBeenLastCalledWith('000002.SZ', expect.any(String), '2026-05-29');
    });
  });

  it('uses timezone-stable calendar math for the chart start date', async () => {
    render(<App />);

    fireEvent.change(screen.getByLabelText('trade date'), { target: { value: '2026-03-01' } });

    await waitFor(() => {
      expect(apiMocks.fetchDailyBars).toHaveBeenLastCalledWith('000001.SZ', '2025-09-02', '2026-03-01');
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
