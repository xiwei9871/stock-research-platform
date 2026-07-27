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
    requested_trade_date: '2026-06-08',
    platform_market_date: '2026-06-08',
    data_status: 'ready',
    score_version: 'strategy_topn',
    review_mode: 'strategy_topn',
    generated_at: '2026-06-08T16:00:00Z',
    warnings: [],
    groups: [
      {
        bucket: 'strategy:mid_trend',
        label: 'Mid Trend Combo',
        count: 1,
        strategy_id: 'mid_trend',
        requested_trade_date: '2026-06-08',
        data_trade_date: '2026-06-08',
        freshness_status: 'current',
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
      {
        bucket: 'strategy:tech_bottleneck',
        label: 'Tech Bottleneck Combo',
        count: 0,
        strategy_id: 'tech_bottleneck',
        requested_trade_date: '2026-06-08',
        data_trade_date: '',
        freshness_status: 'missing',
        items: []
      }
    ],
    ...overrides
  };
}

function groupFreshnessName(label: string, dataDate: string, status: string, count: number) {
  return `${label}：数据日期 ${dataDate}，${status}，${count} 只`;
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
    expect(screen.getByText('按策略正式复盘范围')).toBeInTheDocument();
    expect(screen.getByText('平台市场日期')).toBeInTheDocument();
    expect(screen.getByText('复盘队列与平台市场日期一致。')).toBeInTheDocument();
    const currentFreshness = screen.getByLabelText(
      groupFreshnessName('Mid Trend Combo', '2026-06-08', '数据已同步', 1)
    );
    expect(within(currentFreshness).getByText('数据日期 2026-06-08')).toBeInTheDocument();
    expect(within(currentFreshness).getByText('数据已同步')).toBeInTheDocument();
    expect(currentFreshness).toHaveClass('success');
    expect(currentFreshness).not.toHaveClass('warning');
    const missingFreshness = screen.getByLabelText(
      groupFreshnessName('Tech Bottleneck Combo', '暂无', '数据缺失', 0)
    );
    expect(within(missingFreshness).getByText('数据日期 暂无')).toBeInTheDocument();
    expect(within(missingFreshness).getByText('数据缺失')).toBeInTheDocument();
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

  it('uses the requested queue date for platform freshness and group metadata for strategy freshness', async () => {
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
        requested_trade_date: '2026-06-05',
        platform_market_date: '2026-06-15',
        groups: [
          {
            ...makeQueue().groups[0],
            requested_trade_date: '2026-06-05',
            data_trade_date: '2026-06-08',
            freshness_status: 'current'
          },
          {
            bucket: 'strategy:tech_bottleneck',
            label: 'Tech Bottleneck Combo',
            count: 1,
            strategy_id: 'tech_bottleneck',
            requested_trade_date: '2026-06-05',
            data_trade_date: '2026-06-01',
            freshness_status: 'stale',
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
    const currentFreshness = screen.getByLabelText(
      groupFreshnessName('Mid Trend Combo', '2026-06-08', '数据已同步', 1)
    );
    expect(within(currentFreshness).getByText('数据日期 2026-06-08')).toBeInTheDocument();
    expect(within(currentFreshness).getByText('数据已同步')).toBeInTheDocument();
    const staleFreshness = screen.getByLabelText(
      groupFreshnessName('Tech Bottleneck Combo', '2026-06-01', '数据过期', 1)
    );
    expect(within(staleFreshness).getByText('数据日期 2026-06-01')).toBeInTheDocument();
    expect(within(staleFreshness).getByText('数据过期')).toBeInTheDocument();
  });

  it('warns when the requested review date is later than the platform market date', async () => {
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(
      makeQueue({
        trade_date: '2026-07-25',
        requested_trade_date: '2026-07-25',
        platform_market_date: '2026-07-24'
      })
    );

    render(<ReviewQueueWorkspace />);

    expect(
      await screen.findByText('复盘日期晚于平台市场日期 1 个自然日，请确认日期或等待市场数据。')
    ).toBeInTheDocument();
    expect(screen.queryByText('复盘队列与平台市场日期一致。')).not.toBeInTheDocument();
    expect(screen.queryByText('已同步')).not.toBeInTheDocument();
  });

  it('switches groups and shows an empty group state', async () => {
    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('Recent accepted news')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Tech Bottleneck Combo 0' }));

    expect(screen.getByText('2026-06-08 暂无 Tech Bottleneck Combo 复盘标的。')).toBeInTheDocument();
    expect(screen.queryByText('Recent accepted news')).not.toBeInTheDocument();
  });

  it('keeps supplied missing metadata authoritative over legacy item dates', async () => {
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(
      makeQueue({
        groups: [
          makeQueue().groups[0],
          {
            ...makeQueue().groups[1],
            data_trade_date: '',
            freshness_status: 'missing',
            items: [
              {
                ...makeQueue().groups[0].items[0],
                queue_id: 'legacy-stale-item',
                latest_trade_date: '2026-06-01'
              }
            ]
          }
        ]
      })
    );

    render(<ReviewQueueWorkspace />);

    const missingFreshness = await screen.findByLabelText(
      groupFreshnessName('Tech Bottleneck Combo', '暂无', '数据缺失', 1)
    );
    expect(within(missingFreshness).getByText('数据日期 暂无')).toBeInTheDocument();
    expect(within(missingFreshness).getByText('数据缺失')).toBeInTheDocument();
  });

  it('replays the review queue for a selected trade date', async () => {
    const replayQueue = makeQueue({
      trade_date: '2026-07-24',
      requested_trade_date: '2026-07-24',
      groups: [
        {
          ...makeQueue().groups[0],
          requested_trade_date: '2026-07-24',
          data_trade_date: '2026-06-01',
          freshness_status: 'stale',
          count: 2,
          items: [
            makeQueue().groups[0].items[0],
            {
              ...makeQueue().groups[0].items[0],
              queue_id: '2026-07-24:strategy_topn:000002.SZ',
              asset_id: '000002.SZ',
              display_name: '万科A',
              rank: 2,
              topn_rank: 2
            }
          ]
        },
        {
          ...makeQueue().groups[1],
          requested_trade_date: '2026-07-24'
        }
      ]
    });
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(makeQueue()).mockResolvedValueOnce(replayQueue);

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('Recent accepted news')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('选择复盘日期'), { target: { value: '2026-07-24' } });
    fireEvent.click(screen.getByRole('button', { name: '回放该日复盘队列' }));

    await waitFor(() =>
      expect(apiMocks.fetchReviewQueue).toHaveBeenLastCalledWith({
        tradeDate: '2026-07-24',
        limit: 10,
        lookbackDays: 90
      })
    );
    expect(screen.getByLabelText('选择复盘日期')).toHaveValue('2026-07-24');
    const staleFreshness = screen.getByLabelText(
      groupFreshnessName('Mid Trend Combo', '2026-06-01', '数据过期', 2)
    );
    expect(within(staleFreshness).getByText('数据日期 2026-06-01')).toBeInTheDocument();
    expect(within(staleFreshness).getByText('数据过期')).toBeInTheDocument();
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
