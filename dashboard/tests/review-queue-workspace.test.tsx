import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReviewQueueWorkspace } from '../src/components/ReviewQueueWorkspace';
import type { ReviewQueueResponse } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchReviewQueue: vi.fn(),
  fetchPlatformSummary: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeQueue(overrides: Partial<ReviewQueueResponse> = {}): ReviewQueueResponse {
  return {
    trade_date: '2026-06-08',
    score_version: 'strategy_topn',
    review_mode: 'strategy_topn',
    generated_at: '2026-06-08T16:00:00Z',
    warnings: [],
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
            trade_date: '2026-06-08',
            latest_trade_date: '2026-06-08',
            run_id: 'eod-2026-06-08-local',
            score_version: 'strategy_topn',
            display_name: '平安银行',
            rank: 1,
            score: 88.2,
            source_type: 'strategy_topn',
            source_name: 'Mid Trend Combo',
            source_rank: 1,
            topn_rank: 1,
            strategy_id: 'mid_trend',
            strategy_name: 'Mid Trend Combo',
            strategy_run_id: 'mid_trend:run',
            review_tier: 'top5_focus',
            digest_key: '2026-06-08:strategy_topn:000001.SZ',
            digest_title: 'Strong evidence',
            bucket: 'strong',
            source_kinds: ['strategy', 'research'],
            risk_count: 1,
            warning_count: 1,
            next_action_count: 4,
            digest: {
              asset_id: '000001.SZ',
              canonical_asset_id: '000001.SZ',
              trade_date: '2026-06-08',
              title: 'Strong evidence',
              score: 88.2,
              bucket: 'strong',
              facts: [
                { kind: 'strategy', label: 'Recent accepted news' },
                { kind: 'research', label: 'Broker target raised' }
              ],
              risk_flags: [{ key: 'crowded', label: 'Crowded short-term trade', severity: 'medium' }],
              source_refs: { strategy_asset_id: '000001.SZ' },
              warnings: ['Check earnings calendar'],
              next_actions: [
                {
                  key: 'review_stock',
                  label: 'Review Stock',
                  workspace: 'stock',
                  asset_id: '000001.SZ',
                  query: '平安银行'
                },
                {
                  key: 'open_news',
                  label: 'Open News',
                  workspace: 'news',
                  asset_id: '000001.SZ',
                  query: '平安银行',
                  news_id: 'news-1'
                },
                {
                  key: 'open_research',
                  label: 'Open Research',
                  workspace: 'researchReports',
                  asset_id: '000001.SZ',
                  query: '平安银行',
                  report_id: 'report-1',
                  event_key: 'report-1:000001.SZ'
                },
                {
                  key: 'open_market',
                  label: 'Open Market',
                  workspace: 'market',
                  asset_id: '000001.SZ',
                  query: '平安银行',
                  event_key: 'limit-up:000001.SZ',
                  monitor_tab: 'limit_up'
                }
              ]
            }
          }
        ]
      },
      { bucket: 'strategy:tech_bottleneck', label: 'Tech Bottleneck Combo', count: 0, items: [] }
    ],
    ...overrides
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchReviewQueue.mockResolvedValue(makeQueue());
  apiMocks.fetchPlatformSummary.mockResolvedValue({
    latest_market_date: '2026-06-08',
    latest_factor_date: '2026-06-08',
    latest_score_date: '2026-06-08',
    market_asset_count: 1,
    score_asset_count: 1,
    factor_count: 1,
    score_versions: ['strategy_topn'],
    topn_preview: []
  });
});

afterEach(() => {
  cleanup();
});

