import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockHeatmapPanel } from '../src/components/market-monitor/StockHeatmapPanel';
import type { StockHeatmapPayload } from '../src/api/types';

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
  scale: vi.fn(),
  beginPath: vi.fn(),
  rect: vi.fn(),
  clip: vi.fn()
};

function makePayload(overrides: Partial<StockHeatmapPayload> = {}): StockHeatmapPayload {
  return {
    trade_date: '2026-07-07',
    market: 'all',
    period: '1d',
    group: 'industry',
    size_by: 'amount',
    updated_at: '2026-07-07T15:00:00+08:00',
    source: 'market_daily_bar',
    data_status: 'completed',
    warnings: [],
    summary: {
      stock_count: 2,
      up_count: 1,
      flat_count: 0,
      down_count: 1,
      total_amount: 4000000000
    },
    groups: [
      {
        group_id: 'BK_BANK',
        group_name: '银行',
        value: 4000000000,
        change_pct: 0.0125,
        stock_count: 2,
        children: [
          {
            asset_id: 'CN:SZ:000001',
            symbol: '000001',
            name: '平安银行',
            price: 12.5,
            change_pct: 0.02,
            amount: 3000000000,
            value: 3000000000,
            group_id: 'BK_BANK',
            group_name: '银行'
          },
          {
            asset_id: 'CN:SH:600000',
            symbol: '600000',
            name: '浦发银行',
            price: 9,
            change_pct: -0.01,
            amount: 1000000000,
            value: 1000000000,
            group_id: 'BK_BANK',
            group_name: '银行'
          }
        ]
      }
    ],
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
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true, value: 720 });
  Object.defineProperty(HTMLElement.prototype, 'clientHeight', { configurable: true, value: 420 });
});

afterEach(() => {
  cleanup();
});

describe('StockHeatmapPanel', () => {
  it('renders loading and empty states', () => {
    const { rerender } = render(<StockHeatmapPanel payload={null} loading error={null} onSelectStock={vi.fn()} />);

    expect(screen.getByText('个股云图加载中')).toBeInTheDocument();

    rerender(
      <StockHeatmapPanel
        payload={makePayload({ data_status: 'missing', summary: { stock_count: 0, up_count: 0, flat_count: 0, down_count: 0, total_amount: 0 }, groups: [] })}
        loading={false}
        error={null}
        onSelectStock={vi.fn()}
      />
    );

    expect(screen.getByText('暂无个股云图数据')).toBeInTheDocument();
  });

  it('renders summary, canvas, and stock list for loaded payloads', () => {
    render(<StockHeatmapPanel payload={makePayload()} loading={false} error={null} onSelectStock={vi.fn()} />);

    expect(screen.getByRole('img', { name: '全市场个股云图' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '热区个股 Top N' })).toBeInTheDocument();
    expect(screen.getByText('个股 2')).toBeInTheDocument();
    expect(screen.getByText('上涨 1')).toBeInTheDocument();
    expect(screen.getByText('平安银行')).toBeInTheDocument();
    expect(screen.getByText('浦发银行')).toBeInTheDocument();
    expect(screen.getByText('30.00亿')).toBeInTheDocument();
    expect(canvasContext.fillRect).toHaveBeenCalled();
  });

  it('renders an asset repeated across heatmap groups without duplicate React keys', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const payload = makePayload();
    const repeated = payload.groups[0].children[0];
    payload.groups = [
      payload.groups[0],
      {
        ...payload.groups[0],
        group_id: 'BK_REPEAT',
        group_name: '重复分组',
        children: [{ ...repeated, group_id: 'BK_REPEAT', group_name: '重复分组' }]
      }
    ];

    render(<StockHeatmapPanel payload={payload} loading={false} error={null} onSelectStock={vi.fn()} />);

    expect(errorSpy.mock.calls.flat().join(' ')).not.toContain('same key');
    errorSpy.mockRestore();
  });

  it('calls onSelectStock from the accessible stock list', () => {
    const onSelectStock = vi.fn();

    render(<StockHeatmapPanel payload={makePayload()} loading={false} error={null} onSelectStock={onSelectStock} />);

    fireEvent.click(screen.getByRole('button', { name: /打开 平安银行/ }));

    expect(onSelectStock).toHaveBeenCalledWith('CN:SZ:000001');
  });

  it('renders an error state', () => {
    render(<StockHeatmapPanel payload={null} loading={false} error="加载失败" onSelectStock={vi.fn()} />);

    expect(screen.getByText('加载失败')).toBeInTheDocument();
  });
});
