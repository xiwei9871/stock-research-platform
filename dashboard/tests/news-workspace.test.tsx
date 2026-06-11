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
  items: [makeNewsItem()]
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
  it('opens a stock when a news item has a deterministic candidate', async () => {
    const onOpenAsset = vi.fn();
    render(<NewsWorkspace onOpenAsset={onOpenAsset} />);

    fireEvent.click(await screen.findByRole('button', { name: 'Open 600000.SH' }));

    expect(onOpenAsset).toHaveBeenCalledWith('600000.SH');
  });
});
