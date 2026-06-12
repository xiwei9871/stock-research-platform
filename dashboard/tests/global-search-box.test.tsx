import '@testing-library/jest-dom/vitest';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GlobalSearchBox } from '../src/components/GlobalSearchBox';
import type { GlobalSearchResponse, GlobalSearchResult } from '../src/api/types';

const apiMocks = vi.hoisted(() => ({
  fetchGlobalSearch: vi.fn()
}));

vi.mock('../src/api/client', () => apiMocks);

function makeResult(overrides: Partial<GlobalSearchResult> = {}): GlobalSearchResult {
  return {
    type: 'asset',
    id: 'CN:SH:600519',
    title: '贵州茅台',
    subtitle: '600519.SH',
    metadata: {},
    target: { workspace: 'stock', asset_id: 'CN:SH:600519' },
    ...overrides
  };
}

function makePayload(overrides: Partial<GlobalSearchResponse> = {}): GlobalSearchResponse {
  return {
    query: '茅台',
    groups: [
      {
        key: 'assets',
        label: 'Stocks',
        items: [makeResult()]
      }
    ],
    warnings: [],
    ...overrides
  };
}

async function searchFor(query: string) {
  fireEvent.change(screen.getByLabelText('Global search'), { target: { value: query } });
  await act(async () => {
    vi.advanceTimersByTime(250);
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.clearAllMocks();
  apiMocks.fetchGlobalSearch.mockResolvedValue(makePayload());
});

afterEach(() => {
  vi.useRealTimers();
  cleanup();
});

describe('GlobalSearchBox', () => {
  it('renders grouped search results and opens a clicked result', async () => {
    const selected = makeResult({ id: 'news-1', type: 'news', title: '茅台新闻', subtitle: '公告摘要' });
    apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
      makePayload({
        groups: [
          { key: 'assets', label: 'Stocks', items: [makeResult()] },
          { key: 'news', label: 'News', items: [selected] }
        ],
        warnings: ['partial news index']
      })
    );
    const onOpenResult = vi.fn();

    render(<GlobalSearchBox onOpenResult={onOpenResult} />);
    await searchFor('  茅台  ');

    expect(apiMocks.fetchGlobalSearch).toHaveBeenCalledWith('茅台', 5);
    expect(await screen.findByRole('heading', { name: 'Stocks' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'News' })).toBeInTheDocument();
    expect(screen.getByText('partial news index')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('option', { name: /茅台新闻 公告摘要/ }));

    expect(onOpenResult).toHaveBeenCalledWith(selected);
    expect(screen.getByLabelText('Global search')).toHaveValue('');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('does not call the API for a one-character query', async () => {
    render(<GlobalSearchBox onOpenResult={vi.fn()} />);

    await searchFor('茅');

    expect(apiMocks.fetchGlobalSearch).not.toHaveBeenCalled();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('does not let a stale first response replace newer results', async () => {
    let resolveFirst: (payload: GlobalSearchResponse) => void = () => undefined;
    apiMocks.fetchGlobalSearch
      .mockReturnValueOnce(new Promise<GlobalSearchResponse>((resolve) => {
        resolveFirst = resolve;
      }))
      .mockResolvedValueOnce(
        makePayload({
          query: '浦发',
          groups: [{ key: 'assets', label: 'Stocks', items: [makeResult({ title: '浦发银行' })] }]
        })
      );

    render(<GlobalSearchBox onOpenResult={vi.fn()} />);

    await searchFor('茅台');
    await searchFor('浦发');

    expect(await screen.findByText('浦发银行')).toBeInTheDocument();

    await act(async () => {
      resolveFirst(
        makePayload({
          query: '茅台',
          groups: [{ key: 'assets', label: 'Stocks', items: [makeResult({ title: '贵州茅台' })] }]
        })
      );
    });

    expect(screen.getByText('浦发银行')).toBeInTheDocument();
    expect(screen.queryByText('贵州茅台')).not.toBeInTheDocument();
  });

  it('opens the highlighted result with ArrowDown and Enter', async () => {
    const first = makeResult({ id: 'CN:SH:600519', title: '贵州茅台' });
    const second = makeResult({ id: 'CN:SZ:000001', title: '平安银行', subtitle: '000001.SZ' });
    const onOpenResult = vi.fn();
    apiMocks.fetchGlobalSearch.mockResolvedValueOnce(
      makePayload({
        groups: [{ key: 'assets', label: 'Stocks', items: [first, second] }]
      })
    );

    render(<GlobalSearchBox onOpenResult={onOpenResult} />);
    await searchFor('银行');

    const input = screen.getByLabelText('Global search');
    await screen.findByText('贵州茅台');

    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(onOpenResult).toHaveBeenCalledWith(second);
    expect(within(screen.queryByRole('listbox') ?? document.body).queryByText('平安银行')).not.toBeInTheDocument();
  });
});
