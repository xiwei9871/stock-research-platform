import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MyReviewsView } from '../src/views/MyReviewsView';
import type { UserReviewSession } from '../src/api/types';

type ImportMetaWithGlob = ImportMeta & {
  glob: (
    pattern: string,
    options: { query: string; import: string; eager: boolean }
  ) => Record<string, string>;
};

const reviewsViewSource = (import.meta as ImportMetaWithGlob).glob('../src/views/MyReviewsView.tsx', {
  query: '?raw',
  import: 'default',
  eager: true
})['../src/views/MyReviewsView.tsx'] as string;

const apiMocks = vi.hoisted(() => ({
  fetchMyReviewSessions: vi.fn(),
  createMyReviewSession: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeSession(id: number, tradeDate: string, title = '盘后复盘'): UserReviewSession {
  return {
    id,
    user_id: 9,
    trade_date: tradeDate,
    title,
    summary: '',
    market_view: '',
    position_view: '',
    next_action: '',
    created_at: '2026-06-20T00:00:00Z',
    updated_at: '2026-06-20T00:00:00Z',
    items: []
  };
}

describe('MyReviewsView', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('imports review client helpers directly', () => {
    expect(reviewsViewSource).toContain("from '../api/client'");
    expect(reviewsViewSource).toContain('fetchMyReviewSessions');
    expect(reviewsViewSource).toContain('createMyReviewSession');
    expect(reviewsViewSource).not.toContain('import * as client');
    expect(reviewsViewSource).not.toContain('Record<string, unknown>');
  });

  it('creates a review session using the selected trade date and refreshes the list', async () => {
    apiMocks.fetchMyReviewSessions
      .mockResolvedValueOnce([makeSession(1, '2026-06-19', '复盘记录')])
      .mockResolvedValueOnce([makeSession(2, '2026-06-20'), makeSession(1, '2026-06-19', '复盘记录')]);
    apiMocks.createMyReviewSession.mockResolvedValue(makeSession(2, '2026-06-20'));

    render(<MyReviewsView />);

    expect(await screen.findByRole('heading', { name: '我的复盘' })).toBeVisible();

    fireEvent.change(screen.getByLabelText('交易日'), { target: { value: '2026-06-20' } });
    fireEvent.click(screen.getByRole('button', { name: '新建我的复盘' }));

    await waitFor(() => {
      expect(apiMocks.createMyReviewSession).toHaveBeenCalledWith({
        trade_date: '2026-06-20',
        title: '盘后复盘'
      });
    });
    await waitFor(() => {
      expect(apiMocks.fetchMyReviewSessions).toHaveBeenCalledTimes(2);
    });
    expect(await screen.findByText('2026-06-20')).toBeVisible();
  });
});