describe('ReviewQueueWorkspace', () => {
  it('loads grouped queue items and renders the selected evidence preview', async () => {
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(makeQueue());

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByRole('heading', { name: '策略复盘队列' })).toBeInTheDocument();
    expect(apiMocks.fetchReviewQueue).toHaveBeenCalledWith({ limit: 10, lookbackDays: 90 });
    expect(screen.getByRole('button', { name: 'Mid Trend Combo 1' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('复盘范围')).toBeInTheDocument();
    expect(screen.getByText('启用策略 Top10')).toBeInTheDocument();
    expect(screen.getByText('平台市场日期')).toBeInTheDocument();
    expect(screen.getByText('复盘队列与平台市场日期一致。')).toBeInTheDocument();
    expect(screen.getByText('Mid Trend Combo：最新 2026-06-08，1 只')).toBeInTheDocument();
    const sourceFilters = within(screen.getByLabelText('策略复盘分组')).getByLabelText('证据来源');
    expect(within(sourceFilters).getByText('策略')).toBeInTheDocument();
    expect(within(sourceFilters).getByText('研报')).toBeInTheDocument();
    const queueRow = screen.getByRole('button', { name: /平安银行/ });
    expect(queueRow).toHaveAttribute('aria-pressed', 'true');
    expect(queueRow).toHaveStyle({
      gridTemplateColumns: '48px minmax(180px, 1.4fr) 92px 96px minmax(120px, 0.8fr) 96px 104px'
    });
    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(within(queueRow).getByText('Strong evidence')).toBeInTheDocument();
    expect(within(queueRow).getByText('策略')).toBeInTheDocument();
    expect(within(queueRow).getByText('研报')).toBeInTheDocument();
    expect(within(queueRow).getByText('Top5 重点复盘')).toBeInTheDocument();
    expect(within(queueRow).getByText('1 风险 / 1 提醒')).toBeInTheDocument();

    const preview = screen.getByRole('region', { name: '选中标的证据' });
    const sourceChips = within(preview).getByLabelText('证据来源');
    expect(within(preview).getByText('Strong evidence')).toBeInTheDocument();
    expect(within(preview).getByText('Recent accepted news')).toBeInTheDocument();
    expect(within(sourceChips).getByText('策略')).toBeInTheDocument();
    expect(within(sourceChips).getByText('研报')).toBeInTheDocument();
  });

  it('shows platform and per-strategy freshness when review queue is stale', async () => {
    apiMocks.fetchPlatformSummary.mockResolvedValueOnce({
      latest_market_date: '2026-06-15',
      latest_factor_date: '2026-06-15',
      latest_score_date: '2026-06-15',
      market_asset_count: 1,
      score_asset_count: 1,
      factor_count: 1,
      score_versions: ['strategy_topn'],
      topn_preview: []
    });
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(
      makeQueue({
        trade_date: '2026-06-05',
        groups: [
          makeQueue().groups[0],
          {
            bucket: 'strategy:tech_bottleneck',
            label: 'Tech Bottleneck Combo',
            count: 1,
            items: [
              {
                ...makeQueue().groups[0].items[0],
                queue_id: '2026-06-01:strategy_topn:000002.SZ',
                asset_id: '000002.SZ',
                display_name: '万科A',
                trade_date: '2026-06-01',
                latest_trade_date: '2026-06-01',
                strategy_id: 'tech_bottleneck',
                strategy_name: 'Tech Bottleneck Combo',
                source_name: 'Tech Bottleneck Combo'
              }
            ]
          }
        ]
      })
    );

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('复盘队列落后平台市场日期 10 个自然日，请检查复盘生成任务。')).toBeInTheDocument();
    expect(screen.getByText('Mid Trend Combo：最新 2026-06-08，1 只')).toBeInTheDocument();
    expect(screen.getByText('Tech Bottleneck Combo：最新 2026-06-01，1 只')).toBeInTheDocument();
  });

  it('switches groups and shows an empty group state', async () => {
    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('Recent accepted news')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Tech Bottleneck Combo 0' }));

    expect(screen.getByText('2026-06-08 暂无 Tech Bottleneck Combo 复盘标的。')).toBeInTheDocument();
    expect(screen.queryByText('Recent accepted news')).not.toBeInTheDocument();
  });

  it('replays the review queue for a selected trade date', async () => {
    const replayQueue = makeQueue({
      trade_date: '2026-06-24',
      groups: [
        {
          ...makeQueue().groups[0],
          count: 2,
          items: [
            makeQueue().groups[0].items[0],
            {
              ...makeQueue().groups[0].items[0],
              queue_id: '2026-06-24:strategy_topn:000002.SZ',
              asset_id: '000002.SZ',
              display_name: '万科A',
              rank: 2,
              topn_rank: 2
            }
          ]
        },
        { bucket: 'strategy:tech_bottleneck', label: 'Tech Bottleneck Combo', count: 0, items: [] }
      ]
    });
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(makeQueue()).mockResolvedValueOnce(replayQueue);

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('Recent accepted news')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('选择复盘日期'), { target: { value: '2026-06-24' } });
    fireEvent.click(screen.getByRole('button', { name: '回放该日复盘队列' }));

    await waitFor(() =>
      expect(apiMocks.fetchReviewQueue).toHaveBeenLastCalledWith({
        tradeDate: '2026-06-24',
        limit: 10,
        lookbackDays: 90
      })
    );
    expect((await screen.findAllByText('2026-06-24')).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Mid Trend Combo 2' })).toBeInTheDocument();
    expect(screen.getByText('万科A')).toBeInTheDocument();
  });

  it('dispatches source-backed next actions', async () => {
    const onOpenStock = vi.fn();
    const onOpenNews = vi.fn();
    const onOpenResearchReports = vi.fn();
    const onOpenMarketMonitor = vi.fn();

    render(
      <ReviewQueueWorkspace
        onOpenStock={onOpenStock}
        onOpenNews={onOpenNews}
        onOpenResearchReports={onOpenResearchReports}
        onOpenMarketMonitor={onOpenMarketMonitor}
      />
    );

    const preview = await screen.findByRole('region', { name: '选中标的证据' });
    fireEvent.click(within(preview).getByRole('button', { name: 'Review Stock' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open News' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open Research' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open Market' }));

    expect(onOpenStock).toHaveBeenCalledWith(
      '000001.SZ',
      expect.objectContaining({
        sourceWorkspace: 'reviewQueue',
        assetId: '000001.SZ',
        query: '平安银行',
        tradeDate: '2026-06-08',
        runId: 'eod-2026-06-08-local',
        digestKey: '2026-06-08:strategy_topn:000001.SZ',
        sourceType: 'strategy_topn',
        sourceName: 'Mid Trend Combo',
        scoreVersion: 'strategy_topn',
        topnRank: 1
      })
    );
    expect(onOpenNews).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceWorkspace: 'news',
        assetId: '000001.SZ',
        query: '平安银行',
        newsId: 'news-1',
        tradeDate: '2026-06-08'
      })
    );
    expect(onOpenResearchReports).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceWorkspace: 'researchReports',
        assetId: '000001.SZ',
        query: '平安银行',
        reportId: 'report-1',
        eventKey: 'report-1:000001.SZ',
        tradeDate: '2026-06-08'
      })
    );
    expect(onOpenMarketMonitor).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceWorkspace: 'market',
        assetId: '000001.SZ',
        query: '平安银行',
        eventKey: 'limit-up:000001.SZ',
        monitorTab: 'limit_up',
        tradeDate: '2026-06-08'
      })
    );
  });

  it('renders queue-level warnings', async () => {
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(makeQueue({ warnings: ['partial digest failure'] }));

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('partial digest failure')).toBeInTheDocument();
  });

  it('shows local error with retry', async () => {
    apiMocks.fetchReviewQueue
      .mockRejectedValueOnce(new Error('queue offline'))
      .mockResolvedValueOnce(makeQueue());

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('queue offline')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '重新加载复盘队列' }));

    await waitFor(() => expect(apiMocks.fetchReviewQueue).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('平安银行')).toBeInTheDocument();
  });
});
