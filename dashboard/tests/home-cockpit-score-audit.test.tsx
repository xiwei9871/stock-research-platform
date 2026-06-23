import '@testing-library/jest-dom/vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HomeCockpit } from '../src/components/HomeCockpit';

const apiMocks = vi.hoisted(() => ({
  fetchBacktestStrategies: vi.fn(),
  fetchMarketMonitorEod: vi.fn(),
  fetchPlatformReadiness: vi.fn(),
  fetchPlatformSummary: vi.fn(),
  fetchPublicNews: vi.fn(),
  fetchStrategyScoreAudit: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

describe('HomeCockpit strategy score audit summary', () => {
  beforeEach(() => {
    apiMocks.fetchPlatformReadiness.mockResolvedValue({
      mode: 'eod_local',
      status: 'PARTIAL',
      as_of: '2026-06-22T08:30:00+08:00',
      latest_market_date: '2026-06-22',
      latest_trade_date: '2026-06-22',
      display_trade_date: '2026-06-22',
      candidate_trade_date: '2026-06-22',
      health_groups: [],
      checks: [],
      warnings: []
    });
    apiMocks.fetchPlatformSummary.mockResolvedValue({
      latest_market_date: '2026-06-22',
      latest_score_date: '2026-06-22',
      latest_factor_date: '2026-06-22',
      market_asset_count: 5207,
      score_asset_count: 5207,
      factor_count: 43,
      score_versions: ['manual_v1'],
      topn_preview: []
    });
    apiMocks.fetchBacktestStrategies.mockResolvedValue([
      {
        strategy_id: 'lhb_shortline',
        strategy_name: 'LHB Shortline Combo',
        status: 'runnable',
        description: 'LHB combo',
        factor_groups: ['资金行为'],
        signal_inputs: ['龙虎榜'],
        default_parameters: { top_n: 20 },
        latest_evidence: 'Top5/20%/10bps 净值约 2.6069，最大回撤约 -5.32%。',
        latest_metrics: {
          as_of_date: '2026-06-22',
          total_return_pct: 160.7,
          max_drawdown_pct: -5.3,
          latest_day_return_pct: 1.2,
          latest_day_drawdown_pct: -0.4,
          signal_status: 'no_position_rows',
          signal_count: null
        },
        primary_action: 'Run backtest'
      }
    ]);
    apiMocks.fetchMarketMonitorEod.mockResolvedValue({
      trade_date: '2026-06-22',
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
      strategy_signal_summary: { topn_preview_count: 0, topn_preview: [], risk_filter_counts: {} },
      generated_reports: [],
      market_emotion: null,
      emotion_stock_lists: {
        auction_status: 'pending_source',
        auction: [],
        limit_up: [],
        broken_limit_up: [],
        limit_down: []
      },
      warnings: []
    });
    apiMocks.fetchPublicNews.mockResolvedValue({
      items: [],
      warnings: []
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('shows a warning audit summary when anomalies exist', async () => {
    apiMocks.fetchStrategyScoreAudit.mockResolvedValue({
      trade_date: '2026-06-22',
      status: 'success',
      overall_status: 'warning',
      summary_path: '/tmp/strategy_score_audit_summary.json',
      detail_path: '/tmp/strategy_score_audit_detail.csv',
      total_rows: 12,
      selected_rows: 12,
      anomaly_row_count: 5,
      anomaly_counts_by_type: { mapped_score_without_raw_score: 5 },
      strategies: [{ strategy_id: 'lhb_shortline', anomaly_count: 5 }],
      sample_rows: []
    });

    render(<HomeCockpit onNavigate={() => undefined} />);

    const statusRegion = await screen.findByRole('region', { name: '首页状态' });
    const scoreAuditCell = within(statusRegion).getByText('策略打分审计').closest('div');
    expect(scoreAuditCell).not.toBeNull();
    await waitFor(() => expect(within(scoreAuditCell as HTMLDivElement).getByText('需关注')).toBeVisible());
    expect(within(scoreAuditCell as HTMLDivElement).getByText('5 条异常')).toBeVisible();
    expect(apiMocks.fetchStrategyScoreAudit).toHaveBeenCalledWith('2026-06-22');
  });

  it('shows a clean audit summary when anomalies are absent', async () => {
    apiMocks.fetchStrategyScoreAudit.mockResolvedValue({
      trade_date: '2026-06-22',
      status: 'success',
      overall_status: 'ok',
      summary_path: '/tmp/strategy_score_audit_summary.json',
      detail_path: '/tmp/strategy_score_audit_detail.csv',
      total_rows: 12,
      selected_rows: 12,
      anomaly_row_count: 0,
      anomaly_counts_by_type: {},
      strategies: [],
      sample_rows: []
    });

    render(<HomeCockpit onNavigate={() => undefined} />);

    const statusRegion = await screen.findByRole('region', { name: '首页状态' });
    const scoreAuditCell = within(statusRegion).getByText('策略打分审计').closest('div');
    expect(scoreAuditCell).not.toBeNull();
    await waitFor(() => expect(within(scoreAuditCell as HTMLDivElement).getByText('正常')).toBeVisible());
    expect(within(scoreAuditCell as HTMLDivElement).getByText('0 条异常')).toBeVisible();
  });

  it('shows missing audit state without failing the cockpit', async () => {
    apiMocks.fetchStrategyScoreAudit.mockResolvedValue({
      trade_date: '2026-06-22',
      status: 'missing',
      overall_status: 'missing',
      summary_path: '',
      detail_path: '',
      total_rows: 0,
      selected_rows: 0,
      anomaly_row_count: 0,
      anomaly_counts_by_type: {},
      strategies: [],
      sample_rows: [],
      warnings: ['strategy score audit artifact not found for trade_date 2026-06-22']
    });

    render(<HomeCockpit onNavigate={() => undefined} />);

    const statusRegion = await screen.findByRole('region', { name: '首页状态' });
    const scoreAuditCell = within(statusRegion).getByText('策略打分审计').closest('div');
    expect(scoreAuditCell).not.toBeNull();
    await waitFor(() => expect(within(scoreAuditCell as HTMLDivElement).getByText('待补齐')).toBeVisible());
    expect(within(scoreAuditCell as HTMLDivElement).getByText('暂无审计产物')).toBeVisible();
  });
});
