import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ReviewQueueWorkspace } from '../src/components/ReviewQueueWorkspace';
import type { ReviewQueueResponse } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchReviewQueue: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeQueue(overrides: Partial<ReviewQueueResponse> = {}): ReviewQueueResponse {
  return {
    trade_date: '2026-06-08',
    score_version: 'manual_v1',
    generated_at: '2026-06-08T16:00:00Z',
    warnings: [],
    groups: [
      {
        bucket: 'strong',
        label: 'High Conviction',
        count: 1,
        items: [
          {
            queue_id: '2026-06-08:manual_v1:000001.SZ',
            asset_id: '000001.SZ',
            canonical_asset_id: '000001.SZ',
            display_name: '平安银行',
            rank: 1,
            score: 88.2,
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
      { bucket: 'mixed', label: 'Mixed Evidence', count: 0, items: [] },
      { bucket: 'risk_heavy', label: 'Risk Flags', count: 0, items: [] },
      { bucket: 'thin', label: 'Thin / Missing Sources', count: 0, items: [] }
    ],
    ...overrides
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchReviewQueue.mockResolvedValue(makeQueue());
});

afterEach(() => {
  cleanup();
});

describe('ReviewQueueWorkspace', () => {
  it('loads grouped queue items and renders the selected evidence preview', async () => {
    apiMocks.fetchReviewQueue.mockResolvedValueOnce(makeQueue());

    render(<ReviewQueueWorkspace />);

    expect(await screen.findByRole('heading', { name: 'Review Queue' })).toBeInTheDocument();
    expect(apiMocks.fetchReviewQueue).toHaveBeenCalledWith({ limit: 20, lookbackDays: 90 });
    expect(screen.getByRole('button', { name: 'High Conviction 1' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Score Version')).toBeInTheDocument();
    expect(screen.getByText('manual_v1')).toBeInTheDocument();
    const sourceFilters = screen.getByLabelText('Source Filters');
    expect(within(sourceFilters).getByText('strategy')).toBeInTheDocument();
    expect(within(sourceFilters).getByText('research')).toBeInTheDocument();
    const queueRow = screen.getByRole('button', { name: /平安银行/ });
    expect(queueRow).toHaveAttribute('aria-pressed', 'true');
    expect(queueRow).toHaveStyle({
      gridTemplateColumns: '48px minmax(180px, 1.4fr) 92px 96px minmax(120px, 0.8fr) 96px 104px'
    });
    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(within(queueRow).getByText('Strong evidence')).toBeInTheDocument();
    expect(within(queueRow).getByText('strategy')).toBeInTheDocument();
    expect(within(queueRow).getByText('research')).toBeInTheDocument();
    expect(within(queueRow).getByText('1 risk')).toBeInTheDocument();
    expect(within(queueRow).getByText('1 warning')).toBeInTheDocument();

    const preview = screen.getByRole('region', { name: 'Selected Evidence' });
    const sourceChips = within(preview).getByLabelText('Evidence sources');
    expect(within(preview).getByText('Strong evidence')).toBeInTheDocument();
    expect(within(preview).getByText('Recent accepted news')).toBeInTheDocument();
    expect(within(sourceChips).getByText('strategy')).toBeInTheDocument();
    expect(within(sourceChips).getByText('research')).toBeInTheDocument();
  });

  it('switches groups and shows an empty group state', async () => {
    render(<ReviewQueueWorkspace />);

    expect(await screen.findByText('Recent accepted news')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Mixed Evidence 0' }));

    expect(screen.getByText('No mixed evidence items for 2026-06-08.')).toBeInTheDocument();
    expect(screen.queryByText('Recent accepted news')).not.toBeInTheDocument();
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

    const preview = await screen.findByRole('region', { name: 'Selected Evidence' });
    fireEvent.click(within(preview).getByRole('button', { name: 'Review Stock' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open News' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open Research' }));
    fireEvent.click(within(preview).getByRole('button', { name: 'Open Market' }));

    expect(onOpenStock).toHaveBeenCalledWith(
      '000001.SZ',
      expect.objectContaining({ sourceWorkspace: 'search', assetId: '000001.SZ', query: '平安银行' })
    );
    expect(onOpenNews).toHaveBeenCalledWith(
      expect.objectContaining({ sourceWorkspace: 'news', assetId: '000001.SZ', query: '平安银行', newsId: 'news-1' })
    );
    expect(onOpenResearchReports).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceWorkspace: 'researchReports',
        assetId: '000001.SZ',
        query: '平安银行',
        reportId: 'report-1',
        eventKey: 'report-1:000001.SZ'
      })
    );
    expect(onOpenMarketMonitor).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceWorkspace: 'market',
        assetId: '000001.SZ',
        query: '平安银行',
        eventKey: 'limit-up:000001.SZ',
        monitorTab: 'limit_up'
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
    fireEvent.click(screen.getByRole('button', { name: 'Retry Review Queue' }));

    await waitFor(() => expect(apiMocks.fetchReviewQueue).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('平安银行')).toBeInTheDocument();
  });
});
