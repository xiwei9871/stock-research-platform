import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { StockMarketContextHeatmapPayload } from '../src/api/types';
import { StockMarketContextHeatmap } from '../src/components/stock-workspace/StockMarketContextHeatmap';

class TestResizeObserver {
  observe = vi.fn();
  disconnect = vi.fn();
}

const canvasContext = {
  clearRect: vi.fn(),
  fillRect: vi.fn(),
  strokeRect: vi.fn(),
  fillText: vi.fn(),
  measureText: vi.fn((text: string) => ({ width: text.length * 8 })),
  save: vi.fn(),
  restore: vi.fn(),
  scale: vi.fn()
};

function makePayload(overrides: Partial<StockMarketContextHeatmapPayload> = {}): StockMarketContextHeatmapPayload {
  return {
    asset_id: '000001.SZ',
    canonical_asset_id: 'CN:SZ:000001',
    trade_date: '2026-07-07',
    industry: { industry_id: 'bank', industry_name: '银行', industry_system: 'csrc' },
    selected: {
      asset_id: 'CN:SZ:000001',
      symbol: '000001',
      name: '平安银行',
      price: 12.5,
      change_pct: 0.02,
      amount: 3000000000,
      amount_rank: 1,
      change_rank: 1,
      amount_percentile: 1,
      change_percentile: 1
    },
    summary: {
      peer_count: 2,
      up_count: 1,
      flat_count: 0,
      down_count: 1,
      total_amount: 4000000000,
      selected_in_peer_set: true
    },
    peers: [
      {
        asset_id: 'CN:SZ:000001',
        symbol: '000001',
        name: '平安银行',
        price: 12.5,
        change_pct: 0.02,
        amount: 3000000000,
        value: 3000000000,
        is_selected: true
      },
      {
        asset_id: 'CN:SH:600000',
        symbol: '600000',
        name: '浦发银行',
        price: 9,
        change_pct: -0.01,
        amount: 1000000000,
        value: 1000000000,
        is_selected: false
      }
    ],
    data_status: 'completed',
    warnings: [],
    ...overrides
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.ResizeObserver = TestResizeObserver as unknown as typeof ResizeObserver;
  Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
    configurable: true,
    value: vi.fn((contextId: string) => (contextId === '2d' ? canvasContext : null)) as unknown as HTMLCanvasElement['getContext']
  });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 460 });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 240 });
});

afterEach(() => {
  cleanup();
});

describe('StockMarketContextHeatmap', () => {
  it('renders loading and empty states', () => {
    const { rerender } = render(<StockMarketContextHeatmap payload={null} loading error={null} onSelectStock={vi.fn()} />);
    expect(screen.getByText('同业热力加载中')).toBeInTheDocument();

    rerender(
      <StockMarketContextHeatmap
        payload={makePayload({
          selected: null,
          peers: [],
          data_status: 'missing',
          summary: {
            peer_count: 0,
            up_count: 0,
            flat_count: 0,
            down_count: 0,
            total_amount: 0,
            selected_in_peer_set: false
          }
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getByText('暂无同业市场定位数据')).toBeInTheDocument();
  });

  it('renders selected stock summary and canvas', () => {
    render(<StockMarketContextHeatmap payload={makePayload()} loading={false} error={null} onSelectStock={vi.fn()} />);

    expect(screen.getByRole('img', { name: '同业市场定位热力图' })).toBeInTheDocument();
    expect(screen.getByText('银行')).toBeInTheDocument();
    expect(screen.getByText('同业 2')).toBeInTheDocument();
    expect(screen.getByText('涨跌排名 #1')).toBeInTheDocument();
    expect(screen.getByText('成交额排名 #1')).toBeInTheDocument();
    expect(screen.getAllByText('平安银行').length).toBeGreaterThan(0);
    expect(canvasContext.strokeRect).toHaveBeenCalled();
  });

  it('calls onSelectStock when a peer is selected', () => {
    const onSelectStock = vi.fn();
    render(<StockMarketContextHeatmap payload={makePayload()} loading={false} error={null} onSelectStock={onSelectStock} />);

    fireEvent.click(screen.getByRole('button', { name: /打开同业 浦发银行/ }));

    expect(onSelectStock).toHaveBeenCalledWith('CN:SH:600000');
  });

  it('dedupes repeated peer asset ids without duplicate key warnings', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    render(
      <StockMarketContextHeatmap
        payload={makePayload({
          peers: [
            {
              asset_id: 'CN:SZ:000001',
              symbol: '000001',
              name: '平安银行',
              price: 12.5,
              change_pct: 0.02,
              amount: 3000000000,
              value: 3000000000,
              is_selected: true
            },
            {
              asset_id: 'CN:SZ:000001',
              symbol: '000001',
              name: '平安银行',
              price: 12.5,
              change_pct: 0.02,
              amount: 3000000000,
              value: 3000000000,
              is_selected: false
            },
            {
              asset_id: 'CN:SH:600000',
              symbol: '600000',
              name: '浦发银行',
              price: 9,
              change_pct: -0.01,
              amount: 1000000000,
              value: 1000000000,
              is_selected: false
            }
          ]
        })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getAllByRole('button', { name: /打开同业/ })).toHaveLength(2);
    const messages = consoleError.mock.calls.map((call) => call.join(' ')).join('\n');
    expect(messages).not.toContain('Encountered two children with the same key');
    consoleError.mockRestore();
  });

  it('renders local error state', () => {
    render(<StockMarketContextHeatmap payload={null} loading={false} error="GET failed" onSelectStock={vi.fn()} />);
    expect(screen.getByText('GET failed')).toBeInTheDocument();
  });
});
