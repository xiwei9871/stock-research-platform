import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getNewsAssetCandidate, NewsWorkspace } from '../src/components/NewsWorkspace';
import type { PublicNewsItem, PublicNewsResponse } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchPublicNews: vi.fn(),
  refreshPublicNews: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeNewsItem(overrides: Partial<PublicNewsItem> = {}): PublicNewsItem {
  return {
    news_id: 'n1',
    source: 'sina_finance',
    source_channel: 'company',
    category: 'company',
    title: '600000 浦发银行公告',
    summary: '公司新闻',
    url: 'https://example.com/news/1',
    published_at: '2026-06-08T09:30:00',
    collected_at: '2026-06-08T09:31:00',
    raw_id: 'n1',
    raw_payload: {},
    status: 'active',
    ...overrides
  };
}

const newsPayload: PublicNewsResponse = {
  warnings: [],
  items: [
    makeNewsItem({
      stocks: [{ asset_id: 'CN:SH:600000', ts_code: '600000.SH', stock_name: '浦发银行' }]
    })
  ]
};

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchPublicNews.mockResolvedValue(newsPayload);
  apiMocks.refreshPublicNews.mockResolvedValue({ stored: 1, items_received: 1, counts_by_category: {}, warnings: [] });
});

afterEach(() => {
  cleanup();
});

describe('getNewsAssetCandidate', () => {
  it('normalizes a bare six digit title candidate', () => {
    expect(getNewsAssetCandidate(makeNewsItem({ title: '600000 浦发银行公告' }))).toBe('600000.SH');
  });
});

describe('NewsWorkspace', () => {
  it('opens a stock when a news item has an API stock mention', async () => {
    const onOpenAsset = vi.fn();
    render(<NewsWorkspace onOpenAsset={onOpenAsset} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open 浦发银行 in Stock Workspace' }));

    expect(onOpenAsset).toHaveBeenCalledWith('CN:SH:600000');
  });

  it('renders db freshness and stock mention chips', async () => {
    const openAsset = vi.fn();
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [
        makeNewsItem({
          title: '贵州茅台经营快讯',
          category: 'company',
          stocks: [{ asset_id: 'CN:SH:600519', ts_code: '600519.SH', stock_name: '贵州茅台' }]
        })
      ],
      total: 1,
      limit: 200,
      offset: 0,
      summary: {
        total_news: 1,
        latest_collected_at: '2026-06-12T01:30:00+00:00',
        source_count: 1,
        source_counts: [{ name: 'sina_finance', rows: 1 }],
        category_counts: [{ name: 'company', rows: 1 }]
      },
      warnings: []
    });

    render(<NewsWorkspace onOpenAsset={openAsset} />);

    expect(await screen.findByText('贵州茅台经营快讯')).toBeInTheDocument();
    expect(screen.getByText(/DB collected/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open 贵州茅台 in Stock Workspace' }));
    expect(openAsset).toHaveBeenCalledWith('CN:SH:600519');
  });

  it('shows fallback warnings without clearing rows', async () => {
    apiMocks.fetchPublicNews.mockResolvedValueOnce({
      items: [makeNewsItem({ title: '缓存新闻' })],
      summary: { total_news: 1, latest_collected_at: '2026-06-12T01:30:00+00:00' },
      warnings: ['fallback json cache used: db offline']
    });

    render(<NewsWorkspace />);

    expect(await screen.findByText('缓存新闻')).toBeInTheDocument();
    expect(screen.getByText('fallback json cache used: db offline')).toBeInTheDocument();
  });
});
