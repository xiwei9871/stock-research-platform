import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WatchlistWorkspace } from '../src/components/WatchlistWorkspace';
import type { WatchlistSignalRow } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchWatchlistSignals: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

const rows: WatchlistSignalRow[] = [
  {
    watchlist_id: 'default',
    trade_date: '2026-06-08',
    asset_id: '000001.SZ',
    stock_code: '000001',
    stock_name: '平安银行',
    priority: 8,
    signal_score: 82.4,
    primary_signal: 'candidate',
    signal_tags: ['breakout', 'volume'],
    risk_tags: ['earnings'],
    must_watch: true,
    reason_json: {
      next_action: 'review close above 10d high',
      reason: 'score breakout'
    }
  },
  {
    watchlist_id: 'default',
    trade_date: '2026-06-08',
    asset_id: '600000.SH',
    stock_code: '600000',
    stock_name: '浦发银行',
    priority: 3,
    signal_score: 52,
    primary_signal: 'observe',
    signal_tags: ['base'],
    risk_tags: ['liquidity'],
    must_watch: false,
    reason_json: {}
  }
];

beforeEach(() => {
  vi.clearAllMocks();
  apiMocks.fetchWatchlistSignals.mockResolvedValue(rows);
});

afterEach(() => {
  cleanup();
});

describe('WatchlistWorkspace', () => {
  it('renders the EOD queue and opens a selected stock', async () => {
    const onOpenAsset = vi.fn();
    render(<WatchlistWorkspace onOpenAsset={onOpenAsset} />);

    expect(await screen.findByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('review close above 10d high')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Open 000001.SZ' }));

    expect(onOpenAsset).toHaveBeenCalledWith('000001.SZ');
    expect(apiMocks.fetchWatchlistSignals).toHaveBeenCalledWith('default', '2026-06-18');
  });

  it('uses the supplied latest trade date instead of the legacy hard-coded date', async () => {
    render(<WatchlistWorkspace defaultTradeDate="2026-06-18" />);

    expect(await screen.findByText('平安银行')).toBeInTheDocument();
    expect(screen.getByLabelText('trade date')).toHaveValue('2026-06-18');
    expect(apiMocks.fetchWatchlistSignals).toHaveBeenCalledWith('default', '2026-06-18');
  });

  it('filters by status and minimum priority', async () => {
    render(<WatchlistWorkspace />);

    expect(await screen.findByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('浦发银行')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('watchlist status'), { target: { value: 'candidate' } });
    fireEvent.change(screen.getByLabelText('minimum priority'), { target: { value: '5' } });

    await waitFor(() => {
      expect(screen.getByText('平安银行')).toBeInTheDocument();
      expect(screen.queryByText('浦发银行')).not.toBeInTheDocument();
    });
  });

  it('explains an empty manual observation queue', async () => {
    apiMocks.fetchWatchlistSignals.mockResolvedValueOnce([]);

    render(<WatchlistWorkspace />);

    expect(await screen.findByText('当前观察池暂无记录。')).toBeInTheDocument();
    expect(screen.getByText('当前日期暂无观察记录。你可以在个股工作台点击“观察”创建人工观察项；如果想看策略候选池，请切换到复盘队列。')).toBeInTheDocument();
    expect(screen.getByText('当前查询：default / 2026-06-18')).toBeInTheDocument();
  });
});
