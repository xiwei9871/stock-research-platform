import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MyWatchlistView } from '../src/views/MyWatchlistView';
import type { UserWatchlistItem } from '../src/api/types';

type ImportMetaWithGlob = ImportMeta & {
  glob: (
    pattern: string,
    options: { query: string; import: string; eager: boolean }
  ) => Record<string, string>;
};

const watchlistViewSource = (import.meta as ImportMetaWithGlob).glob('../src/views/MyWatchlistView.tsx', {
  query: '?raw',
  import: 'default',
  eager: true
})['../src/views/MyWatchlistView.tsx'] as string;

const apiMocks = vi.hoisted(() => ({
  fetchMyWatchlist: vi.fn(),
  createMyWatchlistItem: vi.fn(),
  removeMyWatchlistItem: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeItem(assetId: string, overrides: Partial<UserWatchlistItem> = {}): UserWatchlistItem {
  return {
    id: assetId === '000001.SZ' ? 1 : 2,
    user_id: 7,
    asset_id: assetId,
    trade_date_added: '2026-06-20',
    source: 'manual',
    notes: '',
    created_at: '2026-06-20T00:00:00Z',
    updated_at: '2026-06-20T00:00:00Z',
    ...overrides
  };
}

describe('MyWatchlistView', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('imports watchlist client helpers directly', () => {
    expect(watchlistViewSource).toContain("from '../api/client'");
    expect(watchlistViewSource).toContain('fetchMyWatchlist');
    expect(watchlistViewSource).toContain('createMyWatchlistItem');
    expect(watchlistViewSource).toContain('removeMyWatchlistItem');
    expect(watchlistViewSource).not.toContain('import * as client');
    expect(watchlistViewSource).not.toContain('Record<string, unknown>');
  });

  it('adds a watchlist item and refreshes the list', async () => {
    apiMocks.fetchMyWatchlist
      .mockResolvedValueOnce([makeItem('000001.SZ')])
      .mockResolvedValueOnce([makeItem('000001.SZ'), makeItem('000002.SZ')]);
    apiMocks.createMyWatchlistItem.mockResolvedValue(makeItem('000002.SZ'));

    render(<MyWatchlistView />);

    expect(await screen.findByText('000001.SZ')).toBeVisible();

    fireEvent.change(screen.getByLabelText('资产代码'), { target: { value: '000002.SZ' } });
    fireEvent.click(screen.getByRole('button', { name: '添加到观察池' }));

    await waitFor(() => {
      expect(apiMocks.createMyWatchlistItem).toHaveBeenCalledWith({ asset_id: '000002.SZ' });
    });
    await waitFor(() => {
      expect(apiMocks.fetchMyWatchlist).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('000002.SZ')).toBeVisible();
  });

  it('removes a watchlist item and refreshes the list', async () => {
    apiMocks.fetchMyWatchlist
      .mockResolvedValueOnce([makeItem('000001.SZ'), makeItem('000002.SZ')])
      .mockResolvedValueOnce([makeItem('000002.SZ')]);
    apiMocks.removeMyWatchlistItem.mockResolvedValue({ ok: true });

    render(<MyWatchlistView />);

    const item = await screen.findByTestId('watchlist-item-000001.SZ');
    fireEvent.click(within(item).getByRole('button', { name: '移除' }));

    await waitFor(() => {
      expect(apiMocks.removeMyWatchlistItem).toHaveBeenCalledWith('000001.SZ');
    });
    await waitFor(() => {
      expect(apiMocks.fetchMyWatchlist).toHaveBeenCalledTimes(2);
    });
    expect(screen.queryByText('000001.SZ')).not.toBeInTheDocument();
  });
});
